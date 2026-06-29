#!/usr/bin/env python3
"""
Review Priority Score (RPS) triage for 1 km HITL chunks.

RPS combines HMM uncertainty (A), cross-athlete kinematic divergence (B), and
terrain-tax severity (C):

    A = % metres with HMM max-state probability p < 0.70
    B = % metres with |NTI_Subject_A - NTI_Subject_B| >= 0.30
    C = min(1.0, max(0, (TI_p90 - 1.0) / 2.5))
    RPS = ((0.6 * A) + (0.4 * B)) * (1 + C)

Queues: RED RPS > 0.75 · YELLOW 0.40–0.75 · GREEN < 0.40

Usage (from repo root):
    python3 04_Python_Scripts/spatial/hitl_chunk_triage.py --km-start 29 --km-end 41

    python3 04_Python_Scripts/spatial/hitl_chunk_triage.py \\
        --panel 03_Processed_Data/spatial/sut43_terrain_ontology/panel_1m.parquet \\
        --hmm-draft 07_ML_Models/terrain_hmm_sut43_draft_predictions.parquet \\
        --chunk-priority 03_Processed_Data/spatial/sut43_terrain_ontology/ground_truth_review/chunk_priority.csv \\
        --output 03_Processed_Data/spatial/sut43_terrain_ontology/ground_truth_review/triage_queue_sut43.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from spatial.corridor_scope import SUT43_FULL_KM_END, SUT43_FULL_KM_START, SUT43_PRIMARY_KM_END, SUT43_PRIMARY_KM_START
from spatial.terrain_map_gen import compute_nti

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_PANEL = BASE_DIR / "03_Processed_Data" / "spatial" / "sut43_terrain_ontology" / "panel_1m.parquet"
DEFAULT_SPINE_PANEL = (
    BASE_DIR / "03_Processed_Data" / "spatial" / "sut43_terrain_ontology" / "panel_race_1m_spine.parquet"
)
DEFAULT_CHUNK_PRIORITY = (
    BASE_DIR
    / "03_Processed_Data"
    / "spatial"
    / "sut43_terrain_ontology"
    / "ground_truth_review"
    / "chunk_priority.csv"
)
DEFAULT_HMM_DRAFT = BASE_DIR / "07_ML_Models" / "terrain_hmm_sut43_draft_predictions.parquet"
DEFAULT_OUTPUT = (
    BASE_DIR
    / "03_Processed_Data"
    / "spatial"
    / "sut43_terrain_ontology"
    / "ground_truth_review"
    / "triage_queue_sut43.csv"
)
TRAIN_TERRAIN_HMM = BASE_DIR / "07_ML_Models" / "train_terrain_hmm.py"

HMM_LOW_CONF_THRESHOLD = 0.70
NTI_DIVERGENCE_THRESHOLD = 0.30
RPS_RED_THRESHOLD = 0.75
RPS_YELLOW_THRESHOLD = 0.40
HMM_STUB_CONFIDENCE = 0.50
TI_SPIKE_THRESHOLD = 2.5
HMM_MVL_MIN_METRES = 15
HMM_S56_TOLERANCE = 0.10
HMM_SWITCHES_PER_KM_MIN = 2
HMM_SWITCHES_PER_KM_MAX = 8


def chunk_id_for_index(idx: int) -> str:
    return f"chunk_{idx:02d}"


def _normalize_panel(panel: pd.DataFrame) -> pd.DataFrame:
    work = panel.copy()
    if "course_km" not in work.columns and "ref_chainage_m" in work.columns:
        work["course_km"] = work["ref_chainage_m"] / 1000.0
    if "course_m" not in work.columns and "ref_chainage_m" in work.columns:
        work["course_m"] = work["ref_chainage_m"]
    if "session_type" in work.columns:
        work = work[work["session_type"] == "race"]
    return work


def load_chunk_boundaries(
    chunk_priority_path: Path,
    *,
    km_start: float,
    km_end: float,
    chunk_km: float = 1.0,
    prefer_chunk_priority: bool = False,
) -> pd.DataFrame:
    if prefer_chunk_priority and chunk_priority_path.exists():
        chunks = pd.read_csv(chunk_priority_path)
        if {"chunk_id", "km_start", "km_end"}.issubset(chunks.columns):
            mask = (chunks["km_start"] >= km_start - 1e-9) & (chunks["km_end"] <= km_end + 1e-9)
            filtered = chunks.loc[mask, ["chunk_id", "km_start", "km_end"]].copy()
            if not filtered.empty:
                span_lo = float(filtered["km_start"].min())
                span_hi = float(filtered["km_end"].max())
                if abs(span_lo - km_start) < 1e-6 and abs(span_hi - km_end) < 1e-6:
                    return filtered.reset_index(drop=True)

    rows: list[dict[str, Any]] = []
    chunk_idx = 0
    km = km_start
    while km < km_end - 1e-9:
        km_hi = min(km + chunk_km, km_end)
        rows.append({"chunk_id": chunk_id_for_index(chunk_idx), "km_start": round(km, 3), "km_end": round(km_hi, 3)})
        chunk_idx += 1
        km += chunk_km
    return pd.DataFrame(rows)


def per_metre_metrics(panel: pd.DataFrame, hmm_draft: pd.DataFrame | None) -> pd.DataFrame:
    """One row per course_m with A/B/C component inputs."""
    work = _normalize_panel(panel)
    work["nti"] = compute_nti(work)

    per_m = work.groupby("course_m", as_index=False).agg(
        course_km=("course_km", "first"),
        ti_median=("ti", "median"),
        nti_std=("nti", "std"),
        n_athletes=("donor_id", "nunique"),
    )
    per_m["nti_std"] = per_m["nti_std"].fillna(0.0)

    pivot = work.pivot_table(index="course_m", columns="donor_id", values="nti", aggfunc="median").reset_index()
    if "Subject_A" in pivot.columns and "Subject_B" in pivot.columns:
        pivot["nti_gap"] = (pivot["Subject_A"] - pivot["Subject_B"]).abs()
    elif len([c for c in pivot.columns if c != "course_m"]) >= 2:
        subjects = [c for c in pivot.columns if c != "course_m"]
        pivot["nti_gap"] = (pivot[subjects[0]] - pivot[subjects[1]]).abs()
    else:
        pivot["nti_gap"] = 0.0

    per_m = per_m.merge(pivot[["course_m", "nti_gap"]], on="course_m", how="left")
    per_m["nti_gap"] = per_m["nti_gap"].fillna(0.0)
    per_m["high_divergence"] = per_m["nti_gap"] >= NTI_DIVERGENCE_THRESHOLD

    if hmm_draft is not None and not hmm_draft.empty:
        hmm_cols = ["course_m", "hmm_confidence"]
        if "draft_class" in hmm_draft.columns:
            hmm_cols.append("draft_class")
        hmm = hmm_draft[hmm_cols].copy()
        per_m = per_m.merge(hmm, on="course_m", how="left")
        per_m["hmm_confidence"] = per_m["hmm_confidence"].fillna(HMM_STUB_CONFIDENCE)
    else:
        per_m["hmm_confidence"] = HMM_STUB_CONFIDENCE

    per_m["low_hmm_conf"] = per_m["hmm_confidence"] < HMM_LOW_CONF_THRESHOLD
    return per_m.sort_values("course_m").reset_index(drop=True)


def severity_multiplier(ti_p90: float) -> float:
    return float(min(1.0, max(0.0, (ti_p90 - 1.0) / 2.5)))


def queue_for_rps(rps: float) -> str:
    if rps > RPS_RED_THRESHOLD:
        return "RED"
    if rps >= RPS_YELLOW_THRESHOLD:
        return "YELLOW"
    return "GREEN"


def contiguous_run_lengths(classes: pd.Series, target: set[str]) -> list[int]:
    lengths: list[int] = []
    run = 0
    for cls in classes.astype(str):
        if cls in target:
            run += 1
        elif run:
            lengths.append(run)
            run = 0
    if run:
        lengths.append(run)
    return lengths


def count_class_switches(classes: pd.Series) -> int:
    if len(classes) <= 1:
        return 0
    return int((classes.astype(str) != classes.astype(str).shift()).sum() - 1)


def evaluate_hmm_oversmoothing(
    hmm_draft: pd.DataFrame,
    metre_df: pd.DataFrame,
    *,
    km_start: float,
    km_end: float,
) -> dict[str, Any]:
    """Strategic Command 2026-06-29 over-smoothing gates."""
    if hmm_draft is None or hmm_draft.empty or "draft_class" not in hmm_draft.columns:
        return {"available": False, "reason": "no draft_class column"}

    hmm_win = hmm_draft[
        (hmm_draft["course_km"] >= km_start) & (hmm_draft["course_km"] < km_end)
    ].sort_values("course_m")
    ti_win = metre_df[
        (metre_df["course_km"] >= km_start) & (metre_df["course_km"] < km_end)
    ].sort_values("course_m")

    if hmm_win.empty:
        return {"available": False, "reason": "no HMM rows in window"}

    ti_spike_m = int((ti_win["ti_median"] >= TI_SPIKE_THRESHOLD).sum()) if not ti_win.empty else 0
    s56_mask = hmm_win["draft_class"].astype(str).isin({"S5", "S6"})
    hmm_s56_m = int(s56_mask.sum())

    s56_runs = contiguous_run_lengths(hmm_win["draft_class"], {"S5", "S6"})
    min_s56_run = min(s56_runs) if s56_runs else 0

    span_km = max(km_end - km_start, 1e-9)
    switches_per_km = count_class_switches(hmm_win["draft_class"]) / span_km

    s56_ratio_err = (
        abs(hmm_s56_m - ti_spike_m) / max(ti_spike_m, 1)
        if ti_spike_m > 0
        else (0.0 if hmm_s56_m == 0 else 1.0)
    )

    mvl_pass = (not s56_runs) or (min_s56_run >= HMM_MVL_MIN_METRES)
    s56_pass = s56_ratio_err <= HMM_S56_TOLERANCE if ti_spike_m > 0 else hmm_s56_m == 0
    switch_pass = HMM_SWITCHES_PER_KM_MIN <= switches_per_km <= HMM_SWITCHES_PER_KM_MAX

    return {
        "available": True,
        "km_window": [km_start, km_end],
        "ti_spike_metres": ti_spike_m,
        "hmm_s56_metres": hmm_s56_m,
        "s56_volume_error_pct": round(100.0 * s56_ratio_err, 1),
        "min_s56_run_m": min_s56_run,
        "switches_per_km": round(switches_per_km, 2),
        "mvl_pass": mvl_pass,
        "s56_recall_pass": s56_pass,
        "transition_freq_pass": switch_pass,
        "all_pass": mvl_pass and s56_pass and switch_pass,
    }


def print_hmm_gate_report(gates: dict[str, Any]) -> None:
    if not gates.get("available"):
        print(f"HMM over-smoothing gates: skipped ({gates.get('reason', 'unavailable')})")
        return

    print("HMM over-smoothing evaluation (Strategic Command 2026-06-29):")
    print(
        f"  MVL (min S5/S6 run >= {HMM_MVL_MIN_METRES} m): "
        f"{'PASS' if gates['mvl_pass'] else 'FAIL'} (min={gates['min_s56_run_m']} m)"
    )
    print(
        f"  S5/S6 recall (±{int(HMM_S56_TOLERANCE * 100)}% of TI>={TI_SPIKE_THRESHOLD} m): "
        f"{'PASS' if gates['s56_recall_pass'] else 'FAIL'} "
        f"(spike={gates['ti_spike_metres']} m, hmm_s56={gates['hmm_s56_metres']} m, "
        f"err={gates['s56_volume_error_pct']}%)"
    )
    print(
        f"  Transition freq ({HMM_SWITCHES_PER_KM_MIN}–{HMM_SWITCHES_PER_KM_MAX} switches/km): "
        f"{'PASS' if gates['transition_freq_pass'] else 'FAIL'} ({gates['switches_per_km']} switches/km)"
    )
    print(f"  Overall: {'PASS' if gates['all_pass'] else 'FAIL — tune transition matrix diagonal'}")


def build_rps_triage(
    panel: pd.DataFrame,
    hmm_draft: pd.DataFrame | None,
    chunks: pd.DataFrame,
) -> pd.DataFrame:
    metre_df = per_metre_metrics(panel, hmm_draft)

    rows: list[dict[str, Any]] = []
    for _, chunk in chunks.iterrows():
        km_lo = float(chunk["km_start"])
        km_hi = float(chunk["km_end"])
        cid = str(chunk["chunk_id"])

        chunk_m = metre_df[(metre_df["course_km"] >= km_lo) & (metre_df["course_km"] < km_hi)]

        if chunk_m.empty:
            a_val = b_val = c_val = rps = 0.0
        else:
            a_val = float(chunk_m["low_hmm_conf"].mean())
            b_val = float(chunk_m["high_divergence"].mean())
            ti_p90 = float(chunk_m["ti_median"].quantile(0.90))
            c_val = severity_multiplier(ti_p90)
            rps = round(((0.6 * a_val) + (0.4 * b_val)) * (1.0 + c_val), 4)

        rows.append(
            {
                "chunk_id": cid,
                "km_start": round(km_lo, 3),
                "km_end": round(km_hi, 3),
                "A": round(a_val, 4),
                "B": round(b_val, 4),
                "C": round(c_val, 4),
                "RPS": rps,
                "queue": queue_for_rps(rps),
            }
        )

    return pd.DataFrame(rows).sort_values("RPS", ascending=False).reset_index(drop=True)


def write_sut160_stub(output_path: Path) -> None:
    stub = pd.DataFrame(
        [
            {
                "chunk_id": "chunk_stub_00",
                "km_start": 140.0,
                "km_end": 141.0,
                "A": "",
                "B": "",
                "C": "",
                "RPS": "",
                "queue": "PENDING",
            }
        ]
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    stub.to_csv(output_path, index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="HITL chunk RPS triage ranker")
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--use-spine-panel", action="store_true", help="Use panel_race_1m_spine.parquet")
    parser.add_argument("--hmm-draft", type=Path, default=DEFAULT_HMM_DRAFT)
    parser.add_argument("--chunk-priority", type=Path, default=DEFAULT_CHUNK_PRIORITY)
    parser.add_argument("--use-chunk-priority", action="store_true", help="Use chunk_priority.csv when span matches")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--sut160-stub", type=Path, default=None, help="Optional triage_queue_sut160.csv stub path")
    parser.add_argument("--km-start", type=float, default=SUT43_FULL_KM_START)
    parser.add_argument("--km-end", type=float, default=SUT43_FULL_KM_END)
    parser.add_argument("--chunk-km", type=float, default=1.0)
    parser.add_argument("--top-red", type=int, default=10, help="Print top N RED chunks")
    args = parser.parse_args()

    panel_path = DEFAULT_SPINE_PANEL if args.use_spine_panel else args.panel
    if not panel_path.exists():
        raise FileNotFoundError(f"Panel not found: {panel_path}")

    panel = pd.read_parquet(panel_path)
    panel_km = _normalize_panel(panel)
    print(f"Panel: {panel_path.name} km {panel_km['course_km'].min():.1f}–{panel_km['course_km'].max():.1f}")

    hmm_draft: pd.DataFrame | None = None
    hmm_stubbed = False
    if args.hmm_draft.exists():
        hmm_draft = pd.read_parquet(args.hmm_draft)
        print(f"Loaded HMM draft: {len(hmm_draft)} rows from {args.hmm_draft}")
    else:
        hmm_stubbed = True
        print(f"WARN: HMM draft not found ({args.hmm_draft}) — A stubbed at p={HMM_STUB_CONFIDENCE}")

    chunks = load_chunk_boundaries(
        args.chunk_priority,
        km_start=args.km_start,
        km_end=args.km_end,
        chunk_km=args.chunk_km,
        prefer_chunk_priority=args.use_chunk_priority,
    )
    if chunks.empty:
        raise ValueError(f"No chunks in km {args.km_start}–{args.km_end}")

    metre_df = per_metre_metrics(panel, hmm_draft)
    if not hmm_stubbed and TRAIN_TERRAIN_HMM.exists():
        gates = evaluate_hmm_oversmoothing(hmm_draft, metre_df, km_start=args.km_start, km_end=args.km_end)
        print_hmm_gate_report(gates)
    elif TRAIN_TERRAIN_HMM.exists():
        print("HMM over-smoothing gates: skipped (stubbed draft)")

    triage = build_rps_triage(panel, hmm_draft, chunks)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    triage.to_csv(args.output, index=False)
    print(f"Wrote {args.output} ({len(triage)} chunks)")

    if args.sut160_stub:
        write_sut160_stub(args.sut160_stub)
        print(f"Wrote SUT_160 stub {args.sut160_stub}")

    red = triage[triage["queue"] == "RED"].head(args.top_red)
    counts = triage["queue"].value_counts().to_dict()
    print(f"\nQueue counts: RED={counts.get('RED', 0)} YELLOW={counts.get('YELLOW', 0)} GREEN={counts.get('GREEN', 0)}")
    print(f"\nTop {args.top_red} RED chunks (descending RPS):")
    if red.empty:
        print("  (none — showing highest-RPS chunks)")
        for _, row in triage.head(args.top_red).iterrows():
            print(
                f"  {row['chunk_id']} km {row['km_start']}-{row['km_end']} "
                f"RPS={row['RPS']} queue={row['queue']} A={row['A']} B={row['B']} C={row['C']}"
            )
    else:
        for _, row in red.iterrows():
            print(
                f"  {row['chunk_id']} km {row['km_start']}-{row['km_end']} "
                f"RPS={row['RPS']} A={row['A']} B={row['B']} C={row['C']}"
            )


if __name__ == "__main__":
    main()
