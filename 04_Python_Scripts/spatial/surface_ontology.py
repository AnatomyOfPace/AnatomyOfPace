"""
Six-class surface ontology (S1–S6) for automated corridor mapping.

Maps to subsets of the 11-class terrain scale in docs/master_plan.md §4.
S-class labels are a stress-test simplification for GMM/K-means on aggregated NTI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


SURFACE_ONTOLOGY_VERSION = "s6_v0"

SURFACE_CLASS_IDS: tuple[str, ...] = ("S1", "S2", "S3", "S4", "S5", "S6")


@dataclass(frozen=True)
class SurfaceClassSpec:
    class_id: str
    label: str
    master_plan_classes: tuple[int, ...]
    ti_target: float
    ti_band: tuple[float, float]
    description: str


SURFACE_CLASS_SPECS: dict[str, SurfaceClassSpec] = {
    "S1": SurfaceClassSpec(
        class_id="S1",
        label="Asphalt",
        master_plan_classes=(1,),
        ti_target=1.0,
        ti_band=(0.85, 1.15),
        description="Perfect energy return; finish-band asphalt and sealed road.",
    ),
    "S2": SurfaceClassSpec(
        class_id="S2",
        label="Gravel",
        master_plan_classes=(2,),
        ti_target=1.0,
        ti_band=(0.90, 1.20),
        description="Rolling hardpack gravel; minimal push-off leakage.",
    ),
    "S3": SurfaceClassSpec(
        class_id="S3",
        label="Grass or hard dirt",
        master_plan_classes=(3, 4),
        ti_target=1.25,
        ti_band=(1.05, 1.45),
        description="Dry slab, grass, or soft vegetation; moderate stabilisation tax.",
    ),
    "S4": SurfaceClassSpec(
        class_id="S4",
        label="Technical rock (medium)",
        master_plan_classes=(5, 6),
        ti_target=1.6,
        ti_band=(1.40, 1.80),
        description="Rooty or coarse stone trail; high braking and eccentric load.",
    ),
    "S5": SurfaceClassSpec(
        class_id="S5",
        label="Technical rock (difficult)",
        master_plan_classes=(7, 10),
        ti_target=2.2,
        ti_band=(1.80, 2.60),
        description="Loose mass or coarse ur; runnability collapse without full bog vacuum.",
    ),
    "S6": SurfaceClassSpec(
        class_id="S6",
        label="Bog (wet mud)",
        master_plan_classes=(11,),
        ti_target=2.5,
        ti_band=(2.00, 4.50),
        description="Deep bog or mud; near-zero speed at high cardiac cost.",
    ),
}


def expected_ti_band(class_id: str) -> tuple[float, float]:
    spec = SURFACE_CLASS_SPECS[class_id]
    return spec.ti_band


def map_cluster_to_surface_class(
    cluster_centroids: Sequence[float],
    *,
    ordered: bool = True,
) -> dict[int, str]:
    """
    Assign each cluster index to nearest S-class by centroid NTI/TI.

    When ordered=True, centroids are sorted ascending before mapping to S1..S6
    (monotonic friction assumption along the stress-test corridor).
    """
    specs = [SURFACE_CLASS_SPECS[cid] for cid in SURFACE_CLASS_IDS]
    targets = [s.ti_target for s in specs]
    ids = list(SURFACE_CLASS_IDS)

    indexed = list(enumerate(cluster_centroids))
    if ordered:
        indexed.sort(key=lambda x: x[1])

    mapping: dict[int, str] = {}
    for rank, (cluster_idx, centroid) in enumerate(indexed):
        if rank >= len(ids):
            mapping[cluster_idx] = "S6"
            continue
        # Nearest target among remaining classes from rank onward preserves order.
        candidates = ids[rank:]
        cand_targets = targets[rank:]
        best = min(
            zip(candidates, cand_targets),
            key=lambda pair: abs(centroid - pair[1]),
        )
        mapping[cluster_idx] = best[0]
    return mapping
