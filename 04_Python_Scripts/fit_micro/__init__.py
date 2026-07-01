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

try:
    from fit_micro.effort_paradox import compute_paradox_metrics, run_corridor_paradox_scan
except ImportError:  # optional — not shipped in all cloud workspaces

    def compute_paradox_metrics(*args: object, **kwargs: object):  # type: ignore[misc]
        raise ImportError(
            "fit_micro.effort_paradox is unavailable in this workspace; "
            "install or restore the module for Effort Paradox metrics."
        )

    def run_corridor_paradox_scan(*args: object, **kwargs: object):  # type: ignore[misc]
        raise ImportError(
            "fit_micro.effort_paradox is unavailable in this workspace; "
            "install or restore the module for corridor paradox scans."
        )

__all__ = [
    "compute_paradox_metrics",
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
    "run_corridor_paradox_scan",
]
