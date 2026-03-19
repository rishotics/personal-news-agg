import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from difflib import SequenceMatcher

import feedparser
import requests

from config import RSS_FEEDS, NEWS_API_KEY, MAX_ARTICLES_BEFORE_DEDUP, MAX_CURATED_ARTICLES
from services.claude_client import summarize

logger = logging.getLogger(__name__)


@dataclass
class Article:
    title: str
    url: str
    source: str
    summary: str
    published: str | None = None
    image_url: str | None = None


def _fetch_rss() -> list[Article]:
    """Fetch articles from configured RSS feeds."""
    articles = []
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
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


def fetch() -> dict:
    """Fetch, deduplicate, and summarize world news."""
    rss_articles = _fetch_rss()
    newsapi_articles = _fetch_newsapi()
    all_articles = rss_articles + newsapi_articles
    logger.info("Fetched %d articles (%d RSS, %d NewsAPI)", len(all_articles), len(rss_articles), len(newsapi_articles))

    deduped = _deduplicate(all_articles)
    logger.info("After dedup: %d articles", len(deduped))

    # Build image lookup from original articles (keyed by URL)
    image_map = {a.url: a.image_url for a in deduped if a.image_url}

    # Build content for Claude
    articles_text = "\n\n".join(
        f"Title: {a.title}\nSource: {a.source}\nURL: {a.url}\nSummary: {a.summary}"
        for a in deduped
    )

    system_prompt = f"""You are a newspaper editor curating a daily world news briefing.
Given the articles below, produce exactly {MAX_CURATED_ARTICLES} curated news items covering business, tech, AI, economics, and politics.
Group items by theme. For each item provide:
- headline (concise, newspaper-style)
- summary (2 sentences max)
- source (original publication name)
- url (original article link)

Return valid JSON: a list of objects with keys: headline, summary, source, url, theme."""

    response = summarize(system_prompt, articles_text)

    # Parse Claude's JSON response
    try:
        # Handle markdown code blocks
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        curated = json.loads(text)
    except json.JSONDecodeError:
        logger.error("Failed to parse Claude response as JSON, using raw text")
        curated = [{"headline": "World News Summary", "summary": response, "source": "Claude", "url": "", "theme": "General"}]

    # Inject image URLs from original articles
    for article in curated:
        url = article.get("url", "")
        if url in image_map:
            article["image_url"] = image_map[url]
        else:
            article["image_url"] = None

    return {
        "article_count": len(curated),
        "articles": curated,
    }
