import json
import logging

import feedparser
import requests

from config import X_BEARER_TOKEN, TWITTER_ACCOUNTS, MAX_TWEETS_PER_SEARCH
from services.claude_client import summarize

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"

# Fallback RSS feeds — tech news sources that heavily cover X/Twitter discussions
FALLBACK_RSS = [
    "https://www.techmeme.com/feed.xml",
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "https://techcrunch.com/feed/",
    "https://www.theverge.com/rss/index.xml",
    "https://hnrss.org/newest?q=twitter+OR+x.com+OR+tweet",
]


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

    if resp.status_code in (429, 402):
        logger.warning("Twitter API unavailable (status %d), will try fallback", resp.status_code)
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


def _fetch_fallback_discussions() -> list[dict]:
    """Fallback: fetch tech news headlines that cover X/Twitter discussions and trending topics."""
    articles = []
    for feed_url in FALLBACK_RSS:
        try:
            feed = feedparser.parse(feed_url)
            source = feed.feed.get("title", feed_url)
            for entry in feed.entries[:15]:
                title = entry.get("title", "")
                summary = entry.get("summary", "")[:300]
                url = entry.get("link", "")
                articles.append({"title": title, "summary": summary, "source": source, "url": url})
        except Exception as e:
            logger.warning("Fallback RSS %s failed: %s", feed_url, e)

    logger.info("Fetched %d fallback articles for Twitter section", len(articles))
    return articles


def _summarize_tweets(tweets: list[dict]) -> dict:
    """Summarize tweets with Claude."""
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

    return summarize(system_prompt, tweets_text)


def _summarize_fallback(articles: list[dict]) -> dict:
    """Summarize fallback articles as if they were Twitter discussions."""
    articles_text = "\n\n".join(
        f"[{a['source']}] {a['title']}\n{a['summary']}"
        for a in articles[:30]
    )

    system_prompt = """You are a social media analyst writing a newspaper column called "From the Timeline".
The Twitter API is unavailable today, so you're working from tech news headlines instead.
Based on these articles, infer what people on X/Twitter are likely discussing right now.

Produce:
1. A brief opening paragraph about today's trending tech discussions (don't mention that you're using news articles as source)
2. Top 5 topics people are likely debating on X (each with a likely key voice/account and a 1-2 sentence summary of the discussion)
3. Any breaking news

Return valid JSON with keys: opening_paragraph, top_discussions (list of {topic, author, summary}), breaking_news (list of strings, can be empty)."""

    return summarize(system_prompt, articles_text)


def _parse_response(response: str) -> dict:
    """Parse Claude's JSON response."""
    try:
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(text)
    except json.JSONDecodeError:
        logger.error("Failed to parse Twitter summary as JSON")
        return {
            "opening_paragraph": response,
            "top_discussions": [],
            "breaking_news": [],
        }


def fetch() -> dict:
    """Fetch tweets (with fallback) and summarize with Claude."""
    tweets = _fetch_tweets()

    if tweets:
        logger.info("Fetched %d tweets via X API", len(tweets))
        response = _summarize_tweets(tweets)
        parsed = _parse_response(response)
        return {
            "tweet_count": len(tweets),
            "summary": parsed.get("opening_paragraph", ""),
            "top_discussions": parsed.get("top_discussions", []),
            "breaking_news": parsed.get("breaking_news", []),
        }

    # Fallback: use tech news to infer Twitter discussions
    logger.info("X API unavailable, using fallback sources")
    fallback_articles = _fetch_fallback_discussions()

    if not fallback_articles:
        return {
            "tweet_count": 0,
            "summary": "Twitter section unavailable today.",
            "top_discussions": [],
            "breaking_news": [],
        }

    response = _summarize_fallback(fallback_articles)
    parsed = _parse_response(response)

    return {
        "tweet_count": 0,
        "is_fallback": True,
        "summary": parsed.get("opening_paragraph", ""),
        "top_discussions": parsed.get("top_discussions", []),
        "breaking_news": parsed.get("breaking_news", []),
    }
