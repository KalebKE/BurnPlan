from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Tuple

from .artifacts import canonical_json


def build_project_proposals(
    base_map: Mapping[str, Any],
    onboarding: Mapping[str, Any],
    quality: Mapping[str, Any],
    teams: Mapping[str, Any],
) -> Dict[str, str]:
    docs = {
        "docs/architecture.md": render_architecture_doc(base_map, onboarding),
        "docs/design.md": render_design_doc(base_map, onboarding),
        "docs/code-map.md": render_code_doc(base_map),
        "docs/testing.md": render_testing_doc(base_map, quality),
        "docs/code-health.md": render_code_health_doc(quality),
        "docs/agent-operating-model.md": render_agent_operating_model(teams),
        "docs/adr/0001-initial-architecture.md": render_initial_adr(base_map, onboarding),
    }
    agents = render_agent_specs(teams)
    manifest = {
        "schemaVersion": 1,
        "docs": sorted(docs),
        "agents": sorted(agents),
        "promotionTargets": {
            "docs": sorted(docs),
            "agents": sorted(_promotion_target(path) for path in agents),
        },
    }
    outputs = {f"proposals/{path}": content for path, content in docs.items()}
    outputs.update({f"proposals/{path}": content for path, content in agents.items()})
    outputs["proposals/manifest.json"] = canonical_json(manifest)
    return outputs


def write_proposals(out_dir: Path, proposals: Mapping[str, str]) -> None:
    for rel_path, content in proposals.items():
        path = out_dir / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def proposals_would_change(out_dir: Path, proposals: Mapping[str, str]) -> bool:
    return any(_path_would_change(out_dir / rel_path, content) for rel_path, content in proposals.items())


def promote(out_dir: Path, repo_root: Path, target: str, force: bool = False) -> List[Path]:
    if target not in {"docs", "agents", "all"}:
        raise ValueError("burnplan promote target must be docs, agents, or all")
    proposal_root = out_dir / "proposals"
    if not proposal_root.exists():
        raise ValueError(f"proposal directory does not exist: {proposal_root}. Run burnplan onboard or burnplan optimize first.")

    pairs: List[Tuple[Path, Path]] = []
    if target in {"docs", "all"}:
        pairs.extend(_promotion_pairs(proposal_root / "docs", repo_root / "docs"))
    if target in {"agents", "all"}:
        pairs.extend(_promotion_pairs(proposal_root / "agents" / "generic", repo_root / "docs" / "agents"))
        pairs.extend(_promotion_pairs(proposal_root / "agents" / "claude", repo_root / ".claude" / "agents"))

    conflicts = [destination for _source, destination in pairs if destination.exists() and not force]
    if conflicts:
        raise ValueError(f"refusing to overwrite existing file: {conflicts[0]}. Pass --force to overwrite.")

    promoted: List[Path] = []
    for source, destination in pairs:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        promoted.append(destination)
    return promoted


def render_architecture_doc(base_map: Mapping[str, Any], onboarding: Mapping[str, Any]) -> str:
    lines = _header("Architecture", "Review and edit this BurnPlan proposal before treating it as project truth.")
    lines.extend(["## System Summary", "", _summary(base_map, onboarding), ""])
    intent = onboarding.get("architectureIntent")
    if intent:
        lines.extend(["## Desired Architecture", "", str(intent), ""])
    lines.extend(["## Code Areas", ""])
    for area in base_map.get("codeAreas", []) or []:
        lines.append(f"### {area.get('name') or area.get('id')}")
        if area.get("purpose"):
            lines.extend(["", str(area["purpose"])])
        _list(lines, "Paths", area.get("paths", []))
        _list(lines, "Entrypoints", area.get("entrypoints", []))
        _list(lines, "Public Contracts", area.get("publicContracts", []))
        _list(lines, "Dependencies", area.get("dependencies", []))
        _list(lines, "Change Rules", area.get("changeRules", []))
        lines.append("")
    lines.extend(["## Architecture References", ""])
    refs = base_map.get("architecture", []) or []
    if refs:
        for item in refs:
            paths = ", ".join(f"`{path}`" for path in item.get("paths", []) or [])
            lines.append(f"- {item.get('name', 'Architecture')} ({item.get('kind', 'other')}): {paths}")
    else:
        lines.append("- No architecture references were detected.")
    lines.append("")
    return "\n".join(lines)


