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
    "direct":    [],          # no fetch — answered from model knowledge / memory
}

DEPTH_SECONDS: dict[Depth, int] = {
    "quick":    30,
    "standard": 120,
    "deep":     600,
    "custom":   0,          # caller sets time_limit_seconds manually
}

# How long memory entries are considered fresh for each intent type
MEMORY_TTL_DAYS: dict[Intent, int] = {
    "direct":    365,   # math/constants — essentially permanent
    "reference":  30,   # encyclopedic — stable but can change
    "news":        1,   # current events — stale within a day
    "logs":        0,   # ephemeral — don't cache
    "network":     0,   # ephemeral — don't cache
}

# Whether a quorum (multi-model debate) is needed for this intent
NEEDS_QUORUM: dict[Intent, bool] = {
    "direct":    False,  # single correct answer, no bias possible
    "reference": True,
    "news":      True,
    "logs":      False,  # deterministic analysis
    "network":   False,  # deterministic scan
}


class QueryPacket(BaseModel):
    original_query:     str
    intent:             Intent
    expanded_queries:   List[str]
    target_sources:     List[str]
    depth:              Depth
    time_limit_seconds: int
    keywords:           List[str]
    notes:              str = ""    # optimizer observations for the caller
    needs_quorum:       bool = True # False for direct/factual queries
    memory_ttl_days:    int  = 7    # how long a cached synthesis stays fresh


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
  direct    — single-answer factual query: math, constants, definitions, conversions,
              spelling, physical constants. These have ONE correct answer with NO bias
              or debate possible. IMPORTANT: Physics/science constants are ALWAYS direct,
              NOT reference. Examples: "what is 2+2", "speed of light in a vacuum",
              "what is the speed of light", "how fast does light travel", "Planck constant",
              "boiling point of water", "how do you spell necessary", "what year did WW2 end",
              "convert 100F to Celsius". No web fetch needed. Answer from model knowledge.
  news      — current events, recent happenings, breaking stories, today/this week
  reference — historical facts, encyclopedic knowledge, how-things-work, opinions,
              explanations of complex topics, "why" questions, "how does X work"
  logs      — error logs, stack traces, debug output, application errors
  network   — port scans, service discovery, network topology queries

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
                    "options": {"temperature": 0},   # deterministic — classification must be stable
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
            needs_quorum=NEEDS_QUORUM.get(intent, True),
            memory_ttl_days=MEMORY_TTL_DAYS.get(intent, 7),
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
            needs_quorum=True,
            memory_ttl_days=7,
        )
