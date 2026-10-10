# tests/test_transform.py
# Unit tests for every helper function in src/transform.py.
#
# Run with:
#   pytest tests/ -v
#
# Each test function:
#   - Has a clear name describing what it verifies
#   - Uses fixtures from conftest.py
#   - Tests one behaviour at a time (small, focused assertions)

import pytest
import pandas as pd
import numpy as np
from src.transform import (
    rename_columns,
    cast_types,
    drop_duplicates,
    drop_invalid_rows,
    add_derived_columns,
    add_metadata,
)


# ─────────────────────────────────────────────────────────────
# rename_columns
# ─────────────────────────────────────────────────────────────

class TestRenameColumns:

    def test_pascalcase_columns_are_renamed(self, raw_df):
        """VendorID, PULocationID, DOLocationID etc. become snake_case."""
        df = rename_columns(raw_df.copy())
        assert "vendor_id"      in df.columns
        assert "pu_location_id" in df.columns
        assert "do_location_id" in df.columns
        assert "VendorID"       not in df.columns

    def test_datetime_columns_renamed(self, raw_df):
        """tpep_pickup_datetime → pickup_datetime."""
        df = rename_columns(raw_df.copy())
        assert "pickup_datetime"  in df.columns
        assert "dropoff_datetime" in df.columns

    def test_airport_fee_normalised(self, raw_df):
        """Airport_fee (capital A) is renamed to airport_fee."""
        df = rename_columns(raw_df.copy())
        assert "airport_fee" in df.columns
        assert "Airport_fee" not in df.columns

    def test_no_extra_columns(self, raw_df):
        """After rename, no original PascalCase column names remain."""
        df = rename_columns(raw_df.copy())
        pascal_columns = [c for c in df.columns if any(ch.isupper() for ch in c[1:])]
        # store_and_fwd_flag is all lowercase — only flag is unexpected caps
        assert pascal_columns == [], f"Unexpected uppercase columns: {pascal_columns}"


# ─────────────────────────────────────────────────────────────
# cast_types
# ─────────────────────────────────────────────────────────────

class TestCastTypes:

    def test_datetimes_are_timestamp(self, raw_df):
        """pickup_datetime and dropoff_datetime become datetime64."""
        df = rename_columns(raw_df.copy())
        df = cast_types(df)
        assert pd.api.types.is_datetime64_any_dtype(df["pickup_datetime"])
        assert pd.api.types.is_datetime64_any_dtype(df["dropoff_datetime"])

    def test_integer_columns_are_Int64(self, raw_df):
        """vendor_id, passenger_count etc. become nullable Int64."""
        df = rename_columns(raw_df.copy())
        df = cast_types(df)
        assert df["vendor_id"].dtype.name      == "Int64"
        assert df["passenger_count"].dtype.name == "Int64"
        assert df["pu_location_id"].dtype.name  == "Int64"

    def test_float_columns_are_float64(self, raw_df):
        """trip_distance, fare_amount etc. become float64."""
        df = rename_columns(raw_df.copy())
        df = cast_types(df)
        assert df["trip_distance"].dtype == np.float64
        assert df["fare_amount"].dtype   == np.float64
        assert df["total_amount"].dtype  == np.float64

    def test_null_datetime_becomes_nat(self, raw_df):
        """A null pickup_datetime string should become NaT after casting."""
        df = rename_columns(raw_df.copy())
        df = cast_types(df)
        # Row 3 has None as pickup_datetime
        assert pd.isna(df.loc[3, "pickup_datetime"])


# ─────────────────────────────────────────────────────────────
# drop_duplicates
# ─────────────────────────────────────────────────────────────

class TestDropDuplicates:

    def test_exact_duplicate_removed(self, raw_df):
        """Row 1 is an exact copy of row 0 — only one should remain."""
        df = rename_columns(raw_df.copy())
        df = cast_types(df)
        before = len(df)
        df = drop_duplicates(df)
        assert len(df) == before - 1

    def test_non_duplicate_rows_kept(self, raw_df):
        """Rows that are not duplicates should all be kept."""
        df = rename_columns(raw_df.copy())
        df = cast_types(df)
        df = drop_duplicates(df)
        # We started with 5 rows, 1 duplicate → should have 4
        assert len(df) == 4


# ─────────────────────────────────────────────────────────────
# drop_invalid_rows
# ─────────────────────────────────────────────────────────────

