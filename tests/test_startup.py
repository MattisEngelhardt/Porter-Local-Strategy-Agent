"""Tests for startup dependency checks."""

from __future__ import annotations

from typing import Any

import pytest

from core.config import AppConfig
from core.startup import StartupError, check_searxng


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


def test_check_searxng_raises_when_engines_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    """JSON availability alone is not healthy when all upstream engines are failing."""
    config = AppConfig()

    def fake_get(url: str, params: dict[str, str], timeout: float) -> _FakeResponse:
        assert url == "http://localhost:8888/search"
        assert params == {"q": "OpenAI", "format": "json"}
        assert timeout == 5.0
        return _FakeResponse(
            {
                "results": [],
                "unresponsive_engines": [
                    ["brave", "HTTP connection error"],
                    ["duckduckgo", "HTTP connection error"],
                    ["wikipedia", "HTTP connection error"],
                ],
            }
        )

    monkeypatch.setattr("core.startup.httpx.get", fake_get)

    with pytest.raises(StartupError) as excinfo:
        check_searxng(config)

    message = str(excinfo.value)
    assert "search engines are failing" in message
    assert "CERTIFICATE_VERIFY_FAILED" in message
    assert "searxng-data/certs" in message
    assert "do not set 'outgoing.verify: false'" in message


def test_check_searxng_allows_empty_results_without_engine_outage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A genuinely empty result page should not be treated as an infra failure."""
    config = AppConfig()

    def fake_get(url: str, params: dict[str, str], timeout: float) -> _FakeResponse:
        return _FakeResponse({"results": [], "unresponsive_engines": []})

    monkeypatch.setattr("core.startup.httpx.get", fake_get)

    check_searxng(config)
