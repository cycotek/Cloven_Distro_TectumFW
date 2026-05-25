"""
context.py — Context Assembler

Takes raw fetch results from the crawler / fetchers and assembles them into
a single structured context document that the quorum LLMs can reason over.

Also writes the job and results to the database so the quorum API can
query fetch_context by job_id when building its synthesis prompt.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

import psycopg2

from optimizer import QueryPacket


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _dsn() -> str:
    return (
        f"host={os.getenv('DATABASE_HOST', 'cloven_tectum_db')} "
        f"port={os.getenv('DATABASE_PORT', '5432')} "
        f"dbname={os.getenv('DATABASE_NAME', 'cloven_tectum')} "
        f"user={os.getenv('DATABASE_USER', 'cloven')} "
        f"password={os.getenv('DATABASE_PASS', 'changeme')}"
    )


@contextmanager
def get_db():
    conn = psycopg2.connect(_dsn())
    try:
        yield conn
    finally:
        conn.close()


# ── Context builder ────────────────────────────────────────────────────────────

def _format_web_section(pages: List[dict]) -> str:
    """Format crawled web pages into a readable block."""
    lines = []
    for i, p in enumerate(pages[:10], 1):
        lean_tag = f"[lean:{p.get('lean', 'unknown')}]" if p.get("lean") else ""
        score_tag = f"[primary:{p.get('primary_score', '?')}]"
        lines.append(
            f"--- Source {i}: {p.get('title', 'Untitled')} {lean_tag}{score_tag}\n"
            f"URL: {p.get('url', '')}\n"
            f"{p.get('content', '')[:1500]}\n"
        )
    return "\n".join(lines)


def _format_wiki_section(articles: List[dict]) -> str:
    lines = []
    for a in articles[:5]:
        lines.append(
            f"--- Wikipedia: {a.get('title', '')}\n"
            f"URL: {a.get('url', '')}\n"
            f"{a.get('summary', '')}\n"
        )
    return "\n".join(lines)


def _format_rss_section(entries: List[dict]) -> str:
    lines = []
    for e in entries[:10]:
        lean_tag = f"[lean:{e.get('lean', 'unknown')}]"
        lines.append(
            f"--- News: {e.get('title', '')} {lean_tag}\n"
            f"URL: {e.get('url', '')}\n"
            f"Published: {e.get('published', '')}\n"
            f"{e.get('summary', '')}\n"
        )
    return "\n".join(lines)


def _format_log_section(analysis: dict) -> str:
    lines = [f"Log analysis: {analysis.get('summary', '')}"]
    for finding in analysis.get("findings", [])[:5]:
        lines.append(
            f"\nError type: {finding['type']} ({finding['count']} occurrence(s))\n"
            f"Sample: {finding['matches'][0]['line'] if finding['matches'] else ''}\n"
            f"Search suggestion: {'; '.join(finding.get('search_suggestions', []))}"
        )
    return "\n".join(lines)


def _format_network_section(open_ports: List[dict]) -> str:
    if not open_ports:
        return "Network scan: no open ports found."
    lines = ["Network scan results:"]
    for p in open_ports:
        banner = f" — {p['banner']}" if p.get("banner") else ""
        lines.append(f"  {p['host']}:{p['port']} ({p['service']}){banner}")
    return "\n".join(lines)


def assemble_context(
    packet: QueryPacket,
    web_pages:   Optional[List[dict]] = None,
    wiki_articles: Optional[List[dict]] = None,
    rss_entries: Optional[List[dict]] = None,
    log_analysis: Optional[dict] = None,
    network_results: Optional[List[dict]] = None,
) -> str:
    """
    Assembles all fetched results into a single context document string.

    The string is designed to be prepended to the quorum prompt so LLMs
    have raw source material to reason over.
    """
    sections = [
        f"=== RESEARCH CONTEXT ===",
        f"Original query: {packet.original_query}",
        f"Intent: {packet.intent}  |  Depth: {packet.depth}",
        f"Expanded queries: {', '.join(packet.expanded_queries)}",
        "",
    ]

    if web_pages:
        sections += ["── Web Sources ──", _format_web_section(web_pages), ""]
    if wiki_articles:
        sections += ["── Wikipedia ──", _format_wiki_section(wiki_articles), ""]
    if rss_entries:
        sections += ["── News Feeds ──", _format_rss_section(rss_entries), ""]
    if log_analysis:
        sections += ["── Log Analysis ──", _format_log_section(log_analysis), ""]
    if network_results:
        sections += ["── Network Scan ──", _format_network_section(network_results), ""]

    sections.append("=== END CONTEXT ===")
    return "\n".join(sections)


# ── DB persistence ─────────────────────────────────────────────────────────────

def save_fetch_job(
    job_id: str,
    packet: QueryPacket,
    status: str = "complete",
) -> None:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO fetch_jobs
               (id, query, intent, expanded_queries, depth, time_limit_seconds, status)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (id) DO UPDATE
               SET intent             = EXCLUDED.intent,
                   expanded_queries   = EXCLUDED.expanded_queries,
                   depth              = EXCLUDED.depth,
                   time_limit_seconds = EXCLUDED.time_limit_seconds,
                   status             = EXCLUDED.status,
                   completed_at       = CASE WHEN EXCLUDED.status = 'complete'
                                             THEN NOW() ELSE fetch_jobs.completed_at END""",
            (
                job_id,
                packet.original_query,
                packet.intent,
                packet.expanded_queries,
                packet.depth,
                packet.time_limit_seconds,
                status,
            ),
        )
        conn.commit()
        cur.close()


def save_fetch_results(job_id: str, results: List[Dict[str, Any]]) -> None:
    if not results:
        return
    with get_db() as conn:
        cur = conn.cursor()
        for r in results:
            cur.execute(
                """INSERT INTO fetch_results
                   (job_id, url, title, content, source_type, score, political_lean, hop_depth)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    job_id,
                    r.get("url", ""),
                    r.get("title", ""),
                    r.get("content", ""),
                    r.get("source_type", "web"),
                    r.get("primary_score") or r.get("relevance"),
                    r.get("lean", "unknown"),
                    r.get("hop", 0),
                ),
            )
        conn.commit()
        cur.close()


def save_fetch_context(job_id: str, context_text: str, packet: QueryPacket) -> None:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO fetch_context (job_id, context_text, query_packet)
               VALUES (%s, %s, %s)
               ON CONFLICT (job_id) DO UPDATE
               SET context_text = EXCLUDED.context_text,
                   query_packet  = EXCLUDED.query_packet""",
            (job_id, context_text, json.dumps(packet.model_dump())),
        )
        conn.commit()
        cur.close()


def get_context_for_job(job_id: str) -> Optional[str]:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT context_text FROM fetch_context WHERE job_id = %s", (job_id,)
        )
        row = cur.fetchone()
        cur.close()
    return row[0] if row else None
