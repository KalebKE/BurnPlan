from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from skyhook.artifacts import load_existing_map, output_dir as skyhook_output_dir, write_outputs
from skyhook.cli import build_map
from skyhook.route import build_route, normalize_profile

from .artifacts import canonical_json, read_json


DEFAULT_TEAMS: Dict[str, Any] = {
    "schemaVersion": 1,
    "teams": {
        "product-owner": {
            "description": "Turns product intent into stories, requirements, and acceptance criteria.",
            "behaviors": {
                "story": {
                    "routeProfile": "product_planning",
                    "instructions": "Use product docs, existing flows, and domain terms to shape a user story.",
                },
                "requirements": {
                    "routeProfile": "requirements_planning",
                    "instructions": "Find existing requirements, acceptance criteria, contracts, and open questions.",
                },
            },
            "subagents": {
                "story-writer": {
                    "behavior": "story",
                    "description": "Drafts user stories from product intent, existing flows, and domain language.",
                    "instructions": [
                        "Start from the product_planning route pack.",
                        "Write user-facing outcomes before implementation detail.",
                        "Capture assumptions and open questions explicitly.",
                    ],
                },
                "requirements-analyst": {
                    "behavior": "requirements",
                    "description": "Turns product intent into functional and non-functional requirements.",
                    "instructions": [
                        "Start from the requirements_planning route pack.",
                        "Separate requirements from implementation approach.",
                        "Name relevant contracts, screens, APIs, and acceptance criteria.",
                    ],
                },
                "acceptance-criteria-reviewer": {
                    "behavior": "requirements",
                    "description": "Reviews stories and requirements for testable acceptance criteria.",
                    "instructions": [
                        "Start from the requirements_planning route pack.",
                        "Check that every acceptance criterion can be verified.",
                        "Flag ambiguous user-visible behavior and missing edge cases.",
                    ],
                },
            },
        },
        "project-manager": {
            "description": "Breaks work down, routes implementation, reviews changes, and hunts bugs.",
            "behaviors": {
                "breakdown": {
                    "routeProfile": "technical_breakdown",
                    "instructions": "Identify architecture boundaries, affected areas, dependency order, and test strategy.",
                },
                "implement": {
                    "routeProfile": "implementation",
                    "instructions": "Read the route pack before editing and verify against relevant tests.",
                },
                "review": {
                    "routeProfile": "code_review",
                    "instructions": "Prioritize risks, tests, contracts, and architecture boundary violations.",
                },
                "bugfix": {
                    "routeProfile": "bug_hunt",
                    "instructions": "Start from symptoms, logs, failing tests, and the smallest reproducible path.",
                },
            },
            "subagents": {
                "technical-planner": {
                    "behavior": "breakdown",
                    "description": "Builds technical breakdowns with dependency order and verification strategy.",
                    "instructions": [
                        "Start from the technical_breakdown route pack.",
                        "Identify boundaries, affected areas, risks, and test strategy before implementation.",
                        "Split work into independently reviewable slices.",
                    ],
                },
                "implementer": {
                    "behavior": "implement",
                    "description": "Implements scoped changes using routed code, docs, and tests.",
                    "instructions": [
                        "Start from the implementation route pack.",
                        "Read likely edit targets and relevant tests before changing code.",
                        "Document material changes with burnplan document.",
                    ],
                },
                "reviewer": {
                    "behavior": "review",
                    "description": "Reviews code for defects, missing tests, and architecture violations.",
                    "instructions": [
                        "Start from the code_review route pack.",
                        "Prioritize correctness, regressions, boundary violations, and missing verification.",
                        "Lead with actionable findings tied to files and behavior.",
                    ],
                },
                "bug-hunter": {
                    "behavior": "bugfix",
                    "description": "Diagnoses bugs from symptoms, logs, tests, and narrow repro paths.",
                    "instructions": [
                        "Start from the bug_hunt route pack.",
                        "Preserve the observed symptom and reproduce before broad edits.",
                        "Verify the fix against the smallest meaningful test or runtime check.",
                    ],
                },
            },
        },
    },
}


def teams_path(out_dir: Path, override: Optional[str] = None) -> Path:
    if override:
        path = Path(override)
        return path if path.is_absolute() else out_dir.parent / path
    return out_dir / "teams.json"


def write_team_preset(path: Path, overwrite: bool = False) -> None:
    if path.exists() and not overwrite:
        raise ValueError(f"team config already exists: {path}. Pass --force to overwrite.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(DEFAULT_TEAMS), encoding="utf-8")


def load_teams(path: Path) -> Dict[str, Any]:
    if path.exists():
        return read_json(path)
    return DEFAULT_TEAMS


def resolve_behavior(teams: Mapping[str, Any], team_name: str, behavior_name: str) -> Dict[str, Any]:
    team = ((teams.get("teams") or {}).get(team_name) or {})
    if not team:
        raise ValueError(f"unknown team: {team_name}")
    behavior = ((team.get("behaviors") or {}).get(behavior_name) or {})
    if not behavior:
        raise ValueError(f"unknown behavior for {team_name}: {behavior_name}")
    profile = normalize_profile(str(behavior.get("routeProfile") or ""))
    return {
        "team": team_name,
        "behavior": behavior_name,
        "routeProfile": profile,
        "teamDescription": team.get("description", ""),
        "instructions": behavior.get("instructions", ""),
    }


def build_assignment_route(
    repo_root: Path,
    map_dir: Path,
    skyhook_cfg: Any,
    task: str,
    profile: str,
    args: Any,
) -> Dict[str, Any]:
    data = load_existing_map(map_dir)
    if data is None or getattr(args, "refresh_map", False):
        data, _scan = build_map(
            repo_root,
            skyhook_cfg,
            provider=getattr(args, "provider", None),
            model=getattr(args, "model", None),
            max_files=getattr(args, "max_files", None),
            previous=data,
            error_prefix="assignment map",
        )
        if not getattr(args, "dry_run", False):
            write_outputs(map_dir, data)
    return build_route(data, task, profile=profile)


def route_map_dir(repo_root: Path, map_dir_config: str, override: Optional[str]) -> Path:
    return skyhook_output_dir(repo_root, map_dir_config, override)
