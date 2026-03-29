import logging

import anthropic

from config import CLAUDE_MODEL

logger = logging.getLogger(__name__)

_client = anthropic.Anthropic()


def search_and_summarize(system_prompt: str, query: str, max_tokens: int = 4096) -> str:
    """Use Claude with web search tool to find and summarize information."""
    try:
        response = _client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
            messages=[{"role": "user", "content": query}],
        )
        # Extract text blocks from response (may include tool use blocks)
        texts = [block.text for block in response.content if hasattr(block, "text")]
        return "\n".join(texts)
    except Exception as e:
        logger.error("search_and_summarize failed: %s", e)
        raise


def summarize(system_prompt: str, content: str, max_tokens: int = 4096) -> str:
    """Send content to Claude for summarization/curation."""
    try:
        response = _client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": content}],
        )
        return response.content[0].text
    except anthropic.APIStatusError as e:
        if e.status_code >= 500:
            logger.warning("Claude API 5xx, retrying once: %s", e)
            response = _client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": content}],
            )
            return response.content[0].text
        raise
