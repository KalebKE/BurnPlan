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
