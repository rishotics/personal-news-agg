#!/usr/bin/env python3
"""Personal News Aggregator - generates a daily newspaper and delivers via Telegram."""

import argparse
import logging
import sys
from datetime import datetime, timezone

from jinja2 import Environment, FileSystemLoader

from config import OUTPUT_DIR, TEMPLATES_DIR, MAX_SECTION_FAILURES
from sections import world_news, twitter_feed, product_hunt, market_data, ai_research, funding_rounds, yc_batch, india_startups, this_day
from services import mongo_store, telegram_bot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

SECTION_MAP = {
    "world_news": ("World News", world_news.fetch),
    "funding_rounds": ("Funding Rounds", funding_rounds.fetch),
    "yc_batch": ("YC Batch", yc_batch.fetch),
    "india_startups": ("India Startups", india_startups.fetch),
    "twitter": ("Twitter Feed", twitter_feed.fetch),
    "product_hunt": ("Product Hunt", product_hunt.fetch),
    "ai_research": ("AI Research", ai_research.fetch),
    "this_day": ("This Day", this_day.fetch),
}


def run_section(name: str) -> dict:
    """Run a single section with error handling."""
    display_name, fetcher = SECTION_MAP[name]
    logger.info("Fetching section: %s", display_name)
    try:
        result = fetcher()
        result["status"] = "success"
        return result
    except Exception as e:
        logger.error("Section %s failed: %s", name, e, exc_info=True)
        return {"status": "error", "error": str(e)}


def render_html(context: dict) -> str:
    """Render the newspaper HTML template."""
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("newspaper.html")
    return template.render(**context)


