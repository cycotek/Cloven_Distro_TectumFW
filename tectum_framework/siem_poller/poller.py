#!/usr/bin/env python3
"""
TectumFW SIEM Poller — polls UniFi MCP /events and forwards new events to /siem

Runs as a Docker sidecar in the TectumFW stack. Tracks last-seen event
datetime in a state file so restarts don't re-process old events.

Env vars:
  UNIFI_MCP_URL     URL of the UniFi MCP wrapper (default: http://192.168.1.232:8100)
  UNIFI_MCP_KEY     MCP_API_KEY for the UniFi MCP wrapper (required)
  TECTUM_SIEM_URL   TectumFW /siem endpoint (default: http://cloven_tectum_api:8000/siem)
  POLL_INTERVAL     Seconds between polls (default: 30)
  EVENT_LIMIT       Max events to fetch per poll (default: 200)
  STATE_FILE        Path to persist last-seen timestamp (default: /tmp/siem_poller_state.json)
"""

import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from urllib.error import URLError
from urllib.request import Request, urlopen

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

UNIFI_MCP_URL  = os.getenv("UNIFI_MCP_URL",  "http://192.168.1.232:8100")
UNIFI_MCP_KEY  = os.getenv("UNIFI_MCP_KEY",  "")
TECTUM_SIEM    = os.getenv("TECTUM_SIEM_URL", "http://cloven_tectum_api:8000/siem")
POLL_INTERVAL  = int(os.getenv("POLL_INTERVAL", "30"))
EVENT_LIMIT    = int(os.getenv("EVENT_LIMIT",   "200"))
STATE_FILE     = os.getenv("STATE_FILE", "/tmp/siem_poller_state.json")

_running = True


def _sig(sig, _frame):
    global _running
    log.info("Signal %d — stopping", sig)
    _running = False


signal.signal(signal.SIGTERM, _sig)
signal.signal(signal.SIGINT,  _sig)


# ── State persistence ─────────────────────────────────────────────────────────

def load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"last_seen_at": None, "last_seen_id": None}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _get(url: str, headers: dict) -> dict | list | None:
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except URLError as exc:
        log.warning("GET %s failed: %s", url, exc)
        return None


def _post(url: str, payload: dict, retries: int = 3) -> bool:
    body = json.dumps(payload).encode()
    req  = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    for attempt in range(1, retries + 1):
        try:
            with urlopen(req, timeout=10) as resp:
                log.debug("POST %s  status=%d", url, resp.status)
                return True
        except URLError as exc:
            log.warning("POST attempt %d/%d: %s", attempt, retries, exc)
            if attempt < retries:
                time.sleep(2 * attempt)
    return False


# ── Event processing ──────────────────────────────────────────────────────────

def _event_datetime(evt: dict) -> str | None:
    """Extract a sortable ISO datetime from a UniFi event dict."""
    for field in ("datetime", "time", "timestamp", "created_at"):
        val = evt.get(field)
        if val:
            return str(val)
    return None


def _is_new(evt: dict, last_seen_at: str | None) -> bool:
    if last_seen_at is None:
        return True
    dt = _event_datetime(evt)
    if dt is None:
        return True
    return dt > last_seen_at


def poll_once(state: dict) -> dict:
    if not UNIFI_MCP_KEY:
        log.error("UNIFI_MCP_KEY is not set — cannot authenticate to UniFi MCP")
        return state

    headers = {"Authorization": f"Bearer {UNIFI_MCP_KEY}"}
    url     = f"{UNIFI_MCP_URL}/events?limit={EVENT_LIMIT}"

    data = _get(url, headers)
    if data is None:
        return state

    # UniFi MCP returns {"status":"ok","data":{"count":N,"events":[...]}}
    # Also handle flat list or {"data":[...]} shapes for forward-compat.
    if isinstance(data, list):
        events = data
    elif isinstance(data, dict):
        inner = data.get("data", data)
        if isinstance(inner, dict):
            events = inner.get("events", inner.get("data", []))
        elif isinstance(inner, list):
            events = inner
        else:
            events = data.get("events", [])
    else:
        events = []
    if not isinstance(events, list):
        log.warning("Unexpected /events response shape: %s", type(events))
        return state

    new_events = [e for e in events if _is_new(e, state["last_seen_at"])]
    if not new_events:
        log.debug("No new events (total fetched: %d)", len(events))
        return state

    log.info("Forwarding %d new event(s) to SIEM (of %d fetched)", len(new_events), len(events))

    latest_at = state["last_seen_at"]
    latest_id = state["last_seen_id"]

    for evt in new_events:
        ok = _post(TECTUM_SIEM, evt)
        if ok:
            dt = _event_datetime(evt)
            eid = evt.get("_id") or evt.get("id")
            if dt and (latest_at is None or dt > latest_at):
                latest_at = dt
                latest_id = eid
        else:
            log.error("Failed to forward event %s — stopping this batch to avoid gaps",
                      evt.get("_id", "?"))
            break

    return {"last_seen_at": latest_at, "last_seen_id": latest_id}


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    if not UNIFI_MCP_KEY:
        log.error("UNIFI_MCP_KEY is required. Set it in the environment / .env file.")
        sys.exit(1)

    log.info("SIEM poller starting — %s → %s  interval=%ds",
             UNIFI_MCP_URL, TECTUM_SIEM, POLL_INTERVAL)

    state = load_state()
    log.info("Resuming from last_seen_at=%s", state.get("last_seen_at") or "beginning")

    while _running:
        try:
            state = poll_once(state)
            save_state(state)
        except Exception as exc:
            log.exception("Unexpected error in poll_once: %s", exc)
        time.sleep(POLL_INTERVAL)

    log.info("Poller stopped.")


if __name__ == "__main__":
    main()
