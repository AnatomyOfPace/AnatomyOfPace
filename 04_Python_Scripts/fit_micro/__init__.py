"""Wave 2 `.fit` micro-ingest subpackage — normalized ActivityFrame contract."""

from fit_micro.activity_frame import (
    ACTIVITY_FRAME_COLUMNS,
    PARSER_VERSION,
    read_parquet,
    write_meta_json,
    write_parquet,
)
from fit_micro.fit_ingest import parse_fit
from fit_micro.course_project import project_course_km, resolve_gpx_path
from fit_micro.stream_normalize import normalize_stream
from fit_micro.ti_enrich import enrich_ti

# NOTE: fit_micro.effort_paradox (compute_paradox_metrics, run_corridor_paradox_scan)
# is a planned module (see docs/fit_ingest_workflow.md, docs/training_residual_framework.md)
# and is intentionally not re-exported until implemented.

__all__ = [
    "ACTIVITY_FRAME_COLUMNS",
    "PARSER_VERSION",
    "enrich_ti",
    "normalize_stream",
    "parse_fit",
    "project_course_km",
    "read_parquet",
    "resolve_gpx_path",
    "write_meta_json",
    "write_parquet",
]
