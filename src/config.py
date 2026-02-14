"""Environment-based configuration for the deal flow pipeline."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


class Config:
    """Central configuration — reads from environment variables."""

    # --- Required ---
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    SLACK_WEBHOOK_URL: str = os.getenv("SLACK_WEBHOOK_URL", "")
    SLACK_BOT_TOKEN: str = os.getenv("SLACK_BOT_TOKEN", "")
    SLACK_SIGNING_SECRET: str = os.getenv("SLACK_SIGNING_SECRET", "")

    # --- Optional ---
    GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")
    SCORE_THRESHOLD: int = int(os.getenv("SCORE_THRESHOLD", "75"))

    # --- Sourcing APIs ---
    PHANTOMBUSTER_API_KEY: str = os.getenv("PHANTOMBUSTER_API_KEY", "")
    PHANTOMBUSTER_AGENT_ID: str = os.getenv("PHANTOMBUSTER_AGENT_ID", "")  # For LinkedIn
    APIFY_TOKEN: str = os.getenv("APIFY_TOKEN", "")
    ALGOLIA_APP_ID: str = os.getenv("ALGOLIA_APP_ID", "UJ5WYC0L7X")  # HN Algolia
    ALGOLIA_API_KEY: str = os.getenv("ALGOLIA_API_KEY", "28f453eb1d2f70d535686682d30d81b6") # HN public key

    # --- Enrichment APIs ---
    CRUNCHBASE_API_KEY: str = os.getenv("CRUNCHBASE_API_KEY", "")
    APOLLO_API_KEY: str = os.getenv("APOLLO_API_KEY", "")
    JINA_API_KEY: str = os.getenv("JINA_API_KEY", "") # Reader API

    # --- Database ---
    AIRTABLE_API_KEY: str = os.getenv("AIRTABLE_API_KEY", "")
    AIRTABLE_BASE_ID: str = os.getenv("AIRTABLE_BASE_ID", "")
    AIRTABLE_TABLE_NAME: str = os.getenv("AIRTABLE_TABLE_NAME", "deal_pipeline")

    # --- Paths ---
    DATA_DIR: Path = _PROJECT_ROOT / "data"
    DB_PATH: Path = DATA_DIR / "deals.db"

    # --- Gemini ---
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    @classmethod
    def validate(cls) -> list[str]:
        """Return a list of missing-but-required config keys."""
        missing = []
        if not cls.GEMINI_API_KEY:
            missing.append("GEMINI_API_KEY")
        if not cls.SLACK_WEBHOOK_URL:
            missing.append("SLACK_WEBHOOK_URL")
        return missing

    @classmethod
    def ensure_dirs(cls) -> None:
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
