# run_pipeline.py
# End-to-end orchestrator for the NYC TLC ETL pipeline.
#
# Usage:
#   python run_pipeline.py               # processes 2024-01 (default)
#   python run_pipeline.py 2024 3        # processes 2024-03
#
# Steps (in order):
#   1. Extract  — download Parquet + zone CSV from TLC CDN
#   2. Transform — clean, cast, derive columns; write to staging
#   3. Load      — upsert star schema (dims + fact_trips)
#   4. Quality checks — validate staging data; raise on failure
#
# The pipeline is idempotent: running it twice for the same month
# produces the same result without duplicates.

import sys
import logging

# Pull in all our pipeline modules
from src.extract import extract_trip_data, extract_zone_lookup
from src.transform import transform, load_to_staging
from src.load import load
from src.quality_checks import run_quality_checks, QualityCheckError

# Set up logging — all modules share this configuration via src/config.py,
# but we also configure the root logger here so run_pipeline.py output
# is formatted consistently.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


def run(year: int, month: int, sample_rows: int = 0) -> None:
    """
    Execute the full ETL pipeline for one month of NYC TLC data.

    Args:
        year        : 4-digit year to process (e.g. 2024).
        month       : Month to process (1-12).
        sample_rows : If > 0, only process this many rows (for testing).
    """
    logger.info("=" * 60)
    if sample_rows:
        logger.info("NYC TLC ETL Pipeline — SAMPLE MODE (%d rows) — %d-%02d",
                    sample_rows, year, month)
    else:
        logger.info("NYC TLC ETL Pipeline — starting for %d-%02d", year, month)
    logger.info("=" * 60)

    # ── Step 1: Extract ──────────────────────────────────────
    # Download the raw Parquet file and zone lookup CSV.
    # Both functions skip the download if the file already exists.
    logger.info("STEP 1/4 — Extract")
    parquet_path = extract_trip_data(year, month)
    extract_zone_lookup()

    # ── Step 2: Transform ────────────────────────────────────
    # Clean, cast, and enrich the raw data; load into staging.
    logger.info("STEP 2/4 — Transform")
    df = transform(parquet_path, year, month, sample_rows=sample_rows)
    load_to_staging(df, year, month)

    # ── Step 3: Quality Checks ───────────────────────────────
    # Validate staging data BEFORE loading analytics.
    # If any check fails, a QualityCheckError is raised and
    # the pipeline stops — analytics tables stay unchanged.
    logger.info("STEP 3/4 — Quality Checks")
    try:
        run_quality_checks(year, month)
    except QualityCheckError as e:
        logger.error("Quality check failed:\n%s", e)
        logger.error("Pipeline ABORTED — analytics tables were NOT updated.")
        sys.exit(1)

    # ── Step 4: Load Analytics ───────────────────────────────
    # Populate the star schema from staging data.
    logger.info("STEP 4/4 — Load Analytics")
    load(year, month)

    logger.info("=" * 60)
    logger.info("Pipeline COMPLETE for %d-%02d", year, month)
    logger.info("=" * 60)


if __name__ == "__main__":
    # Usage:
    #   python run_pipeline.py               → full run, 2024-01
    #   python run_pipeline.py 2024 1        → full run, 2024-01
    #   python run_pipeline.py 2024 1 50000  → sample run, first 50k rows
    _sample_rows = 0

    if len(sys.argv) >= 4:
        _sample_rows = int(sys.argv[3])

    if len(sys.argv) >= 3:
        try:
            _year  = int(sys.argv[1])
            _month = int(sys.argv[2])
        except ValueError:
            print("Usage: python run_pipeline.py <year> <month> [sample_rows]")
            sys.exit(1)
    else:
        _year, _month = 2024, 1
        logger.info("No year/month provided — defaulting to %d-%02d", _year, _month)

    run(_year, _month, sample_rows=_sample_rows)
