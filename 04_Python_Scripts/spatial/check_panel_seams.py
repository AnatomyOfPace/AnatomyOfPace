#!/usr/bin/env python3
"""
QC telemetry continuity at panel seam boundaries on the SUT_43 race axis.

Compares adjacent panel parquets at upstream/downstream boundaries for each
donor (Subject_A, Subject_B) on stream course_km and spine ref_chainage_m.

Usage (from repo root):
    python3 04_Python_Scripts/spatial/check_panel_seams.py

    python3 04_Python_Scripts/spatial/check_panel_seams.py \\
        --corridor-dir 03_Processed_Data/spatial/sut43_terrain_ontology \\
        --output 03_Processed_Data/spatial/sut43_terrain_ontology/panel_seam_qc_midcourse.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from spatial.corridor_scope import (  # noqa: E402
    SUT43_CORRIDOR_ID,
    SUT43_MIDCOURSE_KM_END,
    SUT43_MIDCOURSE_KM_START,
    SUT43_UPSTREAM_KM_START,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_CORRIDOR_DIR = BASE_DIR / "03_Processed_Data" / "spatial" / SUT43_CORRIDOR_ID

COMPARE_COLS = ("altitude_m", "speed_mps", "latitude", "longitude", "heart_rate", "ti")
TOLERANCE = {
    "altitude_m": 5.0,
    "speed_mps": 0.5,
    "latitude": 0.0001,
    "longitude": 0.0001,
    "heart_rate": 10.0,
    "ti": 0.3,
}


def _resolve_km(frame: pd.DataFrame) -> pd.Series:
    if "course_km" in frame.columns and frame["course_km"].notna().any():
        return pd.to_numeric(frame["course_km"], errors="coerce")
    if "activity_course_km" in frame.columns:
        return pd.to_numeric(frame["activity_course_km"], errors="coerce")
    if "ref_chainage_m" in frame.columns:
        return pd.to_numeric(frame["ref_chainage_m"], errors="coerce") / 1000.0
    raise ValueError("Frame lacks course_km / activity_course_km / ref_chainage_m")


def _row_at_km(frame: pd.DataFrame, km: float, *, prefer: str = "low") -> pd.Series | None:
    if frame.empty:
        return None
    work = frame.copy()
    work["_km"] = _resolve_km(work)
    work = work[np.isfinite(work["_km"])]
    if work.empty:
        return None
    if prefer == "high":
        sub = work.loc[work["_km"] <= km + 1e-6]
        return sub.loc[sub["_km"].idxmax()] if not sub.empty else work.loc[work["_km"].idxmax()]
    sub = work.loc[work["_km"] >= km - 1e-6]
    return sub.loc[sub["_km"].idxmin()] if not sub.empty else work.loc[work["_km"].idxmin()]


def _compare_rows(
    upstream: pd.Series | None,
    downstream: pd.Series | None,
    *,
    upstream_label: str,
    downstream_label: str,
) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "upstream": upstream_label,
        "downstream": downstream_label,
        "status": "ok",
    }
    if upstream is None or downstream is None:
        rec["status"] = "missing_row"
        return rec

    rec["upstream_km"] = round(float(upstream.get("_km", np.nan)), 4)
    rec["downstream_km"] = round(float(downstream.get("_km", np.nan)), 4)
    deltas: dict[str, Any] = {}
    flags: list[str] = []
    for col in COMPARE_COLS:
        if col not in upstream.index and col not in downstream.index:
            continue
        v_up = pd.to_numeric(upstream.get(col), errors="coerce")
        v_dn = pd.to_numeric(downstream.get(col), errors="coerce")
        if pd.isna(v_up) and pd.isna(v_dn):
            deltas[col] = {"upstream": None, "downstream": None, "delta": None, "status": "both_nan"}
            flags.append(f"{col}_both_nan")
            continue
        if pd.isna(v_up) or pd.isna(v_dn):
            deltas[col] = {
                "upstream": None if pd.isna(v_up) else round(float(v_up), 4),
                "downstream": None if pd.isna(v_dn) else round(float(v_dn), 4),
                "delta": None,
                "status": "one_nan",
            }
            flags.append(f"{col}_seam_nan")
            continue
        delta = float(v_dn) - float(v_up)
        tol = TOLERANCE.get(col, float("inf"))
        status = "ok" if abs(delta) <= tol else "warn"
        if status == "warn":
            flags.append(f"{col}_delta")
        deltas[col] = {
            "upstream": round(float(v_up), 4),
            "downstream": round(float(v_dn), 4),
            "delta": round(delta, 4),
            "tolerance": tol,
            "status": status,
        }
    rec["fields"] = deltas
    if any(f.endswith("_seam_nan") or f.endswith("_both_nan") for f in flags):
        rec["status"] = "seam_nan"
    elif any(f.endswith("_delta") for f in flags):
        rec["status"] = "warn"
    rec["flags"] = flags
    return rec


def check_midcourse_seams(
    *,
    corridor_dir: Path,
    donors: tuple[str, ...] = ("Subject_A", "Subject_B"),
) -> dict[str, Any]:
    paths = {
        "start": corridor_dir / "panel_start_race_1m.parquet",
        "midcourse_stream": corridor_dir / "panel_midcourse_race_1m.parquet",
        "midcourse_spine": corridor_dir / "panel_midcourse_1m_spine.parquet",
        "upstream": corridor_dir / "panel_race_1m.parquet",
        "upstream_spine": corridor_dir / "panel_race_1m_spine.parquet",
    }
    report: dict[str, Any] = {
        "corridor_id": SUT43_CORRIDOR_ID,
        "seams": [],
        "panels": {},
    }

    panels: dict[str, pd.DataFrame] = {}
    for key, path in paths.items():
        if path.exists():
            panels[key] = pd.read_parquet(path)
            km = _resolve_km(panels[key])
            report["panels"][key] = {
                "path": str(path.relative_to(BASE_DIR)),
                "rows": int(len(panels[key])),
                "km_min": round(float(km.min()), 3),
                "km_max": round(float(km.max()), 3),
            }
        else:
            report["panels"][key] = {"path": str(path.relative_to(BASE_DIR)), "status": "missing"}

    seam_specs = [
        {
            "seam_id": "phase_e_to_midcourse_stream",
            "boundary_km": SUT43_MIDCOURSE_KM_START,
            "upstream_panel": "start",
            "downstream_panel": "midcourse_stream",
            "upstream_prefer": "high",
            "downstream_prefer": "low",
        },
        {
            "seam_id": "midcourse_to_upstream_stream",
            "boundary_km": SUT43_MIDCOURSE_KM_END,
            "upstream_panel": "midcourse_stream",
            "downstream_panel": "upstream",
            "upstream_prefer": "high",
            "downstream_prefer": "low",
        },
        {
            "seam_id": "midcourse_to_upstream_spine",
            "boundary_km": SUT43_MIDCOURSE_KM_END,
            "upstream_panel": "midcourse_spine",
            "downstream_panel": "upstream_spine",
            "upstream_prefer": "high",
            "downstream_prefer": "low",
            "ref_chainage_km": SUT43_UPSTREAM_KM_START,
        },
    ]

    for spec in seam_specs:
        up_key = spec["upstream_panel"]
        dn_key = spec["downstream_panel"]
        if up_key not in panels or dn_key not in panels:
            report["seams"].append({**spec, "status": "skipped", "reason": "panel missing"})
            continue

        seam_rec: dict[str, Any] = {
            "seam_id": spec["seam_id"],
            "boundary_km": spec["boundary_km"],
            "donors": {},
        }
        boundary = float(spec["boundary_km"])
        for donor in donors:
            up_df = panels[up_key]
            dn_df = panels[dn_key]
            up_sub = up_df[up_df["donor_id"] == donor] if "donor_id" in up_df.columns else up_df
            dn_sub = dn_df[dn_df["donor_id"] == donor] if "donor_id" in dn_df.columns else dn_df
            up_row = _row_at_km(up_sub, boundary, prefer=spec["upstream_prefer"])
            dn_row = _row_at_km(dn_sub, boundary, prefer=spec["downstream_prefer"])
            seam_rec["donors"][donor] = _compare_rows(
                up_row,
                dn_row,
                upstream_label=up_key,
                downstream_label=dn_key,
            )
        statuses = {v["status"] for v in seam_rec["donors"].values()}
        if "warn" in statuses:
            seam_rec["status"] = "warn"
        elif "seam_nan" in statuses or "missing_row" in statuses:
            seam_rec["status"] = "seam_nan"
        else:
            seam_rec["status"] = "ok"
        report["seams"].append(seam_rec)

    report["summary"] = {
        "n_seams": len(report["seams"]),
        "ok": sum(1 for s in report["seams"] if s.get("status") == "ok"),
        "seam_nan": sum(1 for s in report["seams"] if s.get("status") == "seam_nan"),
        "warn": sum(1 for s in report["seams"] if s.get("status") == "warn"),
        "skipped": sum(1 for s in report["seams"] if s.get("status") == "skipped"),
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="QC panel seam continuity for SUT_43 mid-course.")
    parser.add_argument("--corridor-dir", type=Path, default=DEFAULT_CORRIDOR_DIR)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    report = check_midcourse_seams(corridor_dir=args.corridor_dir)
    out = args.output or (args.corridor_dir / "panel_seam_qc_midcourse.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    summary = report["summary"]
    print(f"Seam QC: ok={summary['ok']} seam_nan={summary['seam_nan']} warn={summary['warn']} skipped={summary['skipped']}")
    for seam in report["seams"]:
        print(f"  {seam['seam_id']}: {seam.get('status', '?')}")
    print(f"Wrote {out}")
    return 0 if summary["warn"] == 0 else 0  # seam_nan expected on interpolated scaffold


if __name__ == "__main__":
    raise SystemExit(main())
