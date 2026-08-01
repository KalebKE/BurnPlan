import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Skyhook"))

from burnplan.transcripts import (
    READ_WINDOW,
    build_behavior_snapshot,
    claude_project_dir,
    measurement_fields,
    scan_session_file,
)


def _assistant(blocks) -> str:
    return json.dumps(
        {
            "type": "assistant",
            "timestamp": "2026-07-01T12:00:00.000Z",
            "message": {"model": "claude-test", "content": blocks},
        }
    )


def _tool(name: str, path: str) -> dict:
    return {"type": "tool_use", "name": name, "input": {"file_path": path}}


class ScanSessionTests(unittest.TestCase):
    def _write_session(self, tmp: Path, lines) -> Path:
        path = tmp / "session.jsonl"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def test_read_then_edit_is_not_counted(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            path = self._write_session(
                tmp,
                [_assistant([_tool("Read", "/repo/a.py"), _tool("Edit", "/repo/a.py")])],
            )
            stats = scan_session_file(path, tmp)
            self.assertEqual(stats, {"edits_total": 1, "edits_wo_read": 0})

    def test_edit_without_read_is_counted(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            path = self._write_session(tmp, [_assistant([_tool("Write", "/repo/b.py")])])
            stats = scan_session_file(path, tmp)
            self.assertEqual(stats, {"edits_total": 1, "edits_wo_read": 1})

    def test_window_evicts_after_twenty_reads(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            blocks = [_tool("Read", "/repo/first.py")]
            blocks += [_tool("Read", f"/repo/f{i}.py") for i in range(READ_WINDOW)]
            blocks += [_tool("Edit", "/repo/first.py")]
            path = self._write_session(tmp, [_assistant(blocks)])
            stats = scan_session_file(path, tmp)
            self.assertEqual(stats, {"edits_total": 1, "edits_wo_read": 1})

    def test_malformed_lines_and_pathless_blocks_are_ignored(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            lines = [
                "not json at all",
                json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Edit", "input": {}}]}}),
                _assistant([_tool("MultiEdit", "/repo/c.py")]),
            ]
            path = self._write_session(tmp, lines)
            stats = scan_session_file(path, tmp)
            self.assertEqual(stats, {"edits_total": 1, "edits_wo_read": 1})

    def test_session_from_another_repo_cwd_is_skipped(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            entry = json.dumps(
                {
                    "type": "assistant",
                    "cwd": "/somewhere/else",
                    "message": {"content": [_tool("Edit", "/repo/d.py")]},
                }
            )
            path = self._write_session(tmp, [entry])
            self.assertIsNone(scan_session_file(path, tmp))


class SnapshotTests(unittest.TestCase):
    def test_project_dir_munges_path(self):
        home = Path("/tmp/claude-home")
        result = claude_project_dir(Path("/Users/dev/Projects/BurnPlan"), home)
        self.assertEqual(result, home / "projects" / "-Users-dev-Projects-BurnPlan")

    def test_snapshot_aggregates_and_windows(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            repo = tmp / "repo"
            repo.mkdir()
            home = tmp / "claude"
            project = claude_project_dir(repo, home)
            project.mkdir(parents=True)
            (project / "fresh.jsonl").write_text(
                _assistant([_tool("Read", "/r/a.py"), _tool("Edit", "/r/a.py"), _tool("Write", "/r/b.py")]) + "\n",
                encoding="utf-8",
            )
            stale = project / "stale.jsonl"
            stale.write_text(_assistant([_tool("Write", "/r/old.py")]) + "\n", encoding="utf-8")
            old = time.time() - 120 * 86400
            os.utime(stale, (old, old))

            snapshot = build_behavior_snapshot(repo, window_days=90, claude_home=home)
            self.assertIsNotNone(snapshot)
            self.assertEqual(snapshot["sessions"], 1)
            self.assertEqual(snapshot["editsTotal"], 2)
            self.assertEqual(snapshot["editsWithoutRead"], 1)
            self.assertEqual(snapshot["editsWithoutReadPct"], 50.0)
            self.assertEqual(snapshot["readWindow"], READ_WINDOW)

    def test_missing_project_dir_returns_none(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            self.assertIsNone(build_behavior_snapshot(tmp / "repo", 90, claude_home=tmp / "claude"))

    def test_measurement_fields_drop_captured_at(self):
        snapshot = {"capturedAt": "20260730T000000Z", "editsTotal": 5, "sessions": 1}
        self.assertEqual(measurement_fields(snapshot), {"editsTotal": 5, "sessions": 1})
        self.assertEqual(measurement_fields(None), {})


if __name__ == "__main__":
    unittest.main()
