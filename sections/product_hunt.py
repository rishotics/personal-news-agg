import json
import logging
import random
from dataclasses import dataclass

import feedparser

from config import PRODUCT_HUNT_PICK_COUNT
from services.claude_client import summarize

logger = logging.getLogger(__name__)

# Product Hunt has a public RSS feed for top posts
PH_RSS_URL = "https://www.producthunt.com/feed"
PH_FRONTPAGE_RSS = "https://www.producthunt.com/feed?category=undefined"


@dataclass
class Product:
    name: str
    tagline: str
    url: str


def _fetch_products_rss() -> list[Product]:
    """Fetch today's products from Product Hunt RSS feed."""
    products = []
    for feed_url in [PH_RSS_URL, PH_FRONTPAGE_RSS]:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                name = entry.get("title", "")
                if not name:
                    continue
                tagline = entry.get("summary", entry.get("description", ""))[:200]
                url = entry.get("link", "")
                if not any(p.name == name for p in products):
                    products.append(Product(name=name, tagline=tagline, url=url))
        except Exception as e:
            logger.warning("Failed to fetch PH RSS %s: %s", feed_url, e)

    logger.info("Fetched %d products from Product Hunt RSS", len(products))
    return products


def fetch() -> dict:
    """Fetch Product Hunt products, pick random ones, enrich with Claude."""
    products = _fetch_products_rss()

    if not products:
        return {
            "products": [],
            "status_note": "Could not fetch Product Hunt products.",
        }

    # Pick random sample from available products
    pick_count = min(PRODUCT_HUNT_PICK_COUNT, len(products))
    picks = random.sample(products, pick_count)

    # Enrich with Claude
    products_text = "\n\n".join(
        f"Name: {p.name}\nTagline: {p.tagline}\nURL: {p.url}"
        for p in picks
    )

    system_prompt = """You are a tech product reviewer writing a "Products to Watch" newspaper column.
For each product below, write a compelling 2-sentence description that explains what it does and why it's interesting.

Return valid JSON: a list of objects with keys: name, tagline, url, description."""

    response = summarize(system_prompt, products_text)

    try:
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        enriched = json.loads(text)
    except json.JSONDecodeError:
        logger.error("Failed to parse Product Hunt summary as JSON")
        enriched = [
            {"name": p.name, "tagline": p.tagline, "url": p.url, "description": p.tagline}
            for p in picks
        ]

    return {"products": enriched}
