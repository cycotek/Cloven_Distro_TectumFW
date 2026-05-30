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
import base64

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from memory import search_memory, store_synthesis
from quorum import DEFAULT_MODELS, OLLAMA_HOST, SYNTHESIS_MODEL, _chat, run_quorum

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

FETCHER_HOST         = os.getenv("FETCHER_HOST", "http://cloven_tectum_fetcher:8001")
_FETCH_POLL_INTERVAL = 2.0    # seconds between status polls
_FETCH_TIMEOUT       = 360.0  # max seconds to wait for fetch to complete

# Fast model for direct (single-answer) queries — skip quorum overhead
DIRECT_MODEL = os.getenv("DIRECT_MODEL", "llama3.2:3b")

# Embedding-only models to exclude from chat/contributor lists
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
_EMBED_PREFIXES = tuple(
    p.split(":")[0].lower()
    for p in [EMBED_MODEL, "nomic-embed-text", "mxbai-embed", "all-minilm",
              "snowflake-arctic-embed", "bge-", "e5-"]
)

def _is_chat_model(name: str) -> bool:
    """Return False for known embedding-only models."""
    n = name.lower()
    return not any(n.startswith(p) for p in _EMBED_PREFIXES)


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

app = FastAPI(title="Cloven Tectum API", version="0.7.0")

SCREENSHOT_DIR = Path("/app/screenshots")


@app.on_event("startup")
def _bootstrap_schema() -> None:
    """
    Apply the (idempotent) schema on startup so the database self-initializes.

    This removes the need to bind-mount schema.sql into the Postgres container,
    which matters for pull-only deploys like Synology Container Manager where no
    repo is present on the host. schema.sql is baked into this image (COPY ./ /app)
    and every statement is IF NOT EXISTS, so running it repeatedly is a no-op.
    Best-effort: a failure is logged, never fatal — the bundled compose also
    applies it via docker-entrypoint-initdb.d.
    """
    import time

    schema_path = Path(__file__).parent / "schema.sql"
    if not schema_path.exists():
        log.warning("schema bootstrap: %s not found, skipping", schema_path)
        return
    sql = schema_path.read_text()
    for attempt in range(1, 11):
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute(sql)
                conn.commit()
                cur.close()
            log.info("schema bootstrap: applied on attempt %d", attempt)
            return
        except Exception as exc:  # DB may still be warming up — retry a few times
            log.warning("schema bootstrap attempt %d failed: %s", attempt, exc)
            time.sleep(3)
    log.error("schema bootstrap: gave up after retries (DB unreachable?)")

@app.post("/save-screenshot")
async def save_screenshot(payload: dict):
    """Temporary endpoint: receives base64 PNG from browser and writes to screenshots dir."""
    filename = payload.get("filename", "shot.png")
    data = payload.get("data", "")
    if "," in data:
        data = data.split(",", 1)[1]
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    (SCREENSHOT_DIR / filename).write_bytes(base64.b64decode(data))
    return {"ok": True, "saved": filename}

_STATIC = Path(__file__).parent / "static"


class QuorumRequest(BaseModel):
    question:         str
    models:           Optional[List[str]] = None
    synthesis_model:  Optional[str] = None
    # Research mode — triggers tectum_fetcher before quorum
    enable_fetch:     bool = False
    fetch_mode:       Literal["quick", "standard", "deep"] = "standard"
    # Memory — set False to force a fresh run even if cache has a hit
    use_memory:       bool = True


# ── Fetcher helpers ───────────────────────────────────────────────────────────

