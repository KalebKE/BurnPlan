import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Skyhook"))

from burnplan import distill
from burnplan.distill import _static_rules, build_or_reuse_rules, source_fingerprint


def _entry(entry_id: str, area: str, why: str, what: str = "Changed something") -> dict:
    return {"id": entry_id, "timestamp": entry_id.split("-", 1)[0], "area": area, "what": what, "why": why, "git": {}}


def _write_worklog(out_dir: Path, entries) -> None:
    worklog = out_dir / "worklog"
    worklog.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        (worklog / f"{entry['id']}.json").write_text(json.dumps(entry), encoding="utf-8")


class StaticRulesTests(unittest.TestCase):
    def test_static_rules_deterministic_and_capped(self):
        entries = [
            _entry(f"20260701T00{index:02d}00Z-work-{index}", f"area{index}", f"Reason number {index} keeps recurring here.")
            for index in range(21)
        ]
        first = _static_rules(entries)
        second = _static_rules(entries)
        self.assertEqual(first, second)
        self.assertLessEqual(len(first), 18)
        area_rules = [rule for rule in first if rule["id"].startswith("area-")]
        self.assertEqual(len(area_rules), 12)

    def test_rule_provenance_ids_are_real_entry_ids(self):
        entries = [
            _entry("20260701T010000Z-retry", "sync", "Transient failures recur in sync paths."),
            _entry("20260701T020000Z-backoff", "sync", "Transient failures need explicit backoff handling."),
        ]
        rules = _static_rules(entries)
        valid_ids = {entry["id"] for entry in entries}
        for rule in rules:
            self.assertTrue(rule["sourceIds"])
            for source_id in rule["sourceIds"]:
                self.assertIn(source_id, valid_ids)

    def test_fingerprint_depends_only_on_entry_ids(self):
        entries_a = [_entry("20260701T010000Z-x", "sync", "One rationale.")]
        entries_b = [_entry("20260701T010000Z-x", "auth", "Completely different rationale.")]
        self.assertEqual(source_fingerprint(entries_a), source_fingerprint(entries_b))
        entries_c = [_entry("20260701T020000Z-y", "sync", "One rationale.")]
        self.assertNotEqual(source_fingerprint(entries_a), source_fingerprint(entries_c))

    def test_stale_marking_for_areas_absent_from_recent_entries(self):
        # Entries are newest-first; the "cold" area only appears beyond the recent window.
        entries = [
            _entry(f"20260702T00{index:02d}00Z-hot-{index}", "hot", f"Hot path issue {index}.")
            for index in range(20)
        ] + [
            _entry("20260601T000000Z-cold", "cold", "Old concern that stopped recurring.")
        ]
        rules = _static_rules(entries)
        by_area = {rule["area"]: rule for rule in rules if rule["id"].startswith("area-")}
        self.assertEqual(by_area["hot"]["status"], "active")
        self.assertEqual(by_area["cold"]["status"], "stale")


class BuildOrReuseTests(unittest.TestCase):
    def test_reuse_gate_returns_previous_artifact_verbatim(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            entries = [_entry("20260701T010000Z-retry", "sync", "Transient failures recur.")]
            _write_worklog(out_dir, entries)

            first = build_or_reuse_rules(out_dir, None, None, allow_model=False)
            (out_dir / "agent-rules.json").write_text(json.dumps(first), encoding="utf-8")
            second = build_or_reuse_rules(out_dir, None, None, allow_model=False)
            self.assertEqual(first, second)

            _write_worklog(out_dir, [_entry("20260701T020000Z-auth", "auth", "Token refresh races logout.")])
            third = build_or_reuse_rules(out_dir, None, None, allow_model=False)
            self.assertNotEqual(first["sourceFingerprint"], third["sourceFingerprint"])

    def test_model_fallback_to_static_when_chat_json_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            _write_worklog(out_dir, [_entry("20260701T010000Z-retry", "sync", "Transient failures recur.")])
            with mock.patch.object(distill, "chat_json", None):
                artifact = build_or_reuse_rules(out_dir, None, None, allow_model=True)
        self.assertEqual(artifact["generatedBy"], "static")
        self.assertEqual(artifact["ruleCount"], 1)

    def test_survives_malformed_worklog_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            valid = _entry("20260701T010000Z-retry", "sync", "Transient failures recur.")
            _write_worklog(out_dir, [valid])
            (out_dir / "worklog" / "20260701T020000Z-broken.json").write_text("{not valid json", encoding="utf-8")

            first = build_or_reuse_rules(out_dir, None, None, allow_model=False)
            second = build_or_reuse_rules(out_dir, None, None, allow_model=False)

        self.assertEqual(first, second)
        self.assertEqual(first["ruleCount"], 1)
        self.assertEqual(first["rules"][0]["sourceIds"], [valid["id"]])
        # The corrupted file is skipped entirely, so it must not affect the fingerprint.
        self.assertEqual(first["sourceFingerprint"], source_fingerprint([valid]))

    def test_dry_run_never_calls_model(self):
        def _fail(*args, **kwargs):
            raise AssertionError("model must not be called on dry-run")

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            _write_worklog(out_dir, [_entry("20260701T010000Z-retry", "sync", "Transient failures recur.")])
            with mock.patch.object(distill, "chat_json", _fail):
                artifact = build_or_reuse_rules(out_dir, None, None, allow_model=False)
        self.assertEqual(artifact["generatedBy"], "static")


if __name__ == "__main__":
    unittest.main()
