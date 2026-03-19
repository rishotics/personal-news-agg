import logging

import anthropic

from config import CLAUDE_MODEL

logger = logging.getLogger(__name__)

_client = anthropic.Anthropic()


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
