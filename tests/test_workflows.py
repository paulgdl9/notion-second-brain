import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).parents[1]
WORKFLOW_DIR = ROOT / "workflows"


class WorkflowContractTests(unittest.TestCase):
    def _workflows(self):
        for path in sorted(WORKFLOW_DIR.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertIsInstance(data, list, path.name)
            for workflow in data:
                yield path, workflow

    def test_connections_reference_existing_nodes(self):
        for path, workflow in self._workflows():
            node_names = {node["name"] for node in workflow["nodes"]}
            self.assertEqual(len(node_names), len(workflow["nodes"]), path.name)
            for source, outputs in workflow.get("connections", {}).items():
                self.assertIn(source, node_names, f"{path.name}: missing source {source}")
                for channel in outputs.values():
                    for branch in channel:
                        for connection in branch or []:
                            self.assertIn(
                                connection["node"],
                                node_names,
                                f"{path.name}: missing target {connection['node']}",
                            )

    def test_daily_brief_uses_english_notion_contract(self):
        content = (WORKFLOW_DIR / "daily-brief.workflow.json").read_text(encoding="utf-8")
        required = (
            "Task|title",
            "Status|select",
            "Area|select",
            "Why|rich_text",
            "Proposed on|date",
            '"selectValue": "To do"',
            '"selectValue": "Abandoned"',
        )
        forbidden = (
            "Tâche|title",
            "Statut|select",
            "Domaine|select",
            "Pourquoi|rich_text",
            "Proposée le|date",
            '"selectValue": "À faire"',
            '"selectValue": "Abandonnée"',
        )
        for value in required:
            self.assertIn(value, content)
        for value in forbidden:
            self.assertNotIn(value, content)


if __name__ == "__main__":
    unittest.main()
