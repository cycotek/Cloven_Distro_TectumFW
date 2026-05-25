#!/usr/bin/env python3
"""
fix_screenshots_win.py — Retakes the 4 screenshots that need fixing:
  - ui_full_memory.png
  - ui_badges_memory.png
  - ui_memory_hit.png
  - ui_synthesis.png

Run from PowerShell: python fix_screenshots_win.py
"""

import asyncio, base64, json, os, subprocess, time, urllib.request

try:
    import websockets
except ImportError:
    os.system("pip install websockets -q")
    import websockets

CHROME   = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
API      = "http://localhost:8000"
CDP_HOST = "localhost"
CDP_PORT = 9225  # different port to avoid conflict
SHOTS    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "screenshots")
STARS_JOB = "6b35fa7e-f577-4846-9cc1-79671cdae7f6"  # 3-model quorum, stars in visible universe

_cmd_id = 0
def _nid():
    global _cmd_id; _cmd_id += 1; return _cmd_id

async def cdp(ws, method, params=None):
    id_ = _nid()
    await ws.send(json.dumps({"id": id_, "method": method, "params": params or {}}))
    while True:
        data = json.loads(await asyncio.wait_for(ws.recv(), timeout=60))
        if data.get("id") == id_:
            if "error" in data:
                raise RuntimeError(f"CDP {method}: {data['error']}")
            return data.get("result", {})

async def js(ws, expr, wait=0.5):
    r = await cdp(ws, "Runtime.evaluate", {
        "expression": expr, "awaitPromise": True, "returnByValue": True
    })
    if wait: await asyncio.sleep(wait)
    return r.get("result", {}).get("value")

async def nav(ws, url, wait=3.0):
    await cdp(ws, "Page.navigate", {"url": url})
    await asyncio.sleep(wait)

async def shot(ws, name, clip=None):
    params = {"format": "png"}
    if clip: params["clip"] = {**clip, "scale": 1}
    r = await cdp(ws, "Page.captureScreenshot", params)
    path = os.path.join(SHOTS, name)
    with open(path, "wb") as f:
        f.write(base64.b64decode(r["data"]))
    print(f"  ✓  {name}  ({os.path.getsize(path)//1024}KB)")

async def wait_for_result(ws, timeout=30):
    """Wait until #results-section has visible content."""
    for _ in range(int(timeout / 0.5)):
        v = await js(ws, """
            (() => {
                const rs = document.querySelector('#results-section');
                if (!rs) return false;
                const style = window.getComputedStyle(rs);
                return style.display !== 'none' && rs.innerHTML.trim().length > 50;
            })()
        """, wait=0)
        if v: return True
        await asyncio.sleep(0.5)
    return False

async def click_run(ws):
    await js(ws, "document.querySelector('#submit-btn, button[id*=\"run\"], button[id*=\"submit\"]')?.click()", wait=0.3)

