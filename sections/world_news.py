import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

import feedparser
import requests

from config import NEWS_BUCKETS, NEWS_API_KEY, MAX_ARTICLES_BEFORE_DEDUP, EDITION_TZ
from services.claude_client import summarize
from services.mongo_store import get_edition_by_date

logger = logging.getLogger(__name__)


@dataclass
class Article:
    title: str
    url: str
    source: str
    summary: str
    published: str | None = None
    image_url: str | None = None


def _fetch_rss(feed_urls: list[str]) -> list[Article]:
    """Fetch articles from the given RSS feeds.

    A feed that returns zero entries is logged loudly: feedparser reports a
    dead feed as an empty list rather than raising, which is how a broken
    source can sit in the config for years contributing nothing.
    """
    articles = []
    for feed_url in feed_urls:
        try:
            feed = feedparser.parse(feed_url)
            if not feed.entries:
                logger.warning("DEAD FEED (0 entries): %s", feed_url)
                continue
            source = feed.feed.get("title", feed_url)
            for entry in feed.entries[:10]:
                pub = entry.get("published", "")
                # Extract image from media_thumbnail or media_content
                image_url = None
                if entry.get("media_thumbnail"):
                    image_url = entry["media_thumbnail"][0].get("url")
                elif entry.get("media_content"):
                    for mc in entry["media_content"]:
                        if mc.get("medium") == "image" or mc.get("url", "").split("?")[0].split(".")[-1] in ("jpg", "jpeg", "png", "webp"):
                            image_url = mc.get("url")
                            break
                articles.append(Article(
                    title=entry.get("title", ""),
                    url=entry.get("link", ""),
                    source=source,
                    summary=entry.get("summary", "")[:300],
                    published=pub,
                    image_url=image_url,
                ))
        except Exception as e:
            logger.warning("Failed to fetch RSS %s: %s", feed_url, e)
    return articles


def _fetch_newsapi() -> list[Article]:
    """Fetch from NewsAPI if key is available."""
    if not NEWS_API_KEY:
        return []
    articles = []
    for category in ["business", "technology", "science"]:
        try:
            resp = requests.get(
                "https://newsapi.org/v2/top-headlines",
                params={"category": category, "language": "en", "pageSize": 10, "apiKey": NEWS_API_KEY},
                timeout=15,
            )
            if resp.ok:
                for item in resp.json().get("articles", []):
                    articles.append(Article(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        source=item.get("source", {}).get("name", "NewsAPI"),
                        summary=item.get("description", "")[:300],
                        published=item.get("publishedAt", ""),
                    ))
        except Exception as e:
            logger.warning("NewsAPI fetch failed for %s: %s", category, e)
    return articles


def _deduplicate(articles: list[Article]) -> list[Article]:
    """Remove near-duplicate articles by title similarity."""
    seen = []
    unique = []
    for article in articles:
        title_lower = article.title.lower().strip()
        is_dup = False
        for seen_title in seen:
            if SequenceMatcher(None, title_lower, seen_title).ratio() > 0.7:
                is_dup = True
                break
        if not is_dup:
            seen.append(title_lower)
            unique.append(article)
    return unique[:MAX_ARTICLES_BEFORE_DEDUP]


def _previous_headlines() -> str:
    """Yesterday's headlines, so today's edition doesn't repeat them."""
    yesterday = (datetime.now(EDITION_TZ) - timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        prev_edition = get_edition_by_date(yesterday)
        if prev_edition:
            prev_articles = prev_edition.get("sections", {}).get("world_news", {}).get("articles", [])
            headlines = [a.get("headline", "") for a in prev_articles]
            if headlines:
                return "\n\nAVOID repeating these stories from yesterday's edition:\n" + "\n".join(
                    f"- {h}" for h in headlines
                )
    except Exception:
        pass  # MongoDB unavailable, skip dedup
    return ""


def _curate_bucket(topic: str, quota: int, articles: list[Article], prev_headlines: str) -> list[dict]:
    """Run one Claude call for a single topic bucket."""
    articles_text = "\n\n".join(
        f"Title: {a.title}\nSource: {a.source}\nURL: {a.url}\nSummary: {a.summary}"
        for a in articles
    )

    system_prompt = f"""You are a newspaper editor curating the "{topic}" column of a daily briefing.
From the articles below, select exactly {quota} items that best belong under "{topic}". Prefer consequential, specific stories over routine coverage.

For each item provide:
- headline (concise, newspaper-style)
- summary (2 sentences max; the second sentence should say why it matters)
- source (original publication name)
- url (original article link)
{prev_headlines}

Return ONLY a valid JSON array of objects with keys: headline, summary, source, url."""

    response = summarize(system_prompt, articles_text)

    text = response.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    start, end = text.find("["), text.rfind("]")
    if start >= 0 and end > start:
        text = text[start:end + 1]

    items = json.loads(text)
    for item in items:
        item["theme"] = topic
    return items[:quota]


def fetch() -> dict:
    """Fetch and curate world news, with guaranteed slots per topic bucket."""
    prev_headlines = _previous_headlines()
    newsapi_articles = _fetch_newsapi()

    curated: list[dict] = []
    image_map: dict[str, str] = {}
    failed_buckets: list[str] = []

    for i, (topic, cfg) in enumerate(NEWS_BUCKETS.items()):
        try:
            articles = _fetch_rss(cfg["feeds"])
            if i == 0:
                articles += newsapi_articles  # NewsAPI is general-interest
            deduped = _deduplicate(articles)
            logger.info("%s: %d articles after dedup", topic, len(deduped))
            if not deduped:
                logger.warning("%s: no articles available, skipping bucket", topic)
                failed_buckets.append(topic)
                continue

            image_map.update({a.url: a.image_url for a in deduped if a.image_url})
            curated.extend(_curate_bucket(topic, cfg["quota"], deduped, prev_headlines))
        except Exception as e:
            # One bad bucket shouldn't cost the whole section.
            logger.error("Bucket %s failed: %s", topic, e)
            failed_buckets.append(topic)

    if not curated:
        raise RuntimeError(f"All news buckets failed: {', '.join(failed_buckets)}")

    # Drop cross-bucket repeats (a story can surface in both Top Stories and
    # Geopolitics); first bucket to claim it wins.
    seen: list[str] = []
    unique = []
    for item in curated:
        h = item.get("headline", "").lower().strip()
        if any(SequenceMatcher(None, h, s).ratio() > 0.7 for s in seen):
            continue
        seen.append(h)
        item["image_url"] = image_map.get(item.get("url", ""))
        unique.append(item)

    logger.info(
        "Curated %d items across %d/%d buckets",
        len(unique), len(NEWS_BUCKETS) - len(failed_buckets), len(NEWS_BUCKETS),
    )
    return {
        "article_count": len(unique),
        "articles": unique,
        "failed_buckets": failed_buckets,
    }
