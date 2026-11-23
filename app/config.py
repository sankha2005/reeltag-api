import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from dotenv import load_dotenv

# Load the backend .env before Settings snapshots the environment.
# Without this, GEMINI_API_KEY / SERPAPI_KEY / ALLOWED_ORIGINS are silently ignored.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@dataclass
class Settings:
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    serpapi_key: str = field(default_factory=lambda: os.getenv("SERPAPI_KEY", ""))
    amazon_associate_tag: str = field(default_factory=lambda: os.getenv("AMAZON_ASSOCIATE_TAG", "reeltag-21"))
    cuelinks_pub_id: str = field(default_factory=lambda: os.getenv("CUELINKS_PUB_ID", ""))
    database_path: str = field(default_factory=lambda: os.getenv("DATABASE_PATH", "./reeltag.db"))
    allowed_origins: List[str] = field(
        default_factory=lambda: [
            o.strip()
            for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,https://reeltag.in").split(",")
            if o.strip()
        ]
    )


settings = Settings()
