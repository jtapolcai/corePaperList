"""LLM-based paper classification verification.

Uses Claude to check whether a paper was correctly identified as a full paper
(vs. short paper, poster, demo, workshop paper, extended abstract, etc.).

Requires ANTHROPIC_API_KEY environment variable.
"""
import json
import re
import sys
import os
import time
from pathlib import Path
from typing import Optional

_parent = os.path.dirname(os.path.dirname(__file__))
if _parent not in sys.path:
    sys.path.insert(0, _parent)

from src.classify_paper import get_paper_length

# Cache file for LLM results (avoids re-calling on every run)
CACHE_PATH = Path(__file__).resolve().parent.parent / "results" / "llm_verify_cache.json"

_PROMPT = """You are reviewing a CS conference or journal paper to check whether it was correctly identified as a FULL paper.

Paper details:
- Title: {title}
- Venue: {venue} ({year})
- Pages: "{pages}"{page_info}
- CORE rank assigned: {rank}

Determine: is this likely a SHORT/POSTER/DEMO/WORKSHOP paper rather than a full paper?

Clear indicators of a short paper:
- Title starts with: "Short Paper:", "Poster:", "Demo:", "Extended Abstract:", "Position Paper:", "Industry Paper:", "Invited Paper:", "Tutorial:", "Work-in-Progress:"
- Title contains keywords: "(short)", "(poster)", "(demo)", "(abstract)", "vision paper", "position statement"
- Page count ≤ 4 is a strong signal; 5–6 pages is borderline depending on venue
- Note: some venues (e.g. SOSP, OSDI) have 2-page position papers that ARE full contributions

Respond ONLY with valid JSON (no markdown, no explanation outside JSON):
{{"likely_short_paper": true/false, "confidence": "high|medium|low", "reason": "one sentence"}}"""


def _get_client():
    try:
        import anthropic
        return anthropic.Anthropic()
    except ImportError:
        raise ImportError("anthropic package not installed; run: pip install anthropic")


def verify_paper(paper: dict, rank: str, client=None) -> dict:
    """Verify a single paper via LLM.

    Args:
        paper: paper dict with keys title, venue, year, pages
        rank: CORE rank string ("A*", "A", "B", "C", "no_rank")
        client: optional pre-created anthropic.Anthropic() client

    Returns dict with keys:
        flagged (bool): True if LLM thinks it's a short/wrong paper
        confidence: "high" | "medium" | "low"
        reason: one-sentence explanation
    """
    if client is None:
        client = _get_client()

    title = paper.get("title", "")
    venue = paper.get("venue", "")
    year = paper.get("year", "")
    pages = paper.get("pages", "")

    page_count = get_paper_length(pages)
    page_info = f" → {page_count} pages" if page_count is not None else ""

    prompt = _PROMPT.format(
        title=title, venue=venue, year=year,
        pages=pages, page_info=page_info, rank=rank,
    )

    try:
        response = client.messages.create(
            model="claude-haiku-5-5",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            result = json.loads(m.group())
            return {
                "flagged": bool(result.get("likely_short_paper", False)),
                "confidence": result.get("confidence", "low"),
                "reason": result.get("reason", ""),
            }
    except Exception as e:
        return {"flagged": False, "confidence": "low", "reason": f"LLM error: {e}"}

    return {"flagged": False, "confidence": "low", "reason": "no parseable response"}


def load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2, ensure_ascii=False))


def verify_papers_batch(
    papers: dict,
    rank: str,
    client=None,
    cache: Optional[dict] = None,
    force: bool = False,
    sleep: float = 0.15,
    on_result=None,
) -> list[dict]:
    """Verify a dict of papers (key→paper) for a given rank.

    Returns a list of flagged paper dicts (each has 'key', 'rank', 'paper',
    'flagged', 'confidence', 'reason').
    """
    if client is None:
        client = _get_client()
    if cache is None:
        cache = {}

    flagged = []
    for key, paper in papers.items():
        if key in cache and not force:
            result = cache[key]
        else:
            result = verify_paper(paper, rank, client)
            result["rank"] = rank
            cache[key] = result
            if sleep:
                time.sleep(sleep)

        if result.get("flagged"):
            entry = {"key": key, "rank": rank, "paper": paper, **result}
            flagged.append(entry)

        if on_result:
            on_result(key, paper, result)

    return flagged
