import importlib.util
import pathlib
import unittest
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
