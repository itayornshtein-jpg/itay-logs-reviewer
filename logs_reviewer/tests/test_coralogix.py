import json

import pytest

import logs_reviewer.coralogix as coralogix
from logs_reviewer import app
from logs_reviewer.reader import LogSource


def test_search_logs_sends_payload(monkeypatch):
    captured: dict = {}

    class FakeResponse:
        def __init__(self, body: bytes):
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return self._body

    def fake_urlopen(request, timeout, context):
        captured["url"] = request.full_url
        captured["data"] = json.loads(request.data.decode("utf-8"))
        captured["headers"] = request.headers
        captured["timeout"] = timeout
        captured["context"] = context
        return FakeResponse(b'{"hits": 1, "records": []}')

    monkeypatch.setenv("CORALOGIX_API_KEY", "test-key")
    monkeypatch.setenv("CORALOGIX_DOMAIN", "example.coralogix.com")
    monkeypatch.setattr(coralogix, "urlopen", fake_urlopen)

    result = coralogix.search_logs(
        "error",
        {"from": "2024-01-01T00:00:00Z", "to": "2024-01-01T01:00:00Z"},
        filters={"severity": "error"},
        pagination={"limit": 15, "offset": 5},
        timeout=5,
    )

    assert result["hits"] == 1
    assert captured["url"] == "https://example.coralogix.com/api/v1/logs/search"
    assert captured["data"]["query"] == "error"
    assert captured["data"]["filters"] == {"severity": "error"}
    assert captured["data"]["pagination"] == {"limit": 15, "offset": 5}
    assert captured["timeout"] == 5
    assert captured["headers"]["Authorization"].endswith("test-key")
    assert captured["context"]


def test_search_logs_validates_timeframe(monkeypatch):
    monkeypatch.setenv("CORALOGIX_API_KEY", "test-key")

    with pytest.raises(ValueError):
        coralogix.search_logs("error", {"from": "missing-to"})


def test_perform_coralogix_search_uses_history(monkeypatch):
    app._history.clear()
    app._record_history([LogSource(name="errors.log", lines=[])], "latest summary")

    captured: dict = {}

    def fake_search_logs(query, timeframe, filters=None, **_):
        captured["query"] = query
        captured["timeframe"] = timeframe
        captured["filters"] = filters
        return {"hits": 0, "records": []}

    monkeypatch.setattr(app, "search_logs", fake_search_logs)

    payload = {"timeframe": {"from": "2024-01-01T00:00:00Z", "to": "2024-01-02T00:00:00Z"}, "use_last_summary": True}
    result = app._perform_coralogix_search(payload)

    assert result["hits"] == 0
    assert captured["query"] == "latest summary"
    assert captured["timeframe"]["from"].startswith("2024-01-01")


def test_perform_coralogix_search_forwards_api_key(monkeypatch):
    captured: dict = {}

    def fake_search_logs(**kwargs):
        captured.update(kwargs)
        return {"hits": 0, "records": []}

    monkeypatch.setattr(app, "search_logs", fake_search_logs)

    payload = {
        "query": "error",
        "timeframe": {"from": "2024-01-01T00:00:00Z", "to": "2024-01-01T01:00:00Z"},
        "api_key": "user-provided-key",
    }

    result = app._perform_coralogix_search(payload)

    assert result["hits"] == 0
    assert captured["api_key"] == "user-provided-key"
    assert captured["query"] == "error"
