import importlib.util
import pathlib
import socket
import unittest
import urllib.error
from unittest import mock


MODULE_PATH = pathlib.Path(__file__).parents[1] / "bridge" / "memo-bridge.py"
SPEC = importlib.util.spec_from_file_location("memo_bridge", MODULE_PATH)
memo_bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(memo_bridge)


class BriefPromptTests(unittest.TestCase):
    def test_completed_tasks_are_included_as_progress_signals(self):
        prompt = memo_bridge.build_brief_prompt(
            items=[],
            date="21/06/2026",
            context="",
            objectives=[],
            open_tasks=[],
            completed_tasks=[
                {
                    "title": "Send five messages",
                    "area": "Projects",
                    "feedback": "Two replies",
                    "completed_on": "2026-06-20T18:00:00.000Z",
                }
            ],
            system_context="Current situation from Notion",
        )

        self.assertIn("RECENTLY COMPLETED TASKS", prompt)
        self.assertIn("Send five messages", prompt)
        self.assertIn("Two replies", prompt)
        self.assertIn("A task marked Done proves it was executed, not its result", prompt)
        self.assertIn("Current situation from Notion", prompt)

    def test_no_personal_context_is_injected_when_context_is_empty(self):
        prompt = memo_bridge.build_brief_prompt([], "21/06/2026", "", [], [], [])

        self.assertNotIn("Current situation from Notion", prompt)


class WeeklyPromptTests(unittest.TestCase):
    def test_weekly_prompt_is_generic_and_marks_briefs_as_intentions(self):
        prompt = memo_bridge.build_weekly_prompt({
            "week_start": "15/06/2026",
            "week_end": "21/06/2026",
            "language": "French",
            "system_context": "Build a useful product.",
            "tasks": [{"title": "Interview users", "status": "Done"}],
        })

        self.assertIn("15/06/2026 through 21/06/2026", prompt)
        self.assertIn("Daily Brief is an intention", prompt)
        self.assertIn("person described in SYSTEM_CONTEXT", prompt)
        self.assertIn('"system_context": "Build a useful product."', prompt)


class TaskExtractionTests(unittest.TestCase):
    def test_extracts_english_task_contract(self):
        brief = """## Daily Brief

### ✅ Today's tasks
- **[Projects]** Ship the migration — keeps the system consistent

### 🎓 To learn
Nothing today.
"""

        self.assertEqual(
            memo_bridge.extract_tasks(brief),
            [{
                "area": "Projects",
                "title": "Ship the migration",
                "why": "keeps the system consistent",
            }],
        )

    def test_unknown_area_uses_configured_fallback(self):
        brief = """### ✅ Today's tasks
- **[Unknown]** Check the fallback
"""

        self.assertEqual(memo_bridge.extract_tasks(brief)[0]["area"], "Knowledge")


class PublicUrlTests(unittest.TestCase):
    @staticmethod
    def _address(ip):
        return [(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]

    @mock.patch.object(memo_bridge.socket, "getaddrinfo")
    def test_accepts_a_global_address(self, getaddrinfo):
        getaddrinfo.return_value = self._address("93.184.216.34")

        self.assertTrue(memo_bridge.is_public("https://example.com/article"))

    @mock.patch.object(memo_bridge.socket, "getaddrinfo")
    def test_rejects_private_and_mixed_dns_answers(self, getaddrinfo):
        getaddrinfo.return_value = self._address("127.0.0.1")
        self.assertFalse(memo_bridge.is_public("http://2130706433/admin"))

        getaddrinfo.return_value = self._address("93.184.216.34") + self._address("10.0.0.4")
        self.assertFalse(memo_bridge.is_public("https://mixed.example"))

    def test_rejects_credentials_and_non_http_schemes(self):
        self.assertFalse(memo_bridge.is_public("https://user:pass@example.com"))
        self.assertFalse(memo_bridge.is_public("file:///etc/passwd"))

    @mock.patch.object(memo_bridge, "is_public", return_value=False)
    def test_rejects_redirects_to_non_public_urls(self, _is_public):
        handler = memo_bridge.PublicOnlyRedirectHandler()

        with self.assertRaises(urllib.error.HTTPError):
            handler.redirect_request(mock.Mock(), None, 302, "Found", {}, "http://127.0.0.1")


class SummarizeFallbackTests(unittest.TestCase):
    @mock.patch.object(memo_bridge, "run_codex_json")
    @mock.patch.object(memo_bridge, "run_claude", return_value=None)
    def test_codex_is_used_when_claude_fails(self, _run_claude, run_codex):
        expected = {"title": "Useful watch item"}
        run_codex.return_value = expected

        parsed, engine = memo_bridge.run_summarize_engine("content")

        self.assertEqual(parsed, expected)
        self.assertEqual(engine, "codex")
        run_codex.assert_called_once_with("content")

    @mock.patch.object(memo_bridge, "run_codex_json", return_value=None)
    @mock.patch.object(memo_bridge, "run_claude", return_value=None)
    def test_local_fallback_is_signaled_when_both_engines_fail(self, _claude, _codex):
        parsed, engine = memo_bridge.run_summarize_engine("content")

        self.assertIsNone(parsed)
        self.assertEqual(engine, "none")


class RunClaudeTests(unittest.TestCase):
    """Regression guard: run_claude must parse the summarizer's JSON output.
    A missing return once made it always yield None, silently disabling Claude."""

    def test_parses_json_from_summarizer_stdout(self):
        completed = mock.Mock(returncode=0, stdout='noise {"title": "ok"} trailing')
        with mock.patch.object(memo_bridge.subprocess, "run", return_value=completed):
            self.assertEqual(memo_bridge.run_claude("content"), {"title": "ok"})

    def test_returns_none_on_nonzero_exit(self):
        failed = mock.Mock(returncode=1, stdout='{"title": "ignored"}')
        with mock.patch.object(memo_bridge.subprocess, "run", return_value=failed):
            self.assertIsNone(memo_bridge.run_claude("content"))


if __name__ == "__main__":
    unittest.main()
