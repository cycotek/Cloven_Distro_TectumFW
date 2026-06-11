"""
tectum_mcp — Model Context Protocol server for TectumFW Standalone

Exposes the TectumFW reasoning stack to any MCP-capable client (Claude, other
agents, your existing MCP fleet) as three tools over streamable-HTTP:

    tectum_ask     Full 3-tier pipeline (memory → direct/quorum → R1 synthesis)
    tectum_fetch   Live research crawl (news / reference / logs / network)
    tectum_recall  Search the pgvector semantic memory directly (no inference)

This service holds no state of its own — it is a thin adapter that calls the
already-HTTP api_server and fetcher inside the standalone deployment. Point it
at those two with TECTUM_API_HOST / TECTUM_FETCHER_HOST.

Transport: streamable-HTTP, served at /mcp on MCP_PORT, so the server is
network-reachable as a single persistent service (Synology Container Manager,
bare metal next to Ollama, etc.) alongside your other MCP servers.
"""

from __future__ import annotations

import asyncio
import os
from typing import List, Optional

import httpx
from mcp.server.fastmcp import FastMCP

# ── Configuration ───────────────────────────────────────────────────────────────

API_HOST     = os.getenv("TECTUM_API_HOST", "http://cloven_tectum_api:8000").rstrip("/")
FETCHER_HOST = os.getenv("TECTUM_FETCHER_HOST", "http://cloven_tectum_fetcher:8001").rstrip("/")
MCP_HOST     = os.getenv("MCP_BIND_HOST", "0.0.0.0")
MCP_PORT     = int(os.getenv("MCP_PORT", "8802"))

# Quorum runs three models + an R1 synthesis pass; that can take a while on a
# loaded GPU, so the tool call timeout is generous.
_ASK_TIMEOUT   = float(os.getenv("TECTUM_ASK_TIMEOUT", "600"))
_FETCH_TIMEOUT = float(os.getenv("TECTUM_FETCH_TIMEOUT", "420"))

mcp = FastMCP("TectumFW", host=MCP_HOST, port=MCP_PORT)


# ── tectum_ask ───────────────────────────────────────────────────────────────────

