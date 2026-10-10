-- 04_create_staging_table.sql
-- Creates the staging schema and the yellow_taxi_clean table.
-- This table holds cleaned, typed, and enriched data — one row per trip.
-- It is logically partitioned by (pickup_year, pickup_month):
-- the pipeline DELETEs rows for the processed month then re-INSERTs,
-- making every run idempotent.

CREATE SCHEMA IF NOT EXISTS staging;

CREATE TABLE IF NOT EXISTS staging.yellow_taxi_clean (
    -- Original columns (cleaned and cast to correct types)
    vendor_id               INTEGER,
    pickup_datetime         TIMESTAMP       NOT NULL,
    dropoff_datetime        TIMESTAMP       NOT NULL,
    passenger_count         INTEGER,
    trip_distance           FLOAT           NOT NULL,
    ratecode_id             INTEGER,
    store_and_fwd_flag      VARCHAR(1),
    pu_location_id          INTEGER         NOT NULL,
    do_location_id          INTEGER         NOT NULL,
    payment_type            INTEGER,
    fare_amount             FLOAT,
    extra                   FLOAT,
    mta_tax                 FLOAT,
    tip_amount              FLOAT,
    tolls_amount            FLOAT,
    improvement_surcharge   FLOAT,
    total_amount            FLOAT           NOT NULL,
    congestion_surcharge    FLOAT,
    airport_fee             FLOAT,

    -- Derived columns added by transform.py (FR-T7)
    trip_duration_minutes   FLOAT,          -- dropoff - pickup in minutes
    trip_speed_mph          FLOAT,          -- distance / (duration / 60)
    pickup_hour             INTEGER,        -- 0-23
    pickup_day_of_week      INTEGER,        -- 0=Monday, 6=Sunday
    pickup_month            INTEGER,        -- 1-12
    pickup_year             INTEGER,        -- e.g. 2024

    -- Pipeline metadata
    data_month              DATE,           -- first day of the processed month
    ingested_at             TIMESTAMP DEFAULT NOW()
);

-- Index on the partition columns so DELETE + SELECT by month are fast
CREATE INDEX IF NOT EXISTS idx_staging_year_month
    ON staging.yellow_taxi_clean (pickup_year, pickup_month);

-- Index on location IDs for join performance when loading analytics
CREATE INDEX IF NOT EXISTS idx_staging_pu_location
    ON staging.yellow_taxi_clean (pu_location_id);

CREATE INDEX IF NOT EXISTS idx_staging_do_location
    ON staging.yellow_taxi_clean (do_location_id);
