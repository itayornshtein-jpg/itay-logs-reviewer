from datetime import datetime

import logs_reviewer.app as app
from logs_reviewer.analyzer import analyze_logs
from logs_reviewer.app import HISTORY_LIMIT, _build_sources, _connect_chatgpt, _history, _record_history, _session_payload
from logs_reviewer.reader import LogSource


def test_build_sources_rejects_non_list_files():
    _history.clear()
    payload = {"files": "not-a-list"}

    assert list(_build_sources(payload)) == []
    assert _history == []  # history should remain untouched


def test_record_history_is_capped_and_prepend_order():
    _history.clear()
    entries = HISTORY_LIMIT + 2

    for idx in range(entries):
        _record_history([LogSource(name=f"file{idx}.log", lines=[])], f"message {idx}")

    assert len(_history) == HISTORY_LIMIT
    assert _history[0]["message"] == f"message {entries - 1}"
    assert _history[-1]["message"] == f"message {entries - HISTORY_LIMIT}"
    assert _history[0]["files"] == [f"file{entries - 1}.log"]


def test_session_payload_reports_status():
    app._chatgpt_session = None

    assert _session_payload() == {"connected": False}

    app._chatgpt_session = type(
        "MockSession",
        (),
        {
            "account": "tester@example.com",
            "resource_summary": "models: gpt-4o-mini",
            "token_hint": "***test",
            "connected_at": datetime(2024, 1, 1, 12, 0, 0),
        },
    )()

    payload = _session_payload()
    assert payload["connected"] is True
    assert payload["account"] == "tester@example.com"
    assert payload["resource_summary"].startswith("models")


def test_connect_chatgpt_updates_session():
    app._chatgpt_session = None

    response = _connect_chatgpt({"token": "secret-token", "resources": {"models": ["gpt-4o-mini"]}})

    assert response["connected"] is True
    assert "gpt-4o-mini" in response["resource_summary"]
    assert app._chatgpt_session is not None


def test_local_summary_payload_includes_deduped_errors():
    sources = [
        LogSource(name="app.log", lines=["ERROR Something failed", "error something failed"]),
        LogSource(name="worker.log", lines=["ValueError: boom"]),
    ]

    report = analyze_logs(sources)
    payload = app._local_summary_payload(report)

    assert payload["errors"] == payload["unique_errors"]
    assert len(payload["errors"]) == 2
    assert payload["errors"][0]["source"] == "app.log"
    assert payload["errors"][0]["line_no"] == 1
