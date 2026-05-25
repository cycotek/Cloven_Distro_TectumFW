"""
crawler.py — Ant Crawler

Citation-graph traversal for news and web content.

Strategy:
  1. Seed URLs come from RSS feeds or a DuckDuckGo Lite search
  2. Each page is fetched and scored:
       - primary source score (0–1): inverse of citation depth
       - derivative score: are there "via", "according to", "report says" markers?
       - political lean: domain lookup
  3. The crawler follows outbound links up to `max_hops` deep,
     preferring links that contain seed keywords
  4. A time budget enforces the research mode limits

Designed to work within Docker with no headless browser — httpx + BeautifulSoup only.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import List, Optional, Set
from urllib.parse import urljoin, urlparse

import httpx

from fetchers.web import fetch_page

# Markers that suggest this article is derivative (cites another source)
_DERIVATIVE_MARKERS = re.compile(
    r"\b(according to|reported by|cited by|via |sourced from|as reported|per |"
    r"citing|quoting|the \w+ reports|says the|told reporters)\b",
    re.IGNORECASE,
)

# Domains to skip (social media, trackers, etc.)
_SKIP_DOMAINS = {
    "twitter.com", "x.com", "facebook.com", "instagram.com", "tiktok.com",
    "linkedin.com", "youtube.com", "reddit.com", "pinterest.com",
    "t.co", "bit.ly", "tinyurl.com", "ow.ly", "goo.gl",
    "doubleclick.net", "googletagmanager.com", "googlesyndication.com",
}


def _is_skippable(url: str) -> bool:
    host = urlparse(url).netloc.removeprefix("www.")
    return any(host == d or host.endswith("." + d) for d in _SKIP_DOMAINS)


def _primary_score(content: str, hop: int) -> float:
    """
    Heuristic: fewer derivative markers + shallower hop → more primary.
    Returns a float in [0, 1].
    """
    marker_count = len(_DERIVATIVE_MARKERS.findall(content))
    marker_penalty = min(marker_count * 0.1, 0.5)
    hop_penalty    = min(hop * 0.2, 0.6)
    return max(0.0, round(1.0 - marker_penalty - hop_penalty, 2))


def _keyword_relevance(url: str, title: str, content: str, keywords: List[str]) -> float:
    """How many query keywords appear in title+content? Normalised to [0,1]."""
    if not keywords:
        return 0.5
    text = (url + " " + title + " " + content[:500]).lower()
    hits = sum(1 for kw in keywords if kw.lower() in text)
    return round(hits / len(keywords), 2)


async def _ddg_search(query: str, max_results: int = 8) -> List[str]:
    """
    DuckDuckGo Lite HTML search — no API key, no JS.
    Returns a list of result URLs.
    """
    try:
        params = {"q": query, "kl": "us-en"}
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(
                "https://lite.duckduckgo.com/lite/",
                params=params,
                headers={"User-Agent": "TectumFetcher/1.0"},
                timeout=10,
            )
            resp.raise_for_status()
            # Extract links from the lite HTML (href= targets)
            urls = re.findall(r'href="(https?://[^"]{10,})"', resp.text)
            # Filter out DDG-internal URLs
            urls = [u for u in urls if "duckduckgo.com" not in u][:max_results]
            return urls
    except Exception:
        return []


async def crawl(
    queries: List[str],
    keywords: List[str],
    max_pages: int = 20,
    max_hops: int = 2,
    time_limit_seconds: float = 120.0,
    seed_urls: Optional[List[str]] = None,
) -> List[dict]:
    """
    Ant crawler entry point.

    Args:
        queries:              expanded search queries from the optimizer
        keywords:             keywords to score relevance against
        max_pages:            hard cap on total pages fetched
        max_hops:             citation graph depth (0 = seeds only)
        time_limit_seconds:   wall-clock budget
        seed_urls:            optional pre-supplied URLs (skip search step)

    Returns:
        List of page result dicts, sorted by primary_score * relevance desc.
        Each dict: {url, title, content, hop, primary_score, relevance, lean, ok}
    """
    deadline = time.monotonic() + time_limit_seconds

    # 1. Seed phase — gather initial URLs via search or supplied list
    seeds: List[str] = list(seed_urls or [])
    if not seeds:
        search_results = await asyncio.gather(
            *[_ddg_search(q, max_results=5) for q in queries[:3]]
        )
        for batch in search_results:
            seeds.extend(batch)

    # De-duplicate seeds
    seen_urls: Set[str] = set()
    frontier: List[tuple[str, int]] = []  # (url, hop)
    for u in seeds:
        if u not in seen_urls and not _is_skippable(u):
            seen_urls.add(u)
            frontier.append((u, 0))

    results: List[dict] = []

    # 2. BFS crawl — share one httpx client across all fetches to reuse the
    # connection pool (eliminates TCP+TLS setup per URL).  BeautifulSoup HTML
    # parsing runs in a thread pool inside fetch_page so the event loop stays
    # free for concurrent HTTP I/O.  Batch size raised from 5 → 10.
    async with httpx.AsyncClient(
        headers={"User-Agent": "TectumFetcher/1.0"},
        follow_redirects=True,
    ) as shared_client:
        while frontier and len(results) < max_pages:
            if time.monotonic() > deadline:
                break

            batch_size = min(10, len(frontier), max_pages - len(results))
            batch, frontier = frontier[:batch_size], frontier[batch_size:]

            pages = await asyncio.gather(
                *[fetch_page(url, client=shared_client) for url, _ in batch]
            )

            for (url, hop), page in zip(batch, pages):
                if time.monotonic() > deadline:
                    break
                if not page["ok"]:
                    continue

                ps  = _primary_score(page["content"], hop)
                rel = _keyword_relevance(url, page["title"], page["content"], keywords)

                results.append({
                    "url":           url,
                    "title":         page["title"],
                    "content":       page["content"],
                    "hop":           hop,
                    "primary_score": ps,
                    "relevance":     rel,
                    "lean":          page["lean"],
                    "ok":            True,
                })

                # Queue child links if we have hop budget left
                if hop < max_hops:
                    for link in page.get("links", []):
                        if (link not in seen_urls and not _is_skippable(link)
                                and len(frontier) < 100):
                            seen_urls.add(link)
                            frontier.append((link, hop + 1))

    # Sort: primary_score * relevance desc
    results.sort(key=lambda r: r["primary_score"] * r["relevance"], reverse=True)
    return results
