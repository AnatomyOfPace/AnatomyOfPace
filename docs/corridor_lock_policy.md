# Corridor lock policy (SUT 160)

**Authority:** Operator policy for corridor span mutations within locked sector zoom maps. Complements spatial terminology in [`docs/course_traversal_terminology.md`](course_traversal_terminology.md). Lock rationales and QC notes must use course-direction vocabulary from that doc (not screen left/right or compass-only framing).

**Scope:** Sandnes Ultra Trail 160 (SUT_160) corridor configuration in `config/race_corridors.json`, `config/corridor_window_analysis.json`, and sector zoom config `config/sut160_sector_zoom.local.json`.

---

## Locked sector rule

A **locked sector** has `"locked": true` in `config/sut160_sector_zoom.local.json` and an operator sign-off record under `docs/outreach/sut160_*_zoom_locked.local.md`.

**No new corridor spans** may be inserted, extended, or auto-added within a locked sector's km window without:

1. **Operator QC** — grade/physics audit, adjacency check, and map verification on the sector zoom PNG.
2. **`lock_version` bump** — update the sector entry in `config/sut160_sector_zoom.local.json` and record the new lock id in the sector lock doc.

Renderer-only changes (label offsets, viewport padding) that do not alter corridor geometry in `race_corridors.json` may proceed under the same `lock_version` bump convention documented in geographic QC notes.

---

## Locked sector inventory (2026-06-26)

| sector_id | lock_version |
|-----------|--------------|
| `gramstad` | `2026-06-24` |
| `lifjell_dale` | `2026-06-24` |
| `hogstad_peninsula` | `2026-06-24` |
| `mid_race_massif` | `2026-06-25` |
| `paradisskaret_finish` | `2026-06-25-gap-154.80-154.95` |
| `start_hills` | `2026-06-25` |
| `bynuten` | `2026-06-25-rev32-selvikstakken` |
| `dansen_bersagel` | `2026-06-25-rev25-dansen_bersagel` |
| `figgjo` | `2026-06-26-rev4-figgjo` |
| `dale_to_paradisskaret` | `2026-06-26-dale-to-paradisskaret` |

Ten sector zoom maps are locked. Sector inventory and regen commands: [`docs/outreach/sut160_sector_zoom_roadmap.local.md`](outreach/sut160_sector_zoom_roadmap.local.md) *(local)*.

### Reopened sectors (draft)

*None — all ten logical sectors locked as of 2026-06-26.*

---

## Full-course geographic QC map

The full-course geographic QC map (`00_course_map_geographic_qc.png`) is a **read-only overlay** for operator review.

| Field | Value |
|-------|-------|
| Status | **LOCKED** `2026-06-26-full-course-geographic-qc` |
| Lock record | `docs/outreach/sut160_geographic_qc_locked.local.md` *(local)* |
| SHA-256 | `dfacb768e416382e4dfb5e1615d91670250608415e2910b0c9ef2d78ef8151c5` |

- The map **may render** corridor polylines and labels across the full course for visual QC.
- The map **must not mutate** corridor spans, sector zoom config, or analysis JSON for any locked sector.
- Regenerating the QC map does not constitute corridor lock approval and does not bypass the locked-sector rule above.

---

## Operator rule — no automatic corridor insertion

**Authoritative (2026-06-25):** No climb, brake, or flat corridor spans may be inserted automatically from physics scans, grade-bin discovery passes, climb/descent scans, flat scans, or **SAFE AUTO** reports — **repository-wide**, including locked and unlocked sectors.

| Requirement | Rule |
|-------------|------|
| Discovery output | **Proposal-only** — reports list candidate `km_start` / `km_end` spans; they do not mutate config |
| Config writes | **Forbidden** until explicit operator approval, grade/physics QC, map verification, and (for locked sectors) `lock_version` bump |
| Agent / pipeline behaviour | May generate reports and operator briefs; **must not** inject into `race_corridors.json`, `corridor_window_analysis.json`, or sector zoom config |

This extends prior decisions: no auto flat corridors; no auto-adds within locked sectors; no automatic corridors of any class from automated discovery.

### Evaluated candidates — not approved for auto-insert

The following five spans were evaluated in discovery / SAFE AUTO passes and remain **proposal-only** until explicit operator sign-off (QC + lock bump where applicable):

