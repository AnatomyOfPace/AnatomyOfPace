# HITL Streamlit Annotator — Operator Playbook

**Script:** `04_Python_Scripts/spatial/hitl_annotator_app.py`  
**Authority:** Dr. Anatomy Pace laboratory · Subject_A / Subject_B race panel only  
**Companion:** `docs/hitl_dashboard_runbook.md` (PNG export + topo QC)

---

## Launch

From repo root:

```bash
pip install streamlit plotly   # or: pip install -r requirements.txt

# Default corridor window (km 29–41)
streamlit run 04_Python_Scripts/spatial/hitl_annotator_app.py

# chunk_05 UI calibration preset — km 34.0–35.0 view on startup
streamlit run 04_Python_Scripts/spatial/hitl_annotator_app.py -- --calibrate chunk_05
```

After launch, browser query params also work:

| Param | Example | Effect |
|-------|---------|--------|
| `calibrate` | `?calibrate=chunk_05` | Apply chunk_05 calibration preset |
| `chunk` | `?chunk=chunk_05` | Alias for `calibrate` |
| `km_start` / `km_end` | `?km_start=34.0&km_end=35.0` | Manual view window (overrides default, not preset lock hints) |

Sidebar **Apply preset window** re-centres the Plotly view and lock-hint fields without writing JSON.

---

## Strategic Command tactical sequencing

| Phase | Target | Rationale |
|-------|--------|-----------|
| **1 — Calibration** | `chunk_05` km 34–35 | Known narrative + partial prior gold; validate UI trust before high-stakes RED queue |
| **2 — RED pivot** | Top triage chunk (likely Vassfjellet ~km 36.7) | Only after chunk_05 lock + UI calibration sign-off |

**Do not auto-lock chunk_05.** The annotator pre-loads the view window and suggests S3/F2 lock hints; the operator promotes spans manually with **Save Lock**.

---

## Step 1 — chunk_05 calibration checklist

Use this session before touching RED-queue chunks.

### Preconditions

| Item | Path / note |
|------|-------------|
| Panel | `03_Processed_Data/spatial/sut43_terrain_ontology/panel_1m.parquet` |
| Terrain map | `config/spatial_terrain_map_sut43.json` |
| Reference PNG | `06_Visualizations/sut43_hitl/chunk_05_km34-35.png` |
| Upstream seam | Locked `chunk_04` S3/F2 @ 33.8–34.0 → continuous S3/F2 @ km 34.0 |

### Operator anchors (km 34–35)

| km | Feature | Expected class |
|----|---------|----------------|
| 34.0 | Seam from chunk_04 | S3/F2 low-friction trail continues |
| ~34.2 | Field anchor — compact runnable dirt | S3/F2 |
| ~34.60 | Trail → F4504 gravel transition (Gramstad farm pin) | S3/F2 ends; S2/F1 gravel begins downstream |
| ~34.64 | Drink CP halt corridor | High NTI σ; TRF exclusion 34.55–35.05 (`cp_halt`) — not a friction downgrade |

### Calibration steps

1. **Launch preset** — `--calibrate chunk_05` or sidebar **Apply preset window**.
2. **Plotly zoom** — Confirm view window 34.0–35.0; pan/zoom on speed + NTI rows. Drink CP should show Subject_A / Subject_B speed collapse with elevated NTI σ band.
3. **Class strip** — Row 4: opaque rectangles = `operator_gold_spans[]`; faint = cluster draft. Expect S3/F2 gold 34.0–34.60 overlapping view; S2/F1 from 34.60 (extends past 35.0).
4. **Athlete overlay** — Enable overlay; verify cross-athlete halt alignment near drink CP (stream km may differ ~280–350 m; geography co-locates).
5. **Expand gold panel** — Main area expander lists spans in view; cross-check against reference PNG.
6. **Manual lock only** — Adjust lock start/end, `surface_class`, `friction_tier`, clinical `reason`; click **Save Lock** when satisfied.
7. **JSON integrity** — After save:
   - `python3 -m json.tool config/spatial_terrain_map_sut43.json > /dev/null` (valid JSON)
   - Confirm new entry appended to `hitl.operator_gold_spans[]` with `mode: operator_gold`, `gold_source: operator`, `locked_at`
   - **Do not** hand-edit mid-array; append-only via app or controlled script
   - Re-export chunk PNG: `validation_dashboard.py --chunk-index 5` or `export_hitl_chunks.sh --chunk-index 5`
8. **Sign-off** — Update `ground_truth_review/chunk_priority.csv` notes only after deliberate operator lock (not during calibration-only UI pass).

### Save Lock — JSON safety

| Rule | Detail |
|------|--------|
| Append-only | `append_operator_gold_span()` reads full map, appends one span, writes `json.dumps(..., indent=2)` + trailing newline |
| No partial writes | If save errors, fix inputs; do not leave truncated JSON |
| Duplicate guard | Operator checks expander before re-locking same km window |
| Friction required | Always set `friction_tier` (F0–F4) per `docs/friction_index_spec.md` |
| TRF vs gold | CP halts → `hitl.trf_exclusions[]`, not S-class downgrade |

---

## Triage queue note

`triage_queue_sut43.csv` is **not** present in-repo. Use:

`03_Processed_Data/spatial/sut43_terrain_ontology/ground_truth_review/chunk_triage_priority.csv`

| chunk_id | triage_rank | triage_score | Interpretation |
|----------|-------------|--------------|----------------|
| chunk_08 | #1 (RED) | 0.1718 | Highest review priority — Vassfjellet / muddy descent band |
| chunk_05 | #8 (YELLOW) | 0.1106 | Lower urgency — **calibration chunk**, not RED pivot |

`chunk_priority.csv` shows chunk_05 at **700 m prior gold / 86.7% coverage** — calibration extends gold toward km 22–35 corridor target (13 km continuous lock wave).

**Sequence:** chunk_05 calibration → manual lock → then RED queue top (likely km 36.7+).

---

## Current draft spans — km 34–35 (terrain map)

As of prep date; operator gold in `config/spatial_terrain_map_sut43.json`:

| km | S/F | Status | Notes |
|----|-----|--------|-------|
| 33.8–34.0 | S3/F2 | Locked (chunk_04) | Ease band seam into chunk_05 |
| 34.0–34.60 | S3/F2 | Prior gold (partial) | Low-friction trail; field anchor ~34.2 |
| 34.60–36.30 | S2/F1 | Prior gold (extends past view) | Gramstad hard-pack gravel |
| 34.55–35.05 | — | TRF `cp_halt` | Drink CP corridor; both athletes |

Unset metres inside chunk_05 (~133 m per `chunk_priority.csv`) await operator refinement after UI calibration.

---

## Controls reference

| Control | Purpose |
|---------|---------|
| Calibration mode / chunk preset | Pre-load km window + anchor checklist |
| View sliders | Plotly zoom (`course_km_start` / `course_km_end`) |
| Lock span inputs | Metre-precise gold span to append |
| surface_class / friction_tier | S1–S6 · F0–F4 |
| Save Lock | Appends to `hitl.operator_gold_spans[]` |
| Athlete overlay | Subject_A / Subject_B speed + NTI traces |

**Upstream sector (km 22–29):** set terrain map path to `config/spatial_terrain_map_sut43_upstream.json` in sidebar. Keep gramstad_band locks in `spatial_terrain_map_sut43.json` only.

---

*Ghost Authority: Subject_A / Subject_B only. No personal identifiers in committed artifacts.*
