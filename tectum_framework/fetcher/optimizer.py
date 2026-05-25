"""
optimizer.py — SORA-style Query Optimizer

Takes a raw user query and uses llama3.2:3b (fast, local) to:
  1. Classify intent: news | reference | logs | network | direct
  2. Expand into structured search terms
  3. Identify target source types
  4. Set a recommended research depth

Returns a QueryPacket that drives the rest of the fetcher pipeline.
The original query is ALWAYS preserved alongside the expansion.
"""

from __future__ import annotations

import json
import logging
import re
from typing import List, Literal, Optional

import httpx
from pydantic import BaseModel

OLLAMA_HOST = __import__("os").getenv("OLLAMA_HOST", "http://ollama:11434")
OPTIMIZER_MODEL = __import__("os").getenv("OPTIMIZER_MODEL", "llama3.2:3b")

log = logging.getLogger(__name__)

Intent = Literal["news", "reference", "logs", "network", "direct"]
Depth  = Literal["quick", "standard", "deep", "custom"]

SOURCE_MAP: dict[Intent, List[str]] = {
    "news":      ["rss", "web_crawl", "wiki"],
    "reference": ["wiki", "web_crawl"],
    "logs":      ["log_analysis"],
    "network":   ["network_scan"],
    "direct":    ["web_fetch"],
}

DEPTH_SECONDS: dict[Depth, int] = {
    "quick":    30,
    "standard": 120,
    "deep":     600,
    "custom":   0,          # caller sets time_limit_seconds manually
}


class QueryPacket(BaseModel):
    original_query:     str
    intent:             Intent
    expanded_queries:   List[str]
    target_sources:     List[str]
    depth:              Depth
    time_limit_seconds: int
    keywords:           List[str]
    notes:              str = ""  # optimizer observations for the caller


_SYSTEM_PROMPT = """\
You are a precision search query optimizer. Your job is to analyze a user query and
produce a structured JSON object that maximizes retrieval quality.

Respond ONLY with a valid JSON object — no markdown fences, no prose.

JSON schema:
{
  "intent": "<news|reference|logs|network|direct>",
  "expanded_queries": ["<search string 1>", "...", "up to 5 strings"],
  "keywords": ["<keyword 1>", "...", "up to 10 keywords"],
  "depth": "<quick|standard|deep>",
  "notes": "<one sentence about why you chose this classification>"
}

Intent definitions:
  news      — current events, recent happenings, breaking stories
  reference — historical facts, encyclopedic knowledge, how-things-work
  logs      — error logs, stack traces, debug output, application errors
  network   — port scans, service discovery, network topology queries
  direct    — a specific URL or RSS feed was given; fetch it directly

Depth guidelines:
  quick    — a factual lookup that a single source answers
  standard — a topic needing 3–5 sources cross-checked
  deep     — investigative or research-grade, many sources, citation graphs
"""


async def optimize(query: str, force_depth: Optional[Depth] = None,
                   time_limit_seconds: int = 0) -> QueryPacket:
    """
    Runs the query through llama3.2:3b to produce a QueryPacket.
    Falls back to a safe default if the model is unavailable or returns
    malformed JSON.
    """
    prompt = f"User query: {query}"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{OLLAMA_HOST}/api/chat",
                json={
                    "model": OPTIMIZER_MODEL,
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user",   "content": prompt},
                    ],
                    "stream": False,
                },
                timeout=30,
            )
            resp.raise_for_status()
            raw = resp.json().get("message", {}).get("content", "")

        # Strip markdown fences if the model wraps anyway
        raw = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`")

        data = json.loads(raw)
        intent: Intent = data.get("intent", "reference")
        if intent not in Intent.__args__:      # type: ignore[attr-defined]
            intent = "reference"

        depth: Depth = force_depth or data.get("depth", "standard")
        if depth not in Depth.__args__:        # type: ignore[attr-defined]
            depth = "standard"

        tls = time_limit_seconds or DEPTH_SECONDS[depth]

        return QueryPacket(
            original_query=query,
            intent=intent,
            expanded_queries=data.get("expanded_queries", [query])[:5],
            target_sources=SOURCE_MAP.get(intent, ["web_crawl"]),
            depth=depth,
            time_limit_seconds=tls,
            keywords=data.get("keywords", [])[:10],
            notes=data.get("notes", ""),
        )

    except Exception as exc:
        log.warning("Optimizer fallback (%s): %s", type(exc).__name__, exc)
        depth = force_depth or "standard"
        return QueryPacket(
            original_query=query,
            intent="reference",
            expanded_queries=[query],
            target_sources=["web_crawl", "wiki"],
            depth=depth,
            time_limit_seconds=time_limit_seconds or DEPTH_SECONDS[depth],
            keywords=query.split()[:10],
            notes=f"Optimizer unavailable — using safe defaults ({exc})",
        )
