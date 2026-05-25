"""
fetchers/web.py — General async web page fetcher with content extraction.

Uses httpx for HTTP, BeautifulSoup for parsing.
Strips nav/header/footer/ads and returns the main readable text.
"""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Comment

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; TectumFetcher/1.0; +https://github.com/cycotek/Cloven_Distro_TectumFW)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# Tags that almost never contain main content
_NOISE_TAGS = {
    "script", "style", "noscript", "nav", "header", "footer",
    "aside", "form", "button", "iframe", "ads", "advertisement",
}

# Domain → political lean lookup (extend as needed)
_LEAN_MAP: dict[str, str] = {
    "foxnews.com":       "right",
    "breitbart.com":     "far-right",
    "nypost.com":        "right-center",
    "wsj.com":           "right-center",
    "reuters.com":       "center",
    "apnews.com":        "center",
    "bbc.com":           "center",
    "bbc.co.uk":         "center",
    "npr.org":           "center-left",
    "msnbc.com":         "left",
    "huffpost.com":      "left",
    "motherjones.com":   "left",
    "jacobin.com":       "far-left",
    "theintercept.com":  "left",
    "democracynow.org":  "left",
    "cnn.com":           "center-left",
    "theguardian.com":   "center-left",
    "washingtonpost.com":"center-left",
    "nytimes.com":       "center-left",
    "politico.com":      "center",
    "thehill.com":       "center",
    "axios.com":         "center",
    "bloomberg.com":     "center",
    "economist.com":     "center-right",
}


def _lean_for_url(url: str) -> str:
    host = urlparse(url).netloc.removeprefix("www.")
    for domain, lean in _LEAN_MAP.items():
        if host == domain or host.endswith("." + domain):
            return lean
    return "unknown"


def _extract_text(html: str, base_url: str = "") -> tuple[str, str, list[str]]:
    """
    Returns (title, clean_text, outbound_links).
    """
    soup = BeautifulSoup(html, "lxml")

    # Remove noise
    for tag in soup(list(_NOISE_TAGS)):
        tag.decompose()
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()

    title = (soup.find("title") or soup.find("h1") or soup.new_tag("t"))
    title_text = title.get_text(strip=True) if hasattr(title, "get_text") else ""

    # Try <article> first, fall back to <main>, then <body>
    content_node = soup.find("article") or soup.find("main") or soup.find("body") or soup
    text = re.sub(r"\n{3,}", "\n\n", content_node.get_text(separator="\n", strip=True))

    # Collect internal + external links
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("http"):
            links.append(href)
        elif base_url and href.startswith("/"):
            links.append(urljoin(base_url, href))

    return title_text, text[:8000], links[:50]  # cap content at 8 k chars, 50 links


async def fetch_page(url: str, timeout: float = 15.0) -> dict:
    """
    Fetches a single URL and returns a structured result dict.

    {
        "url": str,
        "title": str,
        "content": str,
        "links": [str, ...],
        "lean": str,
        "ok": bool,
        "error": str | None,
    }
    """
    lean = _lean_for_url(url)
    try:
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
            resp = await client.get(url, timeout=timeout)
            resp.raise_for_status()
            ct = resp.headers.get("content-type", "")
            if "html" not in ct and "xml" not in ct:
                return {
                    "url": url, "title": "", "content": resp.text[:4000],
                    "links": [], "lean": lean, "ok": True, "error": None,
                }
            title, content, links = _extract_text(resp.text, url)
            return {
                "url": url, "title": title, "content": content,
                "links": links, "lean": lean, "ok": True, "error": None,
            }
    except Exception as exc:
        return {
            "url": url, "title": "", "content": "", "links": [],
            "lean": lean, "ok": False, "error": str(exc),
        }
