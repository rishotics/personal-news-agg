import json
import logging

import feedparser

from config import INDIA_RSS_FEEDS, MAX_INDIA_ITEMS
from services.claude_client import summarize

logger = logging.getLogger(__name__)


def _fetch_india_articles() -> list[dict]:
    """Fetch articles from Indian startup/tech RSS feeds."""
    articles = []
    for feed_url in INDIA_RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            source = feed.feed.get("title", feed_url)
            for entry in feed.entries[:15]:
                title = entry.get("title", "")
                summary = entry.get("summary", entry.get("description", ""))[:400]
                url = entry.get("link", "")
                articles.append({
                    "title": title,
                    "summary": summary,
                    "url": url,
                    "source": source,
                })
        except Exception as e:
            logger.warning("Failed to fetch India RSS %s: %s", feed_url, e)

    logger.info("Fetched %d India startup articles from %d feeds", len(articles), len(INDIA_RSS_FEEDS))
    return articles


def _parse_json(response: str) -> list:
    """Parse Claude's JSON response."""
    text = response.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    if not text.endswith("]"):
        last_brace = text.rfind("}")
        if last_brace > 0:
            text = text[:last_brace + 1] + "]"
    return json.loads(text)


def fetch() -> dict:
    """Fetch and curate Indian startup news."""
    articles = _fetch_india_articles()

    if not articles:
        return {"items": [], "item_count": 0, "breakdown": {}}

    articles_text = "\n\n".join(
        f"Title: {a['title']}\nSource: {a['source']}\nURL: {a['url']}\nSummary: {a['summary']}"
        for a in articles
    )

    system_prompt = f"""You are an Indian tech ecosystem analyst curating a daily India startup briefing.
From the articles below, select {MAX_INDIA_ITEMS} of the most important items and categorize each as one of: "deal", "policy", or "launch".

- "deal": startup funding rounds, acquisitions, or M&A activity
- "policy": regulatory changes, government announcements, RBI/SEBI/DPDP/GIFT City updates, crypto regulation
- "launch": notable product launches, milestones, expansion announcements

For each item provide: headline, summary (2 sentences max), category, source, url.
Return ONLY a valid JSON array (no markdown, no code blocks): a list of objects with keys: headline, summary, category, source, url.
Prioritize: AI/tech companies, fintech, crypto/web3 policy, and any deals above $10M."""

    response = summarize(system_prompt, articles_text)

    try:
        items = _parse_json(response)
    except json.JSONDecodeError:
        logger.error("Failed to parse India startups JSON")
        items = []

    # Calculate breakdown
    breakdown = {}
    for item in items:
        cat = item.get("category", "other")
        breakdown[cat] = breakdown.get(cat, 0) + 1

    return {
        "items": items,
        "item_count": len(items),
        "breakdown": breakdown,
    }
