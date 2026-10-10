# src/load.py
# Reads from staging.yellow_taxi_clean and populates the analytics star schema.
#
# Load order matters because fact_trips has foreign keys to all three dims:
#   1. dim_date      (derived from pickup_datetime values in staging)
#   2. dim_location  (sourced from taxi_zone_lookup.csv)
#   3. dim_payment   (already seeded by the SQL file — still upserted here)
#   4. fact_trips    (references all three dims above)
#
# All loads use INSERT … ON CONFLICT DO NOTHING so running the pipeline
# twice is completely safe (FR-L3).

import logging
import pandas as pd
from sqlalchemy import create_engine, text
from src.config import DATABASE_URL, RAW_DATA_DIR
import os

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _get_engine():
    """Return a SQLAlchemy engine. Centralised so every function reuses it."""
    return create_engine(DATABASE_URL)


def _staging_data(engine, year: int, month: int) -> pd.DataFrame:
    """
    Load the cleaned rows for a specific month from staging.

    Args:
        engine : SQLAlchemy engine.
        year   : Processing year.
        month  : Processing month.

    Returns:
        DataFrame with all staging columns for that month.
    """
    query = text(
        "SELECT * FROM staging.yellow_taxi_clean "
        "WHERE pickup_year = :year AND pickup_month = :month"
    )
    df = pd.read_sql(query, con=engine, params={"year": year, "month": month})
    logger.info("Loaded %d rows from staging for %d-%02d.", len(df), year, month)
    return df


# ─────────────────────────────────────────────────────────────
# Step 1: dim_date
# ─────────────────────────────────────────────────────────────

def load_dim_date(df: pd.DataFrame, engine) -> None:
    """
    Build and upsert date dimension rows from the staging DataFrame (FR-L1).

    Each unique pickup date in the staging data becomes a row in dim_date.
    date_id is an integer in YYYYMMDD format — cheap for joins.

    Args:
        df     : Staging DataFrame.
        engine : SQLAlchemy engine.
    """
    # Extract unique dates from pickup_datetime
    dates = df["pickup_datetime"].dt.normalize().drop_duplicates()

    rows = []
    for d in dates:
        rows.append({
            "date_id":       int(d.strftime("%Y%m%d")),
            "full_date":     d.date(),
            "year":          d.year,
            "month":         d.month,
            "day":           d.day,
            "day_of_week":   d.dayofweek,        # 0=Monday
            "week_of_year":  d.isocalendar()[1],
            "is_weekend":    d.dayofweek >= 5,   # Saturday=5, Sunday=6
            "quarter":       (d.month - 1) // 3 + 1,
        })

    dim_df = pd.DataFrame(rows)

    # Upsert: insert rows that don't already exist
    with engine.begin() as conn:
        for _, row in dim_df.iterrows():
            # Convert numpy/pandas types to plain Python so SQLAlchemy is happy
            conn.execute(
                text("""
                    INSERT INTO analytics.dim_date
                        (date_id, full_date, year, month, day,
                         day_of_week, week_of_year, is_weekend, quarter)
                    VALUES
                        (:date_id, :full_date, :year, :month, :day,
                         :day_of_week, :week_of_year, :is_weekend, :quarter)
                    ON CONFLICT (date_id) DO NOTHING
                """),
                {k: (int(v) if hasattr(v, 'item') else v) for k, v in row.to_dict().items()},
            )

    logger.info("dim_date upserted %d date rows.", len(dim_df))


# ─────────────────────────────────────────────────────────────
# Step 2: dim_location
# ─────────────────────────────────────────────────────────────

def load_dim_location(engine) -> None:
    """
    Load taxi zone data from the local CSV into dim_location (FR-L1).

    The CSV was downloaded by extract.py and lives at data/raw/taxi_zone_lookup.csv.
    Uses INSERT … ON CONFLICT DO NOTHING so re-runs are safe.

    Args:
        engine : SQLAlchemy engine.
    """
    csv_path = os.path.join(RAW_DATA_DIR, "taxi_zone_lookup.csv")

    if not os.path.exists(csv_path):
        raise FileNotFoundError(
            f"Zone lookup CSV not found at {csv_path}. "
            "Run extract_zone_lookup() first."
        )

    zones = pd.read_csv(csv_path)

    # Normalise column names (the CSV uses PascalCase)
    zones = zones.rename(columns={
        "LocationID":   "location_id",
        "Borough":      "borough",
        "Zone":         "zone",
        "service_zone": "service_zone",
    })

    # Keep only the columns we need
    zones = zones[["location_id", "borough", "zone", "service_zone"]]

    with engine.begin() as conn:
        for _, row in zones.iterrows():
            conn.execute(
                text("""
                    INSERT INTO analytics.dim_location
                        (location_id, borough, zone, service_zone)
                    VALUES
                        (:location_id, :borough, :zone, :service_zone)
                    ON CONFLICT (location_id) DO NOTHING
                """),
                row.to_dict(),
            )

    logger.info("dim_location upserted %d location rows.", len(zones))


# ─────────────────────────────────────────────────────────────
# Step 3: dim_payment
# ─────────────────────────────────────────────────────────────

