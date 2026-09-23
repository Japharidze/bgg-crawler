"""Project paths and tunable settings.

Every knob the pipeline needs lives here so runs are reproducible and the
analysis parameters (rating threshold, rare-tag cutoff, bins) are in one place.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
RANKS_CSV = DATA_DIR / "ranks.csv"
DB_PATH = ROOT / "db" / "bgg.duckdb"

# --- API ---------------------------------------------------------------
# Never www.boardgamegeek.com: the redirect drops the Authorization header.
API_BASE = "https://boardgamegeek.com/xmlapi2"
BATCH_SIZE = 20          # hard BGG limit for thing?id=
REQUEST_DELAY = 5.0      # seconds between requests, BGG minimum
MAX_RETRIES = 6
BACKOFF_BASE = 5.0       # seconds; doubled per retry on 500/503
RETRY_202_DELAY = 10.0   # 202 = queued, not an error

# --- Analysis ----------------------------------------------------------
MIN_USERS_RATED = 200    # noise floor for the modelling set
RARE_TAG_MIN_GAMES = 30  # drop mechanics/categories seen in fewer games
WEIGHT_BINS = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 5.0]
PLAYTIME_BINS = [0, 30, 60, 90, 120, 180, 100_000]


def bgg_token() -> str:
    """Bearer token from the environment. Kept out of the repo."""
    token = os.environ.get("BGG_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "BGG_TOKEN is not set. Copy .env.example to .env and add your token."
        )
    return token