async def _classify_question(question: str, mode: str = "standard") -> dict:
    """
    Ask the fetcher to run just the optimizer (no crawl).
    Returns a dict with intent, needs_quorum, memory_ttl_days, etc.
    Falls back to safe defaults on any error.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{FETCHER_HOST}/classify",
                json={"query": question, "mode": mode},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        log.warning("classify_question failed, using defaults: %s", exc)
        return {
            "intent": "reference",
            "needs_quorum": True,
            "memory_ttl_days": 7,
        }


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
        "memory_enabled":  True,
        "direct_model":    DIRECT_MODEL,
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
    all_models   = [m["name"] for m in resp.json().get("models", [])
                    if _is_chat_model(m["name"])]
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


@app.get("/memory/search")
async def memory_search(q: str = Query(...), threshold: float = Query(default=0.88)):
    """Debug endpoint — manually search semantic memory."""
    hit = await search_memory(q, threshold=threshold)
    if not hit:
        return {"hit": False, "result": None}
    return {"hit": True, "result": hit}


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
    models = req.models or DEFAULT_MODELS

    # ── Step 1: Classify intent ───────────────────────────────────────────────
    packet = await _classify_question(req.question, req.fetch_mode)
    intent           = packet.get("intent", "reference")
    needs_quorum     = packet.get("needs_quorum", True)
    memory_ttl_days  = packet.get("memory_ttl_days", 7)

    # News queries always need live context — auto-enable fetch regardless of
    # whether the user toggled Research Mode.  Model training data is frozen;
    # for anything time-sensitive we must get current information.
    auto_fetch = (intent == "news") and not req.enable_fetch
    if auto_fetch:
        log.info("Auto-fetch: news intent detected for %r", req.question[:60])

    log.info("classify: question=%r intent=%s needs_quorum=%s ttl=%d auto_fetch=%s",
             req.question[:60], intent, needs_quorum, memory_ttl_days, auto_fetch)

    # ── Step 2: Memory check (skip for ephemeral intents) ─────────────────────
    memory_hit = None
    if req.use_memory and memory_ttl_days > 0:
        memory_hit = await search_memory(req.question, max_age_days=memory_ttl_days)

    if memory_hit:
        log.info("Memory HIT for %r (sim=%.3f hits=%d)",
                 req.question[:60], memory_hit["similarity"], memory_hit["hit_count"])
        return {
            "job_id":               memory_hit["source_job_id"] or "memory",
            "question":             req.question,
            "models":               models,
            "synthesis_model":      memory_hit.get("source_type", "memory"),
            "responses":            [],
            "narrative":            memory_hit["content"],
            "synthesis_thinking":   "",
            "synthesis_duration_ms": 0,
            "synthesis_tokens_in":  0,
            "synthesis_tokens_out": 0,
            "fetch_job_id":         "",
            "fetch_sources_count":  0,
            "fetch_context_preview": "",
            # Memory metadata
            "from_memory":          True,
            "memory_id":            memory_hit["id"],
            "memory_similarity":    memory_hit["similarity"],
            "memory_hit_count":     memory_hit["hit_count"],
            "memory_created_at":    memory_hit["created_at"],
            "intent":               intent,
        }

    # ── Step 3: Direct path (single model, no quorum) ─────────────────────────
    if not needs_quorum:
        log.info("Direct path for %r (intent=%s)", req.question[:60], intent)
        job_id = str(uuid.uuid4())
        async with httpx.AsyncClient() as client:
            direct_result = await _chat(client, DIRECT_MODEL, req.question, timeout=180)

        narrative = direct_result["content"]

        # Persist a lightweight job record so history still works
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO quorum_jobs (id, question, models, status) "
                "VALUES (%s,%s,%s,'complete')",
                (job_id, req.question, [DIRECT_MODEL]),
            )
            cur.execute(
                """INSERT INTO quorum_responses
                   (job_id, model, response, duration_ms, tokens_in, tokens_out)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (job_id, DIRECT_MODEL, narrative,
                 direct_result.get("duration_ms"),
                 direct_result.get("tokens_in"),
                 direct_result.get("tokens_out")),
            )
            cur.execute(
                """INSERT INTO quorum_narratives
                   (job_id, synthesis_model, narrative, thinking, duration_ms, tokens_in, tokens_out)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (job_id, DIRECT_MODEL, narrative, "",
                 direct_result.get("duration_ms"),
                 direct_result.get("tokens_in"),
                 direct_result.get("tokens_out")),
            )
            conn.commit()
            cur.close()

        # Store in memory (direct facts have very long TTL)
        await store_synthesis(
            query=req.question,
            content=narrative,
            source_job_id=job_id,
            source_type="direct",
            intent=intent,
            memory_ttl_days=memory_ttl_days,
        )

        return {
            "job_id":               job_id,
            "question":             req.question,
            "models":               [DIRECT_MODEL],
            "synthesis_model":      DIRECT_MODEL,
            "responses":            [{"model": DIRECT_MODEL, "content": narrative,
                                      **{k: direct_result.get(k) for k in
                                         ("duration_ms", "tokens_in", "tokens_out")}}],
            "narrative":            narrative,
            "synthesis_thinking":   "",
            "synthesis_duration_ms": direct_result.get("duration_ms"),
            "synthesis_tokens_in":  direct_result.get("tokens_in"),
            "synthesis_tokens_out": direct_result.get("tokens_out"),
            "fetch_job_id":         "",
            "fetch_sources_count":  0,
            "fetch_context_preview": "",
            "from_memory":          False,
            "direct_path":          True,
            "intent":               intent,
        }

    # ── Step 4: Full quorum path ───────────────────────────────────────────────
    job_id = str(uuid.uuid4())

    fetch_job_id        = ""
    fetch_context       = ""
    fetch_sources_count = 0

    if req.enable_fetch or auto_fetch:
        fetch_job_id, fetch_context = await _fetch_context_for_question(
            req.question, req.fetch_mode
        )
        if fetch_context:
            fetch_sources_count = fetch_context.count("\n--- ")

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

    # Store synthesis in memory (news TTL=1d, reference TTL=30d, etc.)
    if memory_ttl_days > 0 and result.get("narrative"):
        await store_synthesis(
            query=req.question,
            content=result["narrative"],
            source_job_id=job_id,
            source_type="synthesis",
            intent=intent,
            memory_ttl_days=memory_ttl_days,
        )

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
        "from_memory":             False,
        "direct_path":             False,
        "intent":                  intent,
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
