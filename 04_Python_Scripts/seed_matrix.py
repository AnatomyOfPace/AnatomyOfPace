"""
Seed Matrix — per-subject asphalt / tartan anchor registry.

Each subject requires a locked frictionless baseline (.fit) for APR and TI.
Subject_B tartan calibration: 5k @ Stavanger Stadion (directive 2026-06-20).

Asphalt_Anchor_Proxy synthesis is HALTED — use real calibration telemetry only.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SEED_MATRIX_PATH = BASE_DIR / "config" / "seed_matrix.local.json"
SEED_MATRIX_EXAMPLE = BASE_DIR / "config" / "seed_matrix.example.json"
RAW_DATA_DIR = BASE_DIR / "02_Raw_Data"

# Fallback when local seed matrix is missing (Subject_A only).
DEFAULT_ANCHOR_BY_SUBJECT = {
    "Subject_A": "Stavanger_Halvmaraton.fit",
}


def _load_matrix() -> dict:
    path = SEED_MATRIX_PATH if SEED_MATRIX_PATH.exists() else SEED_MATRIX_EXAMPLE
    if not path.exists():
        return {"subjects": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_matrix(data: dict) -> None:
    SEED_MATRIX_PATH.parent.mkdir(exist_ok=True)
    SEED_MATRIX_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def proxy_generation_halted() -> bool:
    policy = _load_matrix().get("proxy_policy", {})
    return "halted" in str(policy.get("Asphalt_Anchor_Proxy", "")).lower()


def subject_status(subject_id: str) -> dict:
    return _load_matrix().get("subjects", {}).get(subject_id, {})


def anchor_status(subject_id: str) -> str:
    return subject_status(subject_id).get("status", "unknown")


def anchor_fit_basename(subject_id: str) -> str | None:
    """Return locked anchor filename, or None if awaiting calibration."""
    entry = subject_status(subject_id)
    fit_name = entry.get("anchor_fit")
    if fit_name:
        return fit_name
    if subject_id in DEFAULT_ANCHOR_BY_SUBJECT and anchor_status(subject_id) == "unknown":
        return DEFAULT_ANCHOR_BY_SUBJECT[subject_id]
    return DEFAULT_ANCHOR_BY_SUBJECT.get(subject_id)


def anchor_path(subject_id: str) -> Path:
    """
    Resolve anchor .fit path for a subject.

    Raises FileNotFoundError if anchor is not locked or file is missing.
    """
    name = anchor_fit_basename(subject_id)
    if not name:
        status = anchor_status(subject_id)
        raise FileNotFoundError(
            f"No locked anchor for {subject_id} (status: {status}). "
            f"Run 5k tartan calibration and lock via seed_matrix.lock_anchor()."
        )
    path = RAW_DATA_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Anchor file missing: {path}")
    return path


def anchor_path_or_default(subject_id: str, fallback: str | Path) -> Path:
    """Resolve subject anchor; fall back to explicit path if not locked."""
    try:
        return anchor_path(subject_id)
    except FileNotFoundError:
        p = Path(fallback)
        if not p.is_absolute():
            p = BASE_DIR / p
        return p


def lock_anchor(
    subject_id: str,
    fit_basename: str,
    *,
    surface: str = "tartan",
    protocol: str | None = "5k_stavanger_stadion",
    notes: str = "",
) -> None:
    """Persist a calibrated anchor as the definitive baseline for a subject."""
    data = _load_matrix()
    subjects = data.setdefault("subjects", {})
    entry = subjects.setdefault(subject_id, {})
    entry.update(
        {
            "anchor_fit": fit_basename,
            "surface": surface,
            "status": "locked",
            "locked_at": date.today().isoformat(),
            "calibration_protocol": protocol,
            "notes": notes or entry.get("notes", ""),
        }
    )
    _save_matrix(data)


def calibration_protocol(name: str) -> dict:
    return _load_matrix().get("calibration_protocols", {}).get(name, {})


def subjects_awaiting_calibration() -> list[str]:
    out = []
    for sid, entry in _load_matrix().get("subjects", {}).items():
        if entry.get("status") == "awaiting_calibration":
            out.append(sid)
    return out
