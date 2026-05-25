"""
fetchers/network.py — Async network scanner.

Scans a host or subnet for open ports, grabs service banners,
and maps common ports to service names.  Runs fully inside the
Docker network so it can discover sibling containers.

NOT a security tool — it has no exploit payloads.  Think of it
as a "what can I connect to?" mapper for building service topology.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import List, Optional

# Well-known port → service name
_PORT_SERVICES: dict[int, str] = {
    21:    "ftp",
    22:    "ssh",
    23:    "telnet",
    25:    "smtp",
    53:    "dns",
    80:    "http",
    110:   "pop3",
    143:   "imap",
    443:   "https",
    465:   "smtps",
    587:   "smtp-submission",
    993:   "imaps",
    995:   "pop3s",
    1433:  "mssql",
    3306:  "mysql",
    5432:  "postgresql",
    5900:  "vnc",
    6379:  "redis",
    7681:  "ttyd",
    8000:  "http-alt",
    8080:  "http-proxy",
    8443:  "https-alt",
    9200:  "elasticsearch",
    11434: "ollama",
    27017: "mongodb",
}

# Common ports to scan if none specified
DEFAULT_PORTS = sorted(_PORT_SERVICES.keys())


async def _probe(host: str, port: int, timeout: float) -> Optional[dict]:
    """
    Attempts a TCP connection.  If successful, tries to read a banner.
    Returns None if the port is closed or filtered.
    """
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        banner = ""
        try:
            data = await asyncio.wait_for(reader.read(256), timeout=2.0)
            banner = data.decode("utf-8", errors="replace").strip()[:200]
        except Exception:
            pass
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return {
            "host":    host,
            "port":    port,
            "service": _PORT_SERVICES.get(port, "unknown"),
            "banner":  banner,
            "open":    True,
        }
    except Exception:
        return None


async def scan_host(
    host: str,
    ports: Optional[List[int]] = None,
    timeout: float = 1.0,
    concurrency: int = 50,
) -> List[dict]:
    """
    Scans the given host for open ports and returns a list of open port dicts.

    Args:
        host:        IP address or hostname
        ports:       list of ports to scan (defaults to well-known ports)
        timeout:     per-port TCP connect timeout in seconds
        concurrency: max parallel connections
    """
    target_ports = ports or DEFAULT_PORTS
    sem = asyncio.Semaphore(concurrency)

    async def _guarded(port: int) -> Optional[dict]:
        async with sem:
            return await _probe(host, port, timeout)

    results = await asyncio.gather(*[_guarded(p) for p in target_ports])
    return [r for r in results if r is not None]


async def scan_subnet(
    subnet: str,
    ports: Optional[List[int]] = None,
    timeout: float = 0.5,
    max_hosts: int = 254,
) -> List[dict]:
    """
    Scans all hosts in a CIDR subnet (e.g. '172.20.0.0/24').

    Returns a flat list of open port dicts across all responsive hosts.
    Capped at max_hosts to avoid runaway scans.
    """
    network = ipaddress.IPv4Network(subnet, strict=False)
    hosts = [str(ip) for ip in network.hosts()][:max_hosts]

    all_open: List[dict] = []
    for host in hosts:
        open_ports = await scan_host(host, ports, timeout)
        all_open.extend(open_ports)

    return all_open


def resolve(hostname: str) -> str:
    """Resolves a hostname to IP, returns original string on failure."""
    try:
        return socket.gethostbyname(hostname)
    except Exception:
        return hostname
