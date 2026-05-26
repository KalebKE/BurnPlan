import subprocess
import sys
import tempfile
import unittest
import json
import io
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Skyhook"))

from burnplan.cli import main


class CliTests(unittest.TestCase):
    def test_onboard_no_interview_writes_map_and_ratchet_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / "README.md").write_text("# Demo\n\nDemo repo.", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("print('hello')\n", encoding="utf-8")

            self.assertEqual(main(["onboard", "--repo", str(root), "--provider", "static", "--no-interview"]), 0)

            for name in ["map.json", "map.md", "docs.md", "architecture.md"]:
                self.assertTrue((root / ".skyhook" / name).exists(), name)
            for name in [
                "onboarding.json",
                "onboarding.md",
                "quality.json",
                "quality.md",
                "agent-prompts.json",
                "agent-prompts.md",
                "documentation-ledger.json",
                "documentation-ledger.md",
            ]:
                self.assertTrue((root / ".burnplan" / name).exists(), name)
            self.assertTrue((root / ".burnplan" / "proposals" / "manifest.json").exists())
            self.assertTrue((root / ".burnplan" / "proposals" / "docs" / "architecture.md").exists())
            self.assertTrue((root / ".burnplan" / "proposals" / "agents" / "generic" / "product-owner-story-writer.md").exists())
            self.assertTrue((root / ".burnplan" / "proposals" / "agents" / "claude" / "product-owner-story-writer.md").exists())

    def test_optimize_dry_run_reports_changes_until_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / "README.md").write_text("# Demo\n\nDemo repo.", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("print('hello')\n", encoding="utf-8")

            self.assertEqual(main(["optimize", "--repo", str(root), "--provider", "static", "--dry-run"]), 1)
            self.assertEqual(main(["optimize", "--repo", str(root), "--provider", "static"]), 0)
            self.assertEqual(main(["optimize", "--repo", str(root), "--provider", "static", "--dry-run"]), 0)

    def test_document_writes_worklog_and_rationale_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)

            self.assertEqual(
                main(
                    [
                        "document",
                        "--repo",
                        str(root),
                        "--what",
                        "Added sync retry handling",
                        "--why",
                        "Retries make transient failures explicit for future agents.",
                        "--area",
                        "sync",
                    ]
                ),
                0,
            )

            self.assertEqual(len(list((root / ".burnplan" / "worklog").glob("*.md"))), 1)
            self.assertEqual(len(list((root / ".burnplan" / "rationale").glob("*.md"))), 1)
            self.assertEqual(len(list((root / ".burnplan" / "worklog").glob("*.json"))), 1)
            self.assertEqual(len(list((root / ".burnplan" / "rationale").glob("*.json"))), 1)

    def test_teams_init_writes_default_team_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)

            self.assertEqual(main(["teams", "init", "--repo", str(root)]), 0)

            data = json.loads((root / ".burnplan" / "teams.json").read_text(encoding="utf-8"))
            self.assertEqual(data["teams"]["product-owner"]["behaviors"]["story"]["routeProfile"], "product_planning")
            self.assertEqual(data["teams"]["project-manager"]["behaviors"]["implement"]["routeProfile"], "implementation")
            self.assertIn("story-writer", data["teams"]["product-owner"]["subagents"])
            self.assertIn("technical-planner", data["teams"]["project-manager"]["subagents"])

    def test_assign_routes_team_behavior_to_skyhook_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / "README.md").write_text("# Demo\n\nCheckout workflow.", encoding="utf-8")
            (root / "docs").mkdir()
            (root / "docs" / "design.md").write_text("# Checkout Design\n\nUser checkout story.", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "checkout.py").write_text("class CheckoutService: pass\n", encoding="utf-8")

            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(
                    main(
                        [
                            "assign",
                            "--repo",
                            str(root),
                            "--provider",
                            "static",
                            "--team",
                            "product-owner",
                            "--behavior",
                            "story",
                            "--task",
                            "plan checkout story",
                            "--format",
                            "json",
                        ]
                    ),
                    0,
                )

            data = json.loads(output.getvalue())
            self.assertEqual(data["profile"], "product_planning")
            self.assertEqual(data["assignment"]["team"], "product-owner")
            self.assertEqual(data["assignment"]["behavior"], "story")
            self.assertTrue((root / ".skyhook" / "map.json").exists())

    def test_promote_writes_docs_and_agent_files_after_onboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / "README.md").write_text("# Demo\n\nDemo repo.", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("print('hello')\n", encoding="utf-8")

            self.assertEqual(main(["onboard", "--repo", str(root), "--provider", "static", "--no-interview"]), 0)
            self.assertEqual(main(["promote", "docs", "--repo", str(root)]), 0)
            self.assertEqual(main(["promote", "agents", "--repo", str(root)]), 0)

            self.assertTrue((root / "docs" / "architecture.md").exists())
            self.assertTrue((root / "docs" / "design.md").exists())
            self.assertTrue((root / "docs" / "code-map.md").exists())
            self.assertTrue((root / "docs" / "agents" / "product-owner-story-writer.md").exists())
            self.assertTrue((root / ".claude" / "agents" / "product-owner-story-writer.md").exists())

            self.assertEqual(main(["promote", "docs", "--repo", str(root)]), 2)
            self.assertEqual(main(["promote", "docs", "--repo", str(root), "--force"]), 0)


def _init_repo(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    unittest.main()
