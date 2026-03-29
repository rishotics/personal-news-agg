import json
import logging
from datetime import datetime, timedelta, timezone

import feedparser
import requests

from services.claude_client import summarize

logger = logging.getLogger(__name__)

# arxiv RSS feeds for key AI/robotics categories
ARXIV_FEEDS = [
    "https://rss.arxiv.org/rss/cs.AI",   # Artificial Intelligence
    "https://rss.arxiv.org/rss/cs.CL",   # Computation and Language (NLP)
    "https://rss.arxiv.org/rss/cs.CV",   # Computer Vision
    "https://rss.arxiv.org/rss/cs.LG",   # Machine Learning
    "https://rss.arxiv.org/rss/cs.RO",   # Robotics
]

# Hugging Face daily papers
HF_PAPERS_URL = "https://huggingface.co/api/daily_papers"

# Key labs/orgs to prioritize (papers from these get boosted)
PRIORITY_ORGS = [
    "openai", "anthropic", "deepmind", "google", "meta", "microsoft",
    "nvidia", "apple", "amazon", "ibm", "mistral", "deepseek",
    "alibaba", "qwen", "tencent", "bytedance", "shanghai",
    "stanford", "mit", "cmu", "berkeley", "princeton", "toronto",
    "vector institute", "mila", "eth zurich", "oxford",
    "boston dynamics", "figure", "tesla", "toyota research",
    "physical intelligence", "allen institute", "ai2", "eleutherai",
    "tsinghua", "baidu", "kaist",
]


def _fetch_arxiv_papers() -> list[dict]:
    """Fetch recent papers from arxiv RSS feeds."""
    papers = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=3)

    for feed_url in ARXIV_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            category = feed_url.split("/")[-1]
            for entry in feed.entries[:30]:
                title = entry.get("title", "").replace("\n", " ").strip()
                if not title:
                    continue

                # Parse authors
                authors = ""
                if entry.get("authors"):
                    author_names = [a.get("name", "") for a in entry.authors[:5]]
                    authors = ", ".join(author_names)
                elif entry.get("author"):
                    authors = entry.author

                summary = entry.get("summary", "")[:500].replace("\n", " ").strip()
                url = entry.get("link", "")
                published = entry.get("published", "")

                # Deduplicate by title
                if not any(p["title"] == title for p in papers):
                    papers.append({
                        "title": title,
                        "authors": authors,
                        "summary": summary,
                        "url": url,
                        "category": category,
                        "published": published,
                    })
        except Exception as e:
            logger.warning("Failed to fetch arxiv %s: %s", feed_url, e)

    logger.info("Fetched %d papers from arxiv", len(papers))
    return papers


def _fetch_hf_papers() -> list[dict]:
    """Fetch trending papers from Hugging Face daily papers API."""
    papers = []
    try:
        resp = requests.get(HF_PAPERS_URL, timeout=15)
        if resp.ok:
            for item in resp.json()[:20]:
                paper = item.get("paper", {})
                title = paper.get("title", "")
                if not title:
                    continue
                authors = ", ".join(
                    a.get("name", "") for a in paper.get("authors", [])[:5]
                )
                papers.append({
                    "title": title,
                    "authors": authors,
                    "summary": paper.get("summary", "")[:500].replace("\n", " "),
                    "url": f"https://huggingface.co/papers/{paper.get('id', '')}",
                    "category": "trending",
                    "upvotes": item.get("numLikes", 0),
                })
        else:
            logger.warning("HF papers API returned %d", resp.status_code)
    except Exception as e:
        logger.warning("Failed to fetch HF papers: %s", e)

    logger.info("Fetched %d papers from Hugging Face", len(papers))
    return papers


def _deduplicate(papers: list[dict]) -> list[dict]:
    """Deduplicate papers by title similarity."""
    seen_titles = set()
    unique = []
    for paper in papers:
        title_key = paper["title"].lower().strip()[:80]
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            unique.append(paper)
    return unique


def fetch() -> dict:
    """Fetch and curate top AI/robotics papers."""
    arxiv_papers = _fetch_arxiv_papers()
    hf_papers = _fetch_hf_papers()

    all_papers = hf_papers + arxiv_papers  # HF first (already trending/curated)
    all_papers = _deduplicate(all_papers)

    if not all_papers:
        return {
            "papers": [],
            "status_note": "No papers available today.",
        }

    logger.info("Total unique papers: %d", len(all_papers))

    # Build content for Claude
    papers_text = "\n\n".join(
        f"Title: {p['title']}\nAuthors: {p['authors']}\nCategory: {p['category']}\n"
        f"URL: {p['url']}\nSummary: {p['summary'][:300]}"
        for p in all_papers[:60]
    )

    priority_list = ", ".join(PRIORITY_ORGS[:20])

    system_prompt = f"""You are an AI research editor curating a daily "Papers to Read" column.
From the papers below, select the 8 most important and interesting ones.

Prioritize papers from these top labs: {priority_list}
Also prioritize: breakthrough results, new model releases, novel architectures, robotics advances, and papers with practical impact.

For each selected paper, provide:
- title (original paper title)
- authors (first 2-3 authors)
- lab (the institution/company, inferred from authors or content)
- why (1 sentence on why this paper matters)
- category (one of: LLM, Vision, Robotics, ML Theory, Multimodal, Safety, Agents, Other)
- url (original URL)

Return ONLY a valid JSON array (no markdown, no code blocks, no extra text): a list of objects with keys: title, authors, lab, why, category, url."""

    response = summarize(system_prompt, papers_text)

    try:
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        # Handle truncated JSON — find the last complete object
        if not text.endswith("]"):
            last_brace = text.rfind("}")
            if last_brace > 0:
                text = text[:last_brace + 1] + "]"
        curated = json.loads(text)
    except json.JSONDecodeError:
        logger.error("Failed to parse AI research summary as JSON")
        curated = []

    return {"papers": curated}
