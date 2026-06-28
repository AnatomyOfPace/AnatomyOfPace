#!/usr/bin/env python3
"""
Per-metre TI-band draft layer for HITL surface-class review.

Assigns S1–S6 from cross-athlete ``nti_median`` (same feature as hitl_nti_consistency)
using ``SURFACE_CLASS_SPECS.ti_band`` / ``expected_ti_band()``. Metres with
``nti_std >= variance_threshold`` or ``n_athletes < 2`` are σ-gated as ``deferred``.

GMM cluster draft remains in terrain map ``segments[]``; this layer is written to
``ti_draft_segments[]`` for side-by-side HITL comparison.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "04_Python_Scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "04_Python_Scripts"))

from spatial.corridor_scope import SUT43_PRIMARY_KM_END, SUT43_PRIMARY_KM_START
from spatial.hitl_nti_consistency import per_metre_nti_stats
from spatial.surface_ontology import SURFACE_CLASS_IDS, SURFACE_CLASS_SPECS, expected_ti_band

DEFAULT_VARIANCE_THRESHOLD = 0.30
DEFAULT_MIN_RUN_M = 5
TI_DRAFT_SOURCE = "ti_band"
DEFERRED_CLASS = "deferred"
NTI_FEATURE = "nti_median"


def assign_surface_class_from_nti(nti: float) -> str:
    """Pick best-matching S-class for a scalar NTI via ti_band containment, else nearest target."""
    if not np.isfinite(nti):
        return "S2"
    in_band: list[str] = []
    for cid in SURFACE_CLASS_IDS:
        lo, hi = expected_ti_band(cid)
        if lo <= nti <= hi:
            in_band.append(cid)
    if len(in_band) == 1:
        return in_band[0]
    if len(in_band) > 1:
        return min(
            in_band,
            key=lambda cid: abs(nti - SURFACE_CLASS_SPECS[cid].ti_target),
        )
    return min(
        SURFACE_CLASS_IDS,
        key=lambda cid: abs(nti - SURFACE_CLASS_SPECS[cid].ti_target),
    )


def classify_metre_nti(
    nti: float,
    surface_class: str | None = None,
    *,
    marginal_pad: float = 0.0,
) -> str | None:
    """
    Classify one metre.

    When ``surface_class`` is set, return it if ``nti`` lies in that class band (± pad);
    otherwise fall back to best S-class from ``nti``. When ``surface_class`` is None,
    assign directly from ``nti``.
    """
    if not np.isfinite(nti):
        return None
    if surface_class is not None:
        lo, hi = expected_ti_band(surface_class)
        if marginal_pad:
            lo -= marginal_pad
            hi += marginal_pad
        if lo <= nti <= hi:
            return surface_class
    return assign_surface_class_from_nti(nti)


def _is_sigma_gated(row: Any, *, variance_threshold: float) -> bool:
    n_ath = int(getattr(row, "n_athletes", 0))
    if n_ath < 2:
        return True
    std = float(getattr(row, "nti_std", 0.0))
    if not np.isfinite(std):
        return True
    return std >= variance_threshold


def per_metre_ti_draft_classes(
    agg: pd.DataFrame,
    *,
    variance_threshold: float = DEFAULT_VARIANCE_THRESHOLD,
) -> pd.DataFrame:
    """Return agg rows with ``ti_draft_class`` (S1–S6 or deferred)."""
    out = agg.sort_values("course_m").copy()
    classes: list[str | None] = []
    for row in out.itertuples(index=False):
        if _is_sigma_gated(row, variance_threshold=variance_threshold):
            classes.append(DEFERRED_CLASS)
            continue
        nti = float(getattr(row, "nti_median"))
        if not np.isfinite(nti):
            classes.append(DEFERRED_CLASS)
            continue
        classes.append(classify_metre_nti(nti))
    out["ti_draft_class"] = classes
    return out


def _segment_record(
    m_start: float,
    m_end: float,
    surface_class: str,
) -> dict[str, Any]:
    return {
        "course_m_start": m_start,
        "course_m_end": m_end,
        "course_km_start": m_start / 1000.0,
        "course_km_end": m_end / 1000.0,
        "surface_class": surface_class,
        "source": TI_DRAFT_SOURCE if surface_class != DEFERRED_CLASS else "ti_band_deferred",
    }


def run_length_encode_classes(
    metre_df: pd.DataFrame,
    class_col: str = "ti_draft_class",
    *,
    min_run_m: int = DEFAULT_MIN_RUN_M,
) -> list[dict[str, Any]]:
    """Run-length encode contiguous class metres; absorb sub-``min_run_m`` flickers."""
    if metre_df.empty:
        return []

    work = metre_df.sort_values("course_m").reset_index(drop=True)
    raw: list[dict[str, Any]] = []
    current: str | None = None
    seg_start: float | None = None

    for row in work.itertuples(index=False):
        cls = getattr(row, class_col)
        if cls is None or (isinstance(cls, float) and not np.isfinite(cls)):
            cls = DEFERRED_CLASS
        elif pd.isna(cls):
            cls = DEFERRED_CLASS
        cls = str(cls)
        cm = float(row.course_m)
        if cls != current:
            if current is not None and seg_start is not None:
                raw.append(_segment_record(seg_start, cm, current))
            current = cls
            seg_start = cm

    if current is not None and seg_start is not None:
        last_m = float(work["course_m"].iloc[-1])
        raw.append(_segment_record(seg_start, last_m + 1.0, current))

    if min_run_m <= 1 or not raw:
        return raw

    merged: list[dict[str, Any]] = []
    for seg in raw:
        length_m = float(seg["course_m_end"]) - float(seg["course_m_start"])
        if length_m >= min_run_m or not merged:
            merged.append(seg)
            continue
        prev = merged[-1]
        prev["course_m_end"] = seg["course_m_end"]
        prev["course_km_end"] = seg["course_km_end"]
    return merged


def build_ti_draft_segments(
    panel: pd.DataFrame,
    km_lo: float,
    km_hi: float,
    *,
    variance_threshold: float = DEFAULT_VARIANCE_THRESHOLD,
    min_run_m: int = DEFAULT_MIN_RUN_M,
    session_type: str | None = "race",
) -> list[dict[str, Any]]:
    """
    Build TI-band draft segments for ``[km_lo, km_hi)`` from panel telemetry.

    Uses ``nti_median`` (not ``consensus_nti`` — IQR-trimmed) for HITL alignment with
    hitl_nti_consistency.py.
    """
    agg = per_metre_nti_stats(panel, session_type=session_type)
    if agg.empty:
        return []
    mask = (agg["course_km"] >= km_lo) & (agg["course_km"] < km_hi)
    span = per_metre_ti_draft_classes(
        agg.loc[mask],
        variance_threshold=variance_threshold,
    )
    return run_length_encode_classes(span, min_run_m=min_run_m)


def ti_draft_metadata(
    *,
    variance_threshold: float,
    min_run_m: int,
    km_lo: float,
    km_hi: float,
    n_segments: int,
) -> dict[str, Any]:
    return {
        "method": "nti_median_ti_band",
        "nti_feature": NTI_FEATURE,
        "note": (
            "Uses nti_median for HITL alignment with hitl_nti_consistency; "
            "consensus_nti (IQR-trimmed) may differ slightly on outlier metres."
        ),
        "variance_threshold": variance_threshold,
        "min_run_m": min_run_m,
        "km_start": km_lo,
        "km_end": km_hi,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_segments": n_segments,
    }


def write_ti_draft_to_terrain_map(
    terrain_map: dict[str, Any],
    segments: list[dict[str, Any]],
    *,
    meta: dict[str, Any],
) -> dict[str, Any]:
    """Return updated terrain map dict with ti_draft sidecar fields."""
    updated = dict(terrain_map)
    updated["ti_draft_segments"] = segments
    updated["ti_draft"] = meta
    return updated


def load_terrain_map(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_km_window(
    terrain_map: dict[str, Any],
    panel: pd.DataFrame | None,
    *,
    km_lo: float | None,
    km_hi: float | None,
) -> tuple[float, float]:
    corridor = terrain_map.get("corridor") or {}
    c_lo = corridor.get("km_start")
    c_hi = corridor.get("km_end")
    lo = float(km_lo if km_lo is not None else (c_lo if c_lo is not None else SUT43_PRIMARY_KM_START))
    hi = float(km_hi if km_hi is not None else (c_hi if c_hi is not None else SUT43_PRIMARY_KM_END))
    if panel is not None and not panel.empty:
        work = panel.sort_values("course_m")
        p_lo, p_hi = float(work["course_km"].min()), float(work["course_km"].max())
        if c_lo is not None and c_hi is not None:
            c_lo_f, c_hi_f = float(c_lo), float(c_hi)
            if c_lo_f <= p_hi + 0.5 and c_hi_f >= p_lo - 0.5:
                lo = max(lo, p_lo) if km_lo is None else lo
                hi = min(hi, p_hi) if km_hi is None else hi
            elif km_lo is None and km_hi is None:
                lo, hi = max(SUT43_PRIMARY_KM_START, p_lo), min(SUT43_PRIMARY_KM_END, p_hi)
        else:
            lo = max(lo, p_lo) if km_lo is None else lo
            hi = min(hi, p_hi) if km_hi is None else hi
    return lo, hi


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build TI-band draft segments from panel nti_median (HITL sidecar)"
    )
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument(
        "--terrain-map",
        type=Path,
        default=_REPO_ROOT / "config" / "spatial_terrain_map_sut43.json",
    )
    parser.add_argument("--km-start", type=float, default=None)
    parser.add_argument("--km-end", type=float, default=None)
    parser.add_argument(
        "--variance-threshold",
        type=float,
        default=DEFAULT_VARIANCE_THRESHOLD,
    )
    parser.add_argument("--min-run-m", type=int, default=DEFAULT_MIN_RUN_M)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Merge ti_draft_segments[] into terrain map JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write segments JSON only (without --write)",
    )
    args = parser.parse_args()

    panel_path = args.panel if args.panel.is_absolute() else _REPO_ROOT / args.panel
    tmap_path = args.terrain_map if args.terrain_map.is_absolute() else _REPO_ROOT / args.terrain_map

    panel = pd.read_parquet(panel_path)
    terrain_map = load_terrain_map(tmap_path) if tmap_path.exists() else {}
    km_lo, km_hi = resolve_km_window(
        terrain_map,
        panel,
        km_lo=args.km_start,
        km_hi=args.km_end,
    )

    segments = build_ti_draft_segments(
        panel,
        km_lo,
        km_hi,
        variance_threshold=args.variance_threshold,
        min_run_m=args.min_run_m,
    )
    meta = ti_draft_metadata(
        variance_threshold=args.variance_threshold,
        min_run_m=args.min_run_m,
        km_lo=km_lo,
        km_hi=km_hi,
        n_segments=len(segments),
    )

    n_deferred = sum(1 for s in segments if s.get("surface_class") == DEFERRED_CLASS)
    n_classed = len(segments) - n_deferred
    print(
        f"OK TI draft: {len(segments)} segments "
        f"({n_classed} classed, {n_deferred} deferred) "
        f"km {km_lo:.3f}–{km_hi:.3f} "
        f"(σ≥{args.variance_threshold}, min_run={args.min_run_m} m)"
    )

    if args.write:
        if not tmap_path.exists():
            raise FileNotFoundError(f"Terrain map not found: {tmap_path}")
        updated = write_ti_draft_to_terrain_map(terrain_map, segments, meta=meta)
        tmap_path.write_text(json.dumps(updated, indent=2), encoding="utf-8")
        print(f"OK wrote ti_draft_segments[] → {tmap_path.relative_to(_REPO_ROOT)}")
    elif args.output:
        out = args.output if args.output.is_absolute() else _REPO_ROOT / args.output
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {"ti_draft": meta, "ti_draft_segments": segments}
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"OK segments JSON → {out.relative_to(_REPO_ROOT)}")


if __name__ == "__main__":
    main()
