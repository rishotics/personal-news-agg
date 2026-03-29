import os
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

# Claude
CLAUDE_MODEL = "claude-sonnet-4-20250514"

# RSS Feeds for world news
RSS_FEEDS = [
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
    "https://feeds.reuters.com/reuters/businessNews",
    "https://hnrss.org/frontpage",
    "https://techcrunch.com/feed/",
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml",
]

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
YC_SECTORS_OF_INTEREST = ["AI", "crypto", "fintech", "developer tools", "infrastructure"]

# Limits
MAX_ARTICLES_BEFORE_DEDUP = 50
MAX_CURATED_ARTICLES = 10
MAX_TWEETS_PER_SEARCH = 100
PRODUCT_HUNT_PICK_COUNT = 5
MAX_FUNDING_ITEMS = 8
MAX_INDIA_ITEMS = 8
