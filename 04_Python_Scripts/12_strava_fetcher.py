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
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from donor_io import DONOR_DIR, INBOX_DIR, apply_privacy_clip

BASE_DIR = Path(__file__).resolve().parent.parent
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
    with urllib.request.urlopen(req) as resp:
        token_body = json.loads(resp.read().decode())

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


def refresh_token_if_needed(donor_id: str) -> str:
    """Return valid access token; refresh when expired."""
    data = _load_tokens()
    entry = data.get("donors", {}).get(donor_id)
    if not entry:
        raise KeyError(f"No token for donor {donor_id}. Run --exchange-code first.")

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
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def list_recent_activities(donor_id: str, per_page: int = 10) -> list:
    token = refresh_token_if_needed(donor_id)
    return _api_get(f"/athlete/activities?per_page={per_page}", token)


def download_activity_streams_fit(
    donor_id: str,
    activity_id: int,
    *,
    apply_clip: bool = True,
) -> Path:
    """
    Download activity as .fit via export endpoint; save to gitignored donor folder.

    TODO: wire fitparse + donor_io.apply_privacy_clip on parsed records before
    writing clipped analysis copy. Raw inbox copy always retained locally.
    """
    token = refresh_token_if_needed(donor_id)
    export_url = f"{STRAVA_API}/activities/{activity_id}/export_original"
    req = urllib.request.Request(export_url, headers={"Authorization": f"Bearer {token}"})

    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    donor_inbox = INBOX_DIR / donor_id.replace("/", "_")
    donor_inbox.mkdir(parents=True, exist_ok=True)
    raw_path = donor_inbox / f"activity_{activity_id}.fit"

    with urllib.request.urlopen(req) as resp:
        raw_path.write_bytes(resp.read())

    if apply_clip:
        DONOR_DIR.mkdir(parents=True, exist_ok=True)
        clipped_dir = DONOR_DIR / donor_id.replace("/", "_")
        clipped_dir.mkdir(parents=True, exist_ok=True)
        clipped_path = clipped_dir / f"activity_{activity_id}.fit"
        _write_clipped_fit(raw_path, clipped_path)

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


def poll_donor(donor_id: str, *, download_new: bool = False) -> list[int]:
    """List recent activities; optionally download unseen (state tracking TODO)."""
    activities = list_recent_activities(donor_id)
    ids = []
    for act in activities:
        aid = act["id"]
        ids.append(aid)
        if download_new:
            download_activity_streams_fit(donor_id, aid)
            print(f"  Ingested activity {aid}: {act.get('name', '?')}")
    return ids


def main() -> None:
    parser = argparse.ArgumentParser(description="Strava OAuth donor intake")
    parser.add_argument("--donor", required=True, help="Clinical donor ID (e.g. Reference_Elite_A)")
    parser.add_argument("--authorize-url", action="store_true", help="Print OAuth link for donor")
    parser.add_argument("--redirect-uri", default=DEFAULT_REDIRECT)
    parser.add_argument("--exchange-code", metavar="CODE", help="Exchange OAuth code for tokens")
    parser.add_argument("--poll", action="store_true", help="List recent activities")
    parser.add_argument("--download-new", action="store_true", help="With --poll, download .fit files")
    parser.add_argument("--poll-all", action="store_true", help="Poll every donor in token store")
    args = parser.parse_args()

    if args.authorize_url:
        print(build_authorize_url(args.donor, args.redirect_uri))
        return

    if args.exchange_code:
        entry = exchange_code(args.donor, args.exchange_code)
        print(f"Connected {args.donor} (athlete_id={entry.get('athlete_id')})")
        return

    if args.poll_all:
        donors = _load_tokens().get("donors", {})
        for donor_id in donors:
            print(f"\n{donor_id}:")
            poll_donor(donor_id, download_new=args.download_new)
        return

    if args.poll:
        poll_donor(args.donor, download_new=args.download_new)
        return

    parser.error("Specify --authorize-url, --exchange-code, --poll, or --poll-all")


if __name__ == "__main__":
    main()
