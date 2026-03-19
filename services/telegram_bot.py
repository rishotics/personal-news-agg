import logging
from pathlib import Path

import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def send_summary(text: str) -> bool:
    """Send an HTML-formatted text message to the configured Telegram chat."""
    resp = requests.post(
        f"{BASE_URL}/sendMessage",
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        },
        timeout=30,
    )
    if not resp.ok:
        logger.error("Telegram sendMessage failed: %s", resp.text)
    return resp.ok


def send_html_file(filepath: Path, caption: str = "") -> bool:
    """Send an HTML file as a document to the configured Telegram chat."""
    with open(filepath, "rb") as f:
        resp = requests.post(
            f"{BASE_URL}/sendDocument",
            data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption},
            files={"document": (filepath.name, f, "text/html")},
            timeout=60,
        )
    if not resp.ok:
        logger.error("Telegram sendDocument failed: %s", resp.text)
    return resp.ok
