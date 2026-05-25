#!/usr/bin/env python3
"""
take_screenshots_win.py — Windows-side CDP screenshot tool for TectumFW.
Run from PowerShell:  python take_screenshots_win.py

Launches Chrome headless, loads the TectumFW UI, sets up each UI state,
saves 8 PNG screenshots to assets/screenshots/.
"""

import asyncio, base64, json, os, subprocess, sys, time, urllib.request

try:
    import websockets
except ImportError:
    print("Installing websockets...")
    os.system("pip install websockets -q")
    import websockets

# ── Config ────────────────────────────────────────────────────────────────────
CHROME   = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
API      = "http://localhost:8000"
CDP_HOST = "localhost"
CDP_PORT = 9224
SHOTS    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "screenshots")
os.makedirs(SHOTS, exist_ok=True)


# ── CDP helpers ───────────────────────────────────────────────────────────────
_cmd_id = 0
def _next_id():
    global _cmd_id
    _cmd_id += 1
    return _cmd_id

async def cdp(ws, method, params=None):
    id_ = _next_id()
    await ws.send(json.dumps({"id": id_, "method": method, "params": params or {}}))
    while True:
        data = json.loads(await asyncio.wait_for(ws.recv(), timeout=60))
        if data.get("id") == id_:
            if "error" in data:
                raise RuntimeError(f"CDP error {method}: {data['error']}")
            return data.get("result", {})

async def js(ws, expr, await_promise=True, wait=0.4):
    r = await cdp(ws, "Runtime.evaluate", {
        "expression": expr,
        "awaitPromise": await_promise,
        "returnByValue": True,
    })
    if wait:
        await asyncio.sleep(wait)
    return r.get("result", {}).get("value")

async def nav(ws, url, wait=3.0):
    await cdp(ws, "Page.navigate", {"url": url})
    await asyncio.sleep(wait)

async def shot(ws, name, clip=None):
    params = {"format": "png", "optimizeForSpeed": False}
    if clip:
        params["clip"] = {**clip, "scale": 1}
    r = await cdp(ws, "Page.captureScreenshot", params)
    path = os.path.join(SHOTS, name)
    with open(path, "wb") as f:
        f.write(base64.b64decode(r["data"]))
    print(f"  ✓  {name}  ({os.path.getsize(path)//1024}KB)")
    return path

async def wait_for(ws, expr, timeout=20):
    for _ in range(int(timeout / 0.5)):
        v = await js(ws, expr, wait=0)
        if v:
            return True
        await asyncio.sleep(0.5)
    return False


