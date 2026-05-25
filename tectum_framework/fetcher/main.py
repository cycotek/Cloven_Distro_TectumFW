"""
tectum_fetcher — FastAPI service

Routes
------
POST  /fetch               Submit an async fetch job
GET   /fetch/{job_id}      Poll job status + metadata
GET   /fetch/{job_id}/context  Get the assembled context text for a job
GET   /health
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from contextlib import contextmanager
from typing import List, Literal, Optional

import psycopg2
from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

from context import (
    assemble_context,
    get_context_for_job,
    save_fetch_context,
    save_fetch_job,
    save_fetch_results,
)
from crawler import crawl
from fetchers.logs import analyze_text as analyze_logs
from fetchers.network import scan_host, scan_subnet
from fetchers.rss import fetch_feeds
from fetchers.wiki import fetch_for_query as fetch_wiki
from optimizer import QueryPacket, optimize

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Tectum Fetcher", version="0.1.0")


# ── Request/response models ────────────────────────────────────────────────────

class FetchRequest(BaseModel):
    query: str
    mode:  Literal["quick", "standard", "deep", "custom"] = "standard"
    time_limit_seconds: int = 0          # 0 = use mode default
    seed_urls: Optional[List[str]] = None
    log_text:  Optional[str] = None      # pass log content directly
    scan_host: Optional[str] = None      # host to port-scan
    scan_subnet: Optional[str] = None    # CIDR subnet to scan


# ── DB helper ──────────────────────────────────────────────────────────────────

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


def _create_job_row(job_id: str, query: str) -> None:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO fetch_jobs (id, query, status) VALUES (%s, %s, 'pending')",
            (job_id, query),
        )
        conn.commit()
        cur.close()


def _update_job_status(job_id: str, status: str) -> None:
    with get_db() as conn:
        cur = conn.cursor()
        if status == "complete":
            cur.execute(
                "UPDATE fetch_jobs SET status=%s, completed_at=NOW() WHERE id=%s",
                (status, job_id),
            )
        else:
            cur.execute(
                "UPDATE fetch_jobs SET status=%s WHERE id=%s",
                (status, job_id),
            )
        conn.commit()
        cur.close()


def _get_job(job_id: str) -> Optional[dict]:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT id, query, intent, depth, status, created_at, completed_at,
                      time_limit_seconds
               FROM fetch_jobs WHERE id = %s""",
            (job_id,),
        )
        row = cur.fetchone()
        cur.close()
    if not row:
        return None
    return {
        "job_id":             str(row[0]),
        "query":              row[1],
        "intent":             row[2],
        "depth":              row[3],
        "status":             row[4],
        "created_at":         str(row[5]),
        "completed_at":       str(row[6]) if row[6] else None,
        "time_limit_seconds": row[7],
    }


# ── Background fetch worker ────────────────────────────────────────────────────

async def _run_fetch(job_id: str, req: FetchRequest) -> None:
    """
    Full async fetch pipeline:
    1. Optimize query → QueryPacket
    2. Route to appropriate fetchers based on intent
    3. Assemble context
    4. Write everything to DB
    """
    try:
        _update_job_status(job_id, "running")

        packet: QueryPacket = await optimize(
            req.query,
            force_depth=req.mode,
            time_limit_seconds=req.time_limit_seconds,
        )

        # Update DB row with resolved intent/depth
        save_fetch_job(job_id, packet, status="running")

        web_pages       = []
        wiki_articles   = []
        rss_entries_list = []
        log_analysis_result = None
        network_result_list = []

        # ── Intent routing ──────────────────────────────────────────────────

        if packet.intent in ("news", "reference", "direct"):
            # Web crawl (ant crawler)
            mode_hops = {"quick": 0, "standard": 1, "deep": 2, "custom": 1}
            mode_pages = {"quick": 5, "standard": 15, "deep": 30, "custom": 10}
            web_pages = await crawl(
                queries=packet.expanded_queries,
                keywords=packet.keywords,
                max_pages=mode_pages.get(packet.depth, 15),
                max_hops=mode_hops.get(packet.depth, 1),
                time_limit_seconds=packet.time_limit_seconds * 0.6,
                seed_urls=req.seed_urls,
            )

        if packet.intent in ("news",):
            # RSS feeds for news intent
            rss_entries_list = await fetch_feeds(
                req.query,
                max_entries_per_feed=5,
                max_feeds=6,
            )

        if packet.intent in ("reference",):
            # Wikipedia for reference intent
            wiki_articles = await fetch_wiki(req.query, max_articles=3)

        if packet.intent == "logs" or req.log_text:
            text = req.log_text or req.query
            log_analysis_result = analyze_logs(text)

        if packet.intent == "network" or req.scan_host or req.scan_subnet:
            if req.scan_subnet:
                network_result_list = await scan_subnet(req.scan_subnet)
            elif req.scan_host:
                network_result_list = await scan_host(req.scan_host)

        # ── Assemble ────────────────────────────────────────────────────────

        context_text = assemble_context(
            packet,
            web_pages=web_pages or None,
            wiki_articles=wiki_articles or None,
            rss_entries=rss_entries_list or None,
            log_analysis=log_analysis_result,
            network_results=network_result_list or None,
        )

        # ── Persist ─────────────────────────────────────────────────────────

        all_results = []
        for p in web_pages:
            p["source_type"] = "web_crawl"
            all_results.append(p)
        for a in wiki_articles:
            a["source_type"] = "wiki"
            a["primary_score"] = 0.9
            a["lean"] = "center"
            all_results.append(a)
        for e in rss_entries_list:
            e["source_type"] = "rss"
            e["primary_score"] = 0.7
            e["content"] = e.get("summary", "")
            all_results.append(e)
        for n in network_result_list:
            n["source_type"] = "network_scan"
            n["content"] = f"{n['host']}:{n['port']} {n['service']} {n.get('banner','')}"
            all_results.append(n)

        save_fetch_results(job_id, all_results)
        save_fetch_context(job_id, context_text, packet)
        save_fetch_job(job_id, packet, status="complete")

        log.info("Fetch job %s complete: %d sources", job_id, len(all_results))

    except Exception as exc:
        log.exception("Fetch job %s failed: %s", job_id, exc)
        _update_job_status(job_id, "error")


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/fetch", status_code=202)
async def submit_fetch(req: FetchRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    _create_job_row(job_id, req.query)
    background_tasks.add_task(_run_fetch, job_id, req)
    return {"job_id": job_id, "status": "pending"}


@app.get("/fetch/{job_id}")
def get_fetch_job(job_id: str):
    job = _get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/fetch/{job_id}/context")
def get_context(job_id: str):
    job = _get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] not in ("complete",):
        return {"job_id": job_id, "status": job["status"], "context": None}
    ctx = get_context_for_job(job_id)
    return {"job_id": job_id, "status": "complete", "context": ctx}
