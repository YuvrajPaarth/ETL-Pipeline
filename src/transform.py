# src/transform.py
# Reads raw Parquet data, cleans it, adds derived columns,
# and writes the result into staging.yellow_taxi_clean.
#
# Each function does one job so the code stays easy to read and test.
# All cleaning rules come from FR-T2 through FR-T8 in requirements.md.

import logging
import pandas as pd
from sqlalchemy import create_engine, text
from src.config import DATABASE_URL, CHUNK_SIZE

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Column name mapping
# TLC Parquet files use PascalCase; we standardise to snake_case.
# ─────────────────────────────────────────────────────────────
COLUMN_RENAME_MAP = {
    "VendorID":                 "vendor_id",
    "tpep_pickup_datetime":     "pickup_datetime",
    "tpep_dropoff_datetime":    "dropoff_datetime",
    "passenger_count":          "passenger_count",
    "trip_distance":            "trip_distance",
    "RatecodeID":               "ratecode_id",
    "store_and_fwd_flag":       "store_and_fwd_flag",
    "PULocationID":             "pu_location_id",
    "DOLocationID":             "do_location_id",
    "payment_type":             "payment_type",
    "fare_amount":              "fare_amount",
    "extra":                    "extra",
    "mta_tax":                  "mta_tax",
    "tip_amount":               "tip_amount",
    "tolls_amount":             "tolls_amount",
    "improvement_surcharge":    "improvement_surcharge",
    "total_amount":             "total_amount",
    "congestion_surcharge":     "congestion_surcharge",
    "Airport_fee":              "airport_fee",
    "airport_fee":              "airport_fee",   # handle both casings
}


def rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rename raw Parquet columns to snake_case.
    Unknown columns are left as-is (we don't drop them — just log a warning).

    Args:
        df: Raw DataFrame from the Parquet file.

    Returns:
        DataFrame with standardised column names (FR-T6).
    """
    # Only rename columns that exist in our map; ignore extras
    existing = {k: v for k, v in COLUMN_RENAME_MAP.items() if k in df.columns}
    df = df.rename(columns=existing)

    unknown = [c for c in df.columns if c not in COLUMN_RENAME_MAP.values()]
    if unknown:
        logger.warning("Unknown columns found (will be dropped): %s", unknown)
        df = df.drop(columns=unknown)

    logger.info("Columns after rename: %s", list(df.columns))
    return df


def cast_types(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cast every column to its correct data type (FR-T5).
    Uses pandas nullable integer type (Int64) so NaN values don't
    force floats for integer columns.

    Args:
        df: DataFrame after column rename.

    Returns:
        DataFrame with correct dtypes.
    """
    # Datetime columns
    for col in ("pickup_datetime", "dropoff_datetime"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    # Nullable integer columns (Int64 with capital I supports NaN)
    int_cols = [
        "vendor_id", "passenger_count", "ratecode_id",
        "pu_location_id", "do_location_id", "payment_type",
    ]
    for col in int_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    # Float columns
    float_cols = [
        "trip_distance", "fare_amount", "extra", "mta_tax",
        "tip_amount", "tolls_amount", "improvement_surcharge",
        "total_amount", "congestion_surcharge", "airport_fee",
    ]
    for col in float_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")

    logger.info("Column types cast successfully.")
    return df


def drop_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove exact duplicate rows (FR-T2).

    Args:
        df: DataFrame after type casting.

    Returns:
        DataFrame with duplicates removed.
    """
    before = len(df)
    df = df.drop_duplicates()
    dropped = before - len(df)
    if dropped:
        logger.info("Dropped %d duplicate rows.", dropped)
    return df


def drop_invalid_rows(df: pd.DataFrame) -> pd.DataFrame:
    """
    Drop rows that fail basic validity rules (FR-T3, FR-T4):
      - pickup_datetime or dropoff_datetime is null
      - trip_distance <= 0
      - total_amount <= 0

    Args:
        df: DataFrame after duplicate removal.

    Returns:
        DataFrame with invalid rows removed.
    """
    before = len(df)

    # FR-T3: drop null datetimes
    df = df.dropna(subset=["pickup_datetime", "dropoff_datetime"])

    # FR-T4: drop non-positive distance and fare
    df = df[df["trip_distance"] > 0]
    df = df[df["total_amount"] > 0]

    dropped = before - len(df)
    logger.info("Dropped %d invalid rows (null datetimes / zero distance / zero fare).", dropped)
    return df


def add_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add derived columns for analytics (FR-T7):
      - trip_duration_minutes : how long the trip took
      - trip_speed_mph        : average speed (safe divide by near-zero)
      - pickup_hour           : hour of day (0-23)
      - pickup_day_of_week    : day of week (0=Monday, 6=Sunday)
      - pickup_month          : month number (1-12)
      - pickup_year           : 4-digit year

    Args:
        df: DataFrame after cleaning.

    Returns:
        DataFrame with six new columns appended.
    """
    # Duration: convert timedelta to total minutes
    duration = (df["dropoff_datetime"] - df["pickup_datetime"]).dt.total_seconds() / 60.0
    df["trip_duration_minutes"] = duration.round(2)

    # Speed: miles per hour — avoid division by zero by using a minimum duration
    # Any trip under 0.1 min gets speed=0 to avoid nonsensical values
    safe_duration_hours = duration.clip(lower=0.1) / 60.0
    df["trip_speed_mph"] = (df["trip_distance"] / safe_duration_hours).round(2)

    # Calendar breakdowns from pickup_datetime
    df["pickup_hour"]        = df["pickup_datetime"].dt.hour
    df["pickup_day_of_week"] = df["pickup_datetime"].dt.dayofweek   # 0=Monday
    df["pickup_month"]       = df["pickup_datetime"].dt.month
    df["pickup_year"]        = df["pickup_datetime"].dt.year

    logger.info("Derived columns added: trip_duration_minutes, trip_speed_mph, "
                "pickup_hour, pickup_day_of_week, pickup_month, pickup_year.")
    return df


def drop_duration_outliers(df: pd.DataFrame) -> pd.DataFrame:
    """
    Drop trips with unrealistic durations (FR-Q3 enforced at source).

    Why here and not in quality_checks.py?
    Quality checks are a safety net — they should confirm clean data,
    not fix it. Filtering bad rows is transform's job.

    Valid range: 1 minute ≤ trip_duration_minutes ≤ 300 minutes.
      - Under 1 min : GPS glitch, cancelled trip, meter error
      - Over 300 min: meter left running, data entry error

    Args:
        df: DataFrame after add_derived_columns() has run.

    Returns:
        DataFrame with duration outliers removed.
    """
    before = len(df)
    df = df[df["trip_duration_minutes"].between(1, 300)]
    dropped = before - len(df)
    if dropped:
        logger.info("Dropped %d rows with trip_duration_minutes outside [1, 300].", dropped)
    return df


def add_metadata(df: pd.DataFrame, year: int, month: int) -> pd.DataFrame:
    """
    Append pipeline metadata columns to every row.

    Args:
        df    : Cleaned DataFrame.
        year  : Processing year.
        month : Processing month.

    Returns:
        DataFrame with data_month and ingested_at columns.
    """
    import datetime
    df["data_month"]  = pd.Timestamp(year=year, month=month, day=1).date()
    df["ingested_at"] = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    return df


def transform(parquet_path: str, year: int, month: int, sample_rows: int = 0) -> pd.DataFrame:
    """
    Run the full transform pipeline on a raw Parquet file.

    Steps:
        1. Load Parquet into a DataFrame
        2. Rename columns to snake_case
        3. Cast to correct types
        4. Drop duplicates
        5. Drop invalid rows
        6. Add derived columns
        7. Add pipeline metadata

    Args:
        parquet_path : Local path to the raw .parquet file.
        year         : Year being processed (e.g. 2024).
        month        : Month being processed (1-12).

    Returns:
        Cleaned DataFrame ready to be written to staging.
    """
    logger.info("Loading Parquet file: %s", parquet_path)
    df = pd.read_parquet(parquet_path)
    logger.info("Raw row count: %d", len(df))

    # Sample mode: take only the first N rows for testing the pipeline quickly
    if sample_rows:
        df = df.head(sample_rows)
        logger.info("SAMPLE MODE: using first %d rows only.", sample_rows)

    df = rename_columns(df)
    df = cast_types(df)
    df = drop_duplicates(df)
    df = drop_invalid_rows(df)
    df = add_derived_columns(df)
    df = drop_duration_outliers(df)   # drop after duration is calculated
    df = add_metadata(df, year, month)

    logger.info("Transform complete. Clean row count: %d", len(df))
    return df


def load_to_staging(df: pd.DataFrame, year: int, month: int) -> None:
    """
    Write the cleaned DataFrame into staging.yellow_taxi_clean (FR-T8).

    Strategy: DELETE rows for this month first, then INSERT fresh rows.
    This makes the step idempotent — running it twice gives the same result.

    Args:
        df    : Cleaned DataFrame from transform().
        year  : Year being processed.
        month : Month being processed.
    """
    engine = create_engine(DATABASE_URL)

    with engine.begin() as conn:
        # Delete existing rows for this month so we can re-insert cleanly
        logger.info("Deleting existing staging rows for %d-%02d...", year, month)
        conn.execute(
            text(
                "DELETE FROM staging.yellow_taxi_clean "
                "WHERE pickup_year = :year AND pickup_month = :month"
            ),
            {"year": year, "month": month},
        )

    # Write in chunks to avoid memory spikes on large DataFrames
    # if_exists='append' because the table already exists (created by SQL file)
    logger.info("Inserting %d rows into staging.yellow_taxi_clean...", len(df))
    df.to_sql(
        name="yellow_taxi_clean",
        schema="staging",
        con=engine,
        if_exists="append",
        index=False,
        chunksize=CHUNK_SIZE,
    )
    logger.info("Staging load complete for %d-%02d.", year, month)
