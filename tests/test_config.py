import tempfile
import unittest
from pathlib import Path

from burnplan.config import load_config


class ConfigTests(unittest.TestCase):
    def test_loads_minimal_yaml_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_dir = root / ".burnplan"
            config_dir.mkdir()
            (config_dir / "config.yaml").write_text(
                """
version: 1
outputDir: out
mapDir: maps
quality:
  sinceDays: 30
  maxCommits: 250
""",
                encoding="utf-8",
            )

            cfg = load_config(root)

            self.assertEqual(cfg.output_dir, "out")
            self.assertEqual(cfg.map_dir, "maps")
            self.assertEqual(cfg.quality.since_days, 30)
            self.assertEqual(cfg.quality.max_commits, 250)
            self.assertEqual(cfg.guidance.max_lines, 120)

    def test_guidance_budget_parsed_from_yaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_dir = root / ".burnplan"
            config_dir.mkdir()
            (config_dir / "config.yaml").write_text(
                """
version: 1
guidance:
  maxLines: 40
""",
                encoding="utf-8",
            )

            cfg = load_config(root)

            self.assertEqual(cfg.guidance.max_lines, 40)


if __name__ == "__main__":
    unittest.main()
