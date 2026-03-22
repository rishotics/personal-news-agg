import logging
from datetime import datetime, timezone

from pymongo import MongoClient, DESCENDING

from config import MONGODB_URI

logger = logging.getLogger(__name__)

_client = MongoClient(MONGODB_URI)
_db = _client["news_aggregator"]
_editions = _db["editions"]

# Ensure indexes
_editions.create_index("date", unique=True)
_editions.create_index([("created_at", DESCENDING)])


def get_next_edition_number() -> int:
    last = _editions.find_one(sort=[("edition_number", DESCENDING)])
    return (last["edition_number"] + 1) if last else 1


def save_edition(edition: dict) -> str:
    edition.setdefault("created_at", datetime.now(timezone.utc))
    date = edition.get("date")
    result = _editions.replace_one({"date": date}, edition, upsert=True)
    doc_id = result.upserted_id or date
    logger.info("Saved edition %s (id: %s)", date, doc_id)
    return str(doc_id)


def get_edition_by_date(date_str: str) -> dict | None:
    return _editions.find_one({"date": date_str})


def list_recent_editions(limit: int = 10) -> list[dict]:
    return list(_editions.find().sort("created_at", DESCENDING).limit(limit))
