import logging

import anthropic

from config import CLAUDE_MODEL

logger = logging.getLogger(__name__)

_client = anthropic.Anthropic()

_model_checked = False


def _check_model(response) -> None:
    """Warn once if the API served a different model than we configured.

    A retired model 404s loudly, which the section-failure threshold catches.
    This covers the quieter case: an alias silently resolving somewhere else.
    Warn rather than raise — a working pipeline shouldn't die over an ID that
    differs only cosmetically.
    """
    global _model_checked
    if _model_checked:
        return
    _model_checked = True
    served = getattr(response, "model", "") or ""
    if not served.startswith(CLAUDE_MODEL):
        logger.warning(
            "Model mismatch: configured %r but API served %r", CLAUDE_MODEL, served
        )


def search_and_summarize(system_prompt: str, query: str, max_tokens: int = 8192) -> str:
    """Use Claude with web search tool to find and summarize information."""
    try:
        response = _client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
            messages=[{"role": "user", "content": query}],
        )
        _check_model(response)
        # Extract text blocks from response (may include tool use blocks)
        texts = [block.text for block in response.content if hasattr(block, "text")]
        return "\n".join(texts)
    except Exception as e:
        logger.error("search_and_summarize failed: %s", e)
        raise


def summarize(system_prompt: str, content: str, max_tokens: int = 6144) -> str:
    """Send content to Claude for summarization/curation."""
    # Thinking is on by default from Sonnet 5 onward and shares the max_tokens
    # budget with the response. These are straight text-in/text-out curation
    # calls, so keep it off to avoid truncating a section mid-output.
    kwargs = {
        "model": CLAUDE_MODEL,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "thinking": {"type": "disabled"},
        "messages": [{"role": "user", "content": content}],
    }
    try:
        response = _client.messages.create(**kwargs)
        _check_model(response)
        return response.content[0].text
    except anthropic.APIStatusError as e:
        if e.status_code >= 500:
            logger.warning("Claude API 5xx, retrying once: %s", e)
            response = _client.messages.create(**kwargs)
            _check_model(response)
            return response.content[0].text
        raise
