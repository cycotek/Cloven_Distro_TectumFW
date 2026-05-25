from __future__ import annotations

import asyncio
import os
import uuid
from typing import List, Optional

import httpx
import psycopg2
from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

from quorum_graph import DEFAULT_MODELS, OLLAMA_HOST, SYNTHESIS_MODEL, QuorumState, quorum_graph


def _dsn() -> str:
    return (
        f"host={os.getenv('DATABASE_HOST', 'cloven_tectum_db')} "
        f"port={os.getenv('DATABASE_PORT', '5432')} "
        f"dbname={os.getenv('DATABASE_NAME', 'cloven_tectum')} "
        f"user={os.getenv('DATABASE_USER', 'cloven')} "
        f"password={os.getenv('DATABASE_PASS', 'changeme')}"
    )


def get_conn():
    return psycopg2.connect(_dsn())


app = FastAPI(title="Cloven Tectum API", version="0.3.0")


class QuorumRequest(BaseModel):
    question: str
    models: Optional[List[str]] = None


# ── Background runner ─────────────────────────────────────────────────────────

def _run_quorum(job_id: str, question: str, models: List[str]) -> None:
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE quorum_jobs SET status='running' WHERE id=%s", (job_id,))
        conn.commit()

        state: QuorumState = {
            "job_id": job_id,
            "question": question,
            "models": models,
            "responses": [],
            "narrative": "",
        }
        result = quorum_graph.invoke(state)

        for r in result["responses"]:
            cur.execute(
                "INSERT INTO quorum_responses (job_id, model, response) VALUES (%s,%s,%s)",
                (job_id, r["model"], r["content"]),
            )
        cur.execute(
            "INSERT INTO quorum_narratives (job_id, synthesis_model, narrative) VALUES (%s,%s,%s)",
            (job_id, SYNTHESIS_MODEL, result["narrative"]),
        )
        cur.execute("UPDATE quorum_jobs SET status='complete' WHERE id=%s", (job_id,))
        conn.commit()
    except Exception:
        cur.execute("UPDATE quorum_jobs SET status='error' WHERE id=%s", (job_id,))
        conn.commit()
        raise
    finally:
        cur.close()
        conn.close()


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "Cloven Tectum online — uptime is truth.", "version": "0.3.0"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/models")
async def list_models():
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{OLLAMA_HOST}/api/tags", timeout=10)
        resp.raise_for_status()
    return resp.json()


@app.post("/quorum", status_code=202)
async def submit_quorum(req: QuorumRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    models = req.models or DEFAULT_MODELS

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO quorum_jobs (id, question, models, status) VALUES (%s,%s,%s,'pending')",
        (job_id, req.question, models),
    )
    conn.commit()
    cur.close()
    conn.close()

    background_tasks.add_task(_run_quorum, job_id, req.question, models)
    return {"job_id": job_id, "status": "pending"}


@app.post("/quorum/sync")
async def submit_quorum_sync(req: QuorumRequest):
    job_id = str(uuid.uuid4())
    models = req.models or DEFAULT_MODELS

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO quorum_jobs (id, question, models, status) VALUES (%s,%s,%s,'running')",
        (job_id, req.question, models),
    )
    conn.commit()

    state: QuorumState = {
        "job_id": job_id,
        "question": req.question,
        "models": models,
        "responses": [],
        "narrative": "",
    }
    result = await asyncio.to_thread(quorum_graph.invoke, state)

    for r in result["responses"]:
        cur.execute(
            "INSERT INTO quorum_responses (job_id, model, response) VALUES (%s,%s,%s)",
            (job_id, r["model"], r["content"]),
        )
    cur.execute(
        "INSERT INTO quorum_narratives (job_id, synthesis_model, narrative) VALUES (%s,%s,%s)",
        (job_id, SYNTHESIS_MODEL, result["narrative"]),
    )
    cur.execute("UPDATE quorum_jobs SET status='complete' WHERE id=%s", (job_id,))
    conn.commit()
    cur.close()
    conn.close()

    return {
        "job_id": job_id,
        "question": req.question,
        "models": models,
        "responses": result["responses"],
        "narrative": result["narrative"],
    }


@app.get("/quorum/{job_id}")
def get_quorum(job_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT question, models, status, created_at FROM quorum_jobs WHERE id=%s", (job_id,)
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    question, models, status, created_at = row

    cur.execute(
        "SELECT model, response, responded_at FROM quorum_responses WHERE job_id=%s ORDER BY responded_at",
        (job_id,),
    )
    responses = [{"model": r[0], "content": r[1], "at": str(r[2])} for r in cur.fetchall()]

    cur.execute(
        "SELECT narrative, synthesis_model, created_at FROM quorum_narratives WHERE job_id=%s",
        (job_id,),
    )
    nar = cur.fetchone()
    cur.close()
    conn.close()

    return {
        "job_id": job_id,
        "question": question,
        "models": models,
        "status": status,
        "created_at": str(created_at),
        "responses": responses,
        "narrative": nar[0] if nar else None,
        "synthesis_model": nar[1] if nar else None,
    }
