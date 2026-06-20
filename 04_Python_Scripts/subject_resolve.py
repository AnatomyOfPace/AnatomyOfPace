"""Resolve clinical subject IDs to local-only filename / DB tokens (gitignored registry)."""

from __future__ import annotations

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
REGISTRY_PATH = BASE_DIR / "config" / "subject_registry.local.json"
RAW_DATA_DIR = BASE_DIR / "02_Raw_Data"


def _load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        return {}
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def fit_filename_token(subject_id: str) -> str:
    """Token expected inside local .fit filenames (defaults to clinical ID)."""
    reg = _load_registry()
    return reg.get("fit_tokens", {}).get(subject_id, subject_id)


def db_full_name(subject_id: str) -> str:
    """Athlete name in local SQLite (defaults to clinical ID)."""
    reg = _load_registry()
    return reg.get("db_names", {}).get(subject_id, subject_id)


def find_fit(*tokens: str) -> str:
    """Return first .fit basename under 02_Raw_Data matching all tokens."""
    for path in sorted(RAW_DATA_DIR.glob("*.fit")):
        name = path.name
        if all(token in name for token in tokens):
            return name
    token_str = ", ".join(tokens)
    raise FileNotFoundError(
        f"No .fit file in {RAW_DATA_DIR} matching tokens: {token_str}"
    )
