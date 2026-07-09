#!/usr/bin/env python3
"""Ghost Authority pre-publication scan for markdown and plain text."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Patterns that must not appear in public copy (case-insensitive unless noted).
FORBIDDEN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private training project", re.compile(r"seig\s+og\s+kjapp|endurance_protocol", re.I)),
    ("personal pronoun (I/we/my/our)", re.compile(r"\b(I|we|my|our|me|us)\b")),
    ("EPR / reference-elite mention", re.compile(r"\bEPR\b|reference[- ]elite", re.I)),
    ("legacy Norwegian concept", re.compile(
        r"\b(terrengskatt|terrengindeks|vaskemaskin|innsatsparadokset|kumulativ\s+gjeld|"
        r"sync\s+logg|løpsmanual|referanseløper)\b",
        re.I,
    )),
]

# Optional: flag common operator names if they appear in committed copy.
NAME_BLOCKLIST = re.compile(
    r"\b(eirik|sølvi|solvi|lars\s*ole|kjell|anatomy\s+pace\s+as\s+person)\b",
    re.I,
)

ALLOWED_SUBJECT_IDS = re.compile(
    r"\b(Subject_[A-Z]|Reference_Elite_[A-Z]|Dr\.\s*Anatomy\s*Pace)\b"
)


def scan_text(text: str, path: Path) -> list[str]:
    issues: list[str] = []
    for label, pattern in FORBIDDEN_PATTERNS:
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            snippet = text[max(0, match.start() - 20) : match.end() + 20].replace("\n", " ")
            issues.append(f"{path}:{line}: [{label}] …{snippet}…")

    for match in NAME_BLOCKLIST.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        issues.append(f"{path}:{line}: [possible personal name] '{match.group()}'")

    return issues


def scan_file(path: Path) -> list[str]:
    return scan_text(path.read_text(encoding="utf-8"), path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ghost Authority scan for public copy.")
    parser.add_argument("paths", nargs="+", type=Path, help="Files to scan")
    parser.add_argument("--strict", action="store_true", help="Exit 1 on any hit")
    args = parser.parse_args()

    all_issues: list[str] = []
    for path in args.paths:
        if not path.is_file():
            print(f"SKIP missing: {path}", file=sys.stderr)
            continue
        all_issues.extend(scan_file(path))

    if all_issues:
        print("Ghost Authority scan: FAIL")
        for issue in all_issues:
            print(f"  {issue}")
        return 1 if args.strict else 0

    print(f"Ghost Authority scan: PASS ({len(args.paths)} file(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
