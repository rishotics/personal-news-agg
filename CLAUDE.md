# Personal News Aggregator

Daily newspaper-style aggregator with 3 sections, delivered as styled HTML + Telegram message.

## Sections
1. **World News** - Business, tech, AI, economics, politics from RSS feeds + optional NewsAPI
2. **X/Twitter Feed** - Summary of tweets from key accounts via X API search
3. **Product Hunt** - 5 randomly picked top products with AI-generated descriptions

## Tech Stack
- Python 3.11+
- Anthropic SDK (Claude claude-sonnet-4-20250514 for summarization)
- MongoDB (edition storage)
- Telegram Bot API (delivery)
- Jinja2 (HTML templating)

## Project Structure
- `main.py` - Orchestrator, run with `python main.py`
- `config.py` - All configuration, loads .env
- `sections/` - One module per newspaper section (world_news, twitter_feed, product_hunt)
- `services/` - Shared services (claude_client, telegram_bot, mongo_store)
- `templates/newspaper.html` - Jinja2 HTML template
- `output/` - Generated HTML files (gitignored)

## Running
```bash
pip install -r requirements.txt
python main.py                    # full newspaper
python main.py --section world_news  # single section test
```

## Environment Variables (.env)
- `ANTHROPIC_API_KEY` - Claude API access
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` - Telegram delivery
- `MONGODB_URI` - MongoDB connection string
- `X_BEARER_TOKEN` - Twitter/X API bearer token
- `NEWS_API_KEY` (optional) - NewsAPI.org key for additional news sources

## Design Principles
- Each section fails independently (graceful degradation)
- ~3 Claude API calls per run (one per section)
- Twitter uses search/recent with `from:` operators (app-only auth limitation)
- Product Hunt scraped from front page (no API key needed)
