"""
Tests for slack_notifier.SlackNotifier.

The pre-existing test_slack_notification.py imports SlackNotifier from
dba_ai_agent, which is a different class from the one monitor_and_alert.py
actually uses. That left the notifier used in production with no test at all,
which is how the unconfigured-send bug survived.

Every case below corresponds to a real defect found in review.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from slack_notifier import SlackNotifier  # noqa: E402

SLACK_VARS = (
    "SLACK_WEBHOOK_URL",
    "SLACK_TOKEN",
    "SLACK_CHANNEL",
    "SLACK_TIMEOUT_SECONDS",
)


@pytest.fixture(autouse=True)
def _clear_slack_env(monkeypatch):
    for var in SLACK_VARS:
        monkeypatch.delenv(var, raising=False)


class _Response:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = {"ok": True} if body is None else body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._body


class TestDisabled:
    def test_no_config_means_no_request(self):
        """The bug: it fell through to the Web API and sent
        `Authorization: Bearer None`, then returned True on the 2xx error
        envelope Slack replies with."""
        notifier = SlackNotifier()
        assert notifier.enabled is False
        with patch("slack_notifier.requests.post") as post:
            assert notifier.send_alert("Test", "message") is False
        post.assert_not_called()

    def test_token_without_channel_is_not_enabled(self, monkeypatch):
        monkeypatch.setenv("SLACK_TOKEN", "xoxb-test")
        monkeypatch.setenv("SLACK_CHANNEL", "")
        notifier = SlackNotifier()
        # SLACK_CHANNEL="" must not fall back to the default and look configured.
        assert notifier.enabled is (bool(notifier.channel))

    def test_empty_string_is_treated_as_unset(self, monkeypatch):
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "")
        monkeypatch.setenv("SLACK_TOKEN", "")
        assert SlackNotifier().enabled is False


class TestWebhook:
    def test_success(self, monkeypatch):
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.example.test/x")
        with patch("slack_notifier.requests.post", return_value=_Response()) as post:
            assert SlackNotifier().send_alert("Test", "message") is True
        assert post.call_args.args[0] == "https://hooks.example.test/x"

    def test_http_error_returns_false(self, monkeypatch):
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.example.test/x")
        with patch("slack_notifier.requests.post", return_value=_Response(500)):
            assert SlackNotifier().send_alert("Test", "message") is False

    def test_timeout_is_passed(self, monkeypatch):
        """A notifier without a timeout blocks the monitoring loop forever."""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.example.test/x")
        with patch("slack_notifier.requests.post", return_value=_Response()) as post:
            SlackNotifier().send_alert("Test", "message")
        assert post.call_args.kwargs["timeout"] > 0


class TestWebApi:
    def test_used_only_when_webhook_absent(self, monkeypatch):
        monkeypatch.setenv("SLACK_TOKEN", "xoxb-test")
        with patch("slack_notifier.requests.post", return_value=_Response()) as post:
            assert SlackNotifier().send_alert("Test", "message") is True
        assert post.call_args.args[0] == SlackNotifier.API_URL
        assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer xoxb-test"

    def test_ok_false_is_a_failure(self, monkeypatch):
        """Slack answers 200 with {"ok": false} for a bad token or channel, so
        the status code alone is not an outcome."""
        monkeypatch.setenv("SLACK_TOKEN", "xoxb-test")
        body = {"ok": False, "error": "invalid_auth"}
        with patch("slack_notifier.requests.post", return_value=_Response(200, body)):
            assert SlackNotifier().send_alert("Test", "message") is False

    def test_never_sends_bearer_none(self, monkeypatch):
        monkeypatch.setenv("SLACK_TOKEN", "xoxb-test")
        with patch("slack_notifier.requests.post", return_value=_Response()) as post:
            SlackNotifier().send_alert("Test", "message")
        assert "None" not in post.call_args.kwargs["headers"]["Authorization"]


class TestTypedAlerts:
    def test_typed_alerts_respect_the_disabled_guard(self):
        """Every helper routes through send_alert, so none may reach the network
        while unconfigured."""
        notifier = SlackNotifier()
        with patch("slack_notifier.requests.post") as post:
            assert notifier.send_query_alert({
                "database": "db", "query": "SELECT 1",
                "duration": 1, "rows": 0, "cache_hit_ratio": 99,
            }) is False
        post.assert_not_called()


class TestNoCannedReports:
    def test_fabricated_report_methods_are_gone(self):
        """These sent a hardcoded analysis of a 420 GB `shop` database with
        invented table names and figures, unrelated to whatever the operator
        configured. Publishing that would be fabricated output."""
        for name in ("send_database_analysis", "send_optimization_recommendations"):
            assert not hasattr(SlackNotifier, name), (
                f"{name} reports fixed numbers for a database nobody configured"
            )
