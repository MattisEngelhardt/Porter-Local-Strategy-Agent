"""Shared SearXNG health diagnostics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_ENGINE_OUTAGE_THRESHOLD = 2


def _engine_name(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, Mapping):
        for key in ("engine", "name"):
            value = item.get(key)
            if value:
                return str(value).strip()
        return ""
    if isinstance(item, Sequence) and not isinstance(item, (bytes, bytearray)):
        if item:
            return str(item[0]).strip()
    return ""


def unresponsive_engine_names(data: Mapping[str, Any]) -> list[str]:
    """Return unique engine names from SearXNG's ``unresponsive_engines`` field."""
    raw = data.get("unresponsive_engines") or []
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        return []

    names: list[str] = []
    seen: set[str] = set()
    for item in raw:
        name = _engine_name(item)
        if not name or name in seen:
            continue
        names.append(name)
        seen.add(name)
    return names


def searxng_engine_outage_message(base_url: str, data: Mapping[str, Any]) -> str | None:
    """Diagnose the case where SearXNG is up but its upstream engines are failing."""
    results = data.get("results") or []
    if isinstance(results, Sequence) and not isinstance(results, (str, bytes, bytearray)):
        if len(results) > 0:
            return None

    engines = unresponsive_engine_names(data)
    if len(engines) < _ENGINE_OUTAGE_THRESHOLD:
        return None

    base = base_url.rstrip("/")
    listed = ", ".join(engines[:8])
    if len(engines) > 8:
        listed += f", +{len(engines) - 8} more"

    return (
        "SearXNG is reachable and JSON is enabled, but search engines are failing.\n"
        f"Unresponsive engines: {listed}.\n"
        "Fix:\n"
        "  1. Inspect logs: 'docker compose logs --tail 80 searxng'.\n"
        "  2. If logs show CERTIFICATE_VERIFY_FAILED, the Docker container does not trust "
        "the local proxy/VPN CA.\n"
        "  3. Refresh the mounted CA in searxng-data/certs/*.crt, then run "
        "'docker compose restart searxng'.\n"
        "  4. SearXNG verifies with /etc/ssl/certs/ca-certificates.crt; do not "
        "set 'outgoing.verify: false'.\n"
        f'  5. Verify: curl "{base}/search?q=OpenAI&format=json".'
    )
