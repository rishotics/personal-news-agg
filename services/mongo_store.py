import logging
import re
from datetime import datetime, timedelta, timezone

from pymongo import MongoClient, DESCENDING

from config import MONGODB_URI, MONGO_FEATURED_FUNDING_COLLECTION

logger = logging.getLogger(__name__)

_client = MongoClient(MONGODB_URI)
_db = _client["news_aggregator"]
_editions = _db["editions"]
_featured_funding = _db[MONGO_FEATURED_FUNDING_COLLECTION]

# Ensure indexes
_editions.create_index("date", unique=True)
_editions.create_index([("created_at", DESCENDING)])
_featured_funding.create_index("normalized_name")
# Auto-expire dedup records after 14 days (covers any reasonable dedup window)
_featured_funding.create_index("featured_at", expireAfterSeconds=14 * 24 * 3600)


def _normalize_company(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


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


def get_recently_featured_companies(days: int) -> list[str]:
    """Return list of company names featured in the last `days` days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cursor = _featured_funding.find(
        {"featured_at": {"$gte": cutoff}},
        {"company": 1, "_id": 0},
    )
    return [doc["company"] for doc in cursor if doc.get("company")]


def record_featured_companies(companies: list[dict], date_str: str) -> int:
    """Record featured funding companies for dedup. `companies` items need 'company' key."""
    if not companies:
        return 0
    now = datetime.now(timezone.utc)
    docs = []
    for c in companies:
        name = c.get("company")
        if not name:
            continue
        docs.append({
            "normalized_name": _normalize_company(name),
            "company": name,
            "round_type": c.get("round_type"),
            "featured_on": date_str,
            "featured_at": now,
        })
    if not docs:
        return 0
    _featured_funding.insert_many(docs)
    logger.info("Recorded %d featured funding companies for %s", len(docs), date_str)
    return len(docs)
