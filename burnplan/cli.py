from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from skyhook.artifacts import load_existing_map, output_dir as skyhook_output_dir, outputs_would_change, write_outputs, write_route
from skyhook.cli import build_map
from skyhook.config import load_config as load_skyhook_config
from skyhook.model import ModelError
from skyhook.render import render_route_markdown
from skyhook.schema import canonical_json as skyhook_canonical_json

from .artifacts import (
    guidance_size_report,
    load_json_artifact,
    output_dir,
    ratchet_output_contents,
    ratchet_outputs_would_change,
    write_ratchet_outputs,
)
from .config import load_config
from .distill import build_or_reuse_rules
from .document import build_document_entry, collect_documentation_ledger, write_document_entry
from .hooks import stop_reminder
from .interview import build_agent_guidance, build_onboarding, collect_interview_answers
from .proposals import build_project_proposals, promote, proposals_would_change, write_proposals
from .quality import analyze_quality
from .teams import build_assignment_route, load_teams, resolve_behavior, teams_path, write_team_preset


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "onboard":
            return cmd_onboard(args)
        if args.command == "optimize":
            return cmd_optimize(args)
        if args.command == "document":
            return cmd_document(args)
        if args.command == "teams":
            return cmd_teams(args)
        if args.command == "assign":
            return cmd_assign(args)
        if args.command == "promote":
            return cmd_promote(args)
        if args.command == "hook":
            return cmd_hook(args)
    except KeyboardInterrupt:
        print("burnplan: interrupted", file=sys.stderr)
        return 130
    except (ModelError, ValueError) as exc:
        print(f"burnplan: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"burnplan: {exc}", file=sys.stderr)
        return 2
    parser.print_help(sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="burnplan", description="Ratchet repository context, quality evidence, and agent guidance over time.")
    sub = parser.add_subparsers(dest="command")

    onboard = sub.add_parser("onboard", help="run guided architecture onboarding and generate BurnPlan artifacts")
    add_common_args(onboard)
    onboard.add_argument("--dry-run", action="store_true", help="scan and synthesize without writing files")
    onboard.add_argument("--interview", action="store_true", help="force the interactive onboarding interview")
    onboard.add_argument("--no-interview", action="store_true", help="skip prompts and produce noninteractive onboarding output")
    onboard.add_argument("--refresh-rules", action="store_true", help="re-distill agent rules even when worklog entries are unchanged")

    optimize = sub.add_parser("optimize", help="refresh Skyhook maps and BurnPlan guidance before commit or PR")
    add_common_args(optimize)
    optimize.add_argument("--dry-run", action="store_true", help="report whether artifacts would change")
    optimize.add_argument("--refresh-rules", action="store_true", help="re-distill agent rules even when worklog entries are unchanged")

    document = sub.add_parser("document", help="record what an agent changed and why")
    add_common_args(document, skyhook_provider=False)
    document.add_argument("--what", default=None, help="summary of what changed")
    document.add_argument("--why", default=None, help="rationale for the change")
    document.add_argument("--area", default=None, help="code area or feature name")
    document.add_argument("--from-git", action="store_true", help="fill --what from git status and diff stats")
    document.add_argument("--dry-run", action="store_true", help="show where entries would be written")

    teams = sub.add_parser("teams", help="manage BurnPlan sub-agent team behavior mappings")
    teams_sub = teams.add_subparsers(dest="teams_command")
    teams_init = teams_sub.add_parser("init", help="write the default Product Owner and Project Manager team preset")
    add_common_args(teams_init, skyhook_provider=False)
    teams_init.add_argument("--teams-config", default=None, help="override teams config path")
    teams_init.add_argument("--force", action="store_true", help="overwrite an existing teams config")

    assign = sub.add_parser("assign", help="route a task through a BurnPlan team behavior")
    add_common_args(assign)
    assign.add_argument("--team", required=True, help="team name, for example product-owner or project-manager")
    assign.add_argument("--behavior", required=True, help="team behavior, for example story, requirements, breakdown, implement, review, bugfix")
    assign.add_argument("--task", default=None, help="task or issue text to route")
    assign.add_argument("--task-file", default=None, help="file containing task or issue text")
    assign.add_argument("--teams-config", default=None, help="override teams config path")
    assign.add_argument("--format", choices=["markdown", "json"], default="markdown", help="output format")
    assign.add_argument("--save", action="store_true", help="write route artifacts under .skyhook/routes")
    assign.add_argument("--refresh-map", action="store_true", help="refresh the Skyhook map before routing")
    assign.add_argument("--dry-run", action="store_true", help="route without writing maps or saved route artifacts")

    promote_parser = sub.add_parser("promote", help="promote reviewed BurnPlan proposals into project docs or agent files")
    add_common_args(promote_parser, skyhook_provider=False)
    promote_parser.add_argument("target", choices=["docs", "agents", "all"], help="proposal type to promote")
    promote_parser.add_argument("--force", action="store_true", help="overwrite existing promoted files")

    hook = sub.add_parser("hook", help="run lightweight harness hook actions")
    add_common_args(hook, skyhook_provider=False)
    hook.add_argument("action", choices=["stop"], help="hook action to run")
    return parser


def add_common_args(parser: argparse.ArgumentParser, skyhook_provider: bool = True) -> None:
    parser.add_argument("--repo", default=".", help="repository root, default: current directory")
    parser.add_argument("--config", default=None, help="path to .burnplan/config.yaml")
    parser.add_argument("--skyhook-config", default=None, help="path to .skyhook/config.yaml")
    parser.add_argument("--output-dir", default=None, help="override BurnPlan output directory")
    parser.add_argument("--map-dir", default=None, help="override Skyhook map output directory")
    if skyhook_provider:
        parser.add_argument("--provider", default=None, help="Skyhook model provider: auto, openai, static")
        parser.add_argument("--model", default=None, help="Skyhook model name override")
        parser.add_argument("--max-files", type=int, default=None, help="maximum files for Skyhook to scan")


def cmd_onboard(args: argparse.Namespace) -> int:
    return _run_ratchet("onboard", args)


def cmd_optimize(args: argparse.Namespace) -> int:
    return _run_ratchet("optimize", args)


def _run_ratchet(command: str, args: argparse.Namespace) -> int:
    repo_root, burn_cfg, skyhook_cfg, out_dir, map_dir = load_runtime(args)
    error_prefix = "onboarding map" if command == "onboard" else "optimized map"
    base_map, scan = build_skyhook_map(repo_root, skyhook_cfg, map_dir, args, error_prefix=error_prefix)
    quality = analyze_quality(repo_root, scan, burn_cfg.quality.since_days, burn_cfg.quality.max_commits)
    previous_onboarding = load_json_artifact(out_dir, "onboarding.json")
    answers = collect_interview_answers(_should_interview(args)) if command == "onboard" else []
    onboarding = build_onboarding(scan, base_map, answers, quality, previous=previous_onboarding)
    ledger = collect_documentation_ledger(out_dir)
    dry_run = getattr(args, "dry_run", False)
    rules = build_or_reuse_rules(
        out_dir,
        skyhook_cfg,
        getattr(args, "provider", None),
        allow_model=not dry_run,
        refresh=getattr(args, "refresh_rules", False),
    )
    guidance = build_agent_guidance(base_map, onboarding, quality, ledger, repo_root)
    teams = load_teams(teams_path(out_dir))
    proposals = build_project_proposals(base_map, onboarding, quality, teams, rules)
    would_change = (
        outputs_would_change(map_dir, base_map)
        or ratchet_outputs_would_change(out_dir, onboarding, quality, guidance, ledger, rules)
        or proposals_would_change(out_dir, proposals)
    )
    contents = ratchet_output_contents(out_dir, onboarding, quality, guidance, ledger, rules)
    size_report = guidance_size_report(contents, out_dir, burn_cfg.guidance.max_lines)
    if dry_run:
        print_report(command, scan, out_dir, map_dir, wrote=False, would_change=would_change, size_report=size_report)
        return 1 if command == "optimize" and would_change else 0
    write_outputs(map_dir, base_map)
    write_ratchet_outputs(out_dir, onboarding, quality, guidance, ledger, rules)
    write_proposals(out_dir, proposals)
    print_report(command, scan, out_dir, map_dir, wrote=True, would_change=would_change, size_report=size_report)
    return 0


def cmd_document(args: argparse.Namespace) -> int:
    repo_root, _burn_cfg, _skyhook_cfg, out_dir, _map_dir = load_runtime(args)
    entry = build_document_entry(repo_root, args.what, args.why, args.area, args.from_git)
    if getattr(args, "dry_run", False):
        print(f"burnplan document: dry-run {out_dir}")
        print(f"- worklog: {out_dir / 'worklog' / (entry['id'] + '.md')}")
        print(f"- rationale: {out_dir / 'rationale' / (entry['id'] + '.md')}")
        return 0
    paths = write_document_entry(out_dir, entry)
    print(f"burnplan document: wrote {out_dir}")
    for path in paths:
        print(f"- {path}")
    return 0


def cmd_teams(args: argparse.Namespace) -> int:
    if args.teams_command != "init":
        raise ValueError("burnplan teams requires a subcommand")
    repo_root, _burn_cfg, _skyhook_cfg, out_dir, _map_dir = load_runtime(args)
    path = teams_path(out_dir, args.teams_config)
    write_team_preset(path, overwrite=args.force)
    print(f"burnplan teams init: wrote {path}")
    return 0


def cmd_assign(args: argparse.Namespace) -> int:
    repo_root, burn_cfg, skyhook_cfg, out_dir, map_dir = load_runtime(args)
    teams = load_teams(teams_path(out_dir, args.teams_config))
    assignment = resolve_behavior(teams, args.team, args.behavior)
    route = build_assignment_route(
        repo_root,
        map_dir,
        skyhook_cfg,
        _read_task(args),
        assignment["routeProfile"],
        args,
    )
    route["assignment"] = assignment
    if args.save and not args.dry_run:
        paths = write_route(map_dir, route)
        print(f"burnplan assign: wrote {map_dir / 'routes'}", file=sys.stderr)
        for path in paths:
            print(f"- {path}", file=sys.stderr)
    if args.format == "json":
        print(skyhook_canonical_json(route), end="")
    else:
        print(render_route_markdown(route), end="")
    return 0


def cmd_promote(args: argparse.Namespace) -> int:
    repo_root, _burn_cfg, _skyhook_cfg, out_dir, _map_dir = load_runtime(args)
    paths = promote(out_dir, repo_root, args.target, force=args.force)
    print(f"burnplan promote {args.target}: wrote {len(paths)} files")
    for path in paths:
        print(f"- {path}")
    return 0


def cmd_hook(args: argparse.Namespace) -> int:
    repo_root, _burn_cfg, _skyhook_cfg, out_dir, _map_dir = load_runtime(args)
    if args.action != "stop":
        raise ValueError(f"unsupported hook action: {args.action}")
    message = stop_reminder(repo_root, out_dir)
    if message:
        print(message)
    return 0


def build_skyhook_map(repo_root: Path, skyhook_cfg: Any, map_dir: Path, args: argparse.Namespace, error_prefix: str):
    return build_map(
        repo_root,
        skyhook_cfg,
        provider=getattr(args, "provider", None),
        model=getattr(args, "model", None),
        max_files=getattr(args, "max_files", None),
        previous=load_existing_map(map_dir),
        error_prefix=error_prefix,
    )


def load_runtime(args: argparse.Namespace):
    repo_root = Path(args.repo).resolve()
    burn_cfg = load_config(repo_root, args.config)
    skyhook_cfg = load_skyhook_config(repo_root, args.skyhook_config)
    out_dir = output_dir(repo_root, burn_cfg.output_dir, args.output_dir)
    map_dir = skyhook_output_dir(repo_root, burn_cfg.map_dir, args.map_dir)
    for path in [out_dir, map_dir]:
        _exclude_output_dir(repo_root, skyhook_cfg, path)
    return repo_root, burn_cfg, skyhook_cfg, out_dir, map_dir


def print_report(
    command: str,
    scan,
    out_dir: Path,
    map_dir: Path,
    wrote: bool,
    would_change: Optional[bool] = None,
    size_report: Optional[Mapping[str, Any]] = None,
) -> None:
    action = "wrote" if wrote else "dry-run"
    print(f"burnplan {command}: {action} {out_dir}")
    print(f"- skyhook map: {map_dir}")
    print(f"- files scanned: {len(scan.files)}")
    print(f"- primary languages: {', '.join(list(scan.language_counts.keys())[:5]) or 'none detected'}")
    print(f"- frameworks: {', '.join(scan.frameworks) or 'none detected'}")
    print(f"- docs: {len(scan.docs)}")
    if would_change is not None:
        print(f"- artifacts would change: {'yes' if would_change else 'no'}")
    if size_report is not None:
        print(f"- guidance size: {size_report['lines']} lines (budget {size_report['budgetLines']})")
        if size_report.get("overBudget"):
            print(
                "burnplan: warning: agent-prompts.md exceeds the guidance budget; trim readFirst or raise guidance.maxLines",
                file=sys.stderr,
            )
    if wrote:
        print("- skyhook artifacts: map.md, map.json, docs.md, architecture.md")
        print("- burnplan artifacts: onboarding.md, quality.md, agent-prompts.md, documentation-ledger.md, agent-rules.json")
        print("- proposal artifacts: .burnplan/proposals/docs/* (incl. agent-rules.md, improvement-backlog.md), .burnplan/proposals/agents/* (incl. claude-hooks/)")


def _exclude_output_dir(repo_root: Path, skyhook_cfg: Any, path: Path) -> None:
    try:
        rel_output = path.relative_to(repo_root).as_posix()
    except ValueError:
        rel_output = ""
    if rel_output and rel_output not in skyhook_cfg.scan.exclude:
        skyhook_cfg.scan.exclude.append(rel_output)


def _should_interview(args: argparse.Namespace) -> bool:
    if getattr(args, "interview", False) and getattr(args, "no_interview", False):
        raise ValueError("--interview and --no-interview cannot be used together")
    if getattr(args, "no_interview", False):
        return False
    if getattr(args, "interview", False):
        return True
    return sys.stdin.isatty()


def _read_task(args: argparse.Namespace) -> str:
    if getattr(args, "task", None):
        return str(args.task)
    if getattr(args, "task_file", None):
        return Path(args.task_file).read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise ValueError("burnplan assign requires --task, --task-file, or task text on stdin")


if __name__ == "__main__":
    raise SystemExit(main())