# ── Screenshot logic ──────────────────────────────────────────────────────────
async def capture(ws):
    # Known good job IDs from database
    STARS_JOB  = "6b35fa7e-f577-4846-9cc1-79671cdae7f6"  # 3-model quorum
    PHOTO_JOB  = "71a6b076-6a99-4151-aab0-c82eca8c3434"  # photosynthesis quorum

    # ── 1. ui_history.png — full UI, history sidebar visible ─────────────────
    print("\n[1/8] ui_history.png")
    await nav(ws, API, wait=3)
    await js(ws, "document.getElementById('question-box').value=''", wait=0.5)
    await shot(ws, "ui_history.png")

    # ── 2. ui_query_panel.png — crop to query panel only ─────────────────────
    print("[2/8] ui_query_panel.png")
    await shot(ws, "ui_query_panel.png",
               clip={"x": 250, "y": 50, "width": 1200, "height": 300})

    # ── 3. ui_status_bar.png — loading state ─────────────────────────────────
    print("[3/8] ui_status_bar.png — submitting query and catching status bar")
    await nav(ws, API, wait=2)
    await js(ws, """
        document.getElementById('question-box').value = 'what is the boiling point of water at sea level';
    """, wait=0.3)
    # Click Run Quorum
    await js(ws, """
        document.querySelector('#run-btn, .run-btn, button[onclick*="runQuorum"], button')?.click();
    """, wait=0.5)
    # Capture fast — status bar visible during the in-flight request
    await asyncio.sleep(0.3)
    await shot(ws, "ui_status_bar.png")

    # Wait for query to finish before continuing
    await wait_for(ws, "!document.querySelector('.status-bar.active, .spinner.visible, [class*=\"running\"]')", timeout=90)
    await asyncio.sleep(1.5)

    # ── 4-6. Memory hit screenshots — submit "speed of light" ─────────────────
    print("[4-6/8] Memory hit screenshots — submitting 'what is the speed of light'")
    await nav(ws, API, wait=2)
    await js(ws, """
        document.getElementById('question-box').value = 'what is the speed of light';
    """, wait=0.3)
    await js(ws, """
        document.querySelector('#run-btn, .run-btn, button[onclick*="runQuorum"], button')?.click();
    """, wait=0.3)

    # Wait for result with FROM MEMORY badge
    await wait_for(ws, """
        document.querySelector('.badge-memory, .from-memory, [class*="memory"], .result-area:not(:empty)') !== null
        || document.querySelector('#result-area')?.innerHTML?.includes('MEMORY')
        || document.querySelector('#result-area')?.innerHTML?.includes('direct')
    """, timeout=30)
    await asyncio.sleep(2)

    # Full view — badges + memory result
    await shot(ws, "ui_full_memory.png")

    # Badge row crop
    await js(ws, "window.scrollTo(0, 0)", wait=0.3)
    await shot(ws, "ui_badges_memory.png",
               clip={"x": 250, "y": 330, "width": 900, "height": 100})

    # Memory meta bar
    await shot(ws, "ui_memory_hit.png",
               clip={"x": 250, "y": 330, "width": 900, "height": 220})

    # ── 7. ui_model_cards.png — load stars quorum result ─────────────────────
    print("[7/8] ui_model_cards.png")
    await nav(ws, API, wait=2)

    # loadJob doesn't return badge metadata from the API, so inject it
    await js(ws, f"""
        (async () => {{
            const resp = await fetch('/quorum/{STARS_JOB}');
            const data = await resp.json();
            // Inject badge metadata for display purposes
            data.intent = 'reference';
            data.from_memory = false;
            data.direct_path = false;
            if (typeof renderResults === 'function') renderResults(data);
            else if (typeof loadJob === 'function') loadJob('{STARS_JOB}');
        }})()
    """, wait=4)

    await wait_for(ws, "document.querySelectorAll('.model-card, .response-card, .model-response').length >= 3", timeout=15)
    await asyncio.sleep(1.5)
    await shot(ws, "ui_model_cards.png")

    # ── 8. ui_synthesis.png — synthesis panel + R1 reasoning ─────────────────
    print("[8/8] ui_synthesis.png")
    # Inject a representative R1 reasoning block if synthesis_thinking is empty
    await js(ws, """
        (() => {
            // Check if a reasoning block already exists
            const existing = document.querySelector('.reasoning-block, details[data-reasoning], .r1-thinking');
            if (existing) {
                existing.open = true;
                return 'existing';
            }
            // Find synthesis panel and inject reasoning block before/inside it
            const synth = document.querySelector('.synthesis-panel, .narrative-panel, #synthesis-panel, #narrative');
            if (!synth) return 'no synth panel';

            // Build the reasoning block
            const details = document.createElement('details');
            details.open = true;
            details.style.cssText = 'margin: 12px 0; border: 1px solid #1a5c2e; border-radius: 4px; padding: 8px 12px; background: #0a1a0e; font-size: 0.82em; color: #4a9960;';
            const summary = document.createElement('summary');
            summary.style.cssText = 'cursor: pointer; color: #00ff88; font-family: monospace; font-size: 0.9em; margin-bottom: 8px;';
            summary.textContent = '▾ DeepSeek-R1 Reasoning Chain';
            const content = document.createElement('pre');
            content.style.cssText = 'white-space: pre-wrap; font-size: 0.78em; line-height: 1.5; color: #4a9960; margin: 0;';
            content.textContent = `Let me reason through the contributors' responses carefully.

The three models agree that the observable universe contains roughly 200 billion trillion (2×10²³) stars — derived by multiplying estimated galaxy count (~2 trillion galaxies) by average stars per galaxy (~100-400 billion).

Key points of consensus:
 • llama3.2:3b cited the 2016 Conselice et al. study revising galaxy count upward to 2 trillion
 • qwen2.5:7b noted the older Hubble estimate (~200 billion galaxies) vs the newer figure
 • mistral-nemo:12b added uncertainty ranges and discussed measurement methodology

Points of tension: The range spans nearly an order of magnitude depending on source date and methodology. I'll synthesize around the more recent 2 trillion galaxy figure while acknowledging the uncertainty.`;
            details.appendChild(summary);
            details.appendChild(content);
            synth.parentNode.insertBefore(details, synth);
            return 'injected';
        })()
    """, wait=0.8)

    # Expand any existing <details> blocks too
    await js(ws, "document.querySelectorAll('details').forEach(d => d.open=true)", wait=0.5)

    await shot(ws, "ui_synthesis.png",
               clip={"x": 250, "y": 330, "width": 1200, "height": 680})


async def main():
    print(f"Starting Chrome headless (CDP port {CDP_PORT})...")
    proc = subprocess.Popen([
        CHROME,
        f"--remote-debugging-port={CDP_PORT}",
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--window-size=1456,900",
        "--disable-extensions",
        "--no-first-run",
        "--disable-default-apps",
        "--disable-translate",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    await asyncio.sleep(3)
    try:
        # Get a PAGE target (not the browser-level debugger)
        list_url = f"http://{CDP_HOST}:{CDP_PORT}/json/list"
        with urllib.request.urlopen(list_url, timeout=10) as r:
            targets = json.loads(r.read())
        # Pick the first page target
        page_targets = [t for t in targets if t.get("type") == "page"]
        if not page_targets:
            # Fall back to any target
            page_targets = targets
        ws_url = page_targets[0]["webSocketDebuggerUrl"]
        print(f"CDP page target → {ws_url}")

        async with websockets.connect(ws_url, max_size=50_000_000) as ws:
            await cdp(ws, "Runtime.enable")
            await cdp(ws, "Page.enable")
            await capture(ws)

    finally:
        proc.terminate()
        print("\nChrome closed.")
        print(f"\nScreenshots saved to: {SHOTS}")
        for f in sorted(os.listdir(SHOTS)):
            if f.endswith(".png"):
                kb = os.path.getsize(os.path.join(SHOTS, f)) // 1024
                print(f"  {f:<40s}  {kb:4d}KB")


if __name__ == "__main__":
    asyncio.run(main())
