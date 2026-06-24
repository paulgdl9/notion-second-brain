import importlib.util
import pathlib
import sys
import unittest


MODULE_PATH = pathlib.Path(__file__).parents[1] / "scripts" / "system-context-onboarding.py"
SPEC = importlib.util.spec_from_file_location("system_context_onboarding", MODULE_PATH)
onboarding = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = onboarding
SPEC.loader.exec_module(onboarding)


class SystemContextRenderingTests(unittest.TestCase):
    def test_renders_stable_memory_contract(self):
        markdown = onboarding.render_system_context(
            {
                "identity": "Freelance developer building a Notion+n8n second brain.",
                "year_outcomes": "Ship the personal operating system.",
                "next_90_days": "Simplify the cockpit before adding new surfaces.",
                "active_projects": "Second Brain - daily execution and memory compression.",
                "areas": "Projects, Health, Learning",
            },
            generated_at="2026-06-24",
        )

        self.assertIn("# System Context", markdown)
        self.assertIn("## Direction", markdown)
        self.assertIn("- Simplify the cockpit before adding new surfaces.", markdown)
        self.assertIn("### Task areas", markdown)
        self.assertIn("- Projects", markdown)
        self.assertIn("## Memory Maintenance Rules", markdown)
        self.assertIn("stable memory, not a daily log", markdown)
        self.assertIn("Prefer simplifying the existing system", markdown)

    def test_uses_env_areas_when_answer_is_empty(self):
        markdown = onboarding.render_system_context(
            {"identity": "Operator", "areas": ""},
            areas=["Work", "Knowledge"],
            generated_at="2026-06-24",
        )

        self.assertIn("- Work", markdown)
        self.assertIn("- Knowledge", markdown)

    def test_keeps_commas_inside_regular_answers(self):
        markdown = onboarding.render_system_context(
            {
                "identity": "Developer, founder, and systems thinker",
                "areas": "Projects, Health",
            },
            generated_at="2026-06-24",
        )

        self.assertIn("- Developer, founder, and systems thinker", markdown)
        self.assertIn("- Projects", markdown)
        self.assertIn("- Health", markdown)


if __name__ == "__main__":
    unittest.main()
