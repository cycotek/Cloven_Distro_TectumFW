from __future__ import annotations

import asyncio
import os
from typing import List

import httpx

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
SYNTHESIS_MODEL = os.getenv("SYNTHESIS_MODEL", "mistral-nemo:12b")
_default_models_str = os.getenv("QUORUM_MODELS", "mistral-nemo:12b,qwen2.5:7b,llama3.2:3b")
DEFAULT_MODELS: List[str] = [m.strip() for m in _default_models_str.split(",") if m.strip()]


async def _chat(client: httpx.AsyncClient, model: str, prompt: str, timeout: float = 120) -> str:
    """Send a single chat request to Ollama. Returns the response text."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    resp = await client.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()["message"]["content"]


async def _query_model(client: httpx.AsyncClient, model: str, question: str) -> dict:
    """Query one model, return {model, content}. Never raises — errors are captured."""
    try:
        content = await _chat(client, model, question)
    except Exception as exc:
        content = f"[error from {model}: {exc}]"
    return {"model": model, "content": content}


async def run_quorum(question: str, models: List[str]) -> dict:
    """
    Fan the question out to all models in parallel, then synthesize.

    Returns:
        {
            "responses": [{"model": ..., "content": ...}, ...],
            "narrative": str,
        }
    """
    async with httpx.AsyncClient() as client:
        # Parallel fan-out
        responses: List[dict] = await asyncio.gather(
            *[_query_model(client, m, question) for m in models]
        )

        # Synthesis
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
            narrative = await _chat(client, SYNTHESIS_MODEL, synthesis_prompt, timeout=180)
        except Exception as exc:
            narrative = f"[synthesis error: {exc}]"

    return {"responses": responses, "narrative": narrative}
