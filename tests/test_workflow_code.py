import datetime
import json
import pathlib
import subprocess
import unittest


ROOT = pathlib.Path(__file__).parents[1]
RUNNER = ROOT / "tests" / "run_workflow_code.js"


def run_code(workflow, node, *, inputs=None, nodes=None, env=None):
    request = {
        "workflow": str(ROOT / "workflows" / workflow),
        "node": node,
        "input": inputs or [],
        "nodes": nodes or {},
        "env": env or {},
    }
    completed = subprocess.run(
        ["node", str(RUNNER)],
        input=json.dumps(request),
        capture_output=True,
        check=True,
        text=True,
    )
    return json.loads(completed.stdout)


class DailyBriefCodeTests(unittest.TestCase):
    @staticmethod
    def _notes_blocks(*today_content, include_marker=False):
        yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%d/%m/%Y")
        blocks = [
            {
                "id": "today-heading",
                "type": "heading_2",
                "heading_2": {"rich_text": [{"plain_text": "Today"}]},
            },
            *today_content,
            {
                "id": "journal-heading",
                "type": "heading_2",
                "heading_2": {"rich_text": [{"plain_text": "Journal"}]},
            },
            {
                "id": "date-heading",
                "type": "heading_3",
                "heading_3": {"rich_text": [{"plain_text": f"📅 {yesterday}"}]},
            },
        ]
        if include_marker:
            blocks.append({
                "id": "marker",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"plain_text": "Daily notes"}]},
            })
        blocks.append({
            "id": "todos-heading",
            "type": "heading_2",
            "heading_2": {"rich_text": [{"plain_text": "Todos"}]},
        })
        return blocks

    def test_existing_brief_stops_before_generation(self):
        result = run_code(
            "daily-brief.workflow.json",
            "Skip existing brief",
            inputs=[{
                "type": "heading_2",
                "heading_2": {"rich_text": [{"plain_text": "Daily Brief - 22/06/2026"}]},
            }],
            nodes={"Prepare": [{"date": "22/06/2026", "items": []}]},
        )

        self.assertEqual(result, [])

    def test_missing_brief_continues_with_prepared_payload(self):
        prepared = {"date": "22/06/2026", "items": [], "count": 0}
        result = run_code(
            "daily-brief.workflow.json",
            "Skip existing brief",
            inputs=[{
                "type": "paragraph",
                "paragraph": {"rich_text": [{"plain_text": "Permanent header"}]},
            }],
            nodes={"Prepare": [prepared]},
        )

        self.assertEqual(result, [{"json": prepared}])

    def test_enrich_payload_maps_the_english_notion_schema(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        yesterday = (now - datetime.timedelta(days=1)).date().isoformat()
        today = now.date().isoformat()
        nodes = {
            "Prepare": [{"date": now.strftime("%d/%m/%Y"), "items": [], "count": 0}],
            "Notes - blocks": [],
            "System context - blocks": [{
                "type": "paragraph",
                "paragraph": {"rich_text": [{"plain_text": "Prefer concrete evidence."}]},
            }],
            "Active objectives": [{
                "id": "objective-1",
                "property_name": "Validate reliability",
                "property_status": "Active",
                "property_area": "Projects",
                "property_priority": "High",
                "property_current_state": "Tests are being added",
                "property_next_step": "Run production checks",
                "property_horizon": "This week",
            }],
            "Tasks - all": [
                {
                    "id": "task-open",
                    "property_task": "Review the workflow",
                    "property_status": "To do",
                    "property_area": "Projects",
                    "property_why": "Catch regressions",
                    "property_proposed_on": {"start": yesterday},
                },
                {
                    "id": "task-done",
                    "property_task": "Add graph tests",
                    "property_status": "Done",
                    "property_area": "Projects",
                    "property_feedback": "All connections are valid",
                    "property_done_on": {"start": today},
                },
            ],
        }

        result = run_code(
            "daily-brief.workflow.json",
            "Enrich payload",
            inputs=nodes["Tasks - all"],
            nodes=nodes,
        )[0]["json"]

        self.assertEqual(result["objectives"][0]["name"], "Validate reliability")
        self.assertEqual(result["open_tasks"][0]["title"], "Review the workflow")
        self.assertEqual(result["completed_tasks"][0]["title"], "Add graph tests")
        self.assertIn("Prefer concrete evidence.", result["system_context"])

    def test_notes_rollover_copies_today_under_yesterday(self):
        today_note = {
            "id": "today-note",
            "type": "paragraph",
            "has_children": False,
            "paragraph": {
                "rich_text": [{
                    "type": "text",
                    "plain_text": "A useful observation",
                    "text": {"content": "A useful observation", "link": None},
                    "annotations": {
                        "bold": False,
                        "italic": False,
                        "strikethrough": False,
                        "underline": False,
                        "code": False,
                        "color": "default",
                    },
                }],
                "color": "default",
            },
        }
        result = run_code(
            "daily-brief.workflow.json",
            "Prepare Notes rollover",
            inputs=self._notes_blocks(
                today_note,
                {
                    "id": "empty-paragraph",
                    "type": "paragraph",
                    "has_children": False,
                    "paragraph": {"rich_text": [], "color": "default"},
                },
            ),
        )[0]["json"]

        self.assertTrue(result["needs_write"])
        self.assertTrue(result["needs_clear"])
        self.assertEqual(result["original_ids"], ["today-note", "empty-paragraph"])
        self.assertEqual(result["body"]["after"], "date-heading")
        self.assertEqual(result["body"]["children"][0]["paragraph"]["rich_text"][0]["text"]["content"], "Daily notes")
        self.assertEqual(result["body"]["children"][1]["paragraph"]["rich_text"][0]["text"]["content"], "A useful observation")

    def test_notes_rollover_retries_only_the_clear_after_partial_success(self):
        today_note = {
            "id": "today-note",
            "type": "paragraph",
            "has_children": False,
            "paragraph": {"rich_text": [{"type": "text", "plain_text": "Keep me", "text": {"content": "Keep me"}}]},
        }
        result = run_code(
            "daily-brief.workflow.json",
            "Prepare Notes rollover",
            inputs=self._notes_blocks(today_note, include_marker=True),
        )[0]["json"]

        self.assertFalse(result["needs_write"])
        self.assertTrue(result["needs_clear"])
        self.assertEqual(result["original_ids"], ["today-note"])

    def test_notes_rollover_is_a_noop_when_today_is_empty(self):
        result = run_code(
            "daily-brief.workflow.json",
            "Prepare Notes rollover",
            inputs=self._notes_blocks(),
        )[0]["json"]

        self.assertFalse(result["needs_write"])
        self.assertFalse(result["needs_clear"])


class TaskLifecycleCodeTests(unittest.TestCase):
    def test_builds_set_and_clear_updates(self):
        result = run_code(
            "task-lifecycle.workflow.json",
            "Build date updates",
            inputs=[
                {"id": "done", "property_status": "Done", "property_done_on": None},
                {
                    "id": "reopened",
                    "property_status": "To do",
                    "property_done_on": {"start": "2026-06-21T08:00:00.000Z"},
                },
                {
                    "id": "unchanged",
                    "property_status": "Done",
                    "property_done_on": {"start": "2026-06-21T08:00:00.000Z"},
                },
            ],
        )

        self.assertEqual([item["json"]["action"] for item in result], ["set", "clear"])
        self.assertIsNotNone(result[0]["json"]["body"]["properties"]["Done on"]["date"])
        self.assertIsNone(result[1]["json"]["body"]["properties"]["Done on"]["date"])


class WeeklyReviewCodeTests(unittest.TestCase):
    def test_existing_week_stops_before_notion_reads(self):
        today = datetime.datetime.now()
        start = today - datetime.timedelta(days=today.weekday())
        heading = {
            "type": "heading_2",
            "heading_2": {"rich_text": [{"plain_text": (
                f"Weekly Review — {start.strftime('%d/%m/%Y')} "
                f"to {today.strftime('%d/%m/%Y')}"
            )}]},
        }

        result = run_code(
            "weekly-review.workflow.json",
            "Prepare review period",
            inputs=[heading],
        )

        self.assertEqual(result, [])

    def test_assemble_evidence_uses_done_on_as_completion_proof(self):
        today = datetime.datetime.now()
        monday = today - datetime.timedelta(days=today.weekday())
        period = {
            "week_start": monday.strftime("%d/%m/%Y"),
            "week_end": today.strftime("%d/%m/%Y"),
            "start_iso": monday.strftime("%Y-%m-%d"),
            "end_iso": today.strftime("%Y-%m-%d"),
        }
        nodes = {
            "Prepare review period": [period],
            "System context": [{
                "type": "paragraph",
                "paragraph": {"rich_text": [{"plain_text": "Prioritize evidence."}]},
            }],
            "Notes": [],
            "Objectives": [{
                "property_name": "Ship a reliable system",
                "property_status": "Active",
                "property_current_state": "Weekly review is missing",
            }],
            "Tasks": [
                {
                    "property_task": "Add the weekly workflow",
                    "property_status": "Done",
                    "property_done_on": {"start": today.strftime("%Y-%m-%d")},
                },
                {
                    "property_task": "Old completed task",
                    "property_status": "Done",
                    "property_done_on": {
                        "start": (monday - datetime.timedelta(days=2)).strftime("%Y-%m-%d")
                    },
                },
            ],
            "Daily Briefs": [],
        }

        result = run_code(
            "weekly-review.workflow.json",
            "Assemble evidence",
            nodes=nodes,
            env={"WEEKLY_LANGUAGE": "French", "NOTION_LIBRARY_DATABASE_ID": ""},
        )[0]["json"]

        self.assertEqual(result["language"], "French")
        self.assertEqual([task["title"] for task in result["tasks"]], ["Add the weekly workflow"])
        self.assertEqual(result["objectives"][0]["name"], "Ship a reliable system")
        self.assertIn("Prioritize evidence.", result["system_context"])


if __name__ == "__main__":
    unittest.main()
