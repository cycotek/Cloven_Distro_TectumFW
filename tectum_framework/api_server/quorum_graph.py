from __future__ import annotations

import os
import operator
import uuid
from typing import TypedDict, List, Annotated

import litellm
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
SYNTHESIS_MODEL = os.getenv("SYNTHESIS_MODEL", "mistral-nemo:12b")
_default_models_str = os.getenv("QUORUM_MODELS", "mistral-nemo:12b,qwen2.5:7b,llama3.2:3b")
DEFAULT_MODELS = [m.strip() for m in _default_models_str.split(",") if m.strip()]

litellm.drop_params = True


class QuorumState(TypedDict):
    job_id: str
    question: str
    models: List[str]
    responses: Annotated[List[dict], operator.add]
    narrative: str


def initialize(state: QuorumState) -> dict:
    return {
        "job_id": state.get("job_id") or str(uuid.uuid4()),
        "models": state.get("models") or DEFAULT_MODELS,
        "responses": [],
        "narrative": "",
    }


def route_to_models(state: QuorumState):
    return [
        Send("query_model", {"question": state["question"], "target_model": m})
        for m in state["models"]
    ]


def query_model(state: dict) -> dict:
    model = state["target_model"]
    try:
        resp = litellm.completion(
            model=f"ollama/{model}",
            messages=[{"role": "user", "content": state["question"]}],
            api_base=OLLAMA_HOST,
            timeout=120,
        )
        content = resp.choices[0].message.content or ""
    except Exception as e:
        content = f"[error from {model}: {e}]"
    return {"responses": [{"model": model, "content": content}]}


def synthesize(state: QuorumState) -> dict:
    responses_block = "\n\n".join(
        f"=== {r['model']} ===\n{r['content']}" for r in state["responses"]
    )
    prompt = (
        f"You are a neutral analyst synthesizing multiple AI model responses into a single narrative.\n\n"
        f"Original question: {state['question']}\n\n"
        f"Model responses:\n{responses_block}\n\n"
        f"Synthesize these into a clear, bias-aware narrative. Note where models agree, disagree, "
        f"or show distinct perspectives. Be concise and factual."
    )
    try:
        resp = litellm.completion(
            model=f"ollama/{SYNTHESIS_MODEL}",
            messages=[{"role": "user", "content": prompt}],
            api_base=OLLAMA_HOST,
            timeout=180,
        )
        narrative = resp.choices[0].message.content or ""
    except Exception as e:
        narrative = f"[synthesis error: {e}]"
    return {"narrative": narrative}


def build_quorum_graph():
    g = StateGraph(QuorumState)
    g.add_node("initialize", initialize)
    g.add_node("query_model", query_model)
    g.add_node("synthesize", synthesize)

    g.add_edge(START, "initialize")
    g.add_conditional_edges("initialize", route_to_models, ["query_model"])
    g.add_edge("query_model", "synthesize")
    g.add_edge("synthesize", END)

    return g.compile()


quorum_graph = build_quorum_graph()
