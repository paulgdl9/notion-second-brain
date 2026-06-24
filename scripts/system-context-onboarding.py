#!/usr/bin/env python3
"""Interview the operator and generate a clean Notion System Context page."""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ANSWERS = ROOT / "runtime" / "system-context.answers.json"
DEFAULT_OUTPUT = ROOT / "runtime" / "system-context.md"
DEFAULT_AREAS = "Work,Projects,Finance,Health,Learning,Personal,Knowledge"


@dataclass(frozen=True)
class Question:
    key: str
    prompt: str
    hint: str = ""


QUESTIONS = (
    Question(
        "identity",
        "Who are you right now: roles, work, responsibilities, and current life context?",
        "One compact paragraph is enough.",
    ),
    Question(
        "year_outcomes",
        "What outcomes are you trying to create this year?",
        "Use concrete outcomes, not vague themes.",
    ),
    Question(
        "next_90_days",
        "What matters most in the next 90 days?",
        "This should help the Daily Brief choose what to protect.",
    ),
    Question(
        "active_projects",
        "Which active projects deserve attention now?",
        "Name the project, why it matters, and its next visible milestone.",
    ),
    Question(
        "success_signals",
        "What signals would prove that the system is helping you?",
        "Examples: shipped work, health consistency, fewer stale tasks, better decisions.",
    ),
    Question(
        "constraints",
        "What constraints should the copilot respect?",
        "Time, money, energy, location, obligations, access, deadlines.",
    ),
    Question(
        "non_negotiables",
        "What routines, values, health rules, or relationships are non-negotiable?",
        "These should override attractive but costly suggestions.",
    ),
    Question(
        "strengths",
        "Where are you unusually strong or high-leverage?",
        "Skills, instincts, taste, network, technical advantages.",
    ),
    Question(
        "failure_modes",
        "Where do you predictably drift, overdo, avoid, or lose time?",
        "Be blunt; this is where the brief should catch you.",
    ),
    Question(
        "working_style",
        "How do you work best?",
        "Cadence, depth work, collaboration style, preferred task size.",
    ),
    Question(
        "communication_style",
        "How should the copilot talk to you?",
        "Tone, directness, language, level of challenge, what to avoid.",
    ),
    Question(
        "task_rules",
        "What makes a good task recommendation for you?",
        "Scope, duration, specificity, acceptable number of tasks, areas to protect.",
    ),
    Question(
        "decision_rules",
        "What rules should guide trade-offs?",
        "Example: prefer fewer projects, prefer evidence, protect sleep, ship before polishing.",
    ),
    Question(
        "areas",
        "Which task areas should the system use?",
        "Comma-separated. Leave blank to use MEMO_AREAS from .env.",
    ),
    Question(
        "stop_doing",
        "What should the system discourage or stop repeating?",
        "Patterns, distractions, zombie projects, unnecessary pages or rituals.",
    ),
    Question(
        "recurring_questions",
        "What questions should the copilot keep asking you?",
        "Questions that expose avoidance, contradictions, or leverage.",
    ),
    Question(
        "boundaries",
        "What should it never assume or overstep?",
        "Sensitive areas, uncertain facts, topics that need explicit evidence.",
    ),
    Question(
        "memory_rules",
        "How should this System Context be updated over time?",
        "What belongs here, what should stay in Tasks/Objectives/Journal, and what needs validation.",
    ),
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Interview once, then generate Markdown for the Notion System Context page."
    )
    parser.add_argument("--answers", type=Path, default=DEFAULT_ANSWERS,
                        help="JSON answer cache (default: runtime/system-context.answers.json).")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="Markdown output path (default: runtime/system-context.md).")
    parser.add_argument("--render-only", action="store_true",
                        help="Do not ask questions; render from the saved answers file.")
    parser.add_argument("--force", action="store_true",
                        help="Start a fresh interview instead of loading saved answers.")
    parser.add_argument("--stdout", action="store_true",
                        help="Also print the generated Markdown to stdout.")
    return parser.parse_args(argv)