@mcp.tool()
async def tectum_ask(
    question: str,
    models: Optional[List[str]] = None,
    synthesis_model: Optional[str] = None,
    research: bool = False,
    depth: str = "standard",
    use_memory: bool = True,
) -> str:
    """
    Ask TectumFW a question and get a bias-filtered consensus answer.

    Runs the full 3-tier pipeline: a semantic-memory cache check, then either a
    fast single-model direct path (for immutable facts) or a full quorum where
    several local models answer independently and a synthesis model reconciles
    them into one narrative. Answers are remembered, so repeats return instantly.

    Args:
        question: The question to answer.
        models: Optional list of Ollama model names to use as quorum contributors.
            Omit to use the server's configured default quorum.
        synthesis_model: Optional override for the model that writes the final
            narrative. Omit to use the server default (e.g. deepseek-r1).
        research: If true, crawl live web/RSS/Wikipedia sources before answering
            and ground the quorum in that context. News questions auto-fetch even
            when this is false.
        depth: Research crawl depth when research=true — "quick", "standard", or
            "deep" (roughly 30s / 2min / 10min).
        use_memory: Set false to force a fresh run and bypass the cache.

    Returns:
        The synthesized narrative, prefixed with a short provenance line saying
        how it was served (memory hit / direct / quorum) and the intent.
    """
    payload = {
        "question": question,
        "models": models,
        "synthesis_model": synthesis_model,
        "enable_fetch": bool(research),
        "fetch_mode": depth if depth in ("quick", "standard", "deep") else "standard",
        "use_memory": use_memory,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{API_HOST}/quorum/sync", json=payload, timeout=_ASK_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

    intent = data.get("intent", "?")
    if data.get("from_memory"):
        sim = data.get("memory_similarity")
        hits = data.get("memory_hit_count")
        served = f"served from semantic memory (match={sim}, served {hits}×)"
    elif data.get("direct_path"):
        served = f"direct fast-path via {data.get('synthesis_model', '?')}"
    else:
        contributors = ", ".join(r.get("model", "?") for r in data.get("responses", []))
        served = (
            f"quorum of [{contributors}] synthesized by "
            f"{data.get('synthesis_model', '?')}"
        )

    narrative = data.get("narrative", "") or "[no narrative returned]"
    sources = data.get("fetch_sources_count", 0)
    source_note = f" · {sources} live sources" if sources else ""

    return f"[intent={intent} · {served}{source_note}]\n\n{narrative}"


# ── tectum_fetch ─────────────────────────────────────────────────────────────────

@mcp.tool()
async def tectum_fetch(query: str, mode: str = "standard") -> str:
    """
    Run TectumFW's research fetcher to gather live, real-world context for a query
    — independent of any model. Use this when you need current information that a
    model's training data would not have.

    The fetcher classifies the query's intent and routes it to the right sources:
    news → RSS + web crawl + Wikipedia, reference → Wikipedia + web. It crawls,
    cleans, ranks, and assembles a single attributed context block.

    Args:
        query: What to research.
        mode: Crawl depth — "quick" (~30s), "standard" (~2min), or "deep" (~10min).

    Returns:
        The assembled, source-attributed context text, or a status note if the
        crawl returned nothing.
    """
    if mode not in ("quick", "standard", "deep"):
        mode = "standard"

    async with httpx.AsyncClient() as client:
        sub = await client.post(
            f"{FETCHER_HOST}/fetch", json={"query": query, "mode": mode}, timeout=30
        )
        sub.raise_for_status()
        job_id = sub.json()["job_id"]

        deadline = asyncio.get_event_loop().time() + _FETCH_TIMEOUT
        while True:
            if asyncio.get_event_loop().time() > deadline:
                return f"[fetch job {job_id} timed out after {int(_FETCH_TIMEOUT)}s]"
            await asyncio.sleep(2.0)
            status_resp = await client.get(f"{FETCHER_HOST}/fetch/{job_id}", timeout=10)
            status_resp.raise_for_status()
            status = status_resp.json().get("status", "")
            if status == "complete":
                break
            if status == "error":
                return f"[fetch job {job_id} failed]"

        ctx_resp = await client.get(f"{FETCHER_HOST}/fetch/{job_id}/context", timeout=10)
        ctx_resp.raise_for_status()
        context = ctx_resp.json().get("context") or ""

    return context or "[fetcher returned no usable context for this query]"


# ── tectum_recall ────────────────────────────────────────────────────────────────

@mcp.tool()
async def tectum_recall(query: str, threshold: float = 0.82) -> str:
    """
    Search TectumFW's semantic memory (pgvector) for a previously stored answer,
    matched by meaning rather than exact wording. No model is run — this is an
    instant lookup over everything TectumFW has already answered and cached.

    Use this to check what is already known before asking a fresh question, or to
    retrieve stored research without paying inference cost.

    Args:
        query: The question or topic to look up.
        threshold: Minimum cosine similarity to count as a hit (0.0–1.0). 0.82
            catches paraphrases; raise toward 0.9 for near-exact matches.

    Returns:
        The cached answer with its similarity score and age, or a note that
        nothing similar enough is stored.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_HOST}/memory/search",
            params={"q": query, "threshold": threshold},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

    if not data.get("hit"):
        return f"[no stored answer within similarity {threshold} for: {query}]"

    r = data["result"]
    return (
        f"[recall match={r.get('similarity')} · intent={r.get('intent')} · "
        f"stored {r.get('created_at')} · served {r.get('hit_count')}×]\n\n"
        f"Original query: {r.get('query')}\n\n{r.get('content', '')}"
    )


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
