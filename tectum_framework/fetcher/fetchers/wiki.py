"""
fetchers/wiki.py — Wikipedia article fetcher via the public REST API.

No external Python dependencies beyond httpx.
Returns structured article data: title, summary, full extract, URL, categories.
"""

from __future__ import annotations

import asyncio
from typing import List, Optional
from urllib.parse import quote

import httpx

WIKI_API = "https://en.wikipedia.org/api/rest_v1"
WIKI_SEARCH = "https://en.wikipedia.org/w/api.php"

HEADERS = {
    "User-Agent": "TectumFetcher/1.0 (cloven@thecloven.com)",
    "Accept": "application/json",
}


async def search(query: str, limit: int = 5) -> List[str]:
    """Returns a list of Wikipedia page titles matching the query."""
    params = {
        "action":   "query",
        "list":     "search",
        "srsearch": query,
        "srlimit":  str(limit),
        "format":   "json",
    }
    try:
        async with httpx.AsyncClient(headers=HEADERS) as client:
            resp = await client.get(WIKI_SEARCH, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return [r["title"] for r in data.get("query", {}).get("search", [])]
    except Exception:
        return []


async def get_article(title: str) -> dict:
    """
    Fetches a Wikipedia article by title.

    Returns:
        {
            "title": str,
            "url": str,
            "summary": str,          # intro paragraph (≤ 1 500 chars)
            "extract": str,          # full text extract (≤ 8 000 chars)
            "categories": [str, ...],
            "ok": bool,
            "error": str | None,
        }
    """
    encoded = quote(title.replace(" ", "_"))
    summary_url  = f"{WIKI_API}/page/summary/{encoded}"
    sections_url = f"{WIKI_API}/page/mobile-sections/{encoded}"

    try:
        async with httpx.AsyncClient(headers=HEADERS) as client:
            summary_resp, sections_resp = await asyncio.gather(
                client.get(summary_url,  timeout=10),
                client.get(sections_url, timeout=10),
                return_exceptions=True,
            )

        summary_data = {}
        if not isinstance(summary_resp, Exception):
            summary_resp.raise_for_status()
            summary_data = summary_resp.json()

        full_text = ""
        categories: List[str] = []
        if not isinstance(sections_resp, Exception):
            sections_resp.raise_for_status()
            sdata = sections_resp.json()
            lead = sdata.get("lead", {})
            sections = lead.get("sections", [])
            if sections:
                full_text = sections[0].get("text", "")[:8000]
            categories = [c.get("name", "") for c in sdata.get("lead", {}).get("categories", [])]

        return {
            "title":      summary_data.get("title", title),
            "url":        summary_data.get("content_urls", {}).get("desktop", {}).get("page", ""),
            "summary":    summary_data.get("extract", "")[:1500],
            "extract":    full_text,
            "categories": categories[:20],
            "ok":         True,
            "error":      None,
        }
    except Exception as exc:
        return {
            "title": title, "url": "", "summary": "", "extract": "",
            "categories": [], "ok": False, "error": str(exc),
        }


async def fetch_for_query(query: str, max_articles: int = 3) -> List[dict]:
    """Search Wikipedia for a query and return up to max_articles full articles."""
    titles = await search(query, limit=max_articles)
    if not titles:
        return []
    results = await asyncio.gather(*[get_article(t) for t in titles])
    return [r for r in results if r["ok"]]
