"""Tests for structured logging setup."""

import json

import pytest

from paperless_webdav.logging import setup_logging, get_logger


def test_setup_logging_json_format(capsys: pytest.CaptureFixture[str]) -> None:
    """JSON format should produce valid JSON output."""
    setup_logging(log_level="INFO", log_format="json")
    logger = get_logger("test")

    logger.info("test message", user_id="barry", action="login")

    captured = capsys.readouterr()
    log_line = captured.err.strip()
    parsed = json.loads(log_line)

    assert parsed["event"] == "test message"
    assert parsed["user_id"] == "barry"
    assert parsed["action"] == "login"
    assert "timestamp" in parsed


def test_logger_never_includes_secrets(capsys: pytest.CaptureFixture[str]) -> None:
    """Ensure sensitive fields are redacted."""
    setup_logging(log_level="INFO", log_format="json")
    logger = get_logger("test")

    logger.info("auth", token="secret123", password="hunter2")

    captured = capsys.readouterr()
    log_output = captured.err.strip()

    # Verify secrets are NOT in output
    assert "secret123" not in log_output
    assert "hunter2" not in log_output

    # Verify redaction marker IS present
    assert "[REDACTED]" in log_output

    # Verify JSON structure
    parsed = json.loads(log_output)
    assert parsed["token"] == "[REDACTED]"
    assert parsed["password"] == "[REDACTED]"
