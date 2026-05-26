from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .artifacts import canonical_json


def build_document_entry(repo_root: Path, what: Optional[str], why: Optional[str], area: Optional[str], from_git: bool) -> Dict[str, Any]:
    git_context = _git_context(repo_root) if from_git else {}
    resolved_what = (what or "").strip()
    if not resolved_what and git_context:
        resolved_what = git_context.get("summary", "")
    resolved_why = (why or "").strip()
    if not resolved_what:
        raise ValueError("burnplan document requires --what, or --from-git with local changes")
    if not resolved_why:
        raise ValueError("burnplan document requires --why")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    slug = _slug(area or resolved_what)
    return {
        "id": f"{timestamp}-{slug}",
        "timestamp": timestamp,
        "area": (area or "").strip(),
        "what": resolved_what,
        "why": resolved_why,
        "git": git_context,
    }


def write_document_entry(out_dir: Path, entry: Dict[str, Any]) -> List[Path]:
    worklog_dir = out_dir / "worklog"
    rationale_dir = out_dir / "rationale"
    worklog_dir.mkdir(parents=True, exist_ok=True)
    rationale_dir.mkdir(parents=True, exist_ok=True)

    worklog_md = worklog_dir / f"{entry['id']}.md"
    worklog_json = worklog_dir / f"{entry['id']}.json"
    rationale_md = rationale_dir / f"{entry['id']}.md"
    rationale_json = rationale_dir / f"{entry['id']}.json"
    worklog_md.write_text(render_worklog(entry), encoding="utf-8")
    worklog_json.write_text(canonical_json(entry), encoding="utf-8")
    rationale_md.write_text(render_rationale(entry), encoding="utf-8")
    rationale_json.write_text(canonical_json(entry), encoding="utf-8")
    return [worklog_md, worklog_json, rationale_md, rationale_json]


def collect_documentation_ledger(out_dir: Path) -> Dict[str, Any]:
    worklogs = _read_entries(out_dir / "worklog")
    rationales = _read_entries(out_dir / "rationale")
    return {
        "worklogCount": len(worklogs),
        "rationaleCount": len(rationales),
        "recentWork": worklogs[:10],
        "recentRationale": rationales[:10],
    }


def render_worklog(entry: Dict[str, Any]) -> str:
    lines = [
        f"# Worklog: {entry.get('area') or entry['id']}",
        "",
        f"- Timestamp: `{entry['timestamp']}`",
    ]
    if entry.get("area"):
        lines.append(f"- Area: `{entry['area']}`")
    lines.extend(["", "## What Changed", "", entry["what"].strip(), ""])
    git_summary = (entry.get("git") or {}).get("summary")
    if git_summary:
        lines.extend(["## Git Context", "", "```text", git_summary.strip(), "```", ""])
    return "\n".join(lines)


def render_rationale(entry: Dict[str, Any]) -> str:
    lines = [
        f"# Rationale: {entry.get('area') or entry['id']}",
        "",
        f"- Timestamp: `{entry['timestamp']}`",
    ]
    if entry.get("area"):
        lines.append(f"- Area: `{entry['area']}`")
    lines.extend(["", "## Why This Changed", "", entry["why"].strip(), ""])
    if entry.get("what"):
        lines.extend(["## Related Work", "", entry["what"].strip(), ""])
    return "\n".join(lines)


def _read_entries(directory: Path) -> List[Dict[str, Any]]:
    if not directory.exists():
        return []
    entries: List[Dict[str, Any]] = []
    for path in sorted(directory.glob("*.json"), reverse=True):
        try:
            entries.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return entries


def _git_context(repo_root: Path) -> Dict[str, Any]:
    status = _git(["status", "--short"], repo_root)
    staged_stat = _git(["diff", "--cached", "--stat"], repo_root)
    unstaged_stat = _git(["diff", "--stat"], repo_root)
    pieces = []
    if status:
        pieces.extend(["status:", status])
    if staged_stat:
        pieces.extend(["staged diff:", staged_stat])
    if unstaged_stat:
        pieces.extend(["unstaged diff:", unstaged_stat])
    summary = "\n".join(pieces).strip()
    return {"summary": summary} if summary else {}


def _git(args: List[str], repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(repo_root),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value.lower()).strip("-")
    return (slug[:60].strip("-") or "entry")
