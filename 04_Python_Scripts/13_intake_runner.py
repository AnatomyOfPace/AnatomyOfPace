#!/usr/bin/env python3
"""
Donor intake orchestrator — Strava .fit → Kinematic_Scan → PDF.

Chains 12_strava_fetcher download with 08_kinematic_scan (privacy clip + PDF).

Usage:
    python 13_intake_runner.py --donor Reference_Elite_A --list
    python 13_intake_runner.py --donor Reference_Elite_A --activity 1234567890 --scan --pdf
    python 13_intake_runner.py --donor Reference_Elite_A --activity 1234567890 --download --segments
    python 13_intake_runner.py --donor Reference_Elite_A --activity 1234567890 --scan --pdf --anchor Stavanger_Halvmaraton.fit

Requires: .env with STRAVA_CLIENT_ID / STRAVA_CLIENT_SECRET, donor token in
          config/strava_tokens.local.json
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

import seed_matrix
from donor_io import INBOX_DIR, donor_fit_path

_spec_fetch = importlib.util.spec_from_file_location("strava_fetcher", SCRIPTS / "12_strava_fetcher.py")
_fetch = importlib.util.module_from_spec(_spec_fetch)
_spec_fetch.loader.exec_module(_fetch)

_spec_scan = importlib.util.spec_from_file_location("kinematic_scan", SCRIPTS / "08_kinematic_scan.py")
_scan = importlib.util.module_from_spec(_spec_scan)
_spec_scan.loader.exec_module(_scan)

REPORTS_DIR = BASE_DIR / "06_Visualizations" / "reports"


def resolve_fit_path(donor_id: str, activity_id: int) -> Path:
    """Prefer inbox telemetry after download (.fit or Strava streams JSON)."""
    safe = donor_id.replace("/", "_")
    candidates = [
        INBOX_DIR / safe / f"activity_{activity_id}.fit",
        INBOX_DIR / safe / f"activity_{activity_id}.strava.json",
        donor_fit_path(donor_id, activity_id, clipped=True).with_suffix(".strava.json"),
        donor_fit_path(donor_id, activity_id, clipped=True),
        donor_fit_path(donor_id, activity_id, clipped=False),
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(
        f"No telemetry for {donor_id} activity {activity_id}. "
        "Run download first or pass --local-fit."
    )


def warn_anchor(donor_id: str, anchor_override: str | None) -> None:
    if anchor_override:
        return
    status = seed_matrix.anchor_status(donor_id)
    if status not in ("locked", "unknown"):
        print(f"  WARNING: {donor_id} anchor status={status}. TI may be invalid.")
        print("           Pass --anchor with donor flat race .fit or lock via seed_matrix.")
    elif donor_id not in ("Subject_A", "Subject_B") and status == "unknown":
        print(f"  NOTE: No Seed Matrix entry for {donor_id}.")
        print("        Using --anchor override or Subject_A default if scan proceeds.")


def run_intake(
    donor_id: str,
    activity_id: int | None,
    *,
    list_only: bool,
    download: bool,
    skip_download: bool,
    local_fit: str | None,
    scan: bool,
    pdf: bool,
    anchor: str | None,
    km_start: float | None,
    km_end: float | None,
    segment_km: float,
    per_page: int,
    segments: bool,
) -> None:
    if list_only or (activity_id is None and not download):
        print(f"\nRecent activities for {donor_id}:\n")
        _fetch.poll_donor(donor_id, per_page=per_page)
        return

    if activity_id is None:
        raise SystemExit("ERROR: --activity ID required for download/scan.")

    if download or scan:
        if local_fit:
            src = Path(local_fit)
            if not src.is_absolute():
                src = BASE_DIR / local_fit
            if not src.exists():
                raise SystemExit(f"ERROR: --local-fit not found: {src}")
            dest = INBOX_DIR / donor_id.replace("/", "_") / f"activity_{activity_id}.fit"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(src.read_bytes())
            print(f"\nStaged local FIT → {dest}")
        elif not skip_download:
            print(f"\nDownloading activity {activity_id} for {donor_id}...")
            _fetch.poll_donor(donor_id, activity_id=activity_id, segments=segments)
        else:
            print(f"\nSkipping download (--skip-download); using existing inbox file.")
            if segments:
                print(f"Fetching segment efforts for activity {activity_id}...")
                seg_path = _fetch.download_activity_segment_efforts(donor_id, activity_id)
                print(f"  Segment efforts → {seg_path}")

    if not scan:
        fit_path = resolve_fit_path(donor_id, activity_id)
        print(f"  FIT ready: {fit_path}")
        return

    warn_anchor(donor_id, anchor)
    fit_path = resolve_fit_path(donor_id, activity_id)
    png_path = REPORTS_DIR / f"Kinematic_Scan_{donor_id}_activity_{activity_id}.png"
    pdf_path = REPORTS_DIR / f"Kinematic_Scan_{donor_id}_activity_{activity_id}.pdf" if pdf else None

    print(f"\nRunning Kinematic_Scan on {fit_path.name}...")
    _scan.run_scan(
        fit_path=fit_path,
        subject_id=donor_id,
        anchor_name=anchor,
        segment_km=segment_km,
        privacy_clip=True,
        output_path=png_path,
        legacy_apr=False,
        emit_pdf=pdf,
        pdf_output=pdf_path,
        km_start=km_start,
        km_end=km_end,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Donor intake: Strava → Kinematic_Scan → PDF")
    parser.add_argument("--donor", required=True, help="Clinical donor ID")
    parser.add_argument("--list", action="store_true", help="List recent Strava activities")
    parser.add_argument("--activity", type=int, help="Strava activity ID")
    parser.add_argument("--download", action="store_true", help="Download streams only")
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Use existing inbox file (with --scan)",
    )
    parser.add_argument(
        "--local-fit",
        default=None,
        help="Copy local .fit into inbox for this activity (self-test bypass)",
    )
    parser.add_argument("--scan", action="store_true", help="Run Kinematic_Scan after download")
    parser.add_argument("--pdf", action="store_true", help="Emit Tier 1.1 PDF (requires --scan)")
    parser.add_argument("--anchor", default=None, help="Override anchor .fit basename in 02_Raw_Data/")
    parser.add_argument("--km-start", type=float, default=None)
    parser.add_argument("--km-end", type=float, default=None)
    parser.add_argument("--segment-km", type=float, default=1.0)
    parser.add_argument(
        "--segments",
        action="store_true",
        help="Fetch Strava segment efforts with activity download (or alone with --skip-download)",
    )
    parser.add_argument("--per-page", type=int, default=15)
    args = parser.parse_args()

    if args.pdf and not args.scan:
        parser.error("--pdf requires --scan")

    download = args.download or args.scan
    run_intake(
        args.donor,
        args.activity,
        list_only=args.list,
        download=download,
        skip_download=args.skip_download,
        local_fit=args.local_fit,
        scan=args.scan,
        pdf=args.pdf,
        anchor=args.anchor,
        km_start=args.km_start,
        km_end=args.km_end,
        segment_km=args.segment_km,
        per_page=args.per_page,
        segments=args.segments,
    )


if __name__ == "__main__":
    main()
