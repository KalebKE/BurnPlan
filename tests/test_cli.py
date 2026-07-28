import os
import subprocess
import sys
import tempfile
import unittest
import json
import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Skyhook"))

from burnplan.cli import main

BURNPLAN_ROOT = Path(__file__).resolve().parents[1]
SKYHOOK_ROOT = Path(__file__).resolve().parents[2] / "Skyhook"


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
                "agent-rules.json",
            ]:
                self.assertTrue((root / ".burnplan" / name).exists(), name)
            self.assertTrue((root / ".burnplan" / "proposals" / "manifest.json").exists())
            self.assertTrue((root / ".burnplan" / "proposals" / "docs" / "architecture.md").exists())
            self.assertTrue((root / ".burnplan" / "proposals" / "docs" / "agent-rules.md").exists())
            self.assertTrue((root / ".burnplan" / "proposals" / "docs" / "improvement-backlog.md").exists())
            self.assertTrue((root / ".burnplan" / "proposals" / "agents" / "generic" / "product-owner-story-writer.md").exists())
            self.assertTrue((root / ".burnplan" / "proposals" / "agents" / "claude" / "product-owner-story-writer.md").exists())
            self.assertTrue((root / ".burnplan" / "proposals" / "agents" / "claude-hooks" / "settings-hooks.json").exists())
            self.assertTrue((root / ".burnplan" / "proposals" / "agents" / "claude-hooks" / "README.md").exists())

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

    def test_promote_skip_existing_preserves_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / "README.md").write_text("# Demo\n\nDemo repo.", encoding="utf-8")
            (root / "docs").mkdir()
            sentinel = "# Human-written architecture\n\nDo not clobber.\n"
            (root / "docs" / "architecture.md").write_text(sentinel, encoding="utf-8")

            self.assertEqual(main(["onboard", "--repo", str(root), "--provider", "static", "--no-interview"]), 0)

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(main(["promote", "docs", "--repo", str(root), "--skip-existing"]), 0)

            self.assertEqual((root / "docs" / "architecture.md").read_text(encoding="utf-8"), sentinel)
            self.assertTrue((root / "docs" / "design.md").exists())
            self.assertTrue((root / "docs" / "agent-rules.md").exists())
            self.assertIn("skipped (exists):", stdout.getvalue())
            self.assertIn("architecture.md", stdout.getvalue())

    def test_promote_only_selects_single_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / "README.md").write_text("# Demo\n\nDemo repo.", encoding="utf-8")
            (root / "docs").mkdir()
            sentinel = "# Human architecture\n\nOld truth.\n"
            (root / "docs" / "architecture.md").write_text(sentinel, encoding="utf-8")

            self.assertEqual(main(["onboard", "--repo", str(root), "--provider", "static", "--no-interview"]), 0)

            self.assertEqual(main(["promote", "docs", "--repo", str(root), "--only", "architecture.md", "--force"]), 0)

            promoted = (root / "docs" / "architecture.md").read_text(encoding="utf-8")
            self.assertNotEqual(promoted, sentinel)
            self.assertIn("GENERATED by burnplan", promoted)
            self.assertFalse((root / "docs" / "design.md").exists(), "--only must not promote other docs")

    def test_promote_only_unknown_name_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / "README.md").write_text("# Demo\n\nDemo repo.", encoding="utf-8")

            self.assertEqual(main(["onboard", "--repo", str(root), "--provider", "static", "--no-interview"]), 0)

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.assertEqual(main(["promote", "docs", "--repo", str(root), "--only", "no-such-doc.md"]), 2)
            self.assertIn("matched no proposal files", stderr.getvalue())

    def test_generated_docs_incorporate_existing_documentation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / "README.md").write_text("# Demo\n\nDemo repo.", encoding="utf-8")
            (root / "docs").mkdir()
            (root / "docs" / "ARCHITECTURE.md").write_text(
                "# Architecture\n\nThe sync layer retries with exponential backoff.\n\n"
                "## Module Boundaries\n\nStuff.\n\n## Data Flow\n\nMore stuff.\n",
                encoding="utf-8",
            )

            self.assertEqual(main(["onboard", "--repo", str(root), "--provider", "static", "--no-interview"]), 0)

            proposal = (root / ".burnplan" / "proposals" / "docs" / "architecture.md").read_text(encoding="utf-8")
            self.assertIn("Existing Documentation", proposal)
            self.assertIn("docs/ARCHITECTURE.md", proposal)
            self.assertIn("The sync layer retries with exponential backoff.", proposal)
            self.assertIn("Module Boundaries", proposal)

    def test_promote_skip_existing_conflicts_with_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / "README.md").write_text("# Demo\n\nDemo repo.", encoding="utf-8")

            self.assertEqual(main(["onboard", "--repo", str(root), "--provider", "static", "--no-interview"]), 0)

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.assertEqual(main(["promote", "docs", "--repo", str(root), "--force", "--skip-existing"]), 2)
            self.assertIn("cannot be used together", stderr.getvalue())

    def test_agent_prompts_are_slim(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / "README.md").write_text("# Demo\n\nDemo repo.", encoding="utf-8")

            self.assertEqual(main(["onboard", "--repo", str(root), "--provider", "static", "--no-interview"]), 0)

            prompts_md = (root / ".burnplan" / "agent-prompts.md").read_text(encoding="utf-8")
            self.assertNotIn("Improvement Prompts", prompts_md)
            guidance = json.loads((root / ".burnplan" / "agent-prompts.json").read_text(encoding="utf-8"))
            self.assertNotIn("improvementPrompts", guidance)
            self.assertLessEqual(len(guidance["readFirst"]), 8)
            self.assertEqual(len(guidance["beforeCoding"]), 2)
            self.assertEqual(len(guidance["beforeCommit"]), 2)

    def test_claude_agent_frontmatter_has_tools_and_quoted_description(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / "README.md").write_text("# Demo\n\nDemo repo.", encoding="utf-8")

            self.assertEqual(main(["onboard", "--repo", str(root), "--provider", "static", "--no-interview"]), 0)

            claude_dir = root / ".burnplan" / "proposals" / "agents" / "claude"
            implementer = (claude_dir / "project-manager-implementer.md").read_text(encoding="utf-8")
            self.assertIn("tools: Read, Grep, Glob, Bash, Edit, Write", implementer)
            self.assertIn('description: "', implementer)
            story_writer = (claude_dir / "product-owner-story-writer.md").read_text(encoding="utf-8")
            self.assertIn("tools: Read, Grep, Glob, Bash", story_writer)
            self.assertNotIn("Edit", story_writer.split("---")[1])
            self.assertNotIn("Write", story_writer.split("---")[1])

    def test_claude_agent_body_prefers_provided_route_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / "README.md").write_text("# Demo\n\nDemo repo.", encoding="utf-8")

            self.assertEqual(main(["onboard", "--repo", str(root), "--provider", "static", "--no-interview"]), 0)

            spec = (root / ".burnplan" / "proposals" / "agents" / "claude" / "project-manager-implementer.md").read_text(encoding="utf-8")
            self.assertIn("normally spawned with a Skyhook route pack already included in your prompt", spec)
            self.assertIn("--format json", spec)
            self.assertIn("Fallback only", spec)

    def test_rules_reuse_and_fingerprint_ratchet(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / "README.md").write_text("# Demo\n\nDemo repo.", encoding="utf-8")

            self.assertEqual(main(["onboard", "--repo", str(root), "--provider", "static", "--no-interview"]), 0)
            self.assertEqual(
                main(
                    [
                        "document",
                        "--repo",
                        str(root),
                        "--what",
                        "Added sync retry handling",
                        "--why",
                        "Transient failures recur in sync paths.",
                        "--area",
                        "sync",
                    ]
                ),
                0,
            )

            self.assertEqual(main(["optimize", "--repo", str(root), "--provider", "static", "--dry-run"]), 1)
            self.assertEqual(main(["optimize", "--repo", str(root), "--provider", "static"]), 0)
            self.assertEqual(main(["optimize", "--repo", str(root), "--provider", "static", "--dry-run"]), 0)

            rules_path = root / ".burnplan" / "agent-rules.json"
            first_bytes = rules_path.read_bytes()
            rules = json.loads(first_bytes)
            self.assertEqual(rules["ruleCount"], 1)
            self.assertEqual(rules["rules"][0]["area"], "sync")
            self.assertTrue(rules["rules"][0]["sourceIds"])

            self.assertEqual(main(["optimize", "--repo", str(root), "--provider", "static"]), 0)
            self.assertEqual(rules_path.read_bytes(), first_bytes)

            self.assertEqual(
                main(
                    [
                        "document",
                        "--repo",
                        str(root),
                        "--what",
                        "Hardened auth flow",
                        "--why",
                        "Token refresh must never race the logout path.",
                        "--area",
                        "auth",
                    ]
                ),
                0,
            )
            self.assertEqual(main(["optimize", "--repo", str(root), "--provider", "static", "--dry-run"]), 1)

    def test_promoted_rules_doc_enters_read_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / "README.md").write_text("# Demo\n\nDemo repo.", encoding="utf-8")

            self.assertEqual(main(["onboard", "--repo", str(root), "--provider", "static", "--no-interview"]), 0)
            guidance = json.loads((root / ".burnplan" / "agent-prompts.json").read_text(encoding="utf-8"))
            self.assertNotIn("docs/agent-rules.md", guidance["readFirst"])

            self.assertEqual(main(["promote", "docs", "--repo", str(root)]), 0)
            self.assertEqual(main(["optimize", "--repo", str(root), "--provider", "static"]), 0)

            guidance = json.loads((root / ".burnplan" / "agent-prompts.json").read_text(encoding="utf-8"))
            self.assertIn("docs/agent-rules.md", guidance["readFirst"])

    def test_promote_creates_claude_settings_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / "README.md").write_text("# Demo\n\nDemo repo.", encoding="utf-8")

            self.assertEqual(main(["onboard", "--repo", str(root), "--provider", "static", "--no-interview"]), 0)
            self.assertEqual(main(["promote", "agents", "--repo", str(root)]), 0)

            settings = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))
            stop_groups = settings["hooks"]["Stop"]
            self.assertEqual(len(stop_groups), 1)
            self.assertEqual(stop_groups[0]["hooks"][0]["command"], "burnplan hook stop")

    def test_promote_merges_hooks_into_existing_claude_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / "README.md").write_text("# Demo\n\nDemo repo.", encoding="utf-8")
            user_group = {"hooks": [{"type": "command", "command": "echo user-stop-hook"}]}
            (root / ".claude").mkdir()
            (root / ".claude" / "settings.json").write_text(
                json.dumps({"permissions": {"allow": ["Bash(ls:*)"]}, "hooks": {"Stop": [user_group]}}, indent=2),
                encoding="utf-8",
            )

            self.assertEqual(main(["onboard", "--repo", str(root), "--provider", "static", "--no-interview"]), 0)
            self.assertEqual(main(["promote", "agents", "--repo", str(root)]), 0)

            settings = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(settings["permissions"], {"allow": ["Bash(ls:*)"]})
            stop_groups = settings["hooks"]["Stop"]
            self.assertEqual(len(stop_groups), 2)
            self.assertEqual(stop_groups[0], user_group)
            self.assertEqual(stop_groups[1]["hooks"][0]["command"], "burnplan hook stop")

            self.assertEqual(main(["promote", "agents", "--repo", str(root), "--force"]), 0)
            settings = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(len(settings["hooks"]["Stop"]), 2)

    def test_optimize_reports_guidance_size_and_warns_over_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / "README.md").write_text("# Demo\n\nDemo repo.", encoding="utf-8")
            (root / ".burnplan").mkdir()
            (root / ".burnplan" / "config.yaml").write_text("guidance:\n  maxLines: 1\n", encoding="utf-8")

            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                self.assertEqual(main(["optimize", "--repo", str(root), "--provider", "static"]), 0)

            self.assertIn("guidance size:", stdout.getvalue())
            self.assertIn("(budget 1)", stdout.getvalue())
            self.assertIn("exceeds the guidance budget", stderr.getvalue())

    def test_artifacts_deterministic_across_hash_seeds(self):
        # A single test process runs under one PYTHONHASHSEED, so set/dict
        # iteration-order leaks into generated artifacts can only be caught by
        # regenerating in subprocesses under different seeds. dry-run exit 0
        # asserts every gated artifact is byte-identical to the first write.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / "README.md").write_text("# Demo\n\nDemo repo.", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("print('hello')\n", encoding="utf-8")
            worklog = root / ".burnplan" / "worklog"
            worklog.mkdir(parents=True)
            for entry_id, area, why in [
                ("20260701T010000Z-retry", "sync", "Transient failures recur in sync paths."),
                ("20260701T020000Z-auth", "auth", "Token refresh must never race the logout path."),
                ("20260701T030000Z-backoff", "sync", "Transient failures need explicit backoff handling."),
            ]:
                (worklog / f"{entry_id}.json").write_text(
                    json.dumps(
                        {
                            "id": entry_id,
                            "timestamp": entry_id.split("-", 1)[0],
                            "area": area,
                            "what": "Changed something",
                            "why": why,
                            "git": {},
                        }
                    ),
                    encoding="utf-8",
                )

            self.assertEqual(
                _run_burnplan(root, "1", ["onboard", "--provider", "static", "--no-interview"]),
                0,
            )
            for seed in ["2", "31337"]:
                self.assertEqual(
                    _run_burnplan(root, seed, ["optimize", "--provider", "static", "--dry-run"]),
                    0,
                    f"artifacts changed under PYTHONHASHSEED={seed}",
                )

    def test_promote_refuses_hooks_merge_into_invalid_settings_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / "README.md").write_text("# Demo\n\nDemo repo.", encoding="utf-8")
            (root / ".claude").mkdir()
            broken = "{not valid json"
            (root / ".claude" / "settings.json").write_text(broken, encoding="utf-8")

            self.assertEqual(main(["onboard", "--repo", str(root), "--provider", "static", "--no-interview"]), 0)

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.assertEqual(main(["promote", "agents", "--repo", str(root)]), 2)
            self.assertIn("manually", stderr.getvalue())
            self.assertEqual((root / ".claude" / "settings.json").read_text(encoding="utf-8"), broken)

    def test_promote_warns_when_target_is_gitignored(self):
        # A promoted file that git will ignore vanishes from the next
        # directory-level add with no signal; promote should say so.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / "README.md").write_text("# Demo\n\nDemo repo.", encoding="utf-8")
            (root / ".gitignore").write_text("docs/design.md\n", encoding="utf-8")

            self.assertEqual(main(["onboard", "--repo", str(root), "--provider", "static", "--no-interview"]), 0)

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.assertEqual(main(["promote", "docs", "--repo", str(root)]), 0)

            self.assertTrue((root / "docs" / "design.md").exists())
            warning = stderr.getvalue()
            self.assertIn("gitignored", warning)
            self.assertIn("design.md", warning)
            self.assertNotIn("architecture.md", warning)

    def test_promote_creates_agents_md_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / "README.md").write_text("# Demo\n\nDemo repo.", encoding="utf-8")

            self.assertEqual(main(["onboard", "--repo", str(root), "--provider", "static", "--no-interview"]), 0)
            self.assertEqual(main(["promote", "agents", "--repo", str(root)]), 0)

            agents_md = (root / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("<!-- burnplan:begin -->", agents_md)
            self.assertIn(".burnplan/agent-prompts.md", agents_md)
            self.assertIn("distilled summary", agents_md)

    def test_promote_updates_agents_md_block_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / "README.md").write_text("# Demo\n\nDemo repo.", encoding="utf-8")
            user_content = "# My Codex Instructions\n\nHand-written rules stay.\n"
            stale_block = "<!-- burnplan:begin -->\nOLD BLOCK CONTENT\n<!-- burnplan:end -->\n"
            (root / "AGENTS.md").write_text(user_content + "\n" + stale_block + "\n# Trailing section\n", encoding="utf-8")

            self.assertEqual(main(["onboard", "--repo", str(root), "--provider", "static", "--no-interview"]), 0)
            self.assertEqual(main(["promote", "agents", "--repo", str(root)]), 0)

            agents_md = (root / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("Hand-written rules stay.", agents_md)
            self.assertIn("# Trailing section", agents_md)
            self.assertNotIn("OLD BLOCK CONTENT", agents_md)
            self.assertIn(".burnplan/agent-prompts.md", agents_md)
            self.assertEqual(agents_md.count("<!-- burnplan:begin -->"), 1)

            before = agents_md
            self.assertEqual(main(["promote", "agents", "--repo", str(root), "--force"]), 0)
            self.assertEqual((root / "AGENTS.md").read_text(encoding="utf-8"), before)

    def test_generic_spec_uses_goal_context_constraints(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / "README.md").write_text("# Demo\n\nDemo repo.", encoding="utf-8")

            self.assertEqual(main(["onboard", "--repo", str(root), "--provider", "static", "--no-interview"]), 0)

            spec = (root / ".burnplan" / "proposals" / "agents" / "generic" / "project-manager-implementer.md").read_text(encoding="utf-8")
            for section in ["## Goal", "## Context", "## Constraints"]:
                self.assertIn(section, spec)
            self.assertIn("Return a distilled summary", spec)
            self.assertNotIn("## Description", spec)

    def test_hook_stop_reminds_on_undocumented_dirty_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / "README.md").write_text("# Demo\n\nDemo repo.", encoding="utf-8")
            _commit(root, "initial")

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(main(["hook", "stop", "--repo", str(root)]), 0)
            self.assertEqual(stdout.getvalue(), "")

            (root / "extra.py").write_text("print('dirty')\n", encoding="utf-8")
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(main(["hook", "stop", "--repo", str(root)]), 0)
            self.assertIn("undocumented changes", stdout.getvalue())

            self.assertEqual(
                main(
                    [
                        "document",
                        "--repo",
                        str(root),
                        "--what",
                        "Added extra module",
                        "--why",
                        "Demonstrates the documented path.",
                        "--area",
                        "core",
                    ]
                ),
                0,
            )
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(main(["hook", "stop", "--repo", str(root)]), 0)
            self.assertEqual(stdout.getvalue(), "")


def _init_repo(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _run_burnplan(root: Path, hash_seed: str, args: list) -> int:
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = hash_seed
    env["PYTHONPATH"] = os.pathsep.join([str(BURNPLAN_ROOT), str(SKYHOOK_ROOT)])
    result = subprocess.run(
        [sys.executable, "-m", "burnplan", *args, "--repo", str(root)],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )
    return result.returncode


def _commit(root: Path, message: str) -> None:
    subprocess.run(["git", "add", "."], cwd=root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=BurnPlan Tests",
            "-c",
            "user.email=burnplan@example.com",
            "commit",
            "-m",
            message,
        ],
        cwd=root,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


if __name__ == "__main__":
    unittest.main()
