CREATE TABLE IF NOT EXISTS raw.yellow_taxi_raw (
    vendor_id             INTEGER,
    pickup_datetime       TIMESTAMP,
    dropoff_datetime      TIMESTAMP,
    passenger_count       FLOAT,
    trip_distance         FLOAT,
    ratecode_id           FLOAT,
    pu_location_id        INTEGER,
    do_location_id        INTEGER,
    payment_type          FLOAT,
    fare_amount           FLOAT,
    tip_amount            FLOAT,
    total_amount          FLOAT,
    congestion_surcharge  FLOAT,
    data_month            DATE,        -- which month this row belongs to
    ingested_at           TIMESTAMP    -- when our pipeline inserted this row
);

CREATE TABLE IF NOT EXISTS raw.taxi_zone_lookup (
    location_id   INTEGER PRIMARY KEY,
    borough       VARCHAR(50),
    zone          VARCHAR(100),
    service_zone  VARCHAR(50)
);