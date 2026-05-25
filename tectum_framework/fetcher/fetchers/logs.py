"""
fetchers/logs.py — Log and error analysis fetcher.

Accepts raw log text (or a file path) and returns structured analysis:
  - detected error types
  - parsed stack traces
  - frequency counts
  - suggested search queries for each error

No external dependencies beyond stdlib.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional


# ── Pattern registry ──────────────────────────────────────────────────────────

_PATTERNS = {
    "python_exception":  re.compile(
        r"(?P<exc>[A-Z][a-zA-Z]+Error|Exception|Warning):\s*(?P<msg>.+)", re.MULTILINE
    ),
    "python_traceback":  re.compile(
        r'File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<fn>\S+)', re.MULTILINE
    ),
    "java_exception":    re.compile(
        r"(?P<exc>[a-z][a-zA-Z.]+Exception):\s*(?P<msg>.+)", re.MULTILINE
    ),
    "java_stackframe":   re.compile(
        r"\s+at (?P<cls>[a-zA-Z][a-zA-Z0-9_.]+)\((?P<file>[^:]+):(?P<line>\d+)\)", re.MULTILINE
    ),
    "http_error":        re.compile(
        r'(?:HTTP|http)[/ ](?:1\.[01]|2) (?P<code>[45]\d\d)\b', re.MULTILINE
    ),
    "oom":               re.compile(
        r"(?i)(out of memory|oom killer|cannot allocate|memory error)", re.MULTILINE
    ),
    "segfault":          re.compile(
        r"(?i)(segmentation fault|sigsegv|core dumped)", re.MULTILINE
    ),
    "connection_refused":re.compile(
        r"(?i)(connection refused|ECONNREFUSED|no route to host|ETIMEDOUT)", re.MULTILINE
    ),
    "disk_full":         re.compile(
        r"(?i)(no space left on device|disk full|ENOSPC)", re.MULTILINE
    ),
    "permission_denied": re.compile(
        r"(?i)(permission denied|EACCES|EPERM|access denied)", re.MULTILINE
    ),
    "null_pointer":      re.compile(
        r"(?i)(null pointer|NullPointerException|NoneType.*has no attribute)", re.MULTILINE
    ),
    "timeout":           re.compile(
        r"(?i)(timeout|timed out|ETIMEDOUT|ReadTimeout|ConnectTimeout)", re.MULTILINE
    ),
    "docker_error":      re.compile(
        r"(?i)(container.*exited|failed to start container|docker.*error|OCI runtime)", re.MULTILINE
    ),
    "postgres_error":    re.compile(
        r"(?i)(ERROR:\s+(?P<pg_msg>[^\n]+))", re.MULTILINE
    ),
}

_SEARCH_TEMPLATES: dict[str, str] = {
    "python_exception":   'python "{exc}" "{msg}"',
    "java_exception":     'java "{exc}" fix',
    "http_error":         'HTTP {code} error fix',
    "oom":                "out of memory error fix linux",
    "segfault":           "segmentation fault debugging",
    "connection_refused": "connection refused fix {msg}",
    "disk_full":          "no space left on device fix",
    "permission_denied":  "permission denied fix linux",
    "null_pointer":       "null pointer exception fix",
    "timeout":            "connection timeout fix {msg}",
    "docker_error":       "docker container error fix",
    "postgres_error":     'postgresql "{pg_msg}" fix',
}


# ── Public API ────────────────────────────────────────────────────────────────

def analyze_text(log_text: str) -> dict:
    """
    Analyzes raw log text and returns:
    {
        "total_lines": int,
        "findings": [
            {
                "type": str,
                "count": int,
                "matches": [{"groups": {...}, "line": str}, ...],
                "search_suggestions": [str, ...],
            },
            ...
        ],
        "summary": str,
    }
    """
    lines = log_text.splitlines()
    findings = []

    for name, pattern in _PATTERNS.items():
        matches_raw = list(pattern.finditer(log_text))
        if not matches_raw:
            continue

        # De-duplicate: keep up to 5 unique matches
        seen: set[str] = set()
        unique_matches = []
        for m in matches_raw:
            key = str(m.groupdict())
            if key not in seen:
                seen.add(key)
                # Grab the source line
                start_line = log_text[:m.start()].count("\n")
                line_text = lines[start_line] if start_line < len(lines) else ""
                unique_matches.append({"groups": m.groupdict(), "line": line_text.strip()})
            if len(unique_matches) >= 5:
                break

        # Build search suggestion from first match
        tpl = _SEARCH_TEMPLATES.get(name, "{type} fix")
        first_groups = unique_matches[0]["groups"] if unique_matches else {}
        try:
            suggestion = tpl.format(type=name, **{k: v or "" for k, v in first_groups.items()})
        except KeyError:
            suggestion = f"{name} fix"

        findings.append({
            "type":               name,
            "count":              len(matches_raw),
            "matches":            unique_matches,
            "search_suggestions": [suggestion.strip()],
        })

    # Sort by count desc
    findings.sort(key=lambda f: f["count"], reverse=True)

    # One-line summary
    if findings:
        top = findings[0]
        summary = (
            f"Found {len(findings)} error type(s) in {len(lines)} lines. "
            f"Most frequent: {top['type']} ({top['count']} occurrence(s))."
        )
    else:
        summary = f"No known error patterns detected in {len(lines)} lines."

    return {
        "total_lines": len(lines),
        "findings":    findings,
        "summary":     summary,
    }


def analyze_file(path: str) -> dict:
    """Reads a log file and runs analysis."""
    p = Path(path)
    if not p.exists():
        return {"total_lines": 0, "findings": [], "summary": f"File not found: {path}"}
    text = p.read_text(errors="replace")
    result = analyze_text(text)
    result["source_file"] = str(p.resolve())
    return result