| Candidate | Class | Status |
|-----------|-------|--------|
| Øykjafjellet (start-hills descent roll) | brake / traverse | Not approved for auto-insert |
| Kyllesvatnet (Noredalen valley approach) | flat | Not approved for auto-insert |
| Mattirudlå CP (checkpoint descent band) | brake | Not approved for auto-insert |
| Bogafjellet Climb | climb | Not approved for auto-insert *(operator-inserted 2026-06-24d under manual QC — not a precedent for automation)* |
| Bakkafjellet Climb | climb | Not approved for auto-insert *(operator-inserted 2026-06-24f under manual QC — not a precedent for automation)* |

Existing operator-approved corridors for Bogafjellet and Bakkafjellet in `race_corridors.json` are unchanged; the table records that automated re-discovery must not re-insert or extend them without a fresh operator cycle.

---

## Auto-discovery and agent proposals

Grade-bin scans, collapse-flag exports, climb/descent discovery passes, flat scans, SAFE AUTO exports, and similar automated pipelines produce **report-only** output.

| Action | Locked sector | Unlocked sector / gap band |
|--------|---------------|----------------------------|
| Propose `km_start` / `km_end` spans | Report to operator; **no config write** | Report to operator; **no config write** |
| Inject into `race_corridors.json` | **Forbidden** without operator approval + QC + `lock_version` bump | **Forbidden** without operator approval + QC |
| Inject into `corridor_window_analysis.json` | **Forbidden** without operator approval + QC + `lock_version` bump | **Forbidden** without operator approval + QC |

**Flat corridors:** Auto-add of flat-class corridor spans is prohibited repository-wide. Flat bands remain operator-insert only.

---

## Multi-fit corridor ingest (Dale–Alsvik)

Phase A spatial alignment supports **multiple washed `.fit` sources** per corridor segment via `04_Python_Scripts/spatial/corridor_multi_fit.py`.

| Capability | Behaviour |
|------------|-----------|
| Multiple activities | Manifest `activities[]` — each row is one washed Parquet source |
| Partial coverage | Only the GPS-mapped overlap window is resampled; grid cells outside data remain NaN |
| Reverse traversal | `direction: auto` tags forward/reverse; stream-axis mode mirrors `course_km` within the corridor |
| GPS bridge | `align_mode: bridge` projects SUT_43 (or other) GPS onto SUT_160 organiser GPX (`trail_bridge.py`) |
| Discovery | `python3 04_Python_Scripts/spatial/corridor_multi_fit.py --discover` lists washed micro Parquet |

Example manifest: `config/spatial_align_manifest_dale_alsvik.example.json` (km 140–155.58, Subject_A/B bridge rows).

**Canonical working panel (2026-06-27):** `config/spatial_align_manifest_dale_alsvik.local.json` — two-athlete bridge ingest only (`Subject_A` SUT43_20260418 + `Subject_B` 18162306249). Output: `03_Processed_Data/spatial/dale_to_paradisskaret_stress_test/panel_1m.parquet` with bridge overlap ~140–152 km (~77% of analysis window).

### Reference_Elite_D — deferred, not blocked

Activity `18159079828` (SUT_160 race) remains in `deferred_activities[]` until donor `.fit` is washed. Strava stream JSON may exist locally but **`corridor_multi_fit.py` ingests washed micro Parquet only** (`read_parquet` — no Strava-JSON or streams-only path). Operator may proceed on corridor QC and two-athlete NTI without this row.

Candidate training activities (e.g. `18611057420`, `17862744649`) follow the same rule: download → wash → register in manifest `activities[]`. No partial-bridge shortcut without washed Parquet.

### Late-band coverage gap (km 152.0–155.58)

| Field | Value |
|-------|-------|
| Status | **Unavailable** on two-athlete bridge panel |
| Bridge overlap end | ~152 km (Subject_A/B GPS bridge to SUT_160 organiser GPX) |
| Missing telemetry | Vassfjellet climb → Paradisskaret Downhill finish band |
| Unblocks when | Reference_Elite_D SUT_160 race `.fit` wash **or** late-corridor training `.fit` with GPX overlap km 152–155.58 |

Grid cells km 152–155.58 remain NaN in the current panel until GPX-axis washed Parquet is added. Corridor span definitions in `race_corridors.json` remain locked; this gap is **panel coverage**, not corridor geometry.

---

## See also

- [`docs/course_traversal_terminology.md`](course_traversal_terminology.md) — upstream/downstream, dual-axis, gap placement
- [`docs/sut160_geographic_qc_map_notes.local.md`](sut160_geographic_qc_map_notes.local.md) — operator adjacency and insert notes *(local)*
- [`config/race_corridors.json`](../config/race_corridors.json) — authoritative corridor spans
