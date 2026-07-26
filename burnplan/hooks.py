from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional


STOP_REMINDER = (
    "Working tree has undocumented changes: run "
    "`burnplan document --what ... --why ... --area ...` and `burnplan optimize` before finishing."
)


def stop_reminder(repo_root: Path, out_dir: Path) -> Optional[str]:
    """Cheap end-of-session check used by the generated Claude Code Stop hook.

    Returns a reminder when the working tree is dirty and no worklog entry is
    newer than the last commit; returns None otherwise. Never raises.
    """
    status = _git(["status", "--porcelain"], repo_root)
    if status is None or not status.strip():
        return None
    last_commit_stamp = _git(["log", "-1", "--format=%ct"], repo_root)
    newest_entry = _newest_worklog_timestamp(out_dir)
    if newest_entry is None:
        return STOP_REMINDER
    if last_commit_stamp is None:
        return None
    commit_utc = _epoch_to_stamp(last_commit_stamp.strip())
    if commit_utc is None:
        return None
    if newest_entry >= commit_utc:
        return None
    return STOP_REMINDER


def _newest_worklog_timestamp(out_dir: Path) -> Optional[str]:
    worklog = out_dir / "worklog"
    if not worklog.exists():
        return None
    names = sorted((path.stem for path in worklog.glob("*.json")), reverse=True)
    if not names:
        return None
    return names[0].split("-", 1)[0]


def _epoch_to_stamp(epoch: str) -> Optional[str]:
    import datetime

    try:
        moment = datetime.datetime.fromtimestamp(int(epoch), tz=datetime.timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None
    return moment.strftime("%Y%m%dT%H%M%SZ")


def _git(args: list, repo_root: Path) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout
