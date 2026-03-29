import json
import logging

import feedparser

from config import FUNDING_RSS_FEEDS, MAX_FUNDING_ITEMS
from services.claude_client import summarize

logger = logging.getLogger(__name__)


def _fetch_funding_articles() -> list[dict]:
    """Fetch funding-related articles from RSS feeds."""
    articles = []
    for feed_url in FUNDING_RSS_FEEDS:
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
            logger.warning("Failed to fetch funding RSS %s: %s", feed_url, e)

    logger.info("Fetched %d funding articles from %d feeds", len(articles), len(FUNDING_RSS_FEEDS))
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
    """Fetch and curate funding rounds."""
    articles = _fetch_funding_articles()

    if not articles:
        return {"rounds": [], "round_count": 0}

    articles_text = "\n\n".join(
        f"Title: {a['title']}\nSource: {a['source']}\nURL: {a['url']}\nSummary: {a['summary']}"
        for a in articles
    )

    system_prompt = f"""You are a venture capital analyst curating a daily funding digest.
From the articles below, extract {MAX_FUNDING_ITEMS} notable startup funding rounds from the last 48 hours.
Focus on AI, crypto/web3, fintech, and developer tools companies.
For each round, extract: company name, round type (Seed/Series A/B/C/etc), amount raised, lead investor(s), sector tag, and a 1-sentence summary of what the company does.
If exact details aren't in the article, use "Undisclosed" for missing fields.
Return ONLY a valid JSON array (no markdown, no code blocks): a list of objects with keys: company, round_type, amount, lead_investor, sector, summary, url, source.
Sort by amount descending."""

    response = summarize(system_prompt, articles_text)

    try:
        rounds = _parse_json(response)
    except json.JSONDecodeError:
        logger.error("Failed to parse funding rounds JSON")
        rounds = []

    return {
        "rounds": rounds,
        "round_count": len(rounds),
    }
