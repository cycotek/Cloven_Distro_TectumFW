#!/usr/bin/env python3
"""
take_screenshots.py — CDP-based screenshot tool for TectumFW UI documentation.

Launches Chrome headless, loads the TectumFW UI, sets up each required UI state,
and saves PNG screenshots to assets/screenshots/.
"""

import asyncio
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request

try:
    import websockets
except ImportError:
    print("Installing websockets...")
    os.system("pip3 install websockets --break-system-packages -q")
    import websockets

CHROME = "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"
API    = "http://localhost:8000"
SHOTS  = os.path.join(os.path.dirname(__file__), "assets", "screenshots")
CDP_PORT = 9224  # use a port that won't conflict with existing Chrome

# WSL2: Chrome opens its CDP port on Windows localhost, not the WSL2 interface.
# Detect the Windows host IP (the default route gateway from WSL2).
import subprocess as _sp
try:
    _gw = _sp.check_output("ip route show | grep default | awk '{print $3}'",
                            shell=True, text=True).strip()
    CDP_HOST = _gw if _gw else "localhost"
except Exception:
    CDP_HOST = "localhost"

os.makedirs(SHOTS, exist_ok=True)


# ── CDP helpers ────────────────────────────────────────────────────────────────

async def cdp_send(ws, method, params=None, id_=1):
    msg = json.dumps({"id": id_, "method": method, "params": params or {}})
    await ws.send(msg)
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=30)
        data = json.loads(raw)
        if data.get("id") == id_:
            return data.get("result", {})


async def screenshot(ws, outpath, clip=None):
    params = {"format": "png"}
    if clip:
        params["clip"] = {**clip, "scale": 1}
    result = await cdp_send(ws, "Page.captureScreenshot", params, id_=99)
    png = base64.b64decode(result["data"])
    with open(outpath, "wb") as f:
        f.write(png)
    print(f"  saved {outpath} ({len(png)//1024}KB)")


async def navigate_and_wait(ws, url, wait_ms=2000):
    await cdp_send(ws, "Page.navigate", {"url": url}, id_=10)
    await asyncio.sleep(wait_ms / 1000)


async def exec_js(ws, expr, wait_ms=500):
    result = await cdp_send(ws, "Runtime.evaluate", {
        "expression": expr,
        "awaitPromise": True,
        "returnByValue": True,
    }, id_=20)
    await asyncio.sleep(wait_ms / 1000)
    return result


async def wait_for_js(ws, condition, timeout=20, poll_ms=500):
    """Poll until JS expression returns truthy."""
    for _ in range(int(timeout * 1000 / poll_ms)):
        r = await cdp_send(ws, "Runtime.evaluate",
                           {"expression": condition, "returnByValue": True}, id_=21)
        val = r.get("result", {}).get("value")
        if val:
            return True
        await asyncio.sleep(poll_ms / 1000)
    return False


# ── API helpers ────────────────────────────────────────────────────────────────

def api_get(path):
    with urllib.request.urlopen(f"{API}{path}", timeout=10) as r:
        return json.loads(r.read())


def find_job(intent=None, status="complete", keywords=None):
    jobs = api_get("/quorum/history?limit=50")
    for j in jobs:
        if status and j.get("status") != status:
            continue
        if intent and j.get("intent") != intent:
            continue
        q = j.get("question", "").lower()
        if keywords and not any(k in q for k in keywords):
            continue
        return j["job_id"]
    return None


# ── Main screenshot workflow ────────────────────────────────────────────────────

