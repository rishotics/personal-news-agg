import json
import logging

from config import MAX_YC_PICKS
from services.claude_client import search_and_summarize

logger = logging.getLogger(__name__)


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


def fetch() -> dict:
    """Fetch interesting YC companies using Claude web search."""
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
        "company_count": len(companies),
    }
