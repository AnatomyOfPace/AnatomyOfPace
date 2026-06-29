# Course traversal terminology (SUT 160 / corridor QC)

**Authority:** All spatial terms in corridor QC, gap placement, adjacency notes, and operator locks are defined **relative to direction of travel along the race course** — race start → race finish — **not** map compass, screen left/right, elevation-only cues, or hydrologic flow direction.

**Scope:** Sandnes Ultra Trail 160 (SUT_160) corridor work in *The Anatomy of Pace*. Applies wherever `race_corridors.json`, sector zoom maps, and geographic QC notes describe km windows, gaps, and adjacency.

---

## Anchor axiom

| Rule | Definition |
|------|------------|
| **Positive course progression** | A runner **into the race** moves from lower cumulative race distance toward higher cumulative race distance until the finish line. |
| **Finish anchor** | SUT_160 finish at **km 161** (Alsvik natursenter). **Closer to finish** ≡ **higher km** (nearer 161). **Farther from finish** ≡ **lower km**. |
| **Start anchor** | SUT_160 start at **km ~0** (same venue). **Closer to start** ≡ **lower km**. |

Geographic compass and screen axes are **diagnostic overlays only**. They do not define early/late, upstream/downstream, or before/after.

---

## Direction of travel

| Term | Definition | SUT_160 notes |
|------|------------|---------------|
| **Direction of travel** / **into the race** | Forward along the organiser course polyline in the order runners traverse it on race day. | Monotonic **course km** and **stream km** increase along this direction (modulo GPS noise). |
| **Against the race** / **back toward start** | Opposite to direction of travel. | Lower km; never used for “upstream” without the course qualifier below. |

### Geographic trend (`paradisskaret_finish`, km 152–161)

In the Vassfjellet–Paradisskaret–Alsvik finish band, the organiser route **generally trends west → east** (longitude increasing toward Alsvik), e.g. Vassfjellet summit **eastward** bend, Dybingen isthmus east of Paradisskaret hairpins. **Switchbacks reverse local compass heading** for hundreds of metres; **course km still increases toward km 161**.

Do **not** equate “east on the map” with “late in the race” unless verified at that km — a hairpin can run west while km still climbs.

---

## Core term table

| Term | Along-course meaning | Higher / lower km? | Example (`paradisskaret_finish`, stream km) |
|------|----------------------|--------------------|---------------------------------------------|
| **Early** | Nearer the **start**; less distance already covered; **farther from finish** | **Lower** km | Mattirudlå Downhill end **~151.5** is **early** relative to Alsvik finish **161**. |
| **Late** | Nearer the **finish**; more distance covered; **closer to finish** | **Higher** km | Finish Downhill **160.3–161.0** is **late** in the race. |
| **Upstream** (on course) | **Against** direction of travel; **before** a reference point when running forward; **farther from finish** | **Lower** km than reference | Gap rationale: split at **154.41** was **upstream** of the winding-gravel anchor — **before** M155 / sharp bend. |
| **Downstream** (on course) | **With** direction of travel; **after** a reference point when running forward; **closer to finish** | **Higher** km than reference | Gap moved **downstream** to **154.80–154.95** — **after** moderate Vassfjellet descent, **before** Paradisskaret steep core @ **154.95**. |
| **Before** (point A before B) | A lies at **lower km** than B along the course; runner reaches A first | A km **<** B km | Vassfjellet Downhill end **154.80** is **before** Paradisskaret Downhill start **154.95**. |
| **After** (point A after B) | A lies at **higher km** than B; runner reaches A second | A km **>** B km | Sharp bend apex **155.14** is **after** gap band **154.80–154.95**. |
| **Closer to finish** | Higher km toward **161** | Higher | **156.05** (Dybingen–Alsvik Flat start) is **closer to finish** than **154.80**. |
| **Farther from finish** | Lower km away from **161** | Lower | **152.5** (Vassfjellet Climb start) is **farther from finish** than **160.3**. |
| **Lower km** | Smaller distance value on the stated axis | — | See dual-axis caveat below. |
| **Higher km** | Larger distance value on the stated axis | — | See dual-axis caveat below. |

### Hydrologic / slope upstream (explicit non-equivalence)

| Context | “Upstream” means | vs course upstream |
|---------|------------------|-------------------|
| **Course (this doc)** | Lower km; back toward start | **Authoritative** for corridor QC |
| **Hydrologic / watershed** | Toward the source of a stream | May **oppose** course direction on descents |
| **Slope / “up the hill”** | Against the grade vector | On a descent, **up the hill** is **course upstream** (lower km) even though the runner faces downhill |

**Example:** On Paradisskaret Downhill, the runner descends (elevation loss) **downstream on course** (km increasing toward Alsvik). Water runs **downhill** with the runner; **course upstream** is back up the grade toward Vassfjellet (lower km).

---

## Dual-axis caveat (stream km vs organiser course km)

SUT_160 QC uses two distance axes. **Traversal terms (early/late, upstream/downstream) apply to both** — higher value = closer to finish on that axis — but **numeric km differ** between axes.