class TestDropInvalidRows:

    def test_null_pickup_datetime_dropped(self, raw_df):
        """Row with null pickup_datetime should be removed (FR-T3)."""
        df = rename_columns(raw_df.copy())
        df = cast_types(df)
        df = drop_duplicates(df)
        df = drop_invalid_rows(df)
        # No NaT values should remain in pickup_datetime
        assert df["pickup_datetime"].isna().sum() == 0

    def test_zero_total_amount_dropped(self, raw_df):
        """Row with total_amount = 0 should be removed (FR-T4)."""
        df = rename_columns(raw_df.copy())
        df = cast_types(df)
        df = drop_duplicates(df)
        df = drop_invalid_rows(df)
        assert (df["total_amount"] <= 0).sum() == 0

    def test_negative_trip_distance_dropped(self, raw_df):
        """Row with trip_distance = -1 should be removed (FR-T4)."""
        df = rename_columns(raw_df.copy())
        df = cast_types(df)
        df = drop_duplicates(df)
        df = drop_invalid_rows(df)
        assert (df["trip_distance"] <= 0).sum() == 0

    def test_valid_rows_remain(self, raw_df):
        """After dropping invalids, 3 valid rows should remain."""
        # Start: 5 rows
        # Drop duplicate row 1:          → 4 rows
        # Drop null pickup (row 3):       → 3 rows
        # Drop zero/negative (row 3 was already dropped above,
        #   but it also had trip_distance=-1 and total_amount=0)
        df = rename_columns(raw_df.copy())
        df = cast_types(df)
        df = drop_duplicates(df)
        df = drop_invalid_rows(df)
        assert len(df) == 3


# ─────────────────────────────────────────────────────────────
# add_derived_columns
# ─────────────────────────────────────────────────────────────

class TestAddDerivedColumns:

    def test_trip_duration_minutes_correct(self, clean_df):
        """25-minute trip should have trip_duration_minutes ≈ 25."""
        df = add_derived_columns(clean_df.copy())
        # Row 0: 08:00 → 08:25 = 25 minutes
        assert abs(df.iloc[0]["trip_duration_minutes"] - 25.0) < 0.1

    def test_trip_duration_all_positive(self, clean_df):
        """All remaining trips should have positive duration."""
        df = add_derived_columns(clean_df.copy())
        assert (df["trip_duration_minutes"] > 0).all()

    def test_trip_speed_mph_calculated(self, clean_df):
        """trip_speed_mph should be > 0 for valid trips."""
        df = add_derived_columns(clean_df.copy())
        assert (df["trip_speed_mph"] > 0).all()

    def test_pickup_hour_range(self, clean_df):
        """pickup_hour must be between 0 and 23."""
        df = add_derived_columns(clean_df.copy())
        assert df["pickup_hour"].between(0, 23).all()

    def test_pickup_day_of_week_range(self, clean_df):
        """pickup_day_of_week must be between 0 (Mon) and 6 (Sun)."""
        df = add_derived_columns(clean_df.copy())
        assert df["pickup_day_of_week"].between(0, 6).all()

    def test_pickup_month_is_january(self, clean_df):
        """All fixture rows are in January 2024 → pickup_month should be 1."""
        df = add_derived_columns(clean_df.copy())
        assert (df["pickup_month"] == 1).all()

    def test_pickup_year_is_2024(self, clean_df):
        """All fixture rows are in 2024 → pickup_year should be 2024."""
        df = add_derived_columns(clean_df.copy())
        assert (df["pickup_year"] == 2024).all()

    def test_all_six_columns_added(self, clean_df):
        """Exactly the six required derived columns should be present."""
        df = add_derived_columns(clean_df.copy())
        derived = [
            "trip_duration_minutes", "trip_speed_mph",
            "pickup_hour", "pickup_day_of_week",
            "pickup_month", "pickup_year",
        ]
        for col in derived:
            assert col in df.columns, f"Missing derived column: {col}"


# ─────────────────────────────────────────────────────────────
# add_metadata
# ─────────────────────────────────────────────────────────────

class TestAddMetadata:

    def test_data_month_is_first_of_month(self, clean_df):
        """data_month should always be the first day of the given month."""
        import datetime
        df = add_metadata(clean_df.copy(), year=2024, month=1)
        expected = datetime.date(2024, 1, 1)
        assert (df["data_month"] == expected).all()

    def test_ingested_at_is_recent(self, clean_df):
        """ingested_at should be a recent datetime (within 10 seconds of now)."""
        import datetime
        df = add_metadata(clean_df.copy(), year=2024, month=1)
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        # Check the first row's ingested_at is within 10 seconds of now
        delta = abs((df.iloc[0]["ingested_at"] - now).total_seconds())
        assert delta < 10, f"ingested_at is too far from now: {delta}s"

    def test_both_metadata_columns_added(self, clean_df):
        """Both data_month and ingested_at must be present after add_metadata."""
        df = add_metadata(clean_df.copy(), year=2024, month=1)
        assert "data_month"  in df.columns
        assert "ingested_at" in df.columns
