from __future__ import annotations

import sys
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

from skyhook.scanner import RepoScan


INTERVIEW_QUESTIONS = [
    ("purpose", "What problem does this repository solve?"),
    ("primaryUsers", "Who are the primary users or operators?"),
    ("functionalRequirements", "What functional requirements should future agents preserve?"),
    ("nonFunctionalRequirements", "What non-functional requirements matter most?"),
    ("architectureIntent", "What architecture or design direction should the repository move toward?"),
    ("shortTermGoals", "What should improve in the next few changes?"),
    ("longTermGoals", "What should improve over the next few months?"),
    ("riskAreas", "Which areas are risky, fragile, or easy for agents to misunderstand?"),
    ("documentationPreferences", "How should architecture, ADRs, and design docs be organized?"),
]


def collect_interview_answers(
    interactive: bool,
    input_fn: Callable[[str], str] = input,
    output_stream: Any = sys.stderr,
) -> List[Dict[str, str]]:
    answers: List[Dict[str, str]] = []
    for question_id, prompt in INTERVIEW_QUESTIONS:
        answer = ""
        if interactive:
            output_stream.write(f"\n{prompt}\n")
            answer = input_fn("> ").strip()
        answers.append({"id": question_id, "question": prompt, "answer": answer})
    return answers


def build_onboarding(
    scan: RepoScan,
    base_map: Mapping[str, Any],
    answers: Iterable[Mapping[str, str]],
    quality: Mapping[str, Any],
    previous: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    answer_list = list(answers)
    if previous and not any((item.get("answer") or "").strip() for item in answer_list):
        previous_answers = previous.get("interviewAnswers")
        if isinstance(previous_answers, list) and previous_answers:
            answer_list = [dict(item) for item in previous_answers]
    answer_map = {item.get("id", ""): item.get("answer", "").strip() for item in answer_list}
    gaps = documentation_gaps(scan)
    return {
        "summary": _summary(scan, base_map, answer_map),
        "interviewAnswers": answer_list,
        "functionalRequirements": _split_answer(answer_map.get("functionalRequirements", "")),
        "nonFunctionalRequirements": _split_answer(answer_map.get("nonFunctionalRequirements", "")),
        "architectureIntent": answer_map.get("architectureIntent", ""),
        "shortTermGoals": _split_answer(answer_map.get("shortTermGoals", "")),
        "longTermGoals": _split_answer(answer_map.get("longTermGoals", "")),
        "riskAreas": _split_answer(answer_map.get("riskAreas", "")),
        "documentationGaps": gaps,
        "suggestedDocs": _suggested_docs(gaps, quality),
    }


def documentation_gaps(scan: RepoScan) -> List[Dict[str, str]]:
    docs = scan.docs
    doc_kinds = {doc.doc_kind for doc in docs}
    gaps: List[Dict[str, str]] = []
    if not docs:
        gaps.append(
            {
                "kind": "readme",
                "priority": "high",
                "recommendation": "Add a README with setup, test, and architecture entrypoint links.",
            }
        )
    if "adr" not in doc_kinds:
        gaps.append(
            {
                "kind": "adr",
                "priority": "high",
                "recommendation": "Add ADRs for important decisions so future agents can preserve intent.",
            }
        )
    if not ({"architecture", "c4", "design"} & doc_kinds):
        gaps.append(
            {
                "kind": "architecture",
                "priority": "high",
                "recommendation": "Add an architecture or C4 overview that names boundaries, data flow, and dependency direction.",
            }
        )
    if "runbook" not in doc_kinds:
        gaps.append(
            {
                "kind": "runbook",
                "priority": "medium",
                "recommendation": "Add a runbook for local setup, verification, deployment, and recurring failure modes.",
            }
        )
    if "test" not in doc_kinds:
        gaps.append(
            {
                "kind": "test",
                "priority": "medium",
                "recommendation": "Add testing guidance that tells agents which checks to run for each area.",
            }
        )
    return gaps


def build_agent_guidance(
    base_map: Mapping[str, Any],
    onboarding: Mapping[str, Any],
    quality: Mapping[str, Any],
    ledger: Mapping[str, Any],
) -> Dict[str, Any]:
    orientation = base_map.get("orientation") or {}
    read_first = list(orientation.get("agentStartHere") or [])[:8]
    read_first.extend([".burnplan/onboarding.md", ".burnplan/quality.md", ".burnplan/documentation-ledger.md"])
    improvement_prompts = []
    for weak_point in quality.get("weakPoints", []) or []:
        improvement_prompts.append(f"When touching related code, look for a small documentation or design improvement: {weak_point}")
    for gap in onboarding.get("documentationGaps", []) or []:
        improvement_prompts.append(gap.get("recommendation", "Improve missing documentation."))
    return {
        "readFirst": _unique(read_first),
        "beforeCoding": [
            "Read the relevant code area in .skyhook/map.md before opening source files.",
            "Check .burnplan/quality.md for hotspots or coupling near the files you will touch.",
            "Prefer existing architecture, ADR, design, and runbook docs over source-only inference.",
        ],
        "beforeCommit": [
            "Run burnplan optimize --dry-run to see whether generated guidance changed.",
            "Run burnplan document --what ... --why ... --area ... for material changes.",
            "If a weak point was improved, mention the evidence in the rationale entry.",
        ],
        "improvementPrompts": _unique(improvement_prompts)[:12],
        "documentationEvidence": {
            "worklogCount": ledger.get("worklogCount", 0),
            "rationaleCount": ledger.get("rationaleCount", 0),
        },
    }


def _summary(scan: RepoScan, base_map: Mapping[str, Any], answers: Mapping[str, str]) -> str:
    purpose = answers.get("purpose")
    if purpose:
        return purpose
    orientation = base_map.get("orientation") or {}
    if orientation.get("summary"):
        return str(orientation["summary"])
    return f"{scan.repo_name} has {len(scan.files)} scanned files and {len(scan.docs)} detected documentation files."


def _suggested_docs(gaps: List[Dict[str, str]], quality: Mapping[str, Any]) -> List[Dict[str, str]]:
    docs = [
        {
            "path": f"docs/{gap['kind']}.md" if gap["kind"] != "adr" else "docs/adr/0001-initial-architecture.md",
            "reason": gap["recommendation"],
            "priority": gap["priority"],
        }
        for gap in gaps
    ]
    hotspots = quality.get("hotspots", []) or []
    if hotspots:
        docs.append(
            {
                "path": "docs/hotspots.md",
                "reason": "Capture why the highest-churn files change often and what agents should preserve.",
                "priority": "medium",
            }
        )
    return docs[:12]


def _split_answer(value: str) -> List[str]:
    cleaned = value.strip()
    if not cleaned:
        return []
    lines = [line.strip("-* \t") for line in cleaned.splitlines() if line.strip()]
    if len(lines) > 1:
        return lines
    return [part.strip() for part in cleaned.split(";") if part.strip()]


def _unique(values: Iterable[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
