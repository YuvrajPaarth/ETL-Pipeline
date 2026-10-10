
# src/extract.py
# Downloads NYC TLC trip data (Parquet) and zone lookup (CSV)
# from the TLC CDN to the local data/raw/ directory.

import os
import time
import logging
import requests
from src.config import RAW_DATA_DIR, TLC_BASE_URL, ZONE_LOOKUP_URL

logger = logging.getLogger(__name__)


def download_file(url: str, destination: str) -> None:
    """
    Download a file from a URL to a local path.
    Retries up to 3 times with exponential back-off (2s, 4s, 8s).

    Args:
        url         : The full URL to download from.
        destination : Local file path to save the file to.
    """
    max_retries = 3

    for attempt in range(1, max_retries + 1):
        try:
            logger.info("Attempt %d/%d: downloading %s", attempt,max_retries, url)

            # stream=True means we download in chunks, not all atonce.
            # This prevents memory issues for large files.
            response = requests.get(url, stream=True, timeout=60)

            # Raise an exception if HTTP status is 4xx or 5xx
            response.raise_for_status()

            # Write the file in binary chunks of 8 KB
            with open(destination, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Log file size in MB for visibility
            size_mb = os.path.getsize(destination) / (1024 * 1024)
            logger.info("Downloaded %.1f MB to %s", size_mb, destination)
            return  # success — exit the retry loop

        except requests.RequestException as e:
            logger.warning("Attempt %d failed: %s", attempt, e)

            if attempt < max_retries:
                # Exponential back-off: wait 2s, then 4s, then 8s
                wait = 2 ** attempt
                logger.info("Retrying in %d seconds...", wait)
                time.sleep(wait)
            else:
                # All retries exhausted — raise so the pipeline stops
                raise RuntimeError(
                    f"Failed to download {url} after {max_retries} attempts"
                ) from e


def extract_trip_data(year: int, month: int) -> str:
    """
    Download the yellow taxi Parquet file for a given year and month.
    Skips the download if the file already exists locally.

    Args:
        year  : 4-digit year, e.g. 2024
        month : 1-12

    Returns:
        Local file path of the downloaded Parquet file.
    """
    # Build the filename and URL
    # TLC naming convention: yellow_tripdata_YYYY-MM.parquet
    filename = f"yellow_tripdata_{year}-{month:02d}.parquet"
    url = f"{TLC_BASE_URL}/{filename}"

    # Ensure the local data/raw/ directory exists
    os.makedirs(RAW_DATA_DIR, exist_ok=True)
    destination = os.path.join(RAW_DATA_DIR, filename)

    # Skip download if file already exists (idempotent)
    if os.path.exists(destination):
        size_mb = os.path.getsize(destination) / (1024 * 1024)
        logger.info("File already exists (%.1f MB), skipping download: %s",
                    size_mb, destination)
        return destination

    download_file(url, destination)
    return destination


def extract_zone_lookup() -> str:
    """
    Download the TLC taxi zone lookup CSV.
    Skips if already downloaded.

    Returns:
        Local file path of the zone lookup CSV.
    """
    os.makedirs(RAW_DATA_DIR, exist_ok=True)
    destination = os.path.join(RAW_DATA_DIR, "taxi_zone_lookup.csv")

    if os.path.exists(destination):
        logger.info("Zone lookup already exists, skipping download.")
        return destination

    download_file(ZONE_LOOKUP_URL, destination)
    return destination