from logs_reviewer.app import HISTORY_LIMIT, _build_sources, _history, _record_history
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
