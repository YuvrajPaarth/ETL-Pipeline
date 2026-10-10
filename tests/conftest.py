# tests/conftest.py
# Shared pytest fixtures used by all test files.
#
# conftest.py is automatically loaded by pytest — no imports needed
# in test files. Any fixture defined here is available everywhere.

import pytest
import pandas as pd


@pytest.fixture
def raw_df():
    """
    A small DataFrame that mimics a raw TLC Parquet file.
    Uses the original PascalCase column names exactly as TLC publishes them.
    Contains a mix of valid rows, duplicates, and invalid rows so we can
    test every cleaning function.
    """
    return pd.DataFrame({
        "VendorID":              [1,    1,    2,    2,    1   ],
        "tpep_pickup_datetime":  [
            "2024-01-15 08:00:00",  # valid
            "2024-01-15 08:00:00",  # duplicate of row 0
            "2024-01-15 09:30:00",  # valid
            None,                   # null datetime — should be dropped (FR-T3)
            "2024-01-15 11:00:00",  # valid
        ],
        "tpep_dropoff_datetime": [
            "2024-01-15 08:25:00",  # 25 min trip
            "2024-01-15 08:25:00",  # duplicate
            "2024-01-15 10:00:00",  # 90 min trip
            "2024-01-15 12:00:00",  # will be dropped (pickup is null)
            "2024-01-15 11:10:00",  # 10 min trip
        ],
        "passenger_count":       [1,    1,    2,    3,    1   ],
        "trip_distance":         [2.5,  2.5,  5.0, -1.0,  1.2 ],  # row 3 invalid (FR-T4)
        "RatecodeID":            [1,    1,    1,    1,    1   ],
        "store_and_fwd_flag":    ["N",  "N",  "Y",  "N",  "N" ],
        "PULocationID":          [161,  161,  230,  142,  79  ],
        "DOLocationID":          [236,  236,  100,  150,  80  ],
        "payment_type":          [1,    1,    2,    1,    1   ],
        "fare_amount":           [10.0, 10.0, 20.0, 8.0,  5.0],
        "extra":                 [0.5,  0.5,  0.0,  0.5,  0.5],
        "mta_tax":               [0.5,  0.5,  0.5,  0.5,  0.5],
        "tip_amount":            [2.0,  2.0,  4.0,  0.0,  1.0],
        "tolls_amount":          [0.0,  0.0,  0.0,  0.0,  0.0],
        "improvement_surcharge": [0.3,  0.3,  0.3,  0.3,  0.3],
        "total_amount":          [13.3, 13.3, 24.8, 0.0,  7.3],  # row 3 invalid (FR-T4)
        "congestion_surcharge":  [2.5,  2.5,  0.0,  2.5,  2.5],
        "Airport_fee":           [0.0,  0.0,  0.0,  0.0,  0.0],
    })


@pytest.fixture
def clean_df(raw_df):
    """
    A pre-cleaned DataFrame (after rename + cast + drop steps).
    Used by tests that only need to verify derived columns or metadata.
    """
    from src.transform import rename_columns, cast_types, drop_duplicates, drop_invalid_rows
    df = rename_columns(raw_df.copy())
    df = cast_types(df)
    df = drop_duplicates(df)
    df = drop_invalid_rows(df)
    return df