def render_design_doc(base_map: Mapping[str, Any], onboarding: Mapping[str, Any]) -> str:
    lines = _header("Design", "Review and edit this BurnPlan proposal before treating it as project truth.")
    lines.extend(["## Product Intent", "", _summary(base_map, onboarding), ""])
    _list(lines, "Functional Requirements", onboarding.get("functionalRequirements", []))
    _list(lines, "Non-Functional Requirements", onboarding.get("nonFunctionalRequirements", []))
    _list(lines, "Short-Term Goals", onboarding.get("shortTermGoals", []))
    _list(lines, "Long-Term Goals", onboarding.get("longTermGoals", []))
    _list(lines, "Risk Areas", onboarding.get("riskAreas", []))
    lines.extend(["## Open Questions", "", "- Confirm the user-facing workflows and acceptance criteria for the next planned change.", ""])
    return "\n".join(lines)


def render_code_doc(base_map: Mapping[str, Any]) -> str:
    lines = _header("Code Map", "Review and edit this BurnPlan proposal before treating it as project truth.")
    for area in base_map.get("codeAreas", []) or []:
        lines.append(f"## {area.get('name') or area.get('id')}")
        if area.get("purpose"):
            lines.extend(["", str(area["purpose"]), ""])
        _list(lines, "Paths", area.get("paths", []))
        _list(lines, "Entrypoints", area.get("entrypoints", []))
        _list(lines, "Relevant Tests", area.get("relevantTests", []))
        _list(lines, "Verification Commands", area.get("verificationCommands", []))
        lines.append("")
    return "\n".join(lines)


def render_testing_doc(base_map: Mapping[str, Any], quality: Mapping[str, Any]) -> str:
    lines = _header("Testing And Verification", "Review and edit this BurnPlan proposal before treating it as project truth.")
    commands = []
    for area in base_map.get("codeAreas", []) or []:
        commands.extend(area.get("verificationCommands", []) or [])
    _list(lines, "Verification Commands", _unique(commands))
    lines.extend(["## Discovered Tests", ""])
    tests = base_map.get("tests", []) or []
    if tests:
        for item in tests[:100]:
            lines.append(f"- `{item.get('path', '')}` ({item.get('framework', 'unknown')})")
    else:
        lines.append("- No tests were detected.")
    lines.append("")
    tools = ((quality.get("staticAnalysis") or {}).get("tools") or [])
    lines.extend(["## Static Analysis", ""])
    if tools:
        for tool in tools:
            lines.append(f"- `{tool.get('name')}` via `{tool.get('marker')}`")
    else:
        lines.append("- No static analysis configuration was detected.")
    lines.append("")
    return "\n".join(lines)


def render_code_health_doc(quality: Mapping[str, Any]) -> str:
    lines = _header("Code Health", "Review and edit this BurnPlan proposal before treating it as project truth.")
    _list(lines, "Weak Points", quality.get("weakPoints", []))
    lines.extend(["## Hotspots", ""])
    for item in quality.get("hotspots", []) or []:
        lines.append(f"- `{item.get('path')}`: {item.get('revisions', 0)} recent revisions")
    if not quality.get("hotspots"):
        lines.append("- No hotspots detected.")
    lines.extend(["", "## Coupling", ""])
    for item in quality.get("couplings", []) or []:
        paths = ", ".join(f"`{path}`" for path in item.get("paths", []) or [])
        lines.append(f"- {paths}: {item.get('changes', 0)} co-changes")
    if not quality.get("couplings"):
        lines.append("- No repeated co-change pairs detected.")
    lines.append("")
    return "\n".join(lines)


def render_initial_adr(base_map: Mapping[str, Any], onboarding: Mapping[str, Any]) -> str:
    lines = _header("ADR 0001: Initial Architecture Direction", "Review and edit this BurnPlan proposal before accepting it.")
    lines.extend(
        [
            "## Status",
            "",
            "Proposed",
            "",
            "## Context",
            "",
            _summary(base_map, onboarding),
            "",
            "## Decision",
            "",
            onboarding.get("architectureIntent") or "Capture the intended architecture direction before large changes.",
            "",
            "## Consequences",
            "",
            "- Future agents should read this ADR before changing architecture boundaries.",
            "- Update this ADR or add a new ADR when major design decisions change.",
            "",
        ]
    )
    return "\n".join(lines)


def render_agent_operating_model(teams: Mapping[str, Any]) -> str:
    lines = _header("Agent Operating Model", "Review and edit this BurnPlan proposal before treating it as project truth.")
    for team_name, team in (teams.get("teams") or {}).items():
        lines.append(f"## {team_name}")
        lines.extend(["", str(team.get("description", "")), ""])
        lines.append("### Behaviors")
        for behavior_name, behavior in (team.get("behaviors") or {}).items():
            lines.append(f"- `{behavior_name}` -> Skyhook `{behavior.get('routeProfile')}`")
        lines.extend(["", "### Subagents"])
        for subagent_name, subagent in (team.get("subagents") or {}).items():
            lines.append(f"- `{subagent_name}` ({subagent.get('behavior')}): {subagent.get('description', '')}")
        lines.append("")
    return "\n".join(lines)


