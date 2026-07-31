import json
import logging

import requests

from config import MAX_YC_PICKS, X_BEARER_TOKEN, YC_TWITTER_ACCOUNTS
from services.claude_client import search_and_summarize, summarize

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"

# X credits are metered, so this section is budgeted at exactly one request per
# run: 25 results is ample for two low-volume handles, and the cache makes a
# repeat call within the same process free rather than billable.
YC_TWEET_LIMIT = 25
_tweet_cache: dict[tuple, list[dict]] = {}


def _fetch_yc_tweets(max_results: int = YC_TWEET_LIMIT) -> list[dict]:
    """Fetch recent tweets from YC's official handles.

    Auth/plumbing is duplicated from twitter_feed rather than shared, to keep a
    change here from being able to break the (working) Twitter section.
    """
    if not X_BEARER_TOKEN:
        logger.warning("No X_BEARER_TOKEN set; skipping YC tweet source")
        return []

    cache_key = (tuple(YC_TWITTER_ACCOUNTS), max_results)
    if cache_key in _tweet_cache:
        logger.info("Reusing cached YC tweets (no additional X API request)")
        return _tweet_cache[cache_key]

    from_clauses = " OR ".join(f"from:{a}" for a in YC_TWITTER_ACCOUNTS)
    params = {
        "query": f"({from_clauses}) -is:retweet",
        "max_results": min(max_results, 100),
        "tweet.fields": "created_at,text,public_metrics,entities",
    }
    try:
        resp = requests.get(
            SEARCH_URL,
            headers={"Authorization": f"Bearer {X_BEARER_TOKEN}"},
            params=params,
            timeout=30,
        )
    except requests.RequestException as e:
        logger.warning("YC tweet fetch failed: %s", e)
        return []

    if resp.status_code in (429, 402):
        logger.warning(
            "X API unavailable for YC (status %d), falling back to web search",
            resp.status_code,
        )
        _tweet_cache[cache_key] = []  # don't re-bill a known-failed query
        return []
    if not resp.ok:
        logger.error("X API error %d for YC: %s", resp.status_code, resp.text[:200])
        _tweet_cache[cache_key] = []
        return []

    tweets = resp.json().get("data", [])
    _tweet_cache[cache_key] = tweets
    logger.info("Fetched %d tweets from %s", len(tweets), ", ".join(YC_TWITTER_ACCOUNTS))
    return tweets


def _parse_json_object(response: str) -> dict:
    """Parse a JSON object out of Claude's response."""
    text = response.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    return json.loads(text)


def _parse_json(response: str) -> list:
    """Parse Claude's JSON response."""
    text = response.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    # Find the JSON array in the response
    start = text.find("[")
    end = text.rfind("]")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    elif not text.startswith("["):
        # Try to fix truncated response
        if not text.endswith("]"):
            last_brace = text.rfind("}")
            if last_brace > 0:
                text = "[" + text[:last_brace + 1] + "]" if not text.startswith("[") else text[:last_brace + 1] + "]"
    return json.loads(text)


def _from_tweets(tweets: list[dict]) -> dict:
    """Curate the YC column from YC's own recent tweets."""
    tweets_text = "\n\n".join(
        f"[{t.get('created_at', '')}] {t.get('text', '')}" for t in tweets
    )

    system_prompt = f"""You are a startup analyst curating a "YC Spotlight" column for a daily tech newspaper.
You are given recent tweets from Y Combinator's official accounts. Use ONLY what these tweets support — do not invent companies or details.

Return ONLY a valid JSON object (no markdown, no code blocks) with keys:
- "updates": a 1-2 sentence plain-text digest of what YC itself is talking about right now (announcements, batch news, events, essays).
- "batch": the batch name these tweets are about (e.g. "W26", "S26"), or "Latest" if unclear.
- "companies": array of up to {MAX_YC_PICKS} companies. Each object has keys: name, description (one sentence), sector, batch, url.

STRICT RULE for "companies": include a company ONLY if the tweet presents it as a current YC portfolio or batch company (e.g. a launch, a batch announcement, a funding announcement for a YC company). Do NOT include companies that merely appear as the employer of a speaker, podcast guest, or event participant. It is correct and expected to return an empty array when the tweets are only about events, essays, or Startup School.

If no company meets that bar, return an empty "companies" array and still fill in "updates"."""

    response = summarize(system_prompt, tweets_text)

    try:
        data = _parse_json_object(response)
    except json.JSONDecodeError:
        logger.error("Failed to parse YC tweet JSON")
        return {}

    companies = data.get("companies") or []
    return {
        "companies": companies[:MAX_YC_PICKS],
        "batch": data.get("batch") or "Latest",
        "updates": data.get("updates", ""),
        "company_count": len(companies[:MAX_YC_PICKS]),
        "source": "twitter",
    }


def fetch() -> dict:
    """Curate the YC column from YC's official tweets, falling back to web search."""
    tweets = _fetch_yc_tweets()
    tweeted = _from_tweets(tweets) if tweets else {}

    # Tweets are the best source for "what YC is talking about", but they only
    # sporadically announce batch companies. Backfill the company list from web
    # search so the column never renders empty or padded with speakers' employers.
    if tweeted.get("companies"):
        logger.info(
            "YC section built from %d tweets (%d companies)",
            len(tweets), tweeted.get("company_count", 0),
        )
        return tweeted

    if tweeted.get("updates"):
        logger.info("YC tweets gave updates but no batch companies; backfilling via web search")
        result = _from_web_search()
        result["updates"] = tweeted["updates"]
        result["source"] = "twitter+web_search"
        return result

    logger.warning("No usable YC tweets; falling back to web search")
    return _from_web_search()


def _from_web_search() -> dict:
    """Fallback: find YC companies using Claude web search."""
    system_prompt = """You are a startup analyst curating a "YC Spotlight" column for a daily tech newspaper.
Find companies from the latest Y Combinator batch. Focus on companies in AI, crypto/web3, fintech, developer tools, and infrastructure.

Return ONLY a valid JSON array (no markdown, no code blocks, no extra text) with 6-8 companies.
Each object must have keys: name, description (one sentence), sector, batch (e.g. "W26" or "S25"), url (YC company page or company website)."""

    query = f"""Find {MAX_YC_PICKS} interesting companies from the most recent Y Combinator batch (check for W26, S25, or the latest available batch).
Focus on AI, crypto/web3, fintech, and developer tools companies.
For each company, provide: name, one-line description, sector, batch name, and URL."""

    response = search_and_summarize(system_prompt, query)
    logger.info("YC batch search complete")

    try:
        companies = _parse_json(response)
    except json.JSONDecodeError:
        logger.error("Failed to parse YC batch JSON")
        companies = []

    # Extract batch name from first company
    batch = companies[0].get("batch", "Latest") if companies else "Latest"

    return {
        "companies": companies,
        "batch": batch,
        "updates": "",
        "company_count": len(companies),
        "source": "web_search",
    }
