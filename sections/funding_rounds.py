import json
import logging
import random
from datetime import datetime, timedelta, timezone
from time import mktime

import feedparser

from config import (
    FUNDING_DEDUP_DAYS,
    FUNDING_EARLY_STAGE_COUNT,
    FUNDING_RECAP_PATTERNS,
    FUNDING_RECENCY_HOURS,
    FUNDING_RSS_FEEDS,
    FUNDING_SIGNAL_COUNT,
)
from services.claude_client import summarize
from services import mongo_store

logger = logging.getLogger(__name__)


def _entry_published(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            try:
                return datetime.fromtimestamp(mktime(t), tz=timezone.utc)
            except (TypeError, ValueError):
                continue
    return None


def _is_recap(title: str, url: str) -> bool:
    haystack = f"{title} {url}".lower()
    return any(pattern in haystack for pattern in FUNDING_RECAP_PATTERNS)


def _fetch_funding_articles() -> list[dict]:
    """Fetch funding-related articles from RSS feeds, filtered to recent non-recap items."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=FUNDING_RECENCY_HOURS)
    articles = []
    for feed_url in FUNDING_RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            source = feed.feed.get("title", feed_url)
            for entry in feed.entries[:25]:
                title = entry.get("title", "")
                url = entry.get("link", "")
                if _is_recap(title, url):
                    continue
                published = _entry_published(entry)
                if published and published < cutoff:
                    continue
                summary = entry.get("summary", entry.get("description", ""))[:400]
                articles.append({
                    "title": title,
                    "summary": summary,
                    "url": url,
                    "source": source,
                    "published": published.isoformat() if published else "unknown",
                })
        except Exception as e:
            logger.warning("Failed to fetch funding RSS %s: %s", feed_url, e)

    # Shuffle so the same article doesn't always lead the prompt
    random.shuffle(articles)
    logger.info(
        "Fetched %d recent funding articles from %d feeds (last %dh)",
        len(articles),
        len(FUNDING_RSS_FEEDS),
        FUNDING_RECENCY_HOURS,
    )
    return articles


def _parse_json_object(response: str) -> dict:
    """Parse Claude's JSON object response."""
    text = response.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    # Trim anything after the last closing brace
    last_brace = text.rfind("}")
    if last_brace > 0:
        text = text[:last_brace + 1]
    return json.loads(text)


def _excluded_companies() -> list[str]:
    try:
        return mongo_store.get_recently_featured_companies(FUNDING_DEDUP_DAYS)
    except Exception as e:
        logger.warning("Could not fetch dedup list (continuing without it): %s", e)
        return []


def fetch() -> dict:
    """Fetch and curate funding rounds, split into early-stage and later-stage signal."""
    articles = _fetch_funding_articles()

    if not articles:
        return {"early_stage": [], "later_stage_signal": [], "round_count": 0}

    excluded = _excluded_companies()
    excluded_block = (
        "EXCLUDED COMPANIES (already featured in last 7 days — DO NOT include): "
        + ", ".join(excluded)
        if excluded
        else "EXCLUDED COMPANIES: (none)"
    )

    articles_text = "\n\n".join(
        f"Title: {a['title']}\nSource: {a['source']}\nPublished: {a['published']}\nURL: {a['url']}\nSummary: {a['summary']}"
        for a in articles
    )

    system_prompt = f"""You are a venture analyst writing the funding column of a daily newspaper for tech founders.

From the articles below, extract two buckets of funding rounds:

1. "early_stage" — exactly {FUNDING_EARLY_STAGE_COUNT} rounds. ONLY Pre-Seed, Seed, Seed Extension, Series A, or Series A Extension. Skip if the round is larger than $50M. Bias toward AI, crypto/web3, fintech, dev tools, defense, climate, bio, and consumer. Sort by recency (newest first), not amount.

2. "later_stage_signal" — at most {FUNDING_SIGNAL_COUNT} rounds. Series B or later. Include ONLY if the round genuinely matters for a founder reader (e.g., record valuation in a sector, well-known founder, sector-defining check, strategic acquirer signal). Each must have a `signal_reason` — one short sentence on why a founder should care.

{excluded_block}

For each round include: company, round_type (Pre-Seed/Seed/Seed Extension/Series A/Series A Extension/Series B/etc), amount (e.g., "$3.7M"), lead_investor, sector (one of: AI, Crypto, Fintech, Dev Tools, Defense, Climate, Bio, Consumer, Other), summary (one sentence on what the company does), url, source. For later_stage_signal items also include `valuation` (e.g., "$900B") if mentioned and `signal_reason`.

If a field is missing from the article, use "Undisclosed".
Do NOT include any company in the EXCLUDED COMPANIES list above.
Do NOT invent rounds — only extract from the articles provided.

Return ONLY valid JSON (no markdown, no code blocks) with this shape:
{{"early_stage": [...], "later_stage_signal": [...]}}"""

    response = summarize(system_prompt, articles_text)

    try:
        parsed = _parse_json_object(response)
        early_stage = parsed.get("early_stage", []) or []
        signal = parsed.get("later_stage_signal", []) or []
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.error("Failed to parse funding rounds JSON: %s", e)
        early_stage, signal = [], []

    return {
        "early_stage": early_stage,
        "later_stage_signal": signal,
        "round_count": len(early_stage) + len(signal),
    }