def render_agent_specs(teams: Mapping[str, Any]) -> Dict[str, str]:
    outputs: Dict[str, str] = {}
    for team_name, team in (teams.get("teams") or {}).items():
        behaviors = team.get("behaviors") or {}
        for subagent_name, subagent in (team.get("subagents") or {}).items():
            behavior_name = subagent.get("behavior", "")
            behavior = behaviors.get(behavior_name) or {}
            route_profile = behavior.get("routeProfile", "")
            slug = f"{team_name}-{subagent_name}"
            outputs[f"agents/generic/{slug}.md"] = _render_generic_agent(team_name, subagent_name, team, subagent, route_profile)
            outputs[f"agents/claude/{slug}.md"] = _render_claude_agent(team_name, subagent_name, team, subagent, route_profile)
    outputs["agents/generic/teams.json"] = canonical_json(teams)
    return outputs


def _render_generic_agent(
    team_name: str,
    subagent_name: str,
    team: Mapping[str, Any],
    subagent: Mapping[str, Any],
    route_profile: str,
) -> str:
    behavior = subagent.get("behavior", "")
    lines = _header(f"{team_name}: {subagent_name}", "Portable BurnPlan subagent spec.")
    lines.extend(
        [
            f"- Team: `{team_name}`",
            f"- Behavior: `{behavior}`",
            f"- Skyhook route profile: `{route_profile}`",
            "",
            "## Description",
            "",
            str(subagent.get("description", "")),
            "",
            "## Route Command",
            "",
            "```sh",
            f"burnplan assign --team {team_name} --behavior {behavior} --task-file <task-file>",
            "```",
            "",
            "## Instructions",
            "",
        ]
    )
    for instruction in subagent.get("instructions", []) or []:
        lines.append(f"- {instruction}")
    lines.append("")
    return "\n".join(lines)


def _render_claude_agent(
    team_name: str,
    subagent_name: str,
    team: Mapping[str, Any],
    subagent: Mapping[str, Any],
    route_profile: str,
) -> str:
    behavior = subagent.get("behavior", "")
    name = f"{team_name}-{subagent_name}"
    lines = [
        "---",
        f"name: {name}",
        f"description: {subagent.get('description', '')}",
        "---",
        "",
        f"You are the `{subagent_name}` subagent on the `{team_name}` team.",
        "",
        f"Before doing work, obtain a route pack with `burnplan assign --team {team_name} --behavior {behavior} --task-file <task-file>`.",
        f"Use the Skyhook `{route_profile}` route profile as your initial context.",
        "",
        "## Instructions",
        "",
    ]
    for instruction in subagent.get("instructions", []) or []:
        lines.append(f"- {instruction}")
    lines.append("")
    return "\n".join(lines)


def _promotion_pairs(source: Path, destination: Path) -> List[Tuple[Path, Path]]:
    if not source.exists():
        return []
    pairs: List[Tuple[Path, Path]] = []
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(source)
        target = destination / rel
        pairs.append((path, target))
    return pairs


def _promotion_target(path: str) -> str:
    if path.startswith("agents/generic/"):
        return "docs/agents/" + path.removeprefix("agents/generic/")
    if path.startswith("agents/claude/"):
        return ".claude/agents/" + path.removeprefix("agents/claude/")
    return path


def _header(title: str, note: str) -> List[str]:
    return [f"# {title}", "", f"<!-- GENERATED by burnplan. {note} -->", ""]


def _summary(base_map: Mapping[str, Any], onboarding: Mapping[str, Any]) -> str:
    return str(onboarding.get("summary") or ((base_map.get("orientation") or {}).get("summary")) or "No project summary captured.")


def _list(lines: List[str], title: str, values: Iterable[Any]) -> None:
    lines.extend([f"## {title}", ""])
    values = [value for value in values if value]
    if values:
        for value in values:
            lines.append(f"- `{value}`" if isinstance(value, str) and ("/" in value or value.startswith(".")) else f"- {value}")
    else:
        lines.append("- None captured.")
    lines.append("")


def _unique(values: Iterable[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _path_would_change(path: Path, content: str) -> bool:
    if not path.exists():
        return True
    return path.read_text(encoding="utf-8") != content
