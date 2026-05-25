"""
memory.py — Tectum Semantic Memory Layer

BorderManager-style semantic cache for synthesized knowledge.

Flow:
  1. Before running a quorum, call search_memory(query).
     - If a recent, similar-enough synthesis exists → return it (cache hit).
     - Otherwise → run the full pipeline.
  2. After synthesis, call store_synthesis(...) to embed and save the result.

Embedding model: nomic-embed-text via Ollama /api/embeddings (768-dim vectors)
Similarity:      cosine (pgvector <=> operator returns distance; 1 - distance = similarity)
TTL:             enforced per-query using memory_ttl_days from the QueryPacket
"""

from __future__ import annotations

import logging
import os
import uuid
from contextlib import contextmanager
from typing import Optional

import httpx
import psycopg2

log = logging.getLogger(__name__)

OLLAMA_HOST  = os.getenv("OLLAMA_HOST",  "http://ollama:11434")
EMBED_MODEL  = os.getenv("EMBED_MODEL",  "nomic-embed-text")
DATABASE_HOST = os.getenv("DATABASE_HOST", "cloven_tectum_db")
DATABASE_PORT = os.getenv("DATABASE_PORT", "5432")
DATABASE_NAME = os.getenv("DATABASE_NAME", "cloven_tectum")
DATABASE_USER = os.getenv("DATABASE_USER", "cloven")
DATABASE_PASS = os.getenv("DATABASE_PASS", "changeme")

# Minimum cosine similarity to count as a cache hit (0.0–1.0)
# 0.82 catches paraphrases (e.g. "how fast does light travel" ≈ "what is the speed of light")
# 0.88 requires very close phrasing; 0.75 is broadly permissive; 0.92 is nearly exact.
DEFAULT_SIMILARITY_THRESHOLD = float(os.getenv("MEMORY_SIMILARITY_THRESHOLD", "0.82"))


# ── DB ────────────────────────────────────────────────────────────────────────

def _dsn() -> str:
    return (
        f"host={DATABASE_HOST} port={DATABASE_PORT} "
        f"dbname={DATABASE_NAME} user={DATABASE_USER} password={DATABASE_PASS}"
    )


@contextmanager
def _db():
    conn = psycopg2.connect(_dsn())
    try:
        yield conn
    finally:
        conn.close()


# ── Embedding ─────────────────────────────────────────────────────────────────

async def embed(text: str) -> Optional[list[float]]:
    """
    Call Ollama /api/embeddings to get a vector for *text*.
    Returns None if the embed model is unavailable (graceful degradation —
    memory will simply be bypassed rather than crashing the request).
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{OLLAMA_HOST}/api/embeddings",
                json={"model": EMBED_MODEL, "prompt": text},
                timeout=30,
            )
            resp.raise_for_status()
            vec = resp.json().get("embedding")
            if not vec or len(vec) == 0:
                log.warning("Empty embedding returned for model %s", EMBED_MODEL)
                return None
            return vec
    except Exception as exc:
        log.warning("embed() failed (%s): %s", EMBED_MODEL, exc)
        return None


# ── Search ────────────────────────────────────────────────────────────────────

async def search_memory(
    query: str,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    max_age_days: int = 7,
) -> Optional[dict]:
    """
    Semantic nearest-neighbour search over tectum_memory.

    Returns the best matching memory entry as a dict, or None if:
      - No match above *threshold* similarity exists
      - The best match is older than *max_age_days*
      - The embed model is unavailable
      - Any DB error occurs

    The returned dict has:
      id, content, query, topic, intent, confidence, hit_count,
      source_job_id, source_type, created_at, similarity
    """
    vec = await embed(query)
    if vec is None:
        return None  # embed failed — bypass cache, run full pipeline

    vec_literal = "[" + ",".join(str(v) for v in vec) + "]"

    try:
        with _db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    id,
                    content,
                    query,
                    topic,
                    intent,
                    confidence,
                    hit_count,
                    source_job_id,
                    source_type,
                    created_at,
                    memory_ttl_days,
                    1 - (embedding <=> %s::vector) AS similarity
                FROM tectum_memory
                WHERE
                    created_at >= NOW() - (memory_ttl_days || ' days')::INTERVAL
                    AND 1 - (embedding <=> %s::vector) >= %s
                ORDER BY embedding <=> %s::vector
                LIMIT 1
                """,
                (vec_literal, vec_literal, threshold, vec_literal),
            )
            row = cur.fetchone()

            if row:
                # Bump hit counter and last_used_at
                cur.execute(
                    "UPDATE tectum_memory SET hit_count = hit_count + 1, "
                    "last_used_at = NOW() WHERE id = %s",
                    (row[0],),
                )
                conn.commit()
                cur.close()

                return {
                    "id":             str(row[0]),
                    "content":        row[1],
                    "query":          row[2],
                    "topic":          row[3],
                    "intent":         row[4],
                    "confidence":     row[5],
                    "hit_count":      row[6] + 1,
                    "source_job_id":  str(row[7]) if row[7] else None,
                    "source_type":    row[8],
                    "created_at":     str(row[9]),
                    "similarity":     round(float(row[11]), 4),
                }

            cur.close()
    except Exception as exc:
        log.warning("search_memory() DB error: %s", exc)

    return None


# ── Store ─────────────────────────────────────────────────────────────────────

async def store_synthesis(
    query:          str,
    content:        str,
    source_job_id:  Optional[str] = None,
    source_type:    str = "synthesis",
    intent:         str = "reference",
    memory_ttl_days: int = 7,
    topic:          str = "",
    confidence:     float = 1.0,
) -> Optional[str]:
    """
    Embed *query* (not content) and insert a new memory entry.

    We index by the question embedding so that semantically similar future
    queries ("how fast does light travel" ≈ "what is the speed of light")
    find this memory via cosine similarity.  The full answer is stored as
    content and returned on a cache hit.

    Returns the new memory row UUID, or None on failure.
    Failures are logged but never raised — a store failure must never
    break the main quorum response flow.
    """
    vec = await embed(query)   # index by QUERY, not content
    if vec is None:
        log.warning("store_synthesis: embed failed, skipping memory write")
        return None

    vec_literal = "[" + ",".join(str(v) for v in vec) + "]"
    mem_id = str(uuid.uuid4())

    try:
        with _db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO tectum_memory
                    (id, embedding, content, query, topic, intent,
                     confidence, source_job_id, source_type, memory_ttl_days)
                VALUES (%s, %s::vector, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    mem_id,
                    vec_literal,
                    content,
                    query,
                    topic or query[:80],
                    intent,
                    confidence,
                    source_job_id,
                    source_type,
                    memory_ttl_days,
                ),
            )
            conn.commit()
            cur.close()
        log.info("Memory stored: %s (intent=%s ttl=%dd)", mem_id, intent, memory_ttl_days)
        return mem_id
    except Exception as exc:
        log.warning("store_synthesis() DB error: %s", exc)
        return None
