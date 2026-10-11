# NYC TLC ETL Pipeline 🚕

An automated ETL (Extract, Transform, Load) pipeline that downloads NYC Yellow Taxi trip data, cleans it, loads it into a PostgreSQL data warehouse, and visualises it through a Metabase dashboard.

---

## What it does

```
NYC TLC Website
      ↓  Extract
Download Parquet file (millions of taxi trips)
      ↓  Transform
Clean data → fix types → drop bad rows → add calculated columns
      ↓  Quality Checks
Validate: row count, nulls, ranges, schema
      ↓  Load
Fill PostgreSQL star schema (fact + dimension tables)
      ↓  Dashboard
View live data in Metabase at http://localhost:3000
```

---

## Tech Stack

| Tool | Purpose |
|------|---------|
| Python 3.12 | Pipeline logic |
| pandas | Data cleaning and transformation |
| SQLAlchemy + psycopg2 | PostgreSQL connection |
| PostgreSQL 15 | Data warehouse |
| Metabase | Dashboard / visualisation |
| Docker | Runs PostgreSQL and Metabase |

---

## Project Structure

```
nyc-tlc-etl/
├── src/
│   ├── config.py          # DB credentials and settings
│   ├── extract.py         # Download data from TLC website
│   ├── transform.py       # Clean and enrich data
│   ├── load.py            # Load into analytics star schema
│   └── quality_checks.py  # Validate data quality
├── sql/
│   ├── 01_create_schema.sql
│   ├── 02_create_table.sql
│   ├── 03_create_view.sql
│   ├── 04_create_staging_table.sql
│   └── 05_create_analytics_tables.sql
├── tests/
│   ├── conftest.py        # Shared test fixtures
│   └── test_transform.py  # 25 unit tests
├── data/raw/              # Downloaded Parquet files (gitignored)
├── docs/
│   ├── requirements.md
│   └── design.md
├── docker-compose.yml     # PostgreSQL + Metabase containers
├── .env                   # Database credentials
├── .env.example           # Template for credentials
├── requirements.txt       # Python dependencies
├── run_pipeline.py        # Main pipeline runner
└── run_interactive.py     # Interactive pipeline launcher
```

---

## Database Design (Star Schema)

```
dim_date ──────────────────────────────┐
dim_location (pickup) ─────────────────┤
dim_location (dropoff) ────────────────┤──► fact_trips
dim_payment ───────────────────────────┘
```

| Table | Description |
|-------|-------------|
| `analytics.fact_trips` | One row per taxi trip |
| `analytics.dim_date` | Calendar dimension |
| `analytics.dim_location` | 265 NYC taxi zones |
| `analytics.dim_payment` | Payment type labels |
| `staging.yellow_taxi_clean` | Cleaned data before analytics load |
| `raw.yellow_taxi_raw` | Raw data as downloaded |

---

## How to Run

### Prerequisites
- Docker Desktop installed and running
- Python 3.12+
- Python packages: `pip install -r requirements.txt`

### Step 1 — Start Docker containers
```bash
docker compose up -d
```

This starts:
- PostgreSQL at `localhost:5432`
- Metabase at `http://localhost:3000`

### Step 2 — Run the pipeline (interactive)
```bash
python3 run_interactive.py
```

Follow the prompts to choose year, month, and sample size.

### Step 3 — Or run directly
```bash
# Full run (2.8 million rows)
python3 run_pipeline.py 2024 1

# Sample run (fast, for testing)
python3 run_pipeline.py 2024 1 50000
```

### Step 4 — View in Metabase
Open `http://localhost:3000` in your browser.

---

## Data Cleaning Rules

| Rule | What gets dropped |
|------|------------------|
| Duplicate rows | Exact copies |
| Null datetimes | Rows with missing pickup or dropoff time |
| Zero/negative distance | trip_distance ≤ 0 |
| Zero/negative fare | total_amount ≤ 0 |
| Unrealistic duration | trip_duration_minutes outside [1, 300] |

---

## Derived Columns Added

| Column | Formula |
|--------|---------|
| `trip_duration_minutes` | dropoff_time − pickup_time in minutes |
| `trip_speed_mph` | distance ÷ (duration in hours) |
| `pickup_hour` | Hour of day (0–23) |
| `pickup_day_of_week` | 0=Monday, 6=Sunday |
| `pickup_month` | Month number (1–12) |
| `pickup_year` | 4-digit year |

---

## Running Tests
```bash
python3 -m pytest tests/ -v
```

25 unit tests covering all transform functions.

---

## Data Source

- Provider: NYC Taxi & Limousine Commission (TLC)
- Format: Parquet
- URL: `https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_YYYY-MM.parquet`
- Licence: Public domain (NYC Open Data)
