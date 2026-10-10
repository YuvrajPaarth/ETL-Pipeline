import os
import logging
from dotenv import load_dotenv

# Load the .env file into environment variables
load_dotenv()

# Set up logging so all modules share the same format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

# --- Database settings ---
# os.getenv reads a variable from .env
# The second argument is the default if the variable is missing
DB_USER     = os.getenv("POSTGRES_USER", "tlc_user")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "tlc_password")
DB_HOST     = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT     = os.getenv("POSTGRES_PORT", "5432")
DB_NAME     = os.getenv("POSTGRES_DB", "nyc_tlc")

# SQLAlchemy connection string
# Format: postgresql+psycopg2://user:password@host:port/database
DATABASE_URL = (
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# --- Pipeline settings ---
RAW_DATA_DIR = os.path.join(os.path.dirname(__file__), "..",
"data", "raw")
TLC_BASE_URL = "https://d37ci6vzurychx.cloudfront.net/trip-data"
ZONE_LOOKUP_URL = "https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv"
CHUNK_SIZE = 10_000   # rows per database insert batch

logger.info("Config loaded. Connecting to %s:%s/%s", DB_HOST,
DB_PORT, DB_NAME)
