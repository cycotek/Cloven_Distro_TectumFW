from __future__ import annotations

import asyncio
import os
import time
from typing import List

import httpx

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
SYNTHESIS_MODEL = os.getenv("SYNTHESIS_MODEL", "mistral-nemo:12b")
_default_models_str = os.getenv("QUORUM_MODELS", "mistral-nemo:12b,qwen2.5:7b,llama3.2:3b")
DEFAULT_MODELS: List[str] = [m.strip() for m in _default_models_str.split(",") if m.strip()]


async def _chat(client: httpx.AsyncClient, model: str, prompt: str, timeout: float = 120) -> dict:
    """
    Send a single chat request to Ollama.

    Returns a dict with:
        content      str   — the model's response text
        duration_ms  int   — wall-clock time in milliseconds
        tokens_in    int   — prompt token count
        tokens_out   int   — completion token count
    """
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    t0 = time.monotonic()
    resp = await client.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=timeout)
    duration_ms = int((time.monotonic() - t0) * 1000)
    resp.raise_for_status()
    data = resp.json()

    return {
        "content": data.get("message", {}).get("content", ""),
        "duration_ms": duration_ms,
        "tokens_in": data.get("prompt_eval_count", 0),
        "tokens_out": data.get("eval_count", 0),
    }


async def _query_model(client: httpx.AsyncClient, model: str, question: str) -> dict:
    """Query one model, return {model, content, duration_ms, tokens_in, tokens_out}. Never raises."""
    try:
        result = await _chat(client, model, question)
    except Exception as exc:
        result = {
            "content": f"[error from {model}: {exc}]",
            "duration_ms": 0,
            "tokens_in": 0,
            "tokens_out": 0,
        }
    return {"model": model, **result}


async def run_quorum(question: str, models: List[str]) -> dict:
    """
    Fan the question out to all models in parallel, then synthesize.

    Returns:
        {
            "responses": [
                {"model": str, "content": str, "duration_ms": int, "tokens_in": int, "tokens_out": int},
                ...
            ],
            "narrative": str,
            "synthesis_duration_ms": int,
            "synthesis_tokens_in": int,
            "synthesis_tokens_out": int,
        }
    """
    async with httpx.AsyncClient() as client:
        # Parallel fan-out
        responses: List[dict] = await asyncio.gather(
            *[_query_model(client, m, question) for m in models]
        )

        # Build synthesis prompt from all responses
        responses_block = "\n\n".join(
            f"=== {r['model']} ===\n{r['content']}" for r in responses
        )
        synthesis_prompt = (
            "You are a neutral analyst synthesizing multiple AI model responses into a single narrative.\n\n"
            f"Original question: {question}\n\n"
            f"Model responses:\n{responses_block}\n\n"
            "Synthesize these into a clear, bias-aware narrative. Note where models agree, disagree, "
            "or show distinct perspectives. Be concise and factual."
        )

        try:
            synth = await _chat(client, SYNTHESIS_MODEL, synthesis_prompt, timeout=180)
            narrative = synth["content"]
            synthesis_duration_ms = synth["duration_ms"]
            synthesis_tokens_in = synth["tokens_in"]
            synthesis_tokens_out = synth["tokens_out"]
        except Exception as exc:
            narrative = f"[synthesis error: {exc}]"
            synthesis_duration_ms = 0
            synthesis_tokens_in = 0
            synthesis_tokens_out = 0

    return {
        "responses": responses,
        "narrative": narrative,
        "synthesis_duration_ms": synthesis_duration_ms,
        "synthesis_tokens_in": synthesis_tokens_in,
        "synthesis_tokens_out": synthesis_tokens_out,
    }
