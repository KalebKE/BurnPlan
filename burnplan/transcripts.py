"""Claude Code transcript scanner for behavioral evidence.

Reads the session transcripts Claude Code keeps under ``~/.claude/projects/``
and measures how agents worked in this repository. The one signal captured
today is edits-without-prior-read: an edit to a file whose path is not among
the last 20 read paths in the session. The window size and tool-name sets
mirror blackbox's session-behavior scanner, so the number recorded here and
the number a blackbox dashboard shows for the same repo agree on semantics.

Scanning is never part of onboard/optimize. The ratchet consumes only the
committed ``.burnplan/behavior-evidence.json`` snapshot, which keeps the
dry-run gate deterministic and CI runners without ``~/.claude`` unaffected.
Capture is the deliberate ``burnplan behavior sync`` command. Codex rollouts
are not scanned: edit detection there is approximate enough to be noise.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections import deque
from pathlib import Path
from typing import Any, Dict, Optional

READ_WINDOW = 20
SNAPSHOT_NAME = "behavior-evidence.json"

_EDIT_TOOLS = {"edit", "write", "multiedit", "notebookedit"}


def claude_project_dir(repo_root: Path, claude_home: Optional[Path] = None) -> Path:
    """The transcript directory Claude Code uses for a repository.

    Claude Code names project directories by replacing every character
    outside [A-Za-z0-9] in the absolute repo path with ``-``. Sessions
    started from worktrees or subdirectories land in other directories and
    are not counted.
    """
    if claude_home is not None:
        home = claude_home
    elif os.environ.get("CLAUDE_CONFIG_DIR"):
        home = Path(os.environ["CLAUDE_CONFIG_DIR"])
    else:
        home = Path.home() / ".claude"
    munged = re.sub(r"[^A-Za-z0-9]", "-", str(Path(repo_root).resolve()))
    return home / "projects" / munged


def scan_session_file(path: Path, repo_root: Path) -> Optional[Dict[str, int]]:
    """Edit counts for one session transcript, or None when unusable.

    Semantics mirror blackbox's claudeSignals: assistant entries only,
    tool_use blocks, tool names lowercased, a Read pushes its path onto a
    20-deep window, an Edit/Write/MultiEdit/NotebookEdit counts as an edit
    and as an edit-without-read when its path is not in the window. Blocks
    without a path are ignored. A session whose recorded cwd resolves
    outside the repository is skipped.
    """
    repo_real = str(Path(repo_root).resolve())
    reads: deque = deque(maxlen=READ_WINDOW)
    edits_total = 0
    edits_wo_read = 0
    saw_entries = False
    try:
        handle = path.open(encoding="utf-8", errors="replace")
    except OSError:
        return None
    with handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except (ValueError, TypeError):
                continue
            if not isinstance(entry, dict):
                continue
            cwd = entry.get("cwd")
            if isinstance(cwd, str) and cwd:
                cwd_real = str(Path(cwd).resolve())
                if cwd_real != repo_real and not cwd_real.startswith(repo_real + "/"):
                    return None
            if entry.get("type") != "assistant":
                continue
            saw_entries = True
            message = entry.get("message")
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                name = str(block.get("name", "")).lower()
                target = _block_path(block.get("input"))
                if target is None:
                    continue
                if name == "read":
                    reads.append(target)
                elif name in _EDIT_TOOLS:
                    edits_total += 1
                    if target not in reads:
                        edits_wo_read += 1
    if not saw_entries:
        return None
    return {"edits_total": edits_total, "edits_wo_read": edits_wo_read}


def build_behavior_snapshot(
    repo_root: Path,
    window_days: int,
    claude_home: Optional[Path] = None,
    now: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Aggregate the repo's recent sessions into a snapshot dict.

    Returns None when the transcript directory does not exist or no session
    in the window produced a usable measurement. Sessions are selected by
    file mtime against the window.
    """
    directory = claude_project_dir(repo_root, claude_home)
    if not directory.is_dir():
        return None
    cutoff = (now if now is not None else time.time()) - window_days * 86400
    sessions = 0
    edits_total = 0
    edits_wo_read = 0
    for path in sorted(directory.glob("*.jsonl")):
        try:
            if path.stat().st_mtime < cutoff:
                continue
        except OSError:
            continue
        stats = scan_session_file(path, repo_root)
        if stats is None:
            continue
        sessions += 1
        edits_total += stats["edits_total"]
        edits_wo_read += stats["edits_wo_read"]
    if sessions == 0:
        return None
    pct = round(100.0 * edits_wo_read / edits_total, 1) if edits_total else 0.0
    return {
        "schemaVersion": 1,
        "source": "claude-transcripts",
        "capturedAt": time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now)),
        "windowDays": window_days,
        "readWindow": READ_WINDOW,
        "sessions": sessions,
        "editsTotal": edits_total,
        "editsWithoutRead": edits_wo_read,
        "editsWithoutReadPct": pct,
    }


def measurement_fields(snapshot: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The snapshot minus capture metadata: what fingerprints and rules see.

    Re-running sync with unchanged transcripts must not dirty the ratchet, so
    everything derived from a snapshot ignores capturedAt.
    """
    if not isinstance(snapshot, dict):
        return {}
    return {k: v for k, v in snapshot.items() if k != "capturedAt"}


def _block_path(value: Any) -> Optional[str]:
    if not isinstance(value, dict):
        return None
    for key in ("file_path", "path", "notebook_path"):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate:
            return candidate
    return None
