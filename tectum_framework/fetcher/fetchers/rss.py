"""
fetchers/rss.py — RSS/Atom feed fetcher.

Fetches a curated set of feeds (or user-supplied URLs) and returns recent entries
with title, link, summary, published date, and source lean annotation.
"""

from __future__ import annotations

import asyncio
import time
from typing import List, Optional
from urllib.parse import urlparse

import feedparser
import httpx

# Curated default feed list — mix of centre/left/right for balance
DEFAULT_FEEDS: List[str] = [
    # Centre / wire services
    "https://feeds.reuters.com/reuters/topNews",
    "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",       # centre-left
    "https://feeds.bbci.co.uk/news/rss.xml",
    "https://rss.app/feeds/yzUHl8wTmxHMK2aA.xml",  # AP News
    # Right-centre
    "https://moxie.foxnews.com/google-publisher/latest.xml",
    "https://feeds.a.dj.com/rss/RSSWorldNews.xml",  # WSJ
    # Left-centre
    "https://www.theguardian.com/world/rss",
    "https://feeds.washingtonpost.com/rss/world",
    # Tech / science
    "https://feeds.arstechnica.com/arstechnica/index",
    "https://www.wired.com/feed/rss",
]

_LEAN_MAP: dict[str, str] = {
    "reuters.com":         "center",
    "apnews.com":          "center",
    "bbc.co.uk":           "center",
    "bbc.com":             "center",
    "nytimes.com":         "center-left",
    "washingtonpost.com":  "center-left",
    "theguardian.com":     "center-left",
    "foxnews.com":         "right",
    "wsj.com":             "right-center",
    "arstechnica.com":     "center",
    "wired.com":           "center",
}


def _lean(url: str) -> str:
    host = urlparse(url).netloc.removeprefix("www.")
    for domain, lean in _LEAN_MAP.items():
        if host == domain or host.endswith("." + domain):
            return lean
    return "unknown"


async def _fetch_raw(url: str, timeout: float = 10.0) -> bytes:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url,
            headers={"User-Agent": "TectumFetcher/1.0"},
            timeout=timeout,
            follow_redirects=True,
        )
        resp.raise_for_status()
        return resp.content


async def fetch_feed(feed_url: str, max_entries: int = 10) -> List[dict]:
    """
    Fetches a single RSS/Atom feed and returns up to max_entries items.

    Each item: {url, title, summary, published, source_url, lean}
    """
    try:
        raw = await _fetch_raw(feed_url)
        parsed = feedparser.parse(raw)
        entries = []
        for e in parsed.entries[:max_entries]:
            link = getattr(e, "link", "")
            entries.append({
                "url":        link,
                "title":      getattr(e, "title", ""),
                "summary":    getattr(e, "summary", "")[:500],
                "published":  getattr(e, "published", ""),
                "source_url": feed_url,
                "lean":       _lean(link or feed_url),
            })
        return entries
    except Exception as exc:
        return [{"url": feed_url, "title": "", "summary": f"[error: {exc}]",
                 "published": "", "source_url": feed_url, "lean": "unknown"}]


async def fetch_feeds(
    query: str,
    feed_urls: Optional[List[str]] = None,
    max_entries_per_feed: int = 5,
    max_feeds: int = 6,
) -> List[dict]:
    """
    Fetches multiple feeds concurrently.  Filters entries to those whose title
    or summary contains at least one keyword from the query (case-insensitive).

    Returns a flat list of entry dicts, sorted by relevance (keyword hit count desc).
    """
    urls = (feed_urls or DEFAULT_FEEDS)[:max_feeds]
    keywords = [w.lower() for w in query.split() if len(w) > 3]

    all_results = await asyncio.gather(*[fetch_feed(u, max_entries_per_feed) for u in urls])
    flat = [e for batch in all_results for e in batch]

    def _score(entry: dict) -> int:
        text = (entry["title"] + " " + entry["summary"]).lower()
        return sum(1 for kw in keywords if kw in text)

    flat.sort(key=_score, reverse=True)
    return flat
