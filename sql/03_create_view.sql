CREATE OR REPLACE VIEW raw.v_trips AS
SELECT
    t.vendor_id,
    t.pickup_datetime,
    t.dropoff_datetime,
    t.passenger_count,
    t.trip_distance,
    t.pu_location_id,
    t.do_location_id,
    t.fare_amount,
    t.tip_amount,
    t.total_amount,
    t.congestion_surcharge,
    t.data_month,

    -- Human-readable pickup zone
    pu.zone        AS pu_zone,
    pu.borough     AS pu_borough,

    -- Human-readable dropoff zone
    do_.zone       AS do_zone,
    do_.borough    AS do_borough,

    -- Decode payment type integer to label
    CASE t.payment_type::INTEGER
        WHEN 1 THEN 'Credit card'
        WHEN 2 THEN 'Cash'
        WHEN 3 THEN 'No charge'
        WHEN 4 THEN 'Dispute'
        WHEN 5 THEN 'Unknown'
        WHEN 6 THEN 'Voided trip'
        ELSE 'Other'
    END AS payment_label,

    -- Trip duration in minutes
    ROUND(
        EXTRACT(EPOCH FROM (t.dropoff_datetime -
t.pickup_datetime)) / 60.0
    , 2) AS trip_duration_minutes

FROM raw.yellow_taxi_raw t
LEFT JOIN raw.taxi_zone_lookup pu
    ON t.pu_location_id = pu.location_id
LEFT JOIN raw.taxi_zone_lookup do_
    ON t.do_location_id = do_.location_id;
