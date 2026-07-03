#!/usr/bin/env python3
"""
Train sector-specific gold suggesters, smoke-test vs v0, write eval summary.

Usage (from repo root):
    python3 04_Python_Scripts/spatial/eval_gold_suggester_sectors.py
    python3 04_Python_Scripts/spatial/eval_gold_suggester_sectors.py --train-only
    python3 04_Python_Scripts/spatial/eval_gold_suggester_sectors.py --smoke-only
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from spatial.gold_suggester_routing import (
    SECTOR_BRIDGE_KM_HI,
    SECTOR_BRIDGE_KM_LO,
    SECTOR_DOWNSTREAM_KM_HI,
    SECTOR_DOWNSTREAM_KM_LO,
    SECTOR_START_KM_HI,
    SECTOR_START_KM_LO,
    hybrid_manifest_payload,
    manifest_payload,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
PROCESSED = BASE_DIR / "03_Processed_Data" / "spatial"
MODEL_DIR = BASE_DIR / "07_ML_Models" / "spatial"
CONFIG_DIR = BASE_DIR / "config"

CAL_POOL = PROCESSED / "gold_training_set_calibration_pool.parquet"
SUT43_FULL = PROCESSED / "gold_training_set_sut43_full.parquet"
V0_MODEL = MODEL_DIR / "gold_suggester_v0.joblib"
V0_METADATA = MODEL_DIR / "gold_suggester_v0_metadata.json"
ROUTING_MANIFEST = CONFIG_DIR / "gold_suggester_routing.json"
PURE_MANIFEST = CONFIG_DIR / "gold_suggester_routing_pure.json"
HYBRID_MANIFEST = CONFIG_DIR / "gold_suggester_routing_hybrid.json"
EVAL_OUT = MODEL_DIR / "gold_suggester_sector_eval.json"

HMM_DRAFT = BASE_DIR / "07_ML_Models" / "terrain_hmm_sut43_draft_predictions.parquet"
START_MAP = CONFIG_DIR / "spatial_terrain_map_sut43_start.json"
BRIDGE_MAP = CONFIG_DIR / "spatial_terrain_map_sut43_bridge.json"
GRAMSTAD_MAP = CONFIG_DIR / "spatial_terrain_map_sut43.json"

PANEL_START = PROCESSED / "sut43_terrain_ontology" / "panel_start_1m.parquet"
PANEL_BRIDGE = PROCESSED / "sut43_terrain_ontology" / "panel_bridge_1m.parquet"
PANEL_GRAMSTAD = PROCESSED / "sut43_terrain_ontology" / "panel_1m.parquet"

SMOKE_PANELS = [
    {
        "key": "start_panel_km_0.5_8.0",
        "km_lo": 0.5,
        "km_hi": 8.0,
        "terrain_map": START_MAP,
        "panel": PANEL_START,
    },
    {
        "key": "bridge_panel_km_8_22",
        "km_lo": 8.0,
        "km_hi": 22.0,
        "terrain_map": BRIDGE_MAP,
        "panel": PANEL_BRIDGE,
    },
    {
        "key": "gramstad_km_29_41",
        "km_lo": 29.0,
        "km_hi": 41.0,
        "terrain_map": GRAMSTAD_MAP,
        "panel": PANEL_GRAMSTAD,
    },
]

V0_SMOKE = {
    "start_panel_km_0.5_8.0": {"KEEP": 12, "REVISE": 2},
    "bridge_panel_km_8_22": {"KEEP": 4, "REVISE": 45},
    "gramstad_km_29_41": {"KEEP": 37, "REVISE": 13},
}


def _run_train(argv: list[str]) -> int:
    cmd = [sys.executable, str(BASE_DIR / "04_Python_Scripts/spatial/train_gold_suggester.py"), *argv]
    print("$", " ".join(cmd))
    return subprocess.call(cmd, cwd=BASE_DIR)


def _tag_source(df: pd.DataFrame, anchor: str) -> pd.DataFrame:
    out = df.copy()
    out["source_anchor"] = anchor
    return out


def build_sector_training_parquets() -> dict[str, Path]:
    cal = pd.read_parquet(CAL_POOL)
    full = pd.read_parquet(SUT43_FULL)

    start_rows = _tag_source(
        full[(full["course_km"] >= SECTOR_START_KM_LO) & (full["course_km"] < SECTOR_START_KM_HI)],
        "start",
    )
    start_path = PROCESSED / "gold_training_set_sector_start.parquet"
    pd.concat([cal, start_rows], ignore_index=True).to_parquet(start_path, index=False)

    bridge_rows = _tag_source(
        full[(full["course_km"] >= SECTOR_BRIDGE_KM_LO) & (full["course_km"] < SECTOR_BRIDGE_KM_HI)],
        "bridge",
    )
    bridge_path = PROCESSED / "gold_training_set_sector_bridge.parquet"
    bridge_rows.to_parquet(bridge_path, index=False)

    bridge_upstream_rows = _tag_source(
        full[(full["course_km"] >= SECTOR_BRIDGE_KM_LO) & (full["course_km"] < SECTOR_DOWNSTREAM_KM_HI)],
        "bridge_upstream",
    )
    bridge_upstream_path = PROCESSED / "gold_training_set_sector_bridge_upstream.parquet"
    bridge_upstream_rows.to_parquet(bridge_upstream_path, index=False)

    downstream_rows = _tag_source(
        full[(full["course_km"] >= SECTOR_DOWNSTREAM_KM_LO) & (full["course_km"] < SECTOR_DOWNSTREAM_KM_HI)],
        "sut43",
    )
    downstream_path = PROCESSED / "gold_training_set_sector_downstream.parquet"
    pd.concat([cal, downstream_rows], ignore_index=True).to_parquet(downstream_path, index=False)

    return {
        "start": start_path,
        "bridge": bridge_path,
        "bridge_upstream": bridge_upstream_path,
        "downstream": downstream_path,
    }


def train_sector_models(paths: dict[str, Path]) -> dict[str, Path]:
    models: dict[str, Path] = {}

    start_model = MODEL_DIR / "gold_suggester_sector_start.joblib"
    rc = _run_train(
        [
            "--training-set",
            str(paths["start"]),
            "--model-out",
            str(start_model),
            "--metadata-out",
            str(start_model.with_name(start_model.stem + "_metadata.json")),
            "--sector-id",
            "start",
            "--source-weight",
            "start:0.35",
        ]
    )
    if rc != 0:
        raise RuntimeError("start sector training failed")
    models["start"] = start_model

    downstream_model = MODEL_DIR / "gold_suggester_sector_downstream.joblib"
    rc = _run_train(
        [
            "--training-set",
            str(paths["downstream"]),
            "--model-out",
            str(downstream_model),
            "--metadata-out",
            str(downstream_model.with_name(downstream_model.stem + "_metadata.json")),
            "--sector-id",
            "downstream",
        ]
    )
    if rc != 0:
        raise RuntimeError("downstream sector training failed")
    models["downstream"] = downstream_model

    bridge_model = MODEL_DIR / "gold_suggester_sector_bridge.joblib"
    rc = _run_train(
        [
            "--training-set",
            str(paths["bridge"]),
            "--model-out",
            str(bridge_model),
            "--metadata-out",
            str(bridge_model.with_name(bridge_model.stem + "_metadata.json")),
            "--sector-id",
            "bridge",
            "--no-source-holdout-eval",
        ]
    )
    if rc != 0:
        raise RuntimeError("bridge-only sector training failed")

    bridge_up_model = MODEL_DIR / "gold_suggester_sector_bridge_upstream_exp.joblib"
    rc = _run_train(
        [
            "--training-set",
            str(paths["bridge_upstream"]),
            "--model-out",
            str(bridge_up_model),
            "--metadata-out",
            str(bridge_up_model.with_name(bridge_up_model.stem + "_metadata.json")),
            "--sector-id",
            "bridge_upstream",
            "--no-source-holdout-eval",
        ]
    )
    if rc != 0:
        raise RuntimeError("bridge+upstream sector training failed")

    bridge_meta = json.loads(bridge_model.with_name(bridge_model.stem + "_metadata.json").read_text())
    bridge_up_meta = json.loads(bridge_up_model.with_name(bridge_up_model.stem + "_metadata.json").read_text())
    if bridge_up_meta["surface_metrics"]["accuracy"] > bridge_meta["surface_metrics"]["accuracy"]:
        print("Promoting bridge+upstream model (better surface holdout)")
        bridge_up_model.replace(bridge_model)
        bridge_up_model.with_name(bridge_up_model.stem + "_metadata.json").replace(
            bridge_model.with_name(bridge_model.stem + "_metadata.json")
        )
    else:
        print("Keeping bridge-only model (better or equal surface holdout)")
        bridge_up_model.unlink(missing_ok=True)
        bridge_up_model.with_name(bridge_up_model.stem + "_metadata.json").unlink(missing_ok=True)

    models["bridge"] = bridge_model
    return models


def _smoke_counts(csv_path: Path) -> dict[str, int]:
    if not csv_path.exists():
        return {}
    df = pd.read_csv(csv_path)
    if df.empty or "action" not in df.columns:
        return {}
    return {str(k): int(v) for k, v in df["action"].value_counts().items()}


def run_smoke_panel(
    panel: dict[str, Any],
    *,
    sector_routing: bool,
    model: Path | None,
    out_dir: Path,
    routing_manifest: Path | None = None,
) -> dict[str, int]:
    tag = "sector" if sector_routing else "v0"
    out_csv = out_dir / f"smoke_{tag}_{panel['key']}.csv"
    argv = [
        sys.executable,
        str(BASE_DIR / "04_Python_Scripts/spatial/suggest_gold_spans.py"),
        "--engine",
        "ml",
        "--mode",
        "all",
        "--km-start",
        str(panel["km_lo"]),
        "--km-end",
        str(panel["km_hi"]),
        "--panel",
        str(panel.get("panel", PANEL_GRAMSTAD)),
        "--terrain-map",
        str(panel["terrain_map"]),
        "--hmm-draft",
        str(HMM_DRAFT),
        "--output",
        str(out_csv),
    ]
    for extra in panel.get("extra_maps", []):
        argv.extend(["--extra-terrain-map", str(extra)])
    if sector_routing:
        argv.append("--sector-routing")
        if routing_manifest is not None:
            argv.extend(["--routing-manifest", str(routing_manifest)])
    else:
        argv.extend(["--model", str(model or V0_MODEL)])
    print("$", " ".join(argv))
    rc = subprocess.call(argv, cwd=BASE_DIR)
    if rc != 0:
        raise RuntimeError(f"smoke test failed for {panel['key']} ({tag})")
    return _smoke_counts(out_csv)


def _load_metadata(model_path: Path) -> dict[str, Any]:
    meta_path = model_path.with_name(model_path.stem + "_metadata.json")
    if not meta_path.exists():
        return {}
    return json.loads(meta_path.read_text(encoding="utf-8"))


def _holdout_issues(meta: dict[str, Any], *, min_acc: float = 0.95, min_n: int = 500) -> list[str]:
    issues: list[str] = []
    surf = meta.get("surface_metrics", {})
    if surf.get("n_test", 0) >= min_n and surf.get("accuracy", 1.0) < min_acc:
        issues.append(f"surface holdout {surf['accuracy']:.3f} < {min_acc}")
    per_src = surf.get("per_source_accuracy") or {}
    for anchor, row in per_src.items():
        if row.get("n", 0) >= min_n and row.get("accuracy", 1.0) < min_acc:
            issues.append(f"per_source {anchor} {row['accuracy']:.3f} < {min_acc} (n={row['n']})")
    holdout = meta.get("source_holdout_eval") or {}
    for key, block in holdout.items():
        for head in ("surface", "friction"):
            row = block.get(head)
            if not row:
                continue
            if row.get("n", 0) >= min_n and row.get("accuracy", 1.0) < min_acc:
                issues.append(f"{key}/{head} {row['accuracy']:.3f} < {min_acc} (n={row['n']})")
    return issues


def _promotion_decision(v0_smoke: dict[str, dict[str, int]], sector_smoke: dict[str, dict[str, int]]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    start_v0 = v0_smoke["start_panel_km_0.5_8.0"]
    start_sec = sector_smoke["start_panel_km_0.5_8.0"]
    if start_sec.get("REVISE", 0) > start_v0.get("REVISE", 0):
        issues.append(
            f"start REVISE regressed {start_v0.get('REVISE')}→{start_sec.get('REVISE')}"
        )
    if start_sec.get("KEEP", 0) < start_v0.get("KEEP", 0):
        issues.append(f"start KEEP regressed {start_v0.get('KEEP')}→{start_sec.get('KEEP')}")

    bridge_v0 = v0_smoke["bridge_panel_km_8_22"]
    bridge_sec = sector_smoke["bridge_panel_km_8_22"]
    if bridge_sec.get("REVISE", 99) >= bridge_v0.get("REVISE", 45):
        issues.append(
            f"bridge REVISE not improved {bridge_v0.get('REVISE')}→{bridge_sec.get('REVISE')} (target <20)"
        )

    gram_v0 = v0_smoke["gramstad_km_29_41"]
    gram_sec = sector_smoke["gramstad_km_29_41"]
    if gram_sec.get("REVISE", 0) > gram_v0.get("REVISE", 0):
        issues.append(f"gramstad REVISE regressed {gram_v0.get('REVISE')}→{gram_sec.get('REVISE')}")
    if gram_sec.get("KEEP", 0) < gram_v0.get("KEEP", 0):
        issues.append(f"gramstad KEEP regressed {gram_v0.get('KEEP')}→{gram_sec.get('KEEP')}")

    return len(issues) == 0, issues


def write_pure_routing_manifest() -> None:
    PURE_MANIFEST.write_text(json.dumps(manifest_payload(MODEL_DIR), indent=2) + "\n", encoding="utf-8")


def write_hybrid_routing_manifest() -> None:
    payload = hybrid_manifest_payload(MODEL_DIR)
    HYBRID_MANIFEST.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train and evaluate sector gold suggesters.")
    parser.add_argument("--train-only", action="store_true")
    parser.add_argument("--smoke-only", action="store_true")
    parser.add_argument("--eval-out", type=Path, default=EVAL_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    smoke_dir = PROCESSED / "sector_suggester_smoke"
    smoke_dir.mkdir(parents=True, exist_ok=True)

    models: dict[str, Path] = {}
    if not args.smoke_only:
        paths = build_sector_training_parquets()
        models = train_sector_models(paths)
        write_pure_routing_manifest()
        write_hybrid_routing_manifest()

    sector_meta = {
        sid: _load_metadata(models[sid]) if sid in models else _load_metadata(MODEL_DIR / f"gold_suggester_sector_{sid}.joblib")
        for sid in ("start", "bridge", "downstream")
    }

    if args.train_only:
        print("Train-only complete.")
        return 0

    if args.smoke_only:
        if not PURE_MANIFEST.exists():
            write_pure_routing_manifest()
        if not HYBRID_MANIFEST.exists():
            write_hybrid_routing_manifest()

    v0_smoke: dict[str, dict[str, int]] = {}
    pure_smoke: dict[str, dict[str, int]] = {}
    hybrid_smoke: dict[str, dict[str, int]] = {}
    for panel in SMOKE_PANELS:
        v0_smoke[panel["key"]] = run_smoke_panel(panel, sector_routing=False, model=V0_MODEL, out_dir=smoke_dir)
        pure_smoke[panel["key"]] = run_smoke_panel(
            panel,
            sector_routing=True,
            model=None,
            out_dir=smoke_dir,
            routing_manifest=PURE_MANIFEST,
        )
        hybrid_smoke[panel["key"]] = run_smoke_panel(
            panel,
            sector_routing=True,
            model=None,
            out_dir=smoke_dir,
            routing_manifest=HYBRID_MANIFEST,
        )

    holdout_issues: dict[str, list[str]] = {
        sid: _holdout_issues(meta) for sid, meta in sector_meta.items() if meta
    }
    pure_promote, pure_issues = _promotion_decision(v0_smoke, pure_smoke)
    hybrid_promote, hybrid_issues = _promotion_decision(v0_smoke, hybrid_smoke)
    promote = hybrid_promote
    promo_issues = hybrid_issues if hybrid_promote else pure_issues + [f"hybrid: {i}" for i in hybrid_issues]
    if not hybrid_promote:
        promo_issues = pure_issues
        if not pure_promote:
            promo_issues.append("pure_sector_routing_failed")
    routing_mode = "hybrid" if hybrid_promote else "pure_sector"
    if promote:
        write_hybrid_routing_manifest()
        ROUTING_MANIFEST.write_text(HYBRID_MANIFEST.read_text(encoding="utf-8"), encoding="utf-8")

    eval_doc = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "architecture": "hybrid_sector_routing" if hybrid_promote else "pure_sector_routing",
        "routing_mode": routing_mode,
        "routing_manifest": str(ROUTING_MANIFEST),
        "sector_bounds_km": {
            "start": [SECTOR_START_KM_LO, SECTOR_START_KM_HI],
            "bridge": [SECTOR_BRIDGE_KM_LO, SECTOR_BRIDGE_KM_HI],
            "downstream": [SECTOR_DOWNSTREAM_KM_LO, SECTOR_DOWNSTREAM_KM_HI],
        },
        "training_recipes": {
            "start": "calibration_pool + start gold (km 0.5–8); source_weight start:0.35",
            "bridge": "sut43_full bridge gold km 8–22 (or +upstream km 8–29 if holdout improves)",
            "downstream": "calibration_pool + sut43 km 22–41",
        },
        "v0_baseline_smoke": V0_SMOKE,
        "smoke_v0_rerun": v0_smoke,
        "smoke_pure_sector_routed": pure_smoke,
        "smoke_hybrid_routed": hybrid_smoke,
        "sector_models": {
            sid: {
                "model_path": str(MODEL_DIR / f"gold_suggester_sector_{sid}.joblib"),
                "surface_holdout": meta.get("surface_metrics", {}).get("accuracy"),
                "friction_holdout": meta.get("friction_metrics", {}).get("accuracy"),
                "labeled_metres": meta.get("labeled_metres"),
                "holdout_issues": holdout_issues.get(sid, []),
            }
            for sid, meta in sector_meta.items()
        },
        "promote": promote,
        "promote_pure_sector": pure_promote,
        "promote_hybrid": hybrid_promote,
        "promotion_issues": promo_issues,
        "hybrid_routing": {
            "start_model": str(V0_MODEL),
            "bridge_model": str(MODEL_DIR / "gold_suggester_sector_bridge.joblib"),
            "downstream_model": str(V0_MODEL),
            "rationale": "cal+start-only sector model regressed start smoke (2→8 REVISE); v0 sut43 context retained for start/downstream.",
        },
        "reproduction_cli": {
            "train_all": "python3 04_Python_Scripts/spatial/eval_gold_suggester_sectors.py",
            "suggest_bridge_routed": (
                "python3 04_Python_Scripts/spatial/suggest_gold_spans.py "
                "--engine ml --mode all --km-start 8 --km-end 22 "
                "--terrain-map config/spatial_terrain_map_sut43_bridge.json "
                "--sector-routing"
            ),
        },
    }
    args.eval_out.parent.mkdir(parents=True, exist_ok=True)
    args.eval_out.write_text(json.dumps(eval_doc, indent=2) + "\n", encoding="utf-8")
    print(f"Eval summary → {args.eval_out}")
    print(f"Promote sector routing: {'YES' if promote else 'NO'}")
    if promo_issues:
        for issue in promo_issues:
            print(f"  - {issue}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
