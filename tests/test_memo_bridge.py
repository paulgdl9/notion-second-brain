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
                    "titre": "Envoyer cinq messages",
                    "domaine": "Projects",
                    "feedback": "Deux reponses",
                    "terminee_le": "2026-06-20T18:00:00.000Z",
                }
            ],
            system_context="Situation actuelle depuis Notion",
        )

        self.assertIn("TÂCHES TERMINÉES RÉCEMMENT", prompt)
        self.assertIn("Envoyer cinq messages", prompt)
        self.assertIn("Deux reponses", prompt)
        self.assertIn("Une tâche marquée Fait prouve son exécution, pas son résultat", prompt)
        self.assertIn("Situation actuelle depuis Notion", prompt)

    def test_no_personal_context_is_injected_when_context_is_empty(self):
        prompt = memo_bridge.build_brief_prompt([], "21/06/2026", "", [], [], [])

        self.assertNotIn("Situation actuelle depuis Notion", prompt)


class SummarizeFallbackTests(unittest.TestCase):
    @mock.patch.object(memo_bridge, "run_codex_json")
    @mock.patch.object(memo_bridge, "run_claude", return_value=None)
    def test_codex_is_used_when_claude_fails(self, _run_claude, run_codex):
        expected = {"title": "Veille utile"}
        run_codex.return_value = expected

        parsed, engine = memo_bridge.run_summarize_engine("contenu")

        self.assertEqual(parsed, expected)
        self.assertEqual(engine, "codex")
        run_codex.assert_called_once_with("contenu")

    @mock.patch.object(memo_bridge, "run_codex_json", return_value=None)
    @mock.patch.object(memo_bridge, "run_claude", return_value=None)
    def test_local_fallback_is_signaled_when_both_engines_fail(self, _claude, _codex):
        parsed, engine = memo_bridge.run_summarize_engine("contenu")

        self.assertIsNone(parsed)
        self.assertEqual(engine, "none")


class RunClaudeTests(unittest.TestCase):
    """Regression guard: run_claude must parse the summarizer's JSON output.
    A missing return once made it always yield None, silently disabling Claude."""

    def test_parses_json_from_summarizer_stdout(self):
        completed = mock.Mock(returncode=0, stdout='noise {"title": "ok"} trailing')
        with mock.patch.object(memo_bridge.subprocess, "run", return_value=completed):
            self.assertEqual(memo_bridge.run_claude("contenu"), {"title": "ok"})

    def test_returns_none_on_nonzero_exit(self):
        failed = mock.Mock(returncode=1, stdout='{"title": "ignored"}')
        with mock.patch.object(memo_bridge.subprocess, "run", return_value=failed):
            self.assertIsNone(memo_bridge.run_claude("contenu"))


if __name__ == "__main__":
    unittest.main()
