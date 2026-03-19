import json
import logging

import requests

from config import X_BEARER_TOKEN, TWITTER_ACCOUNTS, MAX_TWEETS_PER_SEARCH
from services.claude_client import summarize

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"


def _build_query() -> str:
    """Build a Twitter search query from configured accounts."""
    from_clauses = " OR ".join(f"from:{acct}" for acct in TWITTER_ACCOUNTS)
    return f"({from_clauses}) -is:retweet lang:en"


def _fetch_tweets() -> list[dict]:
    """Fetch recent tweets from tracked accounts via search API."""
    headers = {"Authorization": f"Bearer {X_BEARER_TOKEN}"}
    query = _build_query()

    params = {
        "query": query,
        "max_results": min(MAX_TWEETS_PER_SEARCH, 100),
        "tweet.fields": "created_at,author_id,public_metrics,text",
        "expansions": "author_id",
        "user.fields": "username,name",
    }

    resp = requests.get(SEARCH_URL, headers=headers, params=params, timeout=30)

    if resp.status_code == 429:
        logger.warning("Twitter API rate limited")
        return []
    if not resp.ok:
        logger.error("Twitter API error %d: %s", resp.status_code, resp.text)
        return []

    data = resp.json()
    tweets = data.get("data", [])

    # Build author lookup
    users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}
    for tweet in tweets:
        author = users.get(tweet.get("author_id"), {})
        tweet["username"] = author.get("username", "unknown")
        tweet["author_name"] = author.get("name", "Unknown")

    return tweets


def fetch() -> dict:
    """Fetch tweets and summarize with Claude."""
    tweets = _fetch_tweets()

    if not tweets:
        return {
            "tweet_count": 0,
            "summary": "Twitter section unavailable — no tweets fetched (possible rate limit).",
            "top_discussions": [],
        }

    logger.info("Fetched %d tweets", len(tweets))

    tweets_text = "\n\n".join(
        f"@{t['username']} ({t['author_name']}): {t['text']}"
        for t in tweets
    )

    system_prompt = """You are a social media analyst writing a newspaper column called "From the Timeline".
Given these tweets from the last 24 hours, produce:
1. A brief opening paragraph summarizing the overall mood/themes
2. Top 5 trending discussions or notable takes (each with the key tweet author and a 1-2 sentence summary)
3. Any breaking news or important announcements

Return valid JSON with keys: opening_paragraph, top_discussions (list of {topic, author, summary}), breaking_news (list of strings, can be empty)."""

    response = summarize(system_prompt, tweets_text)

    try:
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        parsed = json.loads(text)
    except json.JSONDecodeError:
        logger.error("Failed to parse Twitter summary as JSON")
        parsed = {
            "opening_paragraph": response,
            "top_discussions": [],
            "breaking_news": [],
        }

    return {
        "tweet_count": len(tweets),
        "summary": parsed.get("opening_paragraph", ""),
        "top_discussions": parsed.get("top_discussions", []),
        "breaking_news": parsed.get("breaking_news", []),
    }
