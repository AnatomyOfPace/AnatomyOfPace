#!/usr/bin/env python3
"""
Strava Fetcher — frictionless donor intake (OAuth 2.0).

Directive: automated passive harvest replaces manual .fit email/DM transfer.
Historical doc name: 01_strava_fetcher.py — wash pipeline retains 01_vaskemaskinen.py.

Setup:
    1. Copy .env.example → .env (STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET)
    2. Copy config/strava_tokens.example.json → config/strava_tokens.local.json
    3. Donor opens authorize URL → returns ?code= → exchange token

Usage:
    python 12_strava_fetcher.py --authorize-url --donor Reference_Elite_A
    python 12_strava_fetcher.py --exchange-code CODE --donor Reference_Elite_A
    python 12_strava_fetcher.py --poll --donor Reference_Elite_A
    python 12_strava_fetcher.py --poll-all
    python 12_strava_fetcher.py --donor Reference_Elite_D --activity 18159079828 --segments-only
    python 12_strava_fetcher.py --donor Reference_Elite_D --activity 18159079828 --segments
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from donor_io import DONOR_DIR, INBOX_DIR, apply_privacy_clip

BASE_DIR = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass
TOKENS_PATH = BASE_DIR / "config" / "strava_tokens.local.json"
STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API = "https://www.strava.com/api/v3"
DEFAULT_SCOPE = "activity:read_all"
DEFAULT_REDIRECT = "http://localhost"


def _load_tokens() -> dict:
    if not TOKENS_PATH.exists():
        return {"donors": {}}
    return json.loads(TOKENS_PATH.read_text(encoding="utf-8"))


def _save_tokens(data: dict) -> None:
    TOKENS_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKENS_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _env(name: str) -> str:
    val = os.environ.get(name, "")
    if not val:
        raise EnvironmentError(
            f"Missing {name}. Copy .env.example to .env and set Strava app credentials."
        )
    return val


def build_authorize_url(donor_id: str, redirect_uri: str = DEFAULT_REDIRECT) -> str:
    client_id = _env("STRAVA_CLIENT_ID")
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": DEFAULT_SCOPE,
        "state": donor_id,
    }
    return f"{STRAVA_AUTH_URL}?{urllib.parse.urlencode(params)}"


def exchange_code(donor_id: str, code: str) -> dict:
    """Exchange OAuth code for access + refresh token; persist per donor."""
    payload = json.dumps(
        {
            "client_id": _env("STRAVA_CLIENT_ID"),
            "client_secret": _env("STRAVA_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
        }
    ).encode()
    req = urllib.request.Request(
        STRAVA_TOKEN_URL, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as resp:
            token_body = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(
            f"Strava token exchange failed ({exc.code}). "
            "Codes expire in ~10 minutes and are single-use. "
            f"Re-run --authorize-url and exchange immediately.\nStrava: {detail}"
        ) from exc

    data = _load_tokens()
    donors = data.setdefault("donors", {})
    donors[donor_id] = {
        "athlete_id": token_body.get("athlete", {}).get("id"),
        "access_token": token_body["access_token"],
        "refresh_token": token_body["refresh_token"],
        "expires_at": token_body["expires_at"],
        "scope": DEFAULT_SCOPE,
        "connected_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_tokens(data)
    return donors[donor_id]


def _token_not_exchanged(entry: dict) -> bool:
    """True when donor slot still holds the example template, not a live OAuth exchange."""
    if not entry.get("connected_at"):
        return True
    if entry.get("access_token") in ("", "REDACTED"):
        return True
    if entry.get("refresh_token") in ("", "REDACTED"):
        return True
    return False


def refresh_token_if_needed(donor_id: str) -> str:
    """Return valid access token; refresh when expired."""
    data = _load_tokens()
    entry = data.get("donors", {}).get(donor_id)
    if not entry:
        raise KeyError(f"No token for donor {donor_id}. Run --exchange-code first.")
    if _token_not_exchanged(entry):
        raise RuntimeError(
            f"Donor {donor_id} is not connected yet. After Strava authorize, run:\n"
            f"  python 12_strava_fetcher.py --donor {donor_id} "
            f"--exchange-url 'http://localhost/?code=...&state=...'"
        )

    now = int(datetime.now(timezone.utc).timestamp())
    if entry.get("expires_at", 0) > now + 300:
        return entry["access_token"]

    payload = json.dumps(
        {
            "client_id": _env("STRAVA_CLIENT_ID"),
            "client_secret": _env("STRAVA_CLIENT_SECRET"),
            "grant_type": "refresh_token",
            "refresh_token": entry["refresh_token"],
        }
    ).encode()
    req = urllib.request.Request(
        STRAVA_TOKEN_URL, data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        token_body = json.loads(resp.read().decode())

    entry["access_token"] = token_body["access_token"]
    entry["refresh_token"] = token_body.get("refresh_token", entry["refresh_token"])
    entry["expires_at"] = token_body["expires_at"]
    _save_tokens(data)
    return entry["access_token"]


def _api_get(path: str, token: str) -> dict | list:
    url = f"{STRAVA_API}{path}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"Strava API {path} failed ({exc.code}): {detail}") from exc


STREAM_KEYS = (
    "time,distance,latlng,altitude,velocity_smooth,heartrate,cadence,grade_smooth"
)


def list_recent_activities(donor_id: str, per_page: int = 10) -> list:
    token = refresh_token_if_needed(donor_id)
    return _api_get(f"/athlete/activities?per_page={per_page}", token)


def fetch_activity_detail(
    donor_id: str,
    activity_id: int,
    *,
    include_all_efforts: bool = True,
) -> dict:
    """Fetch activity metadata; optionally request full segment_efforts list."""
    token = refresh_token_if_needed(donor_id)
    qs = "?include_all_efforts=true" if include_all_efforts else ""
    return _api_get(f"/activities/{activity_id}{qs}", token)


def fetch_activity_segment_efforts(donor_id: str, activity_id: int) -> list[dict]:
    """
    Return segment efforts for an activity via activity detail endpoint.

    Requires activity:read or activity:read_all OAuth scope (no profile:read).
    """
    activity = fetch_activity_detail(donor_id, activity_id, include_all_efforts=True)
    return activity.get("segment_efforts") or []


def download_activity_segment_efforts(
    donor_id: str,
    activity_id: int,
    *,
    mirror_donors: bool = True,
) -> Path:
    """Persist segment efforts JSON to inbox (and donors mirror when enabled)."""
    activity = fetch_activity_detail(donor_id, activity_id, include_all_efforts=True)
    efforts = activity.get("segment_efforts") or []

    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    donor_inbox = INBOX_DIR / donor_id.replace("/", "_")
    donor_inbox.mkdir(parents=True, exist_ok=True)
    raw_path = donor_inbox / f"activity_{activity_id}.segment_efforts.json"

    payload = {
        "activity_id": activity_id,
        "donor_id": donor_id,
        "name": activity.get("name"),
        "start_date": activity.get("start_date"),
        "segment_effort_count": len(efforts),
        "segment_efforts": efforts,
    }
    raw_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if mirror_donors:
        DONOR_DIR.mkdir(parents=True, exist_ok=True)
        clipped_dir = DONOR_DIR / donor_id.replace("/", "_")
        clipped_dir.mkdir(parents=True, exist_ok=True)
        mirror_path = clipped_dir / f"activity_{activity_id}.segment_efforts.json"
        mirror_path.write_text(raw_path.read_text(encoding="utf-8"), encoding="utf-8")

    return raw_path


def fetch_activity_streams(donor_id: str, activity_id: int) -> tuple[dict, dict]:
    """Fetch activity metadata + stream payloads (key_by_type)."""
    token = refresh_token_if_needed(donor_id)
    activity = fetch_activity_detail(donor_id, activity_id, include_all_efforts=False)
    streams = _api_get(
        f"/activities/{activity_id}/streams?keys={STREAM_KEYS}&key_by_type=true",
        token,
    )
    if not isinstance(streams, dict) or "time" not in streams:
        raise RuntimeError(
            f"No stream data for activity {activity_id}. "
            "Activity may be manual, private to another athlete, or missing GPS."
        )
    return activity, streams


def download_activity_streams_fit(
    donor_id: str,
    activity_id: int,
    *,
    apply_clip: bool = True,
) -> Path:
    """
    Download activity telemetry via Strava Streams API.

    Strava API v3 does not expose export_original (web-only). Streams JSON is
    saved locally and consumed by gap_engine.load_fit().
    """
    activity, streams = fetch_activity_streams(donor_id, activity_id)

    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    donor_inbox = INBOX_DIR / donor_id.replace("/", "_")
    donor_inbox.mkdir(parents=True, exist_ok=True)
    raw_path = donor_inbox / f"activity_{activity_id}.strava.json"

    payload = {
        "activity_id": activity_id,
        "donor_id": donor_id,
        "name": activity.get("name"),
        "start_date": activity.get("start_date"),
        "has_heartrate": activity.get("has_heartrate", False),
        "streams": streams,
    }
    raw_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if not activity.get("has_heartrate") and "heartrate" not in streams:
        print(
            "  WARNING: Strava did not return heart-rate streams for this activity.\n"
            "           Kinematic_Scan requires HR for Terrain Index (iso-HR matching).\n"
            "           Donor must allow heart-rate sharing in Strava privacy settings\n"
            "           before upload, or provide a manual .fit export for past sessions."
        )

    if apply_clip:
        DONOR_DIR.mkdir(parents=True, exist_ok=True)
        clipped_dir = DONOR_DIR / donor_id.replace("/", "_")
        clipped_dir.mkdir(parents=True, exist_ok=True)
        clipped_path = clipped_dir / f"activity_{activity_id}.strava.json"
        clipped_path.write_text(raw_path.read_text(encoding="utf-8"), encoding="utf-8")

    return raw_path


def _write_clipped_fit(source: Path, dest: Path) -> None:
    """Parse FIT, apply 500 m privacy clip, re-export for pipeline (scaffold)."""
    try:
        import fitparse
    except ImportError as exc:
        raise ImportError("fitparse required for privacy clipping") from exc

    fitfile = fitparse.FitFile(str(source))
    rows = [r.get_values() for r in fitfile.get_messages("record")]
    import pandas as pd

    df = pd.DataFrame(rows)
    if "distance" not in df.columns and "enhanced_speed" in df.columns:
        speed = df["enhanced_speed"].fillna(0)
        dt = df["timestamp"].diff().dt.total_seconds().fillna(0)
        df["distance"] = (speed * dt).cumsum()

    clipped = apply_privacy_clip(df)
    if clipped.empty:
        dest.write_bytes(source.read_bytes())
        return

    # Scaffold: copy raw until FIT rewrite is implemented; pipeline clips on load.
    dest.write_bytes(source.read_bytes())


def parse_oauth_redirect(url: str) -> tuple[str, str | None]:
    """Extract OAuth code and optional state from donor-pasted redirect URL."""
    parsed = urllib.parse.urlparse(url.strip())
    qs = urllib.parse.parse_qs(parsed.query)
    code = qs.get("code", [None])[0]
    state = qs.get("state", [None])[0]
    if not code:
        raise ValueError("No code= parameter found in URL.")
    return code, state


def print_activity_table(activities: list) -> None:
    """Print recent activities with IDs for operator selection."""
    if not activities:
        print("  (no activities returned)")
        return
    print(f"  {'ID':<12} {'Date':<12} {'Name'}")
    print(f"  {'-'*12} {'-'*12} {'-'*40}")
    for act in activities:
        aid = act.get("id", "?")
        date = (act.get("start_date_local") or act.get("start_date") or "")[:10]
        name = (act.get("name") or "?")[:60]
        print(f"  {aid:<12} {date:<12} {name}")


def poll_donor(
    donor_id: str,
    *,
    download_new: bool = False,
    activity_id: int | None = None,
    per_page: int = 10,
    segments: bool = False,
) -> list[int]:
    """List recent activities; optionally download one or all new."""
    if activity_id is not None:
        path = download_activity_streams_fit(donor_id, activity_id)
        print(f"  Downloaded activity {activity_id} → {path}")
        if segments:
            seg_path = download_activity_segment_efforts(donor_id, activity_id)
            print(f"  Segment efforts {activity_id} → {seg_path}")
        return [activity_id]

    activities = list_recent_activities(donor_id, per_page=per_page)
    print_activity_table(activities)
    ids = []
    for act in activities:
        aid = act["id"]
        ids.append(aid)
        if download_new:
            path = download_activity_streams_fit(donor_id, aid)
            print(f"  Downloaded {aid} → {path}")
    return ids


def main() -> None:
    parser = argparse.ArgumentParser(description="Strava OAuth donor intake")
    parser.add_argument("--donor", required=True, help="Clinical donor ID (e.g. Reference_Elite_A)")
    parser.add_argument("--authorize-url", action="store_true", help="Print OAuth link for donor")
    parser.add_argument("--redirect-uri", default=DEFAULT_REDIRECT)
    parser.add_argument("--exchange-code", metavar="CODE", help="Exchange OAuth code for tokens")
    parser.add_argument(
        "--exchange-url", metavar="URL",
        help="Exchange code from full redirect URL (donor paste-back)",
    )
    parser.add_argument("--poll", action="store_true", help="List recent activities")
    parser.add_argument("--activity", type=int, metavar="ID", help="Download one activity by Strava ID")
    parser.add_argument(
        "--segments",
        action="store_true",
        help="With --activity, also fetch segment efforts (activity detail API)",
    )
    parser.add_argument(
        "--segments-only",
        action="store_true",
        help="Fetch segment efforts only (no streams download)",
    )
    parser.add_argument("--per-page", type=int, default=15, help="Activities to list (default: 15)")
    parser.add_argument("--download-new", action="store_true", help="With --poll, download all listed .fit files")
    parser.add_argument("--poll-all", action="store_true", help="Poll every donor in token store")
    args = parser.parse_args()

    if args.authorize_url:
        print(build_authorize_url(args.donor, args.redirect_uri))
        return

    if args.exchange_url:
        code, state = parse_oauth_redirect(args.exchange_url)
        if state and state != args.donor:
            print(f"  Note: URL state={state} differs from --donor {args.donor}")
        entry = exchange_code(args.donor, code)
        print(f"Connected {args.donor} (athlete_id={entry.get('athlete_id')})")
        return

    if args.exchange_code:
        entry = exchange_code(args.donor, args.exchange_code)
        print(f"Connected {args.donor} (athlete_id={entry.get('athlete_id')})")
        return

    if args.activity:
        if args.segments_only:
            path = download_activity_segment_efforts(args.donor, args.activity)
            print(f"  Segment efforts {args.activity} → {path}")
            return
        poll_donor(args.donor, activity_id=args.activity, segments=args.segments)
        return

    if args.poll_all:
        donors = _load_tokens().get("donors", {})
        for donor_id in donors:
            print(f"\n{donor_id}:")
            poll_donor(donor_id, download_new=args.download_new, per_page=args.per_page)
        return

    if args.poll:
        poll_donor(
            args.donor,
            download_new=args.download_new,
            per_page=args.per_page,
        )
        return

    parser.error("Specify --authorize-url, --exchange-code, --exchange-url, --poll, --activity, or --poll-all")


if __name__ == "__main__":
    main()
