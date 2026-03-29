# Personal News Aggregator

Daily newspaper-style aggregator with 7 sections, delivered as styled HTML + Telegram message.
Hosted at news.rishotics.com (Vercel), generated daily at 6 AM IST via EC2 cron.

## Sections
1. **World News** - Business, tech, AI, economics, politics from RSS feeds + optional NewsAPI
2. **Funding Rounds** - 5-8 notable AI/crypto/fintech funding rounds from TechCrunch, Crunchbase, The Block, CoinDesk
3. **YC Batch** - 5-8 interesting companies from the latest Y Combinator batch (via Claude web search)
4. **India Startups** - 5-8 items covering Indian startup deals, policy/regulatory updates, and notable launches
5. **X/Twitter Feed** - Summary of tweets from key accounts via X API search (falls back to tech news RSS)
6. **Product Hunt** - 5 randomly picked top products with AI-generated descriptions
7. **AI Research** - Top 8 papers from arxiv + Hugging Face daily papers
8. **Market Ticker** - S&P 500, NASDAQ, Nifty 50, BTC, ETH, SOL, Gold, Oil, USD/INR (no Claude call)

## Tech Stack
- Python 3.11+
- Anthropic SDK (Claude claude-sonnet-4-20250514 for summarization)
- MongoDB (edition storage)
- Telegram Bot API (delivery)
- Jinja2 (HTML templating)

## Project Structure
- `main.py` - Orchestrator, run with `python main.py`
- `config.py` - All configuration, loads .env
- `sections/` - One module per newspaper section
- `services/` - Shared services (claude_client, telegram_bot, mongo_store)
- `templates/newspaper.html` - Jinja2 HTML template
- `output/` - Generated HTML files (gitignored except index.html)
- `deploy/` - EC2 setup scripts

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
- ~7 Claude API calls per run (one per section, market data has none)
- Twitter uses search/recent with `from:` operators; falls back to tech news RSS when credits depleted
- Product Hunt sourced from RSS feed (no API key needed)
- YC batch uses Claude web search as primary data source
- India startups sourced from Inc42, YourStory, ET Tech, Entrackr, Livemint RSS
- AI research from arxiv RSS (cs.AI, cs.CL, cs.CV, cs.LG, cs.RO) + Hugging Face daily papers