def build_telegram_summary(sections: dict, edition_date: str, markets: dict | None = None) -> str:
    """Build a short Telegram summary message."""
    lines = [f"<b>The Daily Digest - {edition_date}</b>\n"]

    # Market ticker in Telegram
    if markets and markets.get("items"):
        ticker_parts = []
        for m in markets["items"]:
            arrow = "+" if m["change_pct"] >= 0 else ""
            ticker_parts.append(f"{m['name']} {arrow}{m['change_pct']}%")
        lines.append(f"<b>Markets:</b> {' | '.join(ticker_parts[:6])}\n")

    wn = sections.get("world_news", {})
    if wn.get("status") == "success":
        count = wn.get("article_count", 0)
        lines.append(f"<b>World News:</b> {count} curated stories")
    else:
        lines.append("<b>World News:</b> unavailable")

    tw = sections.get("twitter", {})
    if tw.get("status") == "success" and tw.get("tweet_count", 0) > 0:
        count = tw.get("tweet_count", 0)
        lines.append(f"<b>Twitter:</b> {count} tweets analyzed")
    else:
        lines.append("<b>Twitter:</b> unavailable")

    ph = sections.get("product_hunt", {})
    if ph.get("products"):
        names = ", ".join(p.get("name", "?") for p in ph["products"][:3])
        lines.append(f"<b>Product Hunt:</b> {names}...")
    else:
        lines.append("<b>Product Hunt:</b> unavailable")

    fr = sections.get("funding_rounds", {})
    early = fr.get("early_stage") or []
    signal = fr.get("later_stage_signal") or []
    if early or signal:
        parts = []
        if early:
            top = early[0]
            parts.append(f"top: {top.get('company', '')} ({top.get('round_type', '')} {top.get('amount', '')})")
        lines.append(f"<b>Funding:</b> {len(early)} early-stage, {len(signal)} signal — {' / '.join(parts) if parts else ''}")
    else:
        lines.append("<b>Funding:</b> unavailable")

    yc = sections.get("yc_batch", {})
    if yc.get("companies"):
        lines.append(f"<b>YC {yc.get('batch', '')}:</b> {yc.get('company_count', 0)} picks")
    else:
        lines.append("<b>YC Batch:</b> unavailable")

    india = sections.get("india_startups", {})
    if india.get("items"):
        bd = india.get("breakdown", {})
        parts = [f"{v} {k}s" for k, v in bd.items()]
        lines.append(f"<b>India:</b> {', '.join(parts)}")
    else:
        lines.append("<b>India:</b> unavailable")

    ar = sections.get("ai_research", {})
    if ar.get("papers"):
        paper = ar["papers"][0]
        lines.append(f"<b>Paper of the Day:</b> {paper.get('title', '')[:70]}")
        for point in paper.get("why_points", [])[:5]:
            lines.append(f"  • {point}")
    else:
        lines.append("<b>Paper of the Day:</b> unavailable")

    td = sections.get("this_day", {})
    if td.get("story"):
        lines.append(f"\n<b>This Day — {td.get('occasion', '')}</b>")
        for line in td["story"]:
            lines.append(f"  {line}")
    if td.get("history"):
        lines.append("\n<b>On This Day in History</b>")
        for h in td["history"]:
            lines.append(f"  • <b>{h.get('year', '')}</b> — {h.get('event', '')}")

    lines.append('\n<a href="https://news.rishotics.com">Read full edition</a>')
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate daily newspaper")
    parser.add_argument("--section", choices=list(SECTION_MAP.keys()), help="Run a single section only")
    parser.add_argument("--no-telegram", action="store_true", help="Skip Telegram delivery")
    parser.add_argument("--no-mongo", action="store_true", help="Skip MongoDB storage")
    parser.add_argument(
        "--skip-if-exists",
        action="store_true",
        help="Exit early if today's edition was already published (for delayed/backup runs)",
    )
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    edition_date = now.strftime("%B %d, %Y")
    date_str = now.strftime("%Y-%m-%d")

    # Check for existing edition. GitHub's scheduler can deliver a cron hours
    # late, so a run that arrives after the edition is already out should stand
    # down rather than burn API calls and send a duplicate Telegram.
    if not args.no_mongo and not args.section:
        existing = mongo_store.get_edition_by_date(date_str)
        if existing:
            if args.skip_if_exists:
                logger.info(
                    "Edition for %s already published (edition %s). Nothing to do.",
                    date_str, existing.get("edition_number", "?"),
                )
                return
            logger.warning("Edition for %s already exists. Generating a new one.", date_str)

    # Fetch market data (not a "section" — always runs, no Claude call)
    logger.info("Fetching market data")
    try:
        markets = market_data.fetch()
    except Exception as e:
        logger.error("Market data failed: %s", e)
        markets = {"items": []}

    # Run sections
    if args.section:
        sections = {args.section: run_section(args.section)}
        # Fill other sections with placeholders for HTML rendering
        for name in SECTION_MAP:
            if name not in sections:
                sections[name] = {"status": "error", "error": "Section not requested"}
    else:
        sections = {}
        for name in SECTION_MAP:
            sections[name] = run_section(name)

    # Get edition number
    edition_number = mongo_store.get_next_edition_number() if not args.no_mongo else 0

    # Render HTML
    context = {
        "edition_date": edition_date,
        "edition_number": edition_number,
        "world_news": sections.get("world_news", {}),
        "twitter": sections.get("twitter", {}),
        "product_hunt": sections.get("product_hunt", {}),
        "ai_research": sections.get("ai_research", {}),
        "funding_rounds": sections.get("funding_rounds", {}),
        "yc_batch": sections.get("yc_batch", {}),
        "india_startups": sections.get("india_startups", {}),
        "this_day": sections.get("this_day", {}),
        # Rename 'items' key to avoid clash with dict.items() in Jinja2
        "india_news": sections.get("india_startups", {}).get("items", []),
        "markets": markets.get("items", []),
        "generated_at": now.strftime("%Y-%m-%d %H:%M UTC"),
    }

    # Health check. A single-section run is expected to "fail" the others, so
    # only judge a full edition.
    failed = [n for n, s in sections.items() if s.get("status") != "success"]
    degraded = not args.section and len(failed) > MAX_SECTION_FAILURES
    if failed:
        logger.warning("%d/%d sections failed: %s", len(failed), len(SECTION_MAP), ", ".join(failed))
    if degraded:
        logger.error(
            "DEGRADED: %d of %d sections failed (threshold %d). Not publishing "
            "over the last good edition.",
            len(failed), len(SECTION_MAP), MAX_SECTION_FAILURES,
        )

    html = render_html(context)
    OUTPUT_DIR.mkdir(exist_ok=True)
    html_path = OUTPUT_DIR / f"newspaper_{date_str}.html"
    html_path.write_text(html, encoding="utf-8")

    if degraded:
        # Keep the dated snapshot for debugging, but leave index.html alone so
        # the site keeps yesterday's real edition instead of a hollow one.
        logger.info("HTML saved to %s (index.html left untouched)", html_path)
    else:
        latest_path = OUTPUT_DIR / "index.html"
        latest_path.write_text(html, encoding="utf-8")
        logger.info("HTML saved to %s (+ index.html)", html_path)

    # Save to MongoDB
    if not args.no_mongo and not args.section and not degraded:
        edition = {
            "edition_number": edition_number,
            "date": date_str,
            "sections": sections,
            "html_path": str(html_path),
            "telegram_sent": False,
        }
        mongo_store.save_edition(edition)

        # Record featured funding companies for 7-day dedup
        fr = sections.get("funding_rounds", {})
        if fr.get("status") == "success":
            featured = (fr.get("early_stage") or []) + (fr.get("later_stage_signal") or [])
            try:
                mongo_store.record_featured_companies(featured, date_str)
            except Exception as e:
                logger.warning("Failed to record featured funding companies: %s", e)

    # Send via Telegram
    if not args.no_telegram and not args.section:
        if degraded:
            telegram_bot.send_summary(
                f"<b>Daily Digest FAILED - {edition_date}</b>\n\n"
                f"{len(failed)} of {len(SECTION_MAP)} sections failed: "
                f"{', '.join(failed)}\n\n"
                "Edition not published; the site still shows the last good one."
            )
            logger.info("Sent failure alert to Telegram")
        else:
            summary = build_telegram_summary(sections, edition_date, markets)
            telegram_bot.send_summary(summary)
            telegram_bot.send_html_file(html_path, caption=f"Daily Digest - {edition_date}")
            logger.info("Sent to Telegram")

    if degraded:
        logger.error("Exiting non-zero so the scheduled run reports failure.")
        sys.exit(1)

    logger.info("Done! Edition %d for %s", edition_number, date_str)


if __name__ == "__main__":
    main()
