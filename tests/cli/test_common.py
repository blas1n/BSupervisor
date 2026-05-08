"""Unit tests for ``bsupervisor.cli.commands._common`` helpers.

Targets the JSON-decode-failure and non-dict-body fallback branches in
:func:`emit_http_error` that the per-sub-app integration tests don't
naturally exercise.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from bsupervisor.cli.commands._common import emit_http_error


def test_emit_http_error_json_decode_failure(capsys: pytest.CaptureFixture[str]) -> None:
    resp = MagicMock()
    resp.status_code = 502
    resp.json.side_effect = ValueError("not json")
    resp.text = "<html>upstream proxy timeout</html>"

    emit_http_error(resp)
    captured = capsys.readouterr()
    assert "HTTP 502" in captured.err
    assert "upstream proxy timeout" in captured.err
    assert "Traceback" not in captured.err


def test_emit_http_error_caps_long_text(capsys: pytest.CaptureFixture[str]) -> None:
    resp = MagicMock()
    resp.status_code = 500
    resp.json.side_effect = ValueError("not json")
    resp.text = "x" * 5000

    emit_http_error(resp)
    captured = capsys.readouterr()
    # Body is capped at 300 chars + "Error: HTTP 500 — " prefix overhead.
    assert len(captured.err) < 400


def test_emit_http_error_non_dict_body(capsys: pytest.CaptureFixture[str]) -> None:
    resp = MagicMock()
    resp.status_code = 422
    resp.json.return_value = ["validation", "errors"]
    resp.text = '["validation", "errors"]'

    emit_http_error(resp)
    captured = capsys.readouterr()
    assert "HTTP 422" in captured.err
    assert "validation" in captured.err
