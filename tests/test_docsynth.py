import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Skyhook"))

from burnplan import docsynth
from burnplan.docsynth import build_or_reuse_doc_synthesis, collect_doc_context, doc_fingerprint


def _base_map(docs):
    return {"docs": docs, "scan": {"digest": "abc123"}, "codeAreas": []}


def _onboarding():
    return {"summary": "Demo project.", "architectureIntent": "Layered."}


class DocContextTests(unittest.TestCase):
    def test_collects_high_priority_docs_with_headings_and_lead(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "docs" / "ARCHITECTURE.md").write_text(
                "# Architecture\n\nRetries use exponential backoff.\n\n## Boundaries\n\nStuff.\n",
                encoding="utf-8",
            )
            (root / "notes.md").write_text("# Notes\n\nScratch.\n", encoding="utf-8")
            base_map = _base_map(
                [
                    {"path": "docs/ARCHITECTURE.md", "kind": "architecture", "title": "Architecture"},
                    {"path": "notes.md", "kind": "unknown", "title": "Notes"},
                ]
            )

            context = collect_doc_context(root, base_map)

        self.assertEqual(len(context), 1)
        doc = context[0]
        self.assertEqual(doc["path"], "docs/ARCHITECTURE.md")
        self.assertEqual(doc["lead"], "Retries use exponential backoff.")
        self.assertIn("## Boundaries", doc["headings"])

    def test_missing_files_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base_map = _base_map([{"path": "docs/GONE.md", "kind": "architecture", "title": "Gone"}])
            self.assertEqual(collect_doc_context(root, base_map), [])


class FingerprintTests(unittest.TestCase):
    def test_fingerprint_changes_with_doc_content(self):
        doc = {"path": "docs/A.md", "kind": "architecture", "text": "one"}
        changed = dict(doc, text="two")
        base_map = _base_map([])
        self.assertNotEqual(
            doc_fingerprint([doc], base_map, _onboarding()),
            doc_fingerprint([changed], base_map, _onboarding()),
        )

    def test_fingerprint_stable_for_same_inputs(self):
        doc = {"path": "docs/A.md", "kind": "architecture", "text": "one"}
        base_map = _base_map([])
        self.assertEqual(
            doc_fingerprint([doc], base_map, _onboarding()),
            doc_fingerprint([doc], base_map, _onboarding()),
        )


class BuildOrReuseTests(unittest.TestCase):
    def test_reuse_gate_returns_previous_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            doc = {"path": "docs/A.md", "kind": "architecture", "text": "one", "headings": [], "lead": ""}
            base_map = _base_map([])

            first = build_or_reuse_doc_synthesis(out_dir, [doc], base_map, _onboarding(), None, None, allow_model=False)
            (out_dir / "doc-synthesis.json").write_text(json.dumps(first), encoding="utf-8")
            second = build_or_reuse_doc_synthesis(out_dir, [doc], base_map, _onboarding(), None, None, allow_model=False)
            self.assertEqual(first, second)

    def test_dry_run_never_calls_model(self):
        def _fail(*args, **kwargs):
            raise AssertionError("model must not be called on dry-run")

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            doc = {"path": "docs/A.md", "kind": "architecture", "text": "one", "headings": [], "lead": ""}
            with mock.patch.object(docsynth, "chat_json", _fail):
                artifact = build_or_reuse_doc_synthesis(
                    out_dir, [doc], _base_map([]), _onboarding(), None, None, allow_model=False
                )
        self.assertEqual(artifact["generatedBy"], "static")
        self.assertEqual(artifact["drafts"], {})

    def test_model_drafts_replace_proposal_content(self):
        fake = mock.Mock(return_value={"architecture": "# Better Architecture\n\nMerged.", "design": ""})
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            doc = {"path": "docs/A.md", "kind": "architecture", "text": "one", "headings": [], "lead": ""}
            with mock.patch.object(docsynth, "chat_json", fake):
                artifact = build_or_reuse_doc_synthesis(
                    out_dir, [doc], _base_map([]), _onboarding(), None, None, allow_model=True
                )
        self.assertEqual(artifact["generatedBy"], "model")
        self.assertEqual(artifact["drafts"], {"architecture": "# Better Architecture\n\nMerged."})
        fake.assert_called_once()

        from burnplan.proposals import build_project_proposals

        proposals = build_project_proposals(
            _base_map([]), _onboarding(), {}, {"teams": {}}, {"rules": []}, [doc], artifact
        )
        architecture = proposals["proposals/docs/architecture.md"]
        self.assertIn("model synthesis", architecture)
        self.assertIn("# Better Architecture", architecture)
        design = proposals["proposals/docs/design.md"]
        self.assertIn("GENERATED by burnplan.", design)

    def test_model_fallback_to_static_when_chat_json_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            doc = {"path": "docs/A.md", "kind": "architecture", "text": "one", "headings": [], "lead": ""}
            with mock.patch.object(docsynth, "chat_json", None):
                artifact = build_or_reuse_doc_synthesis(
                    out_dir, [doc], _base_map([]), _onboarding(), None, None, allow_model=True
                )
        self.assertEqual(artifact["generatedBy"], "static")


if __name__ == "__main__":
    unittest.main()
