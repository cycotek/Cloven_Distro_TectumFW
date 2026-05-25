from __future__ import annotations

import asyncio
import os
import re
import time
from typing import List

import httpx

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
SYNTHESIS_MODEL = os.getenv("SYNTHESIS_MODEL", "mistral-nemo:12b")
_default_models_str = os.getenv("QUORUM_MODELS", "mistral-nemo:12b,qwen2.5:7b,llama3.2:3b")
DEFAULT_MODELS: List[str] = [m.strip() for m in _default_models_str.split(",") if m.strip()]

# How much context to give each contributor model (smaller models have limited windows)
_CONTRIBUTOR_CONTEXT_CHARS = 2000
# Full context goes to the synthesis model (R1 handles long context well)
_SYNTHESIS_CONTEXT_CHARS = 12000


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


def _parse_r1(raw: str) -> tuple[str, str]:
    """
    Split a DeepSeek-R1 response into (thinking, answer).

    R1 wraps its chain-of-thought in <think>...</think> before the final answer.
    For any other model the thinking will be empty and the full text is the answer.
    """
    match = re.search(r"<think>(.*?)</think>(.*)", raw, re.DOTALL)
    if match:
        thinking = match.group(1).strip()
        answer = match.group(2).strip()
    else:
        thinking = ""
        answer = raw.strip()
    return thinking, answer


def _build_contributor_prompt(question: str, fetch_context: str) -> str:
    """Build the prompt sent to each contributor model."""
    if not fetch_context:
        return question
    snippet = fetch_context[:_CONTRIBUTOR_CONTEXT_CHARS]
    return (
        "Use the following research context to inform your answer. "
        "Prioritise facts from the context over your training data where they conflict.\n\n"
        f"--- Research Context (excerpt) ---\n{snippet}\n--- End Context ---\n\n"
        f"Question: {question}"
    )


def _build_synthesis_prompt(question: str, responses_block: str, fetch_context: str) -> str:
    """Build the synthesis prompt for the R1 model."""
    context_section = ""
    if fetch_context:
        full_ctx = fetch_context[:_SYNTHESIS_CONTEXT_CHARS]
        context_section = (
            f"Research context (retrieved sources):\n{full_ctx}\n\n"
        )
    return (
        "You are a neutral analyst synthesizing multiple AI model responses into a single narrative.\n\n"
        f"Original question: {question}\n\n"
        f"{context_section}"
        f"Model responses:\n{responses_block}\n\n"
        "Synthesize these into a clear, bias-aware narrative. "
        "Where research context is provided, ground your synthesis in those sources. "
        "Note where models agree, disagree, or show distinct perspectives. "
        "Be concise and factual."
    )


async def run_quorum(question: str, models: List[str], synthesis_model: str = "",
                    fetch_context: str = "") -> dict:
    """
    Fan the question out to all models in parallel, then synthesize with the
    designated synthesis model (ideally DeepSeek-R1 for auditable reasoning).

    Args:
        fetch_context: Optional pre-retrieved research context from tectum_fetcher.
                       Truncated version is prepended to contributor prompts;
                       full version goes to the synthesis prompt.

    Returns:
        {
            "responses": [...],
            "narrative": str,
            "synthesis_thinking": str,
            "synthesis_duration_ms": int,
            "synthesis_tokens_in": int,
            "synthesis_tokens_out": int,
        }
    """
    synth_model = synthesis_model or SYNTHESIS_MODEL
    contributor_prompt = _build_contributor_prompt(question, fetch_context)

    async with httpx.AsyncClient() as client:
        # Parallel fan-out — each model gets the context-enriched prompt
        responses: List[dict] = await asyncio.gather(
            *[_query_model(client, m, contributor_prompt) for m in models]
        )

        # Build synthesis prompt with full context
        responses_block = "\n\n".join(
            f"=== {r['model']} ===\n{r['content']}" for r in responses
        )
        synthesis_prompt = _build_synthesis_prompt(question, responses_block, fetch_context)

        try:
            synth = await _chat(client, synth_model, synthesis_prompt, timeout=300)
            thinking, narrative = _parse_r1(synth["content"])
            synthesis_duration_ms = synth["duration_ms"]
            synthesis_tokens_in = synth["tokens_in"]
            synthesis_tokens_out = synth["tokens_out"]
        except Exception as exc:
            thinking = ""
            narrative = f"[synthesis error: {exc}]"
            synthesis_duration_ms = 0
            synthesis_tokens_in = 0
            synthesis_tokens_out = 0

    return {
        "responses": responses,
        "narrative": narrative,
        "synthesis_thinking": thinking,
        "synthesis_duration_ms": synthesis_duration_ms,
        "synthesis_tokens_in": synthesis_tokens_in,
        "synthesis_tokens_out": synthesis_tokens_out,
    }
