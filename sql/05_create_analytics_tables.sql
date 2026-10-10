-- 05_create_analytics_tables.sql
-- Creates the analytics schema with a star schema:
--   - dim_date      : calendar dimension
--   - dim_location  : TLC taxi zone dimension
--   - dim_payment   : payment type dimension
--   - fact_trips    : one row per trip (the main fact table)

CREATE SCHEMA IF NOT EXISTS analytics;

-- ─────────────────────────────────────────────────────────────
-- dim_date
-- Stores one row per calendar date.
-- date_id is an integer in YYYYMMDD format (e.g. 20240115)
-- so joins are cheap integer comparisons.
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS analytics.dim_date (
    date_id         INTEGER     PRIMARY KEY,    -- YYYYMMDD
    full_date       DATE        NOT NULL,
    year            INTEGER     NOT NULL,
    month           INTEGER     NOT NULL,       -- 1-12
    day             INTEGER     NOT NULL,       -- 1-31
    day_of_week     INTEGER     NOT NULL,       -- 0=Monday, 6=Sunday
    week_of_year    INTEGER     NOT NULL,       -- 1-53
    is_weekend      BOOLEAN     NOT NULL,
    quarter         INTEGER     NOT NULL        -- 1-4
);

-- ─────────────────────────────────────────────────────────────
-- dim_location
-- One row per TLC LocationID (1-265).
-- Sourced from taxi_zone_lookup.csv.
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS analytics.dim_location (
    location_id     INTEGER     PRIMARY KEY,    -- TLC LocationID
    borough         VARCHAR(50),
    zone            VARCHAR(100),
    service_zone    VARCHAR(50)
);

-- ─────────────────────────────────────────────────────────────
-- dim_payment
-- Static lookup: maps payment_type integer to a human label.
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS analytics.dim_payment (
    payment_type_id INTEGER     PRIMARY KEY,
    payment_label   VARCHAR(50) NOT NULL
);

-- Seed the payment dimension with the known TLC codes.
-- INSERT … ON CONFLICT DO NOTHING makes this safe to re-run.
INSERT INTO analytics.dim_payment (payment_type_id, payment_label) VALUES
    (1, 'Credit card'),
    (2, 'Cash'),
    (3, 'No charge'),
    (4, 'Dispute'),
    (5, 'Unknown'),
    (6, 'Voided trip')
ON CONFLICT (payment_type_id) DO NOTHING;

-- ─────────────────────────────────────────────────────────────
-- fact_trips
-- One row per taxi trip. References all three dimensions.
-- Uses a BIGSERIAL surrogate key (trip_id) as the PK.
-- A natural composite unique key on (pickup_datetime, pu_location_id,
-- do_location_id, total_amount) is used for upserts.
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS analytics.fact_trips (
    trip_id                 BIGSERIAL   PRIMARY KEY,

    -- Timestamps (kept for direct time-range queries in BI tools)
    pickup_datetime         TIMESTAMP   NOT NULL,
    dropoff_datetime        TIMESTAMP   NOT NULL,

    -- Foreign keys to dimensions
    date_id                 INTEGER     REFERENCES analytics.dim_date(date_id),
    pu_location_id          INTEGER     REFERENCES analytics.dim_location(location_id),
    do_location_id          INTEGER     REFERENCES analytics.dim_location(location_id),
    payment_type_id         INTEGER     REFERENCES analytics.dim_payment(payment_type_id),

    -- Measures
    passenger_count         INTEGER,
    trip_distance           FLOAT,
    trip_duration_minutes   FLOAT,
    trip_speed_mph          FLOAT,
    fare_amount             FLOAT,
    tip_amount              FLOAT,
    total_amount            FLOAT,
    pickup_hour             INTEGER,    -- 0-23, stored for fast aggregation
    pickup_day_of_week      INTEGER,    -- 0=Monday, 6=Sunday

    -- Pipeline metadata
    data_month              DATE        NOT NULL,   -- first day of the processed month

    -- Natural key used for upserts (prevents exact duplicate trips)
    UNIQUE (pickup_datetime, pu_location_id, do_location_id, total_amount, data_month)
);

-- Indexes for common BI query patterns
CREATE INDEX IF NOT EXISTS idx_fact_date_id
    ON analytics.fact_trips (date_id);

CREATE INDEX IF NOT EXISTS idx_fact_data_month
    ON analytics.fact_trips (data_month);

CREATE INDEX IF NOT EXISTS idx_fact_pu_location
    ON analytics.fact_trips (pu_location_id);

CREATE INDEX IF NOT EXISTS idx_fact_pickup_hour
    ON analytics.fact_trips (pickup_hour);
