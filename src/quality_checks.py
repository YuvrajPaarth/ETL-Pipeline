# src/quality_checks.py
# Runs four data quality checks against staging.yellow_taxi_clean
# after the transform step and before the analytics load.
#
# If ANY check fails, a QualityCheckError is raised immediately.
# This stops the pipeline so bad data never reaches the analytics tables.
#
# Checks (from FR-Q1 through FR-Q5):
#   1. Row count  — staging must have > 0 rows for this month
#   2. Null check — critical columns must have zero nulls
#   3. Range check — trip_duration_minutes must be between 1 and 300
#   4. Schema check — all expected columns must exist in staging

import logging
from sqlalchemy import create_engine, text
from src.config import DATABASE_URL

logger = logging.getLogger(__name__)


class QualityCheckError(Exception):
    """
    Raised when a data quality check fails.
    Inherits from Exception so callers can catch it specifically.
    """
    pass


# Columns that must never be null in staging (FR-Q2)
CRITICAL_COLUMNS = [
    "pickup_datetime",
    "dropoff_datetime",
    "total_amount",
    "pu_location_id",
    "do_location_id",
]

# All columns the pipeline expects to find in staging (FR-Q4)
EXPECTED_COLUMNS = [
    "vendor_id", "pickup_datetime", "dropoff_datetime",
    "passenger_count", "trip_distance", "ratecode_id",
    "store_and_fwd_flag", "pu_location_id", "do_location_id",
    "payment_type", "fare_amount", "extra", "mta_tax",
    "tip_amount", "tolls_amount", "improvement_surcharge",
    "total_amount", "congestion_surcharge", "airport_fee",
    "trip_duration_minutes", "trip_speed_mph",
    "pickup_hour", "pickup_day_of_week", "pickup_month", "pickup_year",
    "data_month", "ingested_at",
]


def _get_engine():
    """Return a SQLAlchemy engine."""
    return create_engine(DATABASE_URL)


# ─────────────────────────────────────────────────────────────
# Check 1: Row count
# ─────────────────────────────────────────────────────────────

def check_row_count(year: int, month: int, engine) -> None:
    """
    Verify that staging has at least one row for the given month (FR-Q1).

    Args:
        year   : Processing year.
        month  : Processing month.
        engine : SQLAlchemy engine.

    Raises:
        QualityCheckError: If row count is 0.
    """
    result = engine.execute if False else None  # avoid lint warning

    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT COUNT(*) FROM staging.yellow_taxi_clean "
                "WHERE pickup_year = :year AND pickup_month = :month"
            ),
            {"year": year, "month": month},
        ).fetchone()

    count = row[0]
    if count == 0:
        raise QualityCheckError(
            f"[Row Count] FAILED — 0 rows found in staging for {year}-{month:02d}. "
            "The transform step may not have run."
        )

    logger.info("[Row Count] PASSED — %d rows found for %d-%02d.", count, year, month)


# ─────────────────────────────────────────────────────────────
# Check 2: Null check on critical columns
# ─────────────────────────────────────────────────────────────

def check_nulls(year: int, month: int, engine) -> None:
    """
    Verify that critical columns contain zero NULL values (FR-Q2).

    Checks: pickup_datetime, dropoff_datetime, total_amount,
            pu_location_id, do_location_id.

    Args:
        year   : Processing year.
        month  : Processing month.
        engine : SQLAlchemy engine.

    Raises:
        QualityCheckError: If any critical column has nulls.
    """
    failures = []

    with engine.connect() as conn:
        for col in CRITICAL_COLUMNS:
            row = conn.execute(
                text(
                    f"SELECT COUNT(*) FROM staging.yellow_taxi_clean "
                    f"WHERE pickup_year = :year AND pickup_month = :month "
                    f"AND {col} IS NULL"
                ),
                {"year": year, "month": month},
            ).fetchone()

            null_count = row[0]
            if null_count > 0:
                failures.append(f"  - {col}: {null_count} nulls")
                logger.warning("[Null Check] Column '%s' has %d nulls.", col, null_count)
            else:
                logger.info("[Null Check] Column '%s' — no nulls. OK.", col)

    if failures:
        raise QualityCheckError(
            f"[Null Check] FAILED — nulls found in critical columns:\n"
            + "\n".join(failures)
        )

    logger.info("[Null Check] PASSED — all critical columns are null-free.")


# ─────────────────────────────────────────────────────────────
# Check 3: Range check on trip_duration_minutes
# ─────────────────────────────────────────────────────────────

def check_ranges(year: int, month: int, engine) -> None:
    """
    Verify trip_duration_minutes is between 1 and 300 for all rows (FR-Q3).

    Trips under 1 minute are likely GPS glitches or data entry errors.
    Trips over 300 minutes (5 hours) are suspicious outliers.

    Args:
        year   : Processing year.
        month  : Processing month.
        engine : SQLAlchemy engine.

    Raises:
        QualityCheckError: If any row falls outside the valid range.
    """
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT COUNT(*) FROM staging.yellow_taxi_clean "
                "WHERE pickup_year = :year AND pickup_month = :month "
                "AND (trip_duration_minutes < 1 OR trip_duration_minutes > 300)"
            ),
            {"year": year, "month": month},
        ).fetchone()

    out_of_range = row[0]
    if out_of_range > 0:
        raise QualityCheckError(
            f"[Range Check] FAILED — {out_of_range} rows have "
            f"trip_duration_minutes outside [1, 300] for {year}-{month:02d}."
        )

    logger.info("[Range Check] PASSED — all trip durations are within [1, 300] minutes.")


# ─────────────────────────────────────────────────────────────
# Check 4: Schema check
# ─────────────────────────────────────────────────────────────

def check_schema(engine) -> None:
    """
    Verify that all expected columns exist in staging.yellow_taxi_clean (FR-Q4).

    Queries the PostgreSQL information_schema — no data scan needed.

    Args:
        engine : SQLAlchemy engine.

    Raises:
        QualityCheckError: If any expected column is missing.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'staging' "
                "AND table_name = 'yellow_taxi_clean'"
            )
        ).fetchall()

    actual_columns = {row[0] for row in rows}
    missing = [c for c in EXPECTED_COLUMNS if c not in actual_columns]

    if missing:
        raise QualityCheckError(
            f"[Schema Check] FAILED — missing columns in staging.yellow_taxi_clean: "
            f"{missing}"
        )

    logger.info("[Schema Check] PASSED — all %d expected columns present.", len(EXPECTED_COLUMNS))


# ─────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────

def run_quality_checks(year: int, month: int) -> None:
    """
    Run all four quality checks in order (FR-Q1 through FR-Q5).

    Stops at the first failure and raises QualityCheckError.
    If all checks pass, logs a summary and returns normally.

    Args:
        year  : Year being validated.
        month : Month being validated (1-12).

    Raises:
        QualityCheckError: If any check fails.
    """
    logger.info("Running quality checks for %d-%02d...", year, month)
    engine = _get_engine()

    # Each check raises QualityCheckError on failure — stops the pipeline (FR-Q5)
    check_schema(engine)
    check_row_count(year, month, engine)
    check_nulls(year, month, engine)
    check_ranges(year, month, engine)

    logger.info("All quality checks PASSED for %d-%02d.", year, month)
