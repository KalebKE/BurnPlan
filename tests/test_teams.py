import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Skyhook"))

from burnplan.artifacts import canonical_json
from burnplan.teams import DEFAULT_TEAMS


class TeamsTests(unittest.TestCase):
    def test_examples_teams_json_matches_default_teams(self):
        example = Path(__file__).resolve().parents[1] / "examples" / "teams.json"
        self.assertEqual(example.read_text(encoding="utf-8"), canonical_json(DEFAULT_TEAMS))

    def test_default_teams_effort_hints(self):
        subagents = {
            name: subagent
            for team in DEFAULT_TEAMS["teams"].values()
            for name, subagent in team["subagents"].items()
        }
        planning = ["story-writer", "requirements-analyst", "acceptance-criteria-reviewer", "technical-planner"]
        for name in planning:
            self.assertEqual(subagents[name]["effort"], "high", name)
        for name in ["implementer", "reviewer", "bug-hunter"]:
            self.assertEqual(subagents[name]["effort"], "medium", name)

    def test_default_instructions_carry_no_verification_ceremony(self):
        # Claude 5-generation models verify their own work; explicit verification
        # instructions cause over-verification and wasted tokens.
        for team in DEFAULT_TEAMS["teams"].values():
            for name, subagent in team["subagents"].items():
                for instruction in subagent["instructions"]:
                    lowered = instruction.lower()
                    self.assertNotIn("verify the", lowered, f"{name}: {instruction}")
                    self.assertNotIn("double-check", lowered, f"{name}: {instruction}")

    def test_default_teams_tools_allowlists(self):
        subagents = {
            name: subagent
            for team in DEFAULT_TEAMS["teams"].values()
            for name, subagent in team["subagents"].items()
        }
        read_only = [
            "story-writer",
            "requirements-analyst",
            "acceptance-criteria-reviewer",
            "technical-planner",
            "reviewer",
        ]
        for name in read_only:
            tools = subagents[name]["tools"]
            self.assertNotIn("Edit", tools, name)
            self.assertNotIn("Write", tools, name)
            self.assertIn("Read", tools, name)
        for name in ["implementer", "bug-hunter"]:
            tools = subagents[name]["tools"]
            self.assertIn("Edit", tools, name)
            self.assertIn("Write", tools, name)


if __name__ == "__main__":
    unittest.main()
