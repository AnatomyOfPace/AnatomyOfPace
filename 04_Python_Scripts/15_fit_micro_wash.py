#!/usr/bin/env python3
"""
Wave 2 micro wash — `.fit` → normalized ActivityFrame Parquet.

Phase 2a: ingest + normalize + Parquet write.
Phase 2b: `--project-course` (GPX snap → course_km) + `--enrich-ti` (Minetti GAP/TI).

Usage:
    python 04_Python_Scripts/15_fit_micro_wash.py \\
        --donor Subject_A \\
        --activity SUT43_20260418 \\
        --fit 02_Raw_Data/donors/Subject_A/SUT43_20260418.fit \\
        --race SUT_43 --project-course --enrich-ti

Enrich existing Parquet (no re-ingest):
    python 04_Python_Scripts/fit_micro/ti_enrich.py \\
        --donor Subject_A --activity SUT43_20260418 \\
        --project-course --race SUT_43
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from donor_io import apply_privacy_clip
from fit_micro.activity_frame import PARSER_VERSION, write_meta_json, write_parquet
from fit_micro.course_project import project_course_km
from fit_micro.fit_ingest import parse_fit
from fit_micro.stream_normalize import normalize_stream
from fit_micro.ti_enrich import enrich_ti


def wash_fit(
    fit_path: Path,
    *,
    donor_id: str,
    activity_id: str,
    race_id: str | None = None,
    privacy_clip_m: float = 500.0,
    apply_clip: bool = True,
    project_course: bool = False,
    gpx_path: Path | None = None,
    enrich_ti_flag: bool = False,
    subject_id: str | None = None,
) -> Path:
    """Ingest one `.fit` file and write ActivityFrame Parquet + metadata sidecar."""
    raw = parse_fit(fit_path)
    if raw.empty:
        raise ValueError(f"No record messages in {fit_path}")

    frame = normalize_stream(raw, source="fit")

    if apply_clip and privacy_clip_m > 0 and "distance_m" in frame.columns:
        clip_df = frame.rename(columns={"distance_m": "distance"})
        clipped = apply_privacy_clip(clip_df, clip_m=privacy_clip_m)
        frame = clipped.rename(columns={"distance": "distance_m"})

    if project_course:
        frame = project_course_km(frame, race_id=race_id, gpx_path=gpx_path)

    ti_meta = None
    if enrich_ti_flag:
        frame, ti_meta = enrich_ti(frame, subject_id=subject_id or donor_id)

    meta = {
        "donor_id": donor_id,
        "activity_id": activity_id,
        "race_id": race_id,
        "privacy_clip_m": privacy_clip_m if apply_clip else 0,
        "sample_rate_hz": None,
        "has_hr": bool(frame["heart_rate"].notna().any()),
        "parser_version": PARSER_VERSION,
        "course_projected": project_course,
        "ti_enriched": enrich_ti_flag,
    }
    if ti_meta:
        meta["ti_summary"] = {
            k: ti_meta[k]
            for k in ("mean_ti", "median_ti", "n_gap_samples", "anchor")
            if k in ti_meta
        }

    out = write_parquet(frame, donor_id, activity_id, meta=meta)
    write_meta_json(donor_id, activity_id, meta)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Wave 2 `.fit` micro wash → Parquet",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
ingest (copy Garmin export to canonical path first):
  mkdir -p 02_Raw_Data/donors/Subject_A
  cp ~/Downloads/22575150868_ACTIVITY.fit \\
      02_Raw_Data/donors/Subject_A/SUT43_20260418.fit
  ln -sf SUT43_20260418.fit 02_Raw_Data/donors/Subject_A/activity_22575150868.fit

examples (copy-paste from repo root; use python3 if python is unavailable):
  python3 04_Python_Scripts/15_fit_micro_wash.py \\
      --donor Subject_A \\
      --activity SUT43_20260418 \\
      --fit 02_Raw_Data/donors/Subject_A/SUT43_20260418.fit \\
      --race SUT_43 --project-course --enrich-ti

  python3 04_Python_Scripts/fit_micro/ti_enrich.py \\
      --donor Subject_A --activity LFI_20260606 \\
      --project-course --race LFI

Do not use placeholder paths like ~/Downloads/your_export.fit — substitute the
actual .fit filename from Garmin Connect or Strava export.
""",
    )
    parser.add_argument(
        "--donor",
        dest="donor",
        help="Clinical donor ID (e.g. Subject_A, Reference_Elite_D)",
    )
    parser.add_argument(
        "--subject",
        dest="donor",
        help="Alias for --donor (deprecated; prefer --donor)",
    )
    parser.add_argument("--activity", required=True, help="Strava activity ID or label")
    parser.add_argument("--fit", required=True, type=Path, help="Path to source `.fit` file")
    parser.add_argument("--race", default=None, help="Race registry ID (e.g. SUT_160, LFI)")
    parser.add_argument(
        "--gpx",
        type=Path,
        default=None,
        help="Organiser GPX override (default: race-aware lookup)",
    )
    parser.add_argument(
        "--project-course",
        action="store_true",
        help="Snap lat/lon to organiser GPX → course_km (LFI: stream distance)",
    )
    parser.add_argument(
        "--enrich-ti",
        action="store_true",
        help="Compute Minetti GAP + 30 s TI smoothing (requires HR)",
    )
    parser.add_argument("--no-privacy-clip", action="store_true")
    args = parser.parse_args()

    if args.donor is None:
        parser.error("the following arguments are required: --donor (or deprecated alias --subject)")

    if "--subject" in sys.argv:
        print("WARNING: --subject is deprecated; use --donor instead.", file=sys.stderr)

    out = wash_fit(
        args.fit,
        donor_id=args.donor,
        activity_id=args.activity,
        race_id=args.race,
        apply_clip=not args.no_privacy_clip,
        project_course=args.project_course,
        gpx_path=args.gpx,
        enrich_ti_flag=args.enrich_ti,
        subject_id=args.donor,
    )
    print(f"OK → {out}")


if __name__ == "__main__":
    main()