async def capture_all(ws):
    BASE = f"{API}"

    # ── 1. Load fresh page — history sidebar + query panel ──────────────────────
    print("1/8  ui_history.png + ui_query_panel.png")
    await navigate_and_wait(ws, BASE, wait_ms=3000)
    # Clear question box so query panel looks clean
    await exec_js(ws, "document.getElementById('question-box').value=''")
    await asyncio.sleep(0.5)

    await screenshot(ws, os.path.join(SHOTS, "ui_history.png"))

    # Crop to just the query panel (right column, top portion)
    await screenshot(ws, os.path.join(SHOTS, "ui_query_panel.png"),
                     clip={"x": 255, "y": 55, "width": 1200, "height": 320})

    # ── 2. Status bar — submit a question and capture the loading state ──────────
    print("2/8  ui_status_bar.png")
    await navigate_and_wait(ws, BASE, wait_ms=2000)
    # Type question and click Run Quorum
    await exec_js(ws, """
        document.getElementById('question-box').value = 'what is the boiling point of water';
    """)
    await asyncio.sleep(0.3)
    await exec_js(ws, "document.querySelector('button[onclick=\"runQuorum()\"] , button#run-btn, .run-btn, button').click()")
    await asyncio.sleep(0.4)
    # Capture quickly while the status bar is showing
    await screenshot(ws, os.path.join(SHOTS, "ui_status_bar.png"))

    # ── 3-5. Memory hit: "what is the speed of light" ───────────────────────────
    print("3-5/8  memory hit screenshots")

    # Find the direct/memory job
    direct_job = find_job(intent="direct", keywords=["speed of light", "light"])
    if not direct_job:
        # Submit it fresh — it should hit memory
        await navigate_and_wait(ws, BASE, wait_ms=2000)
        await exec_js(ws, """
            document.getElementById('question-box').value = 'what is the speed of light';
        """)
        await exec_js(ws, """
            (async () => {
              const btn = document.querySelector('button');
              if (btn) btn.click();
            })()
        """, wait_ms=5000)
    else:
        await navigate_and_wait(ws, BASE, wait_ms=2000)
        await exec_js(ws, f"loadJob('{direct_job}')", wait_ms=3000)

    # Wait for result
    await wait_for_js(ws, "document.querySelector('.badge-row, .memory-meta, #result-area') !== null", timeout=15)
    await asyncio.sleep(1)

    # Full view
    await screenshot(ws, os.path.join(SHOTS, "ui_full_memory.png"))

    # Badge row close-up
    await screenshot(ws, os.path.join(SHOTS, "ui_badges_memory.png"),
                     clip={"x": 255, "y": 355, "width": 900, "height": 120})

    # Memory meta bar
    await screenshot(ws, os.path.join(SHOTS, "ui_memory_hit.png"),
                     clip={"x": 255, "y": 355, "width": 900, "height": 200})

    # ── 6-7. Model cards + synthesis — find a full quorum result ────────────────
    print("6-7/8  model cards + synthesis")

    quorum_job = find_job(intent="reference", keywords=["diabetes", "stars", "woodchuck", "pizza"])
    if not quorum_job:
        quorum_job = find_job(status="complete", keywords=["diabetes", "stars"])

    if quorum_job:
        await navigate_and_wait(ws, BASE, wait_ms=2000)
        await exec_js(ws, f"loadJob('{quorum_job}')", wait_ms=4000)
        await wait_for_js(ws, "document.querySelectorAll('.model-card, .response-card').length > 0", timeout=10)
        await asyncio.sleep(1.5)
    else:
        # Submit fresh quorum
        await navigate_and_wait(ws, BASE, wait_ms=2000)
        await exec_js(ws, """
            document.getElementById('question-box').value = 'what are black holes';
        """)
        await exec_js(ws, """document.querySelector('button').click()""", wait_ms=60000)
        await wait_for_js(ws, "document.querySelectorAll('.model-card, .response-card').length > 0", timeout=120)
        await asyncio.sleep(2)

    # Try to expand R1 reasoning block if present
    await exec_js(ws, """
        const details = document.querySelector('details');
        if (details) details.open = true;
    """, wait_ms=500)

    await screenshot(ws, os.path.join(SHOTS, "ui_model_cards.png"))
    await screenshot(ws, os.path.join(SHOTS, "ui_synthesis.png"),
                     clip={"x": 255, "y": 350, "width": 1200, "height": 600})

    print("\nAll screenshots saved to:", SHOTS)
    for f in sorted(os.listdir(SHOTS)):
        if f.endswith(".png"):
            size = os.path.getsize(os.path.join(SHOTS, f))
            print(f"  {f:40s}  {size//1024:4d}KB")


async def main():
    # Start Chrome headless with CDP
    chrome_args = [
        CHROME,
        f"--remote-debugging-port={CDP_PORT}",
        "--remote-debugging-address=0.0.0.0",  # bind all interfaces so WSL2 can reach it
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--window-size=1456,819",
        "--disable-extensions",
        "--disable-translate",
        "--no-first-run",
        "--disable-default-apps",
    ]
    print(f"Starting Chrome headless on CDP port {CDP_PORT}...")
    proc = subprocess.Popen(chrome_args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)

    try:
        # Discover the CDP WebSocket URL — Chrome opened on Windows host
        print(f"CDP host: {CDP_HOST}:{CDP_PORT}")
        with urllib.request.urlopen(f"http://{CDP_HOST}:{CDP_PORT}/json/version", timeout=10) as r:
            info = json.loads(r.read())
        ws_url = info["webSocketDebuggerUrl"]
        # Replace 'localhost' in ws_url with the actual host
        ws_url = ws_url.replace("localhost", CDP_HOST)
        print(f"CDP connected: {ws_url}")

        async with websockets.connect(ws_url, max_size=50_000_000) as ws:
            await cdp_send(ws, "Runtime.enable", id_=1)
            await cdp_send(ws, "Page.enable", id_=2)
            await capture_all(ws)

    finally:
        proc.terminate()
        print("Chrome closed.")


if __name__ == "__main__":
    asyncio.run(main())