def load_dim_payment(engine) -> None:
    """
    Upsert static payment type labels into dim_payment (FR-L1).

    The SQL file already seeded these rows on table creation,
    but we re-upsert here so this step is always idempotent even
    if the table was recreated.

    Args:
        engine : SQLAlchemy engine.
    """
    payment_types = [
        (1, "Credit card"),
        (2, "Cash"),
        (3, "No charge"),
        (4, "Dispute"),
        (5, "Unknown"),
        (6, "Voided trip"),
    ]

    with engine.begin() as conn:
        for pid, label in payment_types:
            conn.execute(
                text("""
                    INSERT INTO analytics.dim_payment (payment_type_id, payment_label)
                    VALUES (:payment_type_id, :payment_label)
                    ON CONFLICT (payment_type_id) DO NOTHING
                """),
                {"payment_type_id": pid, "payment_label": label},
            )

    logger.info("dim_payment upserted %d payment type rows.", len(payment_types))


# ─────────────────────────────────────────────────────────────
# Step 4: fact_trips
# ─────────────────────────────────────────────────────────────

def load_fact_trips(df: pd.DataFrame, year: int, month: int, engine) -> None:
    """
    Load trip facts into analytics.fact_trips (FR-L2).

    Strategy:
      - DELETE all fact rows for this month first (by data_month).
      - Bulk INSERT the new rows.
    This is simpler and faster than row-level upserts for a fact table
    that can have millions of rows.

    Args:
        df     : Staging DataFrame for the month.
        year   : Processing year.
        month  : Processing month.
        engine : SQLAlchemy engine.
    """
    import datetime

    # Build the date_id (YYYYMMDD integer) for each row
    df["date_id"] = df["pickup_datetime"].dt.strftime("%Y%m%d").astype(int)

    # Select only the columns fact_trips needs
    fact_cols = [
        "pickup_datetime", "dropoff_datetime",
        "date_id", "pu_location_id", "do_location_id", "payment_type",
        "passenger_count", "trip_distance", "trip_duration_minutes",
        "trip_speed_mph", "fare_amount", "tip_amount", "total_amount",
        "pickup_hour", "pickup_day_of_week", "data_month",
    ]

    # Only keep columns that exist in the DataFrame
    fact_cols = [c for c in fact_cols if c in df.columns]
    fact_df = df[fact_cols].copy()

    # Rename payment_type → payment_type_id to match the fact table schema
    if "payment_type" in fact_df.columns:
        fact_df = fact_df.rename(columns={"payment_type": "payment_type_id"})

    # Convert ALL nullable pandas types to plain Python-native types.
    # SQLAlchemy 2.x cannot handle pandas Int64 / boolean NA values directly.
    # We convert:
    #   Int64  → float64  (float is NaN-safe; postgres casts it to int correctly)
    #   object → str      (safety net for any stray object columns)
    for col in fact_df.columns:
        dtype = fact_df[col].dtype
        if hasattr(dtype, "numpy_dtype"):
            # This catches pandas ExtensionDtype like Int64, boolean etc.
            fact_df[col] = fact_df[col].astype("float64")
        elif fact_df[col].dtype == object:
            fact_df[col] = fact_df[col].astype(str)

    data_month = datetime.date(year, month, 1)

    with engine.begin() as conn:
        logger.info("Deleting existing fact rows for %d-%02d...", year, month)
        conn.execute(
            text("DELETE FROM analytics.fact_trips WHERE data_month = :data_month"),
            {"data_month": data_month},
        )

    logger.info("Inserting %d fact rows for %d-%02d...", len(fact_df), year, month)
    with engine.begin() as conn:
        for i in range(0, len(fact_df), 5000):
            chunk = fact_df.iloc[i:i+5000]
            chunk.to_sql(
                name="_fact_trips_temp",
                schema="analytics",
                con=conn,
                if_exists="replace",
                index=False,
            )
            conn.execute(text("""
                INSERT INTO analytics.fact_trips
                    (pickup_datetime, dropoff_datetime, date_id,
                    pu_location_id, do_location_id, payment_type_id,
                    passenger_count, trip_distance, trip_duration_minutes,
                    trip_speed_mph, fare_amount, tip_amount, total_amount,
                    pickup_hour, pickup_day_of_week, data_month)
                SELECT pickup_datetime, dropoff_datetime, date_id,
                    pu_location_id, do_location_id, payment_type_id,
                    passenger_count, trip_distance, trip_duration_minutes,
                    trip_speed_mph, fare_amount, tip_amount, total_amount,
                    pickup_hour, pickup_day_of_week, data_month::date
                FROM analytics._fact_trips_temp
                ON CONFLICT DO NOTHING
            """))
            logger.info("Inserted chunk %d/%d", min(i + 5000, len(fact_df)), len(fact_df))
        conn.execute(text("DROP TABLE IF EXISTS analytics._fact_trips_temp"))
    logger.info("fact_trips load complete for %d-%02d.", year, month)


# ─────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────

def load(year: int, month: int) -> None:
    """
    Run the full analytics load for a given month.

    Order:
        1. dim_date      (no external deps)
        2. dim_location  (reads CSV)
        3. dim_payment   (static data)
        4. fact_trips    (depends on all three dims existing)

    Args:
        year  : Year being processed.
        month : Month being processed (1-12).
    """
    engine = _get_engine()

    # Pull staging data once; pass it to the functions that need it
    df = _staging_data(engine, year, month)

    if df.empty:
        raise ValueError(
            f"No staging data found for {year}-{month:02d}. "
            "Run the transform step first."
        )

    logger.info("Starting analytics load for %d-%02d...", year, month)

    load_dim_date(df, engine)
    load_dim_location(engine)
    load_dim_payment(engine)
    load_fact_trips(df, year, month, engine)

    logger.info("Analytics load complete for %d-%02d.", year, month)