| Axis | Symbol / field | Role |
|------|----------------|------|
| **Stream km** | `distance_km` on pinned activity FIT; `km_start` / `km_end` in `corridor_window_analysis.json` | Corridor **geometry**, physics audits, adjacency locks |
| **Course km** (organiser GPX) | Integer markers M*n*; `display_axis: course` labels | **Display** labels, CP road crossings, organiser parity |

**Rule:** State which axis when citing a number. **Never** infer upstream/downstream by converting a label on one axis and comparing visually on the map.

**Example conversions** (activity `18159079828`, official 2027 GPX; Gramstad band — see geographic QC notes):

| Stream km | Course km (display) |
|----------:|--------------------:|
| 142.3 | 142.9 |
| 147.4 | 147.3 |

Offset varies by bend (~0.0–0.6 km in late course). **Do not eyeball** finish-band stream km into course labels — use `build_stream_course_axis_map()` at plot time.

Corridor lock `2026-06-25-gap-154.80-154.95` is stated on **stream km**. Sector map labels may show the **course km** band for the same geometry after stream→GPX conversion.

---

## Worked example: Vassfjellet / Paradisskaret gap (lock `2026-06-25-gap-154.80-154.95`)

**Sector:** `paradisskaret_finish` · **Finish:** km **161** Alsvik

| Element | Stream km | Position along course |
|---------|----------:|------------------------|
| Vassfjellet Downhill end | **154.80** | Moderate descent ends |
| **Unassigned gap** | **154.80–154.95** | Winding gravel; no corridor polyline |
| Paradisskaret Downhill start | **154.95** | Steep core begins |
| Sharp bend apex | **155.14** | **Downstream** of gap |
| Dybingen–Alsvik Flat start | **156.05** | **Downstream** of Paradisskaret end **155.58** |
| Alsvik finish | **161.0** | **Late** / **closest to finish** |

**Operator QC (paraphrased):** Prior gap at **154.41–154.45** sat **upstream** (too **early** / too **far from finish**) — immediately after the Vassfjellet summit eastward turn, **before** the winding gravel and M155 cluster. Required move **downstream** to **154.80–154.95** on the approach **before** the sharp bend @ **155.14**, still **~6.1 km upstream of finish** @ **161**.

**Reading “too late” vs “too early”:**

| Operator phrase | Course meaning | km direction |
|-----------------|----------------|--------------|
| “Too **early**” / “too far **upstream**” | Split too **far from finish**; runner has not yet reached intended terrain | **Lower** km than target |
| “Too **late**” / “too close to **Alsvik**” / “too far **downstream**” | Split too **near finish**; runner has already passed intended terrain | **Higher** km than target |

Failure mode: calling **154.41** “too **late**” because it looks **east** on the map — east is only loosely correlated with higher km in this switchback band. The documented lock records **154.41** as **too upstream (early)**, not too late.

---

## Anti-patterns (common failure modes)

| Anti-pattern | Why it fails | Correct framing |
|--------------|--------------|-----------------|
| **Screen left / right** | Map viewport rotates; east may be right, left, or up | Use **lower/higher km** and **upstream/downstream on course** |
| **“Upstream on the descent”** (slope sense) | Sounds like “up the hill” (lower km) but readers hear hydrologic upstream | Say **course upstream** (lower km) or **toward Vassfjellet / away from Alsvik** |
| **Confusing stream km with course km labels** | Same bend can be **154.95** stream vs **~155.x** on map label | Quote **axis**; use `build_stream_course_axis_map()` conversions for QC |
| **Compass west/east without km** | Hairpins run against regional trend | **Late** = high km toward **161**, not “east on screen” |
| **Garmin marker vs stream snap** | Marker on GPX ≠ stream geometry km | Corridor spans on **stream**; white M*n* on **GPX** (see geographic QC notes) |
| **Inverting early/late in gap disputes** | “Move gap later” = **higher km** (downstream), not “later in the meeting” | Repeat anchor km for reference and finish (**161**) |
| **Elevation-only ordering** | Climb then descent can have non-monotonic altitude while km increases | Order by **km**, not by alt |

---

## Usage in repository artifacts

| Artifact | Convention |
|----------|------------|
| `config/race_corridors.json` `note` fields | **Upstream/downstream** = on course; stream km unless `display_axis: course` |
| `docs/sut160_geographic_qc_map_notes.local.md` | Adjacency tables mix axes — follow per-row axis column |
| Operator locks | Prefer **stream km** endpoints; name lock id with stream band when geometry-critical |

---

## See also

- [`docs/corridor_lock_policy.md`](corridor_lock_policy.md) — locked-sector mutation rules, QC map read-only constraint, auto-discovery report-only policy
- `docs/sut160_geographic_qc_map_notes.local.md` — dual-axis rule, sector stacks, gap locks
- `config/race_corridors.json` — authoritative corridor spans (do not re-derive from map eyeball)
- `docs/outreach/sut160_paradisskaret_finish_corridor_split.local.md` — finish-band split rationale (when present)
