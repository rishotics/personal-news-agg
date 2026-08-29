import os
from datetime import timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Paths
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
TEMPLATES_DIR = BASE_DIR / "templates"

# API Keys
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
MONGODB_URI = os.getenv("MONGODB_URI", "")
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN", "")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")

# The paper is read in India, so the edition date, the This Day panchang, and
# the yesterday-lookup key are all reckoned in IST rather than UTC. Without
# this, a run scheduled before 05:30 IST would date the paper to the previous
# day and fetch the wrong day's panchang. India has never observed DST, so a
# fixed offset is correct and avoids a tzdata dependency.
EDITION_TZ = timezone(timedelta(hours=5, minutes=30))

# Claude
CLAUDE_MODEL = "claude-sonnet-5"

# World news, bucketed by topic. Each bucket gets its own Claude call and a
# guaranteed number of slots, so finance and geopolitics can't be crowded out
# by whichever tech story happened to look most dramatic that morning.
#
# Reuters and AP killed public RSS, so they're proxied through Google News
# search RSS (free, no key). All feeds below were verified returning entries;
# re-verify before adding more — a dead feed fails silently as an empty list.
_GOOGLE_NEWS = (
    "https://news.google.com/rss/search?q=when:24h+site:{}&hl=en-US&gl=US&ceid=US:en"
)

NEWS_BUCKETS = {
    "Top Stories": {
        "quota": 3,
        "feeds": [
            "https://feeds.bbci.co.uk/news/world/rss.xml",
            "https://www.theguardian.com/world/rss",
            "https://feeds.npr.org/1004/rss.xml",
            _GOOGLE_NEWS.format("apnews.com"),
        ],
    },
    "Finance & Markets": {
        "quota": 3,
        "feeds": [
            "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain",
            "https://www.cnbc.com/id/10000664/device/rss/rss.html",
            "https://feeds.bloomberg.com/markets/news.rss",
            "https://www.economist.com/latest/rss.xml",
            "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
            _GOOGLE_NEWS.format("reuters.com") + "+business",
        ],
    },
    "Geopolitics": {
        "quota": 3,
        "feeds": [
            "https://www.aljazeera.com/xml/rss/all.xml",
            "https://foreignpolicy.com/feed/",
            "https://warontherocks.com/feed/",
            "https://www.defenseone.com/rss/all/",
            "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml",
        ],
    },
    "Tech & AI": {
        "quota": 3,
        "feeds": [
            "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
            "https://techcrunch.com/feed/",
            "https://feeds.arstechnica.com/arstechnica/technology-lab",
            "https://hnrss.org/frontpage",
        ],
    },
}

# Flat list retained for any consumer that just wants every world-news feed.
RSS_FEEDS = [url for b in NEWS_BUCKETS.values() for url in b["feeds"]]

# Twitter/X accounts to track (seed list, customize as needed)
TWITTER_ACCOUNTS = [
    "elonmusk",
    "sama",
    "kaborecrypto",
    "naval",
    "paulg",
    "lexfridman",
    "AndrewYNg",
    "ylecun",
    "jimcramer",
    "WSJ",
    "Reuters",
    "TechCrunch",
    "OpenAI",
    "AnthropicAI",
    "GoogleDeepMind",
]

# Funding Rounds RSS feeds
FUNDING_RSS_FEEDS = [
    "https://techcrunch.com/category/venture/feed/",
    "https://news.crunchbase.com/feed/",
    "https://www.theblock.co/rss/all",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://www.strictlyvc.com/feed/",
    "https://api.axios.com/feed/pro-rata",
    "https://fortune.com/section/term-sheet/feed/",
]

# Funding section tuning
FUNDING_RECENCY_HOURS = 72
FUNDING_DEDUP_DAYS = 7
FUNDING_EARLY_STAGE_COUNT = 6
FUNDING_SIGNAL_COUNT = 2
# URL/title fragments that signal a recap article (drop these to avoid stale rounds)
FUNDING_RECAP_PATTERNS = [
    "biggest-funding-rounds",
    "funding-roundup",
    "weekly-recap",
    "this-week-in-",
    "biggest-rounds-of",
    "week-in-vc",
    "week-in-venture",
    "rounds-recap",
]

# India Startup RSS feeds
INDIA_RSS_FEEDS = [
    "https://inc42.com/feed/",
    "https://yourstory.com/feed",
    "https://economictimes.indiatimes.com/tech/rssfeeds/13357270.cms",
    "https://entrackr.com/feed/",
    "https://www.livemint.com/rss/technology",
]

# YC Batch
MAX_YC_PICKS = 8

# Official YC handle(s) — primary source for the YC section.
# Verify any handle added here actually exists: the X API rejects the whole
# query with a 400 if a single username is unparsable.
YC_TWITTER_ACCOUNTS = ["ycombinator"]
YC_SECTORS_OF_INTEREST = ["AI", "crypto", "fintech", "developer tools", "infrastructure"]

# Limits
MAX_ARTICLES_BEFORE_DEDUP = 50  # per bucket
# World-news volume is now set per bucket via NEWS_BUCKETS[...]["quota"]
MAX_TWEETS_PER_SEARCH = 100
PRODUCT_HUNT_PICK_COUNT = 5
MAX_FUNDING_ITEMS = 8
MAX_INDIA_ITEMS = 8

# MongoDB collection names
MONGO_FEATURED_FUNDING_COLLECTION = "featured_funding_companies"