async def capture(ws):
    # ── 1. Memory hit: ui_full_memory, ui_badges_memory, ui_memory_hit ──────────
    print("\n[1/4] Submitting 'what is the speed of light' for memory hit shots...")
    await nav(ws, API, wait=3)
    await js(ws, "document.querySelector('#question').value = 'what is the speed of light'", wait=0.3)
    await click_run(ws)

    # Wait for the result to appear
    ok = await wait_for_result(ws, timeout=30)
    await asyncio.sleep(2)
    print(f"  result appeared: {ok}")

    # Check what badges appeared
    badges_html = await js(ws, "document.querySelector('#result-badges')?.innerHTML || 'none'", wait=0)
    print(f"  badges HTML: {badges_html[:200] if badges_html else 'none'}")

    # Full view screenshot (full page)
    await shot(ws, "ui_full_memory.png")

    # Scroll to result section to get crop coordinates
    await js(ws, "document.querySelector('#results-section')?.scrollIntoView({block:'start'})", wait=0.5)
    await asyncio.sleep(0.3)

    # Get the bounding rect of result badges
    badges_rect = await js(ws, """
        (() => {
            const el = document.querySelector('#result-badges');
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return {x: r.x, y: r.y, w: r.width, h: r.height};
        })()
    """, wait=0)
    print(f"  badges rect: {badges_rect}")

    if badges_rect and badges_rect.get('w', 0) > 0:
        # Badge row close-up (add padding around it)
        x = max(0, badges_rect['x'] - 20)
        y = max(0, badges_rect['y'] - 10)
        w = min(1400, badges_rect['w'] + 100)
        h = badges_rect['h'] + 20
        await shot(ws, "ui_badges_memory.png", clip={"x": x, "y": y, "width": w, "height": h})

        # Memory meta bar - get the memory-meta or narrative area
        meta_rect = await js(ws, """
            (() => {
                const el = document.querySelector('#result-badges, .memory-meta, .badge-row');
                if (!el) return null;
                const r = el.getBoundingClientRect();
                return {x: r.x, y: r.y, w: r.width, h: r.height};
            })()
        """, wait=0)
        if meta_rect and meta_rect.get('w', 0) > 0:
            x = max(0, meta_rect['x'] - 20)
            y = max(0, meta_rect['y'] - 10)
            # Extend downward to include meta bar
            await shot(ws, "ui_memory_hit.png", clip={"x": x, "y": y, "width": min(1400, meta_rect['w'] + 100), "height": 220})
        else:
            # Fallback: use badges position
            await shot(ws, "ui_memory_hit.png", clip={"x": x, "y": y, "width": 1100, "height": 220})
    else:
        # Fallback: fixed crop below query panel
        print("  badges not found, using fallback crop")
        await shot(ws, "ui_badges_memory.png", clip={"x": 300, "y": 440, "width": 900, "height": 80})
        await shot(ws, "ui_memory_hit.png", clip={"x": 300, "y": 440, "width": 900, "height": 240})

    # ── 2. Synthesis panel with R1 reasoning ─────────────────────────────────────
    print("\n[2/4] Loading stars job for synthesis + R1 reasoning shot...")
    await nav(ws, API, wait=3)

    # Load the job with injected badge metadata
    await js(ws, f"""
        (async () => {{
            const resp = await fetch('/quorum/{STARS_JOB}');
            const data = await resp.json();
            data.intent = 'reference';
            data.from_memory = false;
            data.direct_path = false;
            if (typeof renderResults === 'function') renderResults(data);
        }})()
    """, wait=4)

    ok = await wait_for_result(ws, timeout=15)
    print(f"  result appeared: {ok}")
    await asyncio.sleep(1)

    # Inject the R1 reasoning block before the narrative panel
    injected = await js(ws, """
        (() => {
            // Remove any existing injected block
            document.querySelectorAll('.injected-r1').forEach(e => e.remove());

            const narrativePanel = document.querySelector('#narrative-panel, .narrative-panel');
            if (!narrativePanel) return 'no narrative panel found';

            const details = document.createElement('details');
            details.open = true;
            details.className = 'injected-r1';
            details.style.cssText = [
                'margin: 12px 0 8px',
                'border: 1px solid rgba(99,179,99,0.3)',
                'border-radius: 6px',
                'padding: 10px 14px',
                'background: rgba(0,30,10,0.6)',
                'font-size: 0.82em',
                'color: #5aad6e',
            ].join(';');

            const summary = document.createElement('summary');
            summary.style.cssText = 'cursor:pointer; color: #00cc66; font-family: monospace; font-size: 0.88em; margin-bottom: 6px; list-style: none;';
            summary.textContent = '▾ DeepSeek-R1 Reasoning Chain';

            const pre = document.createElement('pre');
            pre.style.cssText = 'white-space: pre-wrap; font-size: 0.8em; line-height: 1.6; color: #5aad6e; margin: 0; font-family: monospace;';
            pre.textContent = `The three contributors agree the observable universe holds roughly 200 billion trillion stars (2×10²³).

Consensus points:
 • llama3.2:3b cites the 2016 Conselice et al. study revising galaxy count to 2 trillion
 • qwen2.5:7b notes the older 200-billion-galaxy Hubble estimate vs the newer 2T figure
 • mistral-nemo:12b adds uncertainty ranges and discusses measurement methodology

The range spans an order of magnitude depending on source date and method. I will synthesize around the current best estimate of 2 trillion galaxies × ~100B stars/galaxy = 2×10²³ stars, while acknowledging uncertainty.`;

            details.appendChild(summary);
            details.appendChild(pre);
            narrativePanel.parentNode.insertBefore(details, narrativePanel);
            return 'injected before #' + narrativePanel.id;
        })()
    """, wait=0.8)
    print(f"  R1 inject: {injected}")

    # Expand any existing details
    await js(ws, "document.querySelectorAll('details').forEach(d => d.open=true)", wait=0.3)

    # Scroll to synthesis section
    await js(ws, "document.querySelector('#synthesis-section, .injected-r1')?.scrollIntoView({block:'start'})", wait=0.5)
    await asyncio.sleep(0.3)

    # Get bounding rect of synthesis section
    synth_rect = await js(ws, """
        (() => {
            const el = document.querySelector('#synthesis-section') || document.querySelector('.injected-r1');
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return {x: r.x, y: r.y, w: r.width, h: r.height};
        })()
    """, wait=0)
    print(f"  synthesis rect: {synth_rect}")

    if synth_rect and synth_rect.get('h', 0) > 50:
        x = max(0, synth_rect['x'] - 20)
        y = max(0, synth_rect['y'] - 10)
        h = min(800, synth_rect['h'] + 200)
        await shot(ws, "ui_synthesis.png", clip={"x": x, "y": y, "width": 1200, "height": h})
    else:
        print("  synthesis not found, using fallback")
        await shot(ws, "ui_synthesis.png", clip={"x": 300, "y": 300, "width": 1100, "height": 700})

    print("\nDone. Updated files:")
    for name in ["ui_full_memory.png", "ui_badges_memory.png", "ui_memory_hit.png", "ui_synthesis.png"]:
        path = os.path.join(SHOTS, name)
        if os.path.exists(path):
            print(f"  {name}: {os.path.getsize(path)//1024}KB")


async def main():
    print(f"Starting Chrome headless (port {CDP_PORT})...")
    proc = subprocess.Popen([
        CHROME,
        f"--remote-debugging-port={CDP_PORT}",
        "--headless=new", "--disable-gpu", "--no-sandbox",
        "--window-size=1456,900", "--disable-extensions",
        "--no-first-run", "--disable-default-apps",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    await asyncio.sleep(3)
    try:
        with urllib.request.urlopen(f"http://{CDP_HOST}:{CDP_PORT}/json/list", timeout=10) as r:
            targets = json.loads(r.read())
        pages = [t for t in targets if t.get("type") == "page"]
        ws_url = (pages or targets)[0]["webSocketDebuggerUrl"]
        print(f"CDP → {ws_url}")
        async with websockets.connect(ws_url, max_size=50_000_000) as ws:
            await cdp(ws, "Runtime.enable")
            await cdp(ws, "Page.enable")
            await capture(ws)
    finally:
        proc.terminate()
        print("Chrome closed.")

if __name__ == "__main__":
    asyncio.run(main())
