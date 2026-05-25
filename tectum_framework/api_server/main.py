from __future__ import annotations

import asyncio
import logging
import os
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import List, Literal, Optional

import httpx
import psycopg2
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from quorum import DEFAULT_MODELS, OLLAMA_HOST, SYNTHESIS_MODEL, run_quorum

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

FETCHER_HOST     = os.getenv("FETCHER_HOST", "http://cloven_tectum_fetcher:8001")
_FETCH_POLL_INTERVAL = 2.0    # seconds between status polls
_FETCH_TIMEOUT       = 360.0  # max seconds to wait for fetch to complete


# ── Database ──────────────────────────────────────────────────────────────────

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


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Cloven Tectum API", version="0.6.0")

_STATIC = Path(__file__).parent / "static"


class QuorumRequest(BaseModel):
    question:         str
    models:           Optional[List[str]] = None
    synthesis_model:  Optional[str] = None
    # Research mode — triggers tectum_fetcher before quorum
    enable_fetch:     bool = False
    fetch_mode:       Literal["quick", "standard", "deep"] = "standard"


# ── Fetcher helpers ───────────────────────────────────────────────────────────

async def _submit_fetch(question: str, mode: str) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{FETCHER_HOST}/fetch",
            json={"query": question, "mode": mode},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["job_id"]


async def _poll_fetch(job_id: str) -> str:
    import time
    deadline = time.monotonic() + _FETCH_TIMEOUT
    async with httpx.AsyncClient() as client:
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError(f"Fetch job {job_id} timed out")
            await asyncio.sleep(_FETCH_POLL_INTERVAL)
            resp = await client.get(f"{FETCHER_HOST}/fetch/{job_id}", timeout=10)
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status", "")
            if status == "complete":
                break
            if status == "error":
                raise RuntimeError(f"Fetch job {job_id} failed")
        ctx_resp = await client.get(f"{FETCHER_HOST}/fetch/{job_id}/context", timeout=10)
        ctx_resp.raise_for_status()
        return ctx_resp.json().get("context") or ""


async def _fetch_context_for_question(question: str, mode: str) -> tuple[str, str]:
    """Returns (fetch_job_id, context_text). Never raises — empty strings on failure."""
    try:
        job_id = await _submit_fetch(question, mode)
        log.info("Fetch job submitted: %s (mode=%s)", job_id, mode)
        context = await _poll_fetch(job_id)
        log.info("Fetch job %s complete — %d chars", job_id, len(context))
        return job_id, context
    except Exception as exc:
        log.warning("Fetch failed, proceeding without context: %s", exc)
        return "", ""


# ── Background runner ─────────────────────────────────────────────────────────

def _run_quorum_bg(job_id: str, question: str, models: List[str],
                   synthesis_model: str = "", fetch_context: str = "") -> None:
    with get_db() as conn:
        cur = conn.cursor()
        try:
            cur.execute("UPDATE quorum_jobs SET status='running' WHERE id=%s", (job_id,))
            conn.commit()

            result = asyncio.run(run_quorum(question, models, synthesis_model, fetch_context))

            for r in result["responses"]:
                cur.execute(
                    """INSERT INTO quorum_responses
                       (job_id, model, response, duration_ms, tokens_in, tokens_out)
                       VALUES (%s,%s,%s,%s,%s,%s)""",
                    (job_id, r["model"], r["content"],
                     r.get("duration_ms"), r.get("tokens_in"), r.get("tokens_out")),
                )
            cur.execute(
                """INSERT INTO quorum_narratives
                   (job_id, synthesis_model, narrative, thinking, duration_ms, tokens_in, tokens_out)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (job_id, SYNTHESIS_MODEL, result["narrative"],
                 result.get("synthesis_thinking", ""),
                 result.get("synthesis_duration_ms"),
                 result.get("synthesis_tokens_in"),
                 result.get("synthesis_tokens_out")),
            )
            cur.execute("UPDATE quorum_jobs SET status='complete' WHERE id=%s", (job_id,))
            conn.commit()
        except Exception:
            cur.execute("UPDATE quorum_jobs SET status='error' WHERE id=%s", (job_id,))
            conn.commit()
            raise
        finally:
            cur.close()


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
@app.get("/ui", response_class=HTMLResponse)
def serve_ui():
    index = _STATIC / "index.html"
    if not index.exists():
        return HTMLResponse("<h1>UI not found</h1>", status_code=404)
    return HTMLResponse(index.read_text())


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/config")
def get_config():
    return {
        "synthesis_model": SYNTHESIS_MODEL,
        "default_models":  DEFAULT_MODELS,
        "fetcher_enabled": True,
    }


@app.get("/models")
async def list_models():
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{OLLAMA_HOST}/api/tags", timeout=10)
        resp.raise_for_status()
    return resp.json()


@app.get("/models/split")
async def split_models():
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{OLLAMA_HOST}/api/tags", timeout=10)
        resp.raise_for_status()
    all_models = [m["name"] for m in resp.json().get("models", [])]
    contributors = [m for m in all_models if m != SYNTHESIS_MODEL]
    return {
        "contributors":    contributors,
        "all_models":      all_models,
        "synthesis_model": SYNTHESIS_MODEL,
    }


@app.get("/quorum/history")
def get_history(limit: int = Query(default=50, le=200)):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT id, question, models, status, created_at
               FROM quorum_jobs ORDER BY created_at DESC LIMIT %s""",
            (limit,),
        )
        rows = cur.fetchall()
        cur.close()
    return [
        {"job_id": str(r[0]), "question": r[1], "models": r[2],
         "status": r[3], "created_at": str(r[4])}
        for r in rows
    ]


