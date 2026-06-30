#!/usr/bin/env python3
"""
Export O₂ anchor-run feature parquets (event-agnostic elapsed_m index).

See docs/memos/20_anchor_run_signature_library.md and config/anchor_runs_manifest.json.

Usage (from repo root):
    python3 04_Python_Scripts/spatial/build_anchor_features.py --all
    python3 04_Python_Scripts/spatial/build_anchor_features.py --anchor-id stavanger_halvmarathon
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

_spec = importlib.util.spec_from_file_location("gap_engine", _SCRIPTS / "11_gap_engine.py")
_gap = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_gap)
load_fit = _gap.load_fit
apply_gap = _gap.apply_gap
DEFAULT_ANCHOR = _gap.DEFAULT_ANCHOR
from spatial.telemetry_features import ROLLING_WINDOW_M, add_rolling_features  # noqa: E402
from spatial.locomotion_mode import assign_grade_bin  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_MANIFEST = BASE_DIR / "config" / "anchor_runs_manifest.json"

SCRAMBLE_SPEED_CAP_MPS = 1.8
SCRAMBLE_GRADE_ABS_PCT = 12.0


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _resample_to_1m(df: pd.DataFrame) -> pd.DataFrame:
    """Interpolate session telemetry onto a 1 m elapsed-distance grid."""
    work = df.sort_values("distance").copy()
    dist = work["distance"].to_numpy(dtype=float)
    if len(dist) < 2:
        raise ValueError("Session too short for 1 m resample")
    max_m = float(np.nanmax(dist))
    grid = np.arange(0.0, max_m, 1.0)
    out = pd.DataFrame({"elapsed_m": grid})
    for col in ("ti", "grade_pct", "speed_m_s", "pace_expected", "pace_min_km", "heart_rate"):
        if col not in work.columns:
            continue
        vals = pd.to_numeric(work[col], errors="coerce").to_numpy(dtype=float)
        out[col] = np.interp(grid, dist, vals, left=np.nan, right=np.nan)
    out["speed"] = out.get("speed_m_s", pd.Series(np.nan, index=out.index))
    if "pace_expected" in out.columns and "pace_min_km" in out.columns:
        out["pace_residual"] = out["pace_min_km"] / out["pace_expected"].replace(0, np.nan)
    elif "ti" in out.columns:
        out["pace_residual"] = out["ti"] - 1.0
    return out


def add_scramble_fraction(
    frame: pd.DataFrame,
    *,
    distance_col: str = "elapsed_m",
    window_m: int = ROLLING_WINDOW_M,
) -> pd.DataFrame:
    work = frame.sort_values(distance_col).copy()
    speed = pd.to_numeric(work.get("speed"), errors="coerce")
    grade = pd.to_numeric(work.get("grade_pct"), errors="coerce")
    scramble = (
        (speed < SCRAMBLE_SPEED_CAP_MPS) & (grade.abs() >= SCRAMBLE_GRADE_ABS_PCT)
    ).astype(float)
    win = max(1, int(window_m))
    work["scramble_fraction"] = scramble.rolling(win, min_periods=max(1, win // 3)).mean()
    return work


def build_anchor_frame(
    fit_path: Path,
    *,
    asphalt_anchor: Path,
    window_m: int,
) -> pd.DataFrame:
    session = load_fit(fit_path)
    anchor = load_fit(asphalt_anchor)
    enriched = apply_gap(session, anchor)
    frame = _resample_to_1m(enriched)
    frame = frame.rename(columns={"elapsed_m": "course_m"})
    frame = add_rolling_features(frame, window_m=window_m)
    frame = add_scramble_fraction(frame, distance_col="course_m", window_m=window_m)
    frame = frame.rename(columns={"course_m": "elapsed_m"})
    frame["grade_bin"] = assign_grade_bin(frame["grade_pct"])
    frame["nti_std"] = np.nan
    return frame.sort_values("elapsed_m").reset_index(drop=True)


def export_anchor(
    run: dict,
    *,
    manifest: dict,
    window_m: int,
    force: bool,
) -> Path | None:
    anchor_id = str(run["anchor_id"])
    fit_rel = run.get("fit_path")
    if not fit_rel:
        print(f"  skip {anchor_id}: fit_path null ({run.get('status', '?')})")
        return None
    fit_path = BASE_DIR / fit_rel
    if not fit_path.exists():
        print(f"  skip {anchor_id}: missing {fit_path}")
        return None

    out_dir = BASE_DIR / manifest.get("output_dir", "03_Processed_Data/spatial/anchor_features")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"anchor_features_{anchor_id}.parquet"
    if out_path.exists() and not force:
        print(f"  exists {out_path} (use --force)")
        return out_path

    asphalt = BASE_DIR / manifest.get("asphalt_anchor_fit", "02_Raw_Data/Stavanger_Halvmaraton.fit")
    if not asphalt.exists():
        asphalt = DEFAULT_ANCHOR
    frame = build_anchor_frame(fit_path, asphalt_anchor=asphalt, window_m=window_m)

    meta = {
        "anchor_id": anchor_id,
        "display_name": run.get("display_name"),
        "subject_id": run.get("subject_id"),
        "substrate_class_o1": (run.get("expected") or {}).get("substrate_o1"),
        "friction_tier_o1": (run.get("expected") or {}).get("friction_o1"),
        "pole_policy": run.get("pole_policy", "unknown"),
        "effort_tier": (run.get("expected") or {}).get("effort"),
        "fit_path": fit_rel,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    for col, val in meta.items():
        frame[col] = val

    export_cols = [
        "elapsed_m",
        "anchor_id",
        "display_name",
        "subject_id",
        "substrate_class_o1",
        "friction_tier_o1",
        "pole_policy",
        "effort_tier",
        "grade_bin",
        "ti",
        "grade_pct",
        "speed",
        "pace_expected",
        "pace_residual",
        "ti_mean",
        "ti_std",
        "speed_mean",
        "pace_residual_mean",
        "walk_fraction",
        "scramble_fraction",
    ]
    export_cols = [c for c in export_cols if c in frame.columns]
    frame[export_cols].to_parquet(out_path, index=False)

    ti_med = float(frame["ti"].median())
    print(f"  wrote {out_path} ({len(frame)} rows, ti_med={ti_med:.3f})")
    return out_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build O₂ anchor-run feature parquets.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--anchor-id", type=str, default=None, help="Single anchor_id from manifest")
    parser.add_argument("--all", action="store_true", help="Process all runs with fit_path set")
    parser.add_argument("--window-m", type=int, default=ROLLING_WINDOW_M)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.manifest.exists():
        print(f"Manifest not found: {args.manifest}", file=sys.stderr)
        return 1

    manifest = load_manifest(args.manifest)
    runs = manifest.get("runs", [])
    if args.anchor_id:
        runs = [r for r in runs if r.get("anchor_id") == args.anchor_id]
        if not runs:
            print(f"Unknown anchor_id: {args.anchor_id}", file=sys.stderr)
            return 1
    elif not args.all:
        print("Specify --anchor-id <id> or --all", file=sys.stderr)
        return 1

    print(f"Anchor feature export ({len(runs)} run(s))")
    wrote = 0
    for run in runs:
        if export_anchor(run, manifest=manifest, window_m=args.window_m, force=args.force):
            wrote += 1
    print(f"Done: {wrote} parquet(s)")
    return 0 if wrote else 1


if __name__ == "__main__":
    raise SystemExit(main())