def load_env_areas(env_path=ROOT / ".env", example_path=ROOT / ".env.example"):
    for path in (env_path, example_path):
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
        for line in content.splitlines():
            if line.startswith("MEMO_AREAS="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if value:
                    return split_csv_items(value)
    return split_csv_items(DEFAULT_AREAS)


def clean_item(value):
    return re.sub(r"^[-*]\s+", "", value or "").strip()


def split_csv_items(value):
    return [
        clean_item(item)
        for item in re.split(r"[\n,;]+", value or "")
        if clean_item(item)
    ]


def split_answer_items(value):
    return [
        clean_item(item)
        for item in re.split(r"\n+|;", value or "")
        if clean_item(item)
    ]


def normalize_answer(value):
    lines = [line.strip() for line in (value or "").splitlines()]
    text = "\n".join(line for line in lines if line)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def load_answers(path):
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    answers = data.get("answers", data)
    if not isinstance(answers, dict):
        raise ValueError(f"{path} does not contain an answer object")
    return {str(k): normalize_answer(str(v)) for k, v in answers.items() if str(v).strip()}


def save_answers(path, answers):
    payload = {
        "version": 1,
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "answers": answers,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def ask_questions(answers, answers_path=DEFAULT_ANSWERS):
    print("System Context onboarding")
    print("Answer in any language. Press Enter to keep an existing answer or skip a question.")
    try:
        display_path = answers_path.relative_to(ROOT)
    except ValueError:
        display_path = answers_path
    print(f"Answers are saved as you go in {display_path}.\n")

    for index, question in enumerate(QUESTIONS, start=1):
        current = answers.get(question.key, "")
        print(f"[{index}/{len(QUESTIONS)}] {question.prompt}")
        if question.hint:
            print(f"    {question.hint}")
        if current:
            preview = current.replace("\n", " ")
            if len(preview) > 160:
                preview = preview[:157] + "..."
            print(f"    Current: {preview}")
        try:
            value = input("> ")
        except EOFError:
            print("", file=sys.stderr)
            break
        value = normalize_answer(value)
        if value:
            answers[question.key] = value
        save_answers(answers_path, answers)
        print()
    return answers


def bullets(value, fallback=None):
    items = split_answer_items(value)
    if not items and fallback:
        items = [fallback]
    return markdown_list(items)


def markdown_list(items):
    return "\n".join(f"- {item}" for item in items)


def block(title, value, fallback=None):
    rendered = bullets(value, fallback=fallback)
    if not rendered:
        return ""
    return f"### {title}\n{rendered}"


def render_system_context(answers, areas=None, generated_at=None):
    areas = split_csv_items(answers.get("areas")) or list(areas or load_env_areas())
    generated_at = generated_at or datetime.now().astimezone().strftime("%Y-%m-%d")

    sections = [
        "# System Context",
        "",
        f"Generated from onboarding on {generated_at}. Keep this page compact: stable facts, "
        "operating rules, and durable preferences only. Daily state belongs in Notes, Tasks, "
        "Objectives, and Daily Briefs.",
        "",
        "## Identity",
        block("Current situation", answers.get("identity"), "Not defined yet."),
        "",
        "## Direction",
        block("This year's outcomes", answers.get("year_outcomes"), "Not defined yet."),
        "",
        block("Next 90 days", answers.get("next_90_days"), "Not defined yet."),
        "",
        block("Active projects", answers.get("active_projects"), "Not defined yet."),
        "",
        block("Success signals", answers.get("success_signals")),
        "",
        "## Constraints",
        block("Constraints to respect", answers.get("constraints")),
        "",
        block("Non-negotiables", answers.get("non_negotiables")),
        "",
        "## Operating Profile",
        block("Strengths and leverage", answers.get("strengths")),
        "",
        block("Failure modes to catch", answers.get("failure_modes")),
        "",
        block("Working style", answers.get("working_style")),
        "",
        "## Copilot Rules",
        block("Communication style", answers.get("communication_style")),
        "",
        block("Task recommendation rules", answers.get("task_rules")),
        "",
        block("Decision rules", answers.get("decision_rules")),
        "",
        "### Task areas",
        markdown_list(areas or ["Knowledge"]),
        "",
        block("Discourage or stop repeating", answers.get("stop_doing")),
        "",
        block("Recurring questions to ask", answers.get("recurring_questions")),
        "",
        block("Boundaries and uncertain facts", answers.get("boundaries")),
        "",
        "## Memory Maintenance Rules",
        block("User-specific update rules", answers.get("memory_rules")),
        "",
        "- Treat System Context as stable memory, not a daily log.",
        "- Keep concrete execution state in Objectives and Tasks, not in this page.",
        "- Compress repeated notes into one durable rule only when the pattern is supported by evidence.",
        "- Propose exact edits before changing identity, priorities, constraints, or behavioral rules.",
        "- Remove or rewrite stale facts when stronger recent evidence contradicts them.",
        "- Prefer simplifying the existing system over adding new pages, rituals, or databases.",
        "",
    ]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(sections)).strip() + "\n"


def main(argv=None):
    args = parse_args(argv)
    answers = {} if args.force else load_answers(args.answers)
    if not args.render_only:
        if not sys.stdin.isatty():
            raise SystemExit("Refusing to interview without a terminal. Use --render-only with saved answers.")
        answers = ask_questions(answers, args.answers)
    elif not answers:
        raise SystemExit(f"No saved answers found in {args.answers}")

    markdown = render_system_context(answers)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(markdown, encoding="utf-8")
    save_answers(args.answers, answers)

    if args.stdout:
        print(markdown)
    status = sys.stderr if args.stdout else sys.stdout
    print(f"Wrote {args.output}", file=status)
    print("Paste the Markdown into the Notion page configured as NOTION_CONTEXT_PAGE_ID.", file=status)


if __name__ == "__main__":
    main()