@app.post("/quorum", status_code=202)
async def submit_quorum(req: QuorumRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    models = req.models or DEFAULT_MODELS

    fetch_context = ""
    fetch_job_id  = ""
    if req.enable_fetch:
        fetch_job_id, fetch_context = await _fetch_context_for_question(
            req.question, req.fetch_mode
        )

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO quorum_jobs (id, question, models, status) VALUES (%s,%s,%s,'pending')",
            (job_id, req.question, models),
        )
        conn.commit()
        cur.close()

    background_tasks.add_task(
        _run_quorum_bg, job_id, req.question, models,
        req.synthesis_model or "", fetch_context,
    )
    return {"job_id": job_id, "status": "pending", "fetch_job_id": fetch_job_id}


@app.post("/quorum/sync")
async def submit_quorum_sync(req: QuorumRequest):
    job_id = str(uuid.uuid4())
    models = req.models or DEFAULT_MODELS

    # ── Fetch phase ───────────────────────────────────────────────────────────
    fetch_job_id        = ""
    fetch_context       = ""
    fetch_sources_count = 0

    if req.enable_fetch:
        fetch_job_id, fetch_context = await _fetch_context_for_question(
            req.question, req.fetch_mode
        )
        if fetch_context:
            fetch_sources_count = fetch_context.count("\n--- ")

    # ── Quorum phase ──────────────────────────────────────────────────────────
    used_synthesis_model = req.synthesis_model or SYNTHESIS_MODEL

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO quorum_jobs (id, question, models, status) VALUES (%s,%s,%s,'running')",
            (job_id, req.question, models),
        )
        conn.commit()

        result = await run_quorum(req.question, models, used_synthesis_model, fetch_context)

        for r in result["responses"]:
            cur.execute(
                """INSERT INTO quorum_responses
                   (job_id, model, response, duration_ms, tokens_in, tokens_out)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (job_id, r["model"], r["content"],
                 r.get("duration_ms"), r.get("tokens_in"), r.get("tokens_out")),
            )
        cur.execute(
            """INSERT INTO quorum_narratives
               (job_id, synthesis_model, narrative, thinking, duration_ms, tokens_in, tokens_out)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (job_id, used_synthesis_model, result["narrative"],
             result.get("synthesis_thinking", ""),
             result.get("synthesis_duration_ms"),
             result.get("synthesis_tokens_in"),
             result.get("synthesis_tokens_out")),
        )
        cur.execute("UPDATE quorum_jobs SET status='complete' WHERE id=%s", (job_id,))
        conn.commit()
        cur.close()

    return {
        "job_id":                  job_id,
        "question":                req.question,
        "models":                  models,
        "synthesis_model":         used_synthesis_model,
        "responses":               result["responses"],
        "narrative":               result["narrative"],
        "synthesis_thinking":      result.get("synthesis_thinking", ""),
        "synthesis_duration_ms":   result.get("synthesis_duration_ms"),
        "synthesis_tokens_in":     result.get("synthesis_tokens_in"),
        "synthesis_tokens_out":    result.get("synthesis_tokens_out"),
        "fetch_job_id":            fetch_job_id,
        "fetch_sources_count":     fetch_sources_count,
        "fetch_context_preview":   fetch_context[:500] if fetch_context else "",
    }


@app.get("/quorum/{job_id}")
def get_quorum(job_id: str):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT question, models, status, created_at FROM quorum_jobs WHERE id=%s", (job_id,)
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Job not found")
        question, models, status, created_at = row

        cur.execute(
            """SELECT model, response, duration_ms, tokens_in, tokens_out, responded_at
               FROM quorum_responses WHERE job_id=%s ORDER BY responded_at""",
            (job_id,),
        )
        responses = [
            {"model": r[0], "content": r[1], "duration_ms": r[2],
             "tokens_in": r[3], "tokens_out": r[4], "at": str(r[5])}
            for r in cur.fetchall()
        ]

        cur.execute(
            """SELECT narrative, thinking, synthesis_model, duration_ms,
                      tokens_in, tokens_out, created_at
               FROM quorum_narratives WHERE job_id=%s""",
            (job_id,),
        )
        nar = cur.fetchone()
        cur.close()

    return {
        "job_id":                job_id,
        "question":              question,
        "models":                models,
        "status":                status,
        "created_at":            str(created_at),
        "responses":             responses,
        "narrative":             nar[0] if nar else None,
        "synthesis_thinking":    nar[1] if nar else "",
        "synthesis_model":       nar[2] if nar else None,
        "synthesis_duration_ms": nar[3] if nar else None,
        "synthesis_tokens_in":   nar[4] if nar else None,
        "synthesis_tokens_out":  nar[5] if nar else None,
    }
