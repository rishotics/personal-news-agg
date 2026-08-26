import json
import logging
from datetime import datetime, timezone

from services.claude_client import search_and_summarize

logger = logging.getLogger(__name__)


def _parse_json_object(response: str) -> dict:
    """Pull a JSON object out of Claude's response."""
    text = response.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    return json.loads(text)


def fetch() -> dict:
    """Today's significance in Hindu tradition, plus notable events in history.

    Hindu festivals follow a lunar calendar, so the tithi and any observance
    shift against the Gregorian date every year. This uses web search rather
    than model recall so the panchang details are grounded rather than guessed.
    """
    now = datetime.now(timezone.utc)
    date_long = now.strftime("%B %d, %Y")
    day_month = now.strftime("%B %d")

    system_prompt = """You write the "This Day" column of a daily newspaper. It has two parts.

PART 1 — Hindu tradition. Report what the Hindu calendar says about this specific date, then tell the story behind it.
- Use the panchang details you find in search: tithi, paksha, and the Hindu month.
- If a named festival, vrat, or jayanti falls today, that is the subject.
- If no major festival falls today, do NOT invent one. Use the genuine significance of the tithi itself (for example Ekadashi, Purnima, Amavasya, Chaturthi, Pradosh) and the deity or observance traditionally associated with it.
- Write the story in 5-6 lines. Each line is one sentence, plain prose, no bullet characters or numbering.
- Narrate it as tradition holds, the way a storyteller would. Name the figures involved and what actually happens in the story. Close with what the day asks of people who observe it.
- Be respectful and accurate. Do not blend separate legends together, and do not present contested details as settled.

PART 2 — On this day in world history. Pick the 3 most consequential events that happened on this calendar date in past years.
- Prefer events whose effects are still legible today over trivia.
- Range widely across eras and regions; avoid three events from one country or one century.
- For each: the year, one sentence on what happened, and one short clause on why it still matters.

Return ONLY a valid JSON object, no markdown or code fences, with keys:
- "hindu_occasion": short name of the day, e.g. "Shravana Purnima" or "Krishna Paksha Ekadashi"
- "hindu_panchang": one short line with tithi, paksha, and Hindu month
- "hindu_story": array of 5 or 6 strings, one sentence each
- "history": array of exactly 3 objects with keys "year", "event", "why"
"""

    query = f"""For today, {date_long}:

1. Find the Hindu panchang for {date_long}: the tithi, paksha, Hindu month, and any festival, vrat, jayanti or observance falling on this date. Search for "Hindu calendar {date_long} panchang tithi" and "Hindu festival {date_long}".

2. Find the most significant events in world history that occurred on {day_month} in any past year.

Then write the column as specified."""

    response = search_and_summarize(system_prompt, query, max_tokens=8192)

    try:
        data = _parse_json_object(response)
    except json.JSONDecodeError:
        logger.error("Failed to parse This Day JSON")
        raise

    story = [str(s).strip() for s in (data.get("hindu_story") or []) if str(s).strip()]
    history = [h for h in (data.get("history") or []) if h.get("event")]

    if len(story) < 5:
        logger.warning("This Day: hindu_story has only %d lines", len(story))
    if len(history) < 3:
        logger.warning("This Day: only %d history events", len(history))

    logger.info(
        "This Day: %s (%d story lines, %d events)",
        data.get("hindu_occasion", "?"), len(story), len(history),
    )

    return {
        "date_label": date_long,
        "occasion": data.get("hindu_occasion", ""),
        "panchang": data.get("hindu_panchang", ""),
        "story": story[:6],
        "history": history[:3],
    }
