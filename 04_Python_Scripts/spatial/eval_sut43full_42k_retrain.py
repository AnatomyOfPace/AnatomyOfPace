#!/usr/bin/env python3
"""
Retrain matrix on sut43_full 42k export; evaluate vs production hybrid routing.

Usage (from repo root):
    python3 04_Python_Scripts/spatial/eval_sut43full_42k_retrain.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent.parent
PROCESSED = BASE_DIR / "03_Processed_Data" / "spatial"
MODEL_DIR = BASE_DIR / "07_ML_Models" / "spatial"
CONFIG_DIR = BASE_DIR / "config"
TRAIN_SCRIPT = BASE_DIR / "04_Python_Scripts/spatial/train_gold_suggester.py"
SUGGEST_SCRIPT = BASE_DIR / "04_Python_Scripts/spatial/suggest_gold_spans.py"

SUT43_FULL = PROCESSED / "gold_training_set_sut43_full.parquet"
CAL_POOL = PROCESSED / "gold_training_set_calibration_pool.parquet"
POOLED = PROCESSED / "gold_training_set_pooled_sut43full_cal.parquet"
ROUTING_PROD = CONFIG_DIR / "gold_suggester_routing.json"
HMM_DRAFT = BASE_DIR / "07_ML_Models/terrain_hmm_sut43_draft_predictions.parquet"
V0_MODEL = MODEL_DIR / "gold_suggester_v0.joblib"
BRIDGE_MODEL = MODEL_DIR / "gold_suggester_sector_bridge.joblib"
REPORT_OUT = MODEL_DIR / "gold_suggester_sut43full_42k_retrain_report.json"
SMOKE_DIR = PROCESSED / "sut43full_42k_retrain_smoke"

V0_SURFACE_THRESHOLD = 0.9789574636127722

SMOKE_PANELS = [
    {
        "key": "start_panel_km_0.5_8.0",
        "km_lo": 0.5,
        "km_hi": 8.0,
        "terrain_map": CONFIG_DIR / "spatial_terrain_map_sut43_start.json",
        "panel": PROCESSED / "sut43_terrain_ontology/panel_start_1m.parquet",
    },
    {
        "key": "bridge_panel_km_8_22",
        "km_lo": 8.0,
        "km_hi": 22.0,
        "terrain_map": CONFIG_DIR / "spatial_terrain_map_sut43_bridge.json",
        "panel": PROCESSED / "sut43_terrain_ontology/panel_bridge_1m.parquet",
    },
    {
        "key": "gramstad_km_29_41",
        "km_lo": 29.0,
        "km_hi": 41.0,
        "terrain_map": CONFIG_DIR / "spatial_terrain_map_sut43.json",
        "panel": PROCESSED / "sut43_terrain_ontology/panel_1m.parquet",
    },
    {
        "key": "finish_panel_km_41_42.5",
        "km_lo": 41.0,
        "km_hi": 42.5,
        "terrain_map": CONFIG_DIR / "spatial_terrain_map_sut43_finish.json",
        "panel": PROCESSED / "sut43_terrain_ontology/panel_finish_1m.parquet",
    },
]


def _run(cmd: list[str]) -> int:
    print("$", " ".join(cmd))
    return subprocess.call(cmd, cwd=BASE_DIR)


def _tag_source(df: pd.DataFrame, anchor: str) -> pd.DataFrame:
    out = df.copy()
    out["source_anchor"] = anchor
    return out


def rebuild_pooled_parquet() -> None:
    full = pd.read_parquet(SUT43_FULL)
    cal = pd.read_parquet(CAL_POOL)
    full_tagged = _tag_source(full, "sut43")
    cal_tagged = _tag_source(cal, "calibration_pool")
    bridge_rows = full[(full["course_km"] >= 8.0) & (full["course_km"] < 22.0)]
    bridge_tagged = _tag_source(bridge_rows, "bridge")
    pooled = pd.concat([cal_tagged, full_tagged], ignore_index=True)
    pooled.to_parquet(POOLED, index=False)
    bridge_path = PROCESSED / "gold_training_set_sector_bridge.parquet"
    bridge_tagged.to_parquet(bridge_path, index=False)
    print(f"Pooled parquet: {len(pooled)} rows ({pooled['is_labeled'].sum()} labeled)")
    print(f"Bridge sector parquet: {len(bridge_tagged)} rows (unchanged check)")


def _load_meta(model_path: Path) -> dict[str, Any]:
    meta_path = model_path.with_name(model_path.stem + "_metadata.json")
    if not meta_path.exists():
        return {}
    return json.loads(meta_path.read_text(encoding="utf-8"))


def _meta_summary(meta: dict[str, Any]) -> dict[str, Any]:
    surf = meta.get("surface_metrics", {})
    fric = meta.get("friction_metrics", {})
    out: dict[str, Any] = {
        "surface_holdout": surf.get("accuracy"),
        "friction_holdout": fric.get("accuracy"),
        "labeled_metres": meta.get("labeled_metres"),
        "per_source_surface": surf.get("per_source_accuracy") or {},
    }
    holdout = meta.get("source_holdout_eval") or {}
    cal_sut = holdout.get("train_cal_sut_test_start", {})
    start_cal = holdout.get("train_start_test_cal_sut", {})
    if cal_sut.get("surface"):
        out["train_cal_sut_test_start_surface"] = cal_sut["surface"].get("accuracy")
    if start_cal.get("surface"):
        out["train_start_test_cal_sut_surface"] = start_cal["surface"].get("accuracy")
    return out


def train_experiments() -> dict[str, Path]:
    models: dict[str, Path] = {}
    specs = [
        (
            "sut43full_only",
            [str(SUT43_FULL)],
            [],
            None,
        ),
        (
            "sut43full_cal",
            [str(POOLED)],
            [],
            None,
        ),
        (
            "sut43full_cal_dw_start035",
            [str(POOLED)],
            ["start:0.35"],
            None,
        ),
        (
            "sut43full_cal_dw_start035_finish035",
            [str(POOLED)],
            ["start:0.35", "finish:0.35"],
            None,
        ),
    ]
    for name, sets, weights, sector_id in specs:
        model = MODEL_DIR / f"gold_suggester_exp_{name}.joblib"
        meta = MODEL_DIR / f"gold_suggester_exp_{name}_metadata.json"
        argv = ["python3", str(TRAIN_SCRIPT)]
        for s in sets:
            argv.extend(["--training-set", s])
        argv.extend(["--model-out", str(model), "--metadata-out", str(meta)])
        for w in weights:
            argv.extend(["--source-weight", w])
        if sector_id:
            argv.extend(["--sector-id", sector_id])
        rc = _run(argv)
        if rc != 0:
            raise RuntimeError(f"Training failed: {name}")
        models[name] = model
    return models


def train_finish_sector() -> Path | None:
    full = pd.read_parquet(SUT43_FULL)
    cal = pd.read_parquet(CAL_POOL)
    finish_rows = _tag_source(
        full[(full["course_km"] >= 41.0) & (full["course_km"] < 42.5)],
        "finish",
    )
    cal_asphalt = cal[cal["label_surface"] == "S1"].copy()
    cal_asphalt = _tag_source(cal_asphalt, "calibration_pool")
    finish_path = PROCESSED / "gold_training_set_sector_finish.parquet"
    combined = pd.concat([cal_asphalt, finish_rows], ignore_index=True)
    combined.to_parquet(finish_path, index=False)
    labeled_n = int(combined["is_labeled"].sum())
    print(f"Finish sector training set: {labeled_n} labeled metres")
    if labeled_n < 500:
        print("Skip finish sector training — insufficient N")
        return None
    model = MODEL_DIR / "gold_suggester_sector_finish.joblib"
    meta = MODEL_DIR / "gold_suggester_sector_finish_metadata.json"
    rc = _run(
        [
            "python3",
            str(TRAIN_SCRIPT),
            "--training-set",
            str(finish_path),
            "--model-out",
            str(model),
            "--metadata-out",
            str(meta),
            "--sector-id",
            "finish",
            "--source-weight",
            "finish:0.35",
            "--no-source-holdout-eval",
        ]
    )
    if rc != 0:
        print("Finish sector training failed")
        return None
    return model


def bridge_gold_unchanged() -> dict[str, Any]:
    full = pd.read_parquet(SUT43_FULL)
    bridge = full[(full["course_km"] >= 8.0) & (full["course_km"] < 22.0)]
    meta = _load_meta(BRIDGE_MODEL)
    return {
        "bridge_metres": int(len(bridge)),
        "bridge_labeled": int(bridge["is_labeled"].sum()),
        "prior_bridge_labeled": meta.get("labeled_metres"),
        "unchanged": int(bridge["is_labeled"].sum()) == meta.get("labeled_metres"),
        "retrain_skipped": True,
    }


def _routing_manifest(
    *,
    mode: str,
    start_model: Path,
    bridge_model: Path,
    downstream_model: Path,
    finish_model: Path,
    notes: str = "",
) -> dict[str, Any]:
    return {
        "schema_version": "gold_suggester_routing_v0",
        "course_id": "SUT_43",
        "routing_mode": mode,
        "notes": notes,
        "sectors": [
            {"sector_id": "start", "km_lo": 0.5, "km_hi": 8.0, "model_path": str(start_model)},
            {"sector_id": "bridge", "km_lo": 8.0, "km_hi": 22.0, "model_path": str(bridge_model)},
            {"sector_id": "downstream", "km_lo": 22.0, "km_hi": 41.0, "model_path": str(downstream_model)},
            {"sector_id": "finish", "km_lo": 41.0, "km_hi": 42.5, "model_path": str(finish_model)},
        ],
    }


def _write_routing(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _smoke_counts(csv_path: Path) -> dict[str, int]:
    if not csv_path.exists():
        return {}
    df = pd.read_csv(csv_path)
    if df.empty or "action" not in df.columns:
        return {}
    return {str(k): int(v) for k, v in df["action"].value_counts().items()}


def run_smoke(
    panel: dict[str, Any],
    *,
    tag: str,
    routing_manifest: Path | None = None,
    model: Path | None = None,
) -> dict[str, int]:
    out_csv = SMOKE_DIR / f"smoke_{tag}_{panel['key']}.csv"
    argv = [
        "python3",
        str(SUGGEST_SCRIPT),
        "--engine",
        "ml",
        "--mode",
        "all",
        "--km-start",
        str(panel["km_lo"]),
        "--km-end",
        str(panel["km_hi"]),
        "--panel",
        str(panel["panel"]),
        "--terrain-map",
        str(panel["terrain_map"]),
        "--hmm-draft",
        str(HMM_DRAFT),
        "--output",
        str(out_csv),
    ]
    if routing_manifest is not None:
        argv.extend(["--sector-routing", "--routing-manifest", str(routing_manifest)])
    else:
        argv.extend(["--model", str(model or V0_MODEL)])
    rc = _run(argv)
    if rc != 0:
        raise RuntimeError(f"Smoke failed: {tag} / {panel['key']}")
    return _smoke_counts(out_csv)


def smoke_all_panels(
    tag: str,
    *,
    routing_manifest: Path | None = None,
    model: Path | None = None,
) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for panel in SMOKE_PANELS:
        out[panel["key"]] = run_smoke(panel, tag=tag, routing_manifest=routing_manifest, model=model)
    return out


def _smoke_regressed(
    baseline: dict[str, dict[str, int]],
    candidate: dict[str, dict[str, int]],
) -> list[str]:
    issues: list[str] = []
    for key, base in baseline.items():
        cand = candidate.get(key, {})
        if cand.get("REVISE", 0) > base.get("REVISE", 0):
            issues.append(f"{key}: REVISE {base.get('REVISE')}→{cand.get('REVISE')}")
        if cand.get("KEEP", 0) < base.get("KEEP", 0):
            issues.append(f"{key}: KEEP {base.get('KEEP')}→{cand.get('KEEP')}")
    return issues


def _sector_wins(
    baseline: dict[str, dict[str, int]],
    candidate: dict[str, dict[str, int]],
) -> list[str]:
    wins: list[str] = []
    for key, base in baseline.items():
        cand = candidate.get(key, {})
        if cand.get("REVISE", 99) < base.get("REVISE", 99):
            wins.append(f"{key}: REVISE {base.get('REVISE')}→{cand.get('REVISE')}")
    return wins


def evaluate_candidate(
    name: str,
    meta: dict[str, Any],
    smoke: dict[str, dict[str, int]],
    hybrid_smoke: dict[str, dict[str, int]],
    *,
    is_merged: bool,
) -> tuple[bool, list[str]]:
    issues = _smoke_regressed(hybrid_smoke, smoke)
    wins = _sector_wins(hybrid_smoke, smoke)
    surf = meta.get("surface_holdout") or (meta.get("surface_metrics") or {}).get("accuracy")
    if is_merged and surf is not None and surf < V0_SURFACE_THRESHOLD:
        if not wins:
            issues.append(f"surface holdout {surf:.4f} < {V0_SURFACE_THRESHOLD:.4f}")
    if issues and wins:
        # clear sector-specific win can override global holdout for merged
        holdout_only = all("surface holdout" in i for i in issues)
        if holdout_only and wins:
            issues = [i for i in issues if "surface holdout" not in i]
    return len(issues) == 0, issues


def main() -> int:
    SMOKE_DIR.mkdir(parents=True, exist_ok=True)

    bridge_check = bridge_gold_unchanged()
    print(f"Bridge gold unchanged: {bridge_check['unchanged']} ({bridge_check['bridge_labeled']} m)")

    rebuild_pooled_parquet()
    models = train_experiments()
    finish_model = train_finish_sector()

    # Production hybrid baseline (current routing.json)
    hybrid_smoke = smoke_all_panels("hybrid_prod", routing_manifest=ROUTING_PROD)
    print("Hybrid baseline smoke:", hybrid_smoke)

    experiments: dict[str, Any] = {}

    # Global-model candidates routed uniformly
    for name, model in models.items():
        manifest_path = SMOKE_DIR / f"routing_{name}.json"
        _write_routing(
            manifest_path,
            _routing_manifest(
                mode=f"uniform_{name}",
                start_model=model,
                bridge_model=model,
                downstream_model=model,
                finish_model=model,
                notes=f"All sectors → {name} (42k retrain eval)",
            ),
        )
        smoke = smoke_all_panels(name, routing_manifest=manifest_path)
        meta = _meta_summary(_load_meta(model))
        is_merged = name != "sut43full_only"
        promote, issues = evaluate_candidate(name, meta, smoke, hybrid_smoke, is_merged=is_merged)
        experiments[name] = {
            "smoke": smoke,
            "meta": meta,
            "model": str(model),
            "routing_manifest": str(manifest_path),
            "promote": promote,
            "promotion_issues": issues,
            "sector_wins": _sector_wins(hybrid_smoke, smoke),
        }

    # Hybrid + finish sector model (if trained)
    if finish_model is not None:
        manifest_path = SMOKE_DIR / "routing_hybrid_finish_sector.json"
        _write_routing(
            manifest_path,
            _routing_manifest(
                mode="hybrid_finish_sector",
                start_model=V0_MODEL,
                bridge_model=BRIDGE_MODEL,
                downstream_model=V0_MODEL,
                finish_model=finish_model,
                notes="Production hybrid with finish-specific sector model",
            ),
        )
        smoke = smoke_all_panels("hybrid_finish_sector", routing_manifest=manifest_path)
        meta = _meta_summary(_load_meta(finish_model))
        promote, issues = evaluate_candidate(
            "hybrid_finish_sector",
            meta,
            smoke,
            hybrid_smoke,
            is_merged=False,
        )
        experiments["hybrid_finish_sector"] = {
            "smoke": smoke,
            "meta": meta,
            "model": str(finish_model),
            "routing_manifest": str(manifest_path),
            "promote": promote,
            "promotion_issues": issues,
            "sector_wins": _sector_wins(hybrid_smoke, smoke),
        }

    best_name: str | None = None
    best_issues: list[str] = []
    for name, row in experiments.items():
        if row.get("promote"):
            best_name = name
            best_issues = []
            break

    promote_overall = best_name is not None
    routing_updated = False
    if promote_overall and best_name:
        best_manifest = Path(experiments[best_name]["routing_manifest"])
        ROUTING_PROD.write_text(best_manifest.read_text(encoding="utf-8"), encoding="utf-8")
        routing_updated = True
        print(f"PROMOTED: {best_name} → {ROUTING_PROD}")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sut43_full_labeled_metres": int(pd.read_parquet(SUT43_FULL)["is_labeled"].sum()),
        "v0_surface_holdout_threshold": V0_SURFACE_THRESHOLD,
        "hybrid_baseline_smoke": hybrid_smoke,
        "bridge_gold_check": bridge_check,
        "experiments": experiments,
        "best_candidate": best_name,
        "promote": promote_overall,
        "routing_manifest_updated": routing_updated,
        "promotion_issues": best_issues if not promote_overall else [],
        "reproduction_cli": {
            "full_eval": "python3 04_Python_Scripts/spatial/eval_sut43full_42k_retrain.py",
            "train_sut43full_only": (
                "python3 04_Python_Scripts/spatial/train_gold_suggester.py "
                "--training-set 03_Processed_Data/spatial/gold_training_set_sut43_full.parquet "
                "--model-out 07_ML_Models/spatial/gold_suggester_exp_sut43full_only.joblib "
                "--metadata-out 07_ML_Models/spatial/gold_suggester_exp_sut43full_only_metadata.json"
            ),
            "train_merged_dw": (
                "python3 04_Python_Scripts/spatial/train_gold_suggester.py "
                "--training-set 03_Processed_Data/spatial/gold_training_set_pooled_sut43full_cal.parquet "
                "--source-weight start:0.35 --source-weight finish:0.35 "
                "--model-out 07_ML_Models/spatial/gold_suggester_exp_sut43full_cal_dw_start035_finish035.joblib "
                "--metadata-out 07_ML_Models/spatial/gold_suggester_exp_sut43full_cal_dw_start035_finish035_metadata.json"
            ),
            "smoke_finish_hybrid": (
                "python3 04_Python_Scripts/spatial/suggest_gold_spans.py "
                "--engine ml --mode all --km-start 41 --km-end 42.5 "
                "--panel 03_Processed_Data/spatial/sut43_terrain_ontology/panel_finish_1m.parquet "
                "--terrain-map config/spatial_terrain_map_sut43_finish.json "
                "--sector-routing --routing-manifest config/gold_suggester_routing.json"
            ),
        },
    }
    REPORT_OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Report → {REPORT_OUT}")
    print(f"Promote: {'YES' if promote_overall else 'NO'}")
    if not promote_overall:
        for name, row in experiments.items():
            for issue in row.get("promotion_issues", []):
                print(f"  {name}: {issue}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
