import logging
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

# CoinGecko free API (no key needed)
COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"

# Yahoo Finance v8 quote endpoint (works without auth with crumb workaround)
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/"

INDICES = [
    {"symbol": "^GSPC", "name": "S&P 500"},
    {"symbol": "^IXIC", "name": "NASDAQ"},
    {"symbol": "^DJI", "name": "Dow Jones"},
    {"symbol": "^NSEI", "name": "Nifty 50"},
    {"symbol": "^BSESN", "name": "Sensex"},
    {"symbol": "^FTSE", "name": "FTSE 100"},
    {"symbol": "^N225", "name": "Nikkei 225"},
]

COMMODITIES = [
    {"symbol": "GC=F", "name": "Gold"},
    {"symbol": "CL=F", "name": "Crude Oil"},
]

FOREX = [
    {"symbol": "INR=X", "name": "USD/INR"},
]

CRYPTO_IDS = {
    "bitcoin": "BTC",
    "solana": "SOL",
    "ethereum": "ETH",
}


@dataclass
class MarketItem:
    name: str
    price: float
    change_pct: float  # daily % change
    category: str  # "index", "crypto", "commodity", "forex"


def _fetch_yahoo(symbols: list[dict], category: str) -> list[MarketItem]:
    """Fetch quotes from Yahoo Finance using chart endpoint."""
    items = []
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

    for sym in symbols:
        try:
            resp = requests.get(
                f"{YAHOO_URL}{sym['symbol']}",
                params={"range": "1d", "interval": "1d"},
                headers=headers,
                timeout=10,
            )
            if not resp.ok:
                logger.warning("Yahoo Finance %s returned %d", sym["symbol"], resp.status_code)
                continue

            data = resp.json()
            result = data.get("chart", {}).get("result", [{}])[0]
            meta = result.get("meta", {})
            price = meta.get("regularMarketPrice", 0)
            prev_close = meta.get("chartPreviousClose", meta.get("previousClose", 0))
            change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0

            items.append(MarketItem(
                name=sym["name"],
                price=price,
                change_pct=change_pct,
                category=category,
            ))
        except Exception as e:
            logger.warning("Yahoo Finance fetch failed for %s: %s", sym["symbol"], e)

    return items


def _fetch_crypto() -> list[MarketItem]:
    """Fetch crypto prices from CoinGecko."""
    items = []
    try:
        resp = requests.get(
            COINGECKO_URL,
            params={
                "ids": ",".join(CRYPTO_IDS.keys()),
                "vs_currencies": "usd",
                "include_24hr_change": "true",
            },
            timeout=15,
        )
        if not resp.ok:
            logger.warning("CoinGecko returned %d", resp.status_code)
            return items

        data = resp.json()
        for coin_id, ticker in CRYPTO_IDS.items():
            if coin_id in data:
                items.append(MarketItem(
                    name=ticker,
                    price=data[coin_id].get("usd", 0),
                    change_pct=data[coin_id].get("usd_24h_change", 0),
                    category="crypto",
                ))
    except Exception as e:
        logger.warning("CoinGecko fetch failed: %s", e)

    return items


def fetch() -> dict:
    """Fetch all market data."""
    indices = _fetch_yahoo(INDICES, "index")
    commodities = _fetch_yahoo(COMMODITIES, "commodity")
    forex = _fetch_yahoo(FOREX, "forex")
    crypto = _fetch_crypto()

    all_items = indices + crypto + commodities + forex
    logger.info("Fetched %d market data points", len(all_items))

    return {
        "items": [
            {
                "name": item.name,
                "price": item.price,
                "change_pct": round(item.change_pct, 2),
                "category": item.category,
            }
            for item in all_items
        ],
    }
