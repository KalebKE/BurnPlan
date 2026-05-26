import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Skyhook"))

from burnplan.quality import analyze_quality
from skyhook.config import default_config as default_skyhook_config
from skyhook.scanner import scan_repo


class QualityTests(unittest.TestCase):
    def test_analyzes_git_churn_and_coupling(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init"], cwd=root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            (root / "src").mkdir()
            (root / "src" / "a.py").write_text("a = 1\n", encoding="utf-8")
            (root / "src" / "b.py").write_text("b = 1\n", encoding="utf-8")
            (root / "pyproject.toml").write_text("[tool.ruff]\nline-length = 120\n", encoding="utf-8")
            (root / "build.gradle.kts").write_text("plugins { id(\"com.android.application\") }\n", encoding="utf-8")
            _commit(root, "initial")

            (root / "src" / "a.py").write_text("a = 2\n", encoding="utf-8")
            (root / "src" / "b.py").write_text("b = 2\n", encoding="utf-8")
            _commit(root, "change both")

            (root / "src" / "a.py").write_text("a = 3\n", encoding="utf-8")
            (root / "src" / "b.py").write_text("b = 3\n", encoding="utf-8")
            _commit(root, "change both again")

            scan = scan_repo(root, default_skyhook_config())
            quality = analyze_quality(root, scan, since_days=365, max_commits=50)

            self.assertTrue(quality["source"]["available"])
            self.assertGreaterEqual(quality["source"]["commitsAnalyzed"], 3)
            self.assertEqual(quality["hotspots"][0]["path"], "src/a.py")
            self.assertTrue(any(item["paths"] == ["src/a.py", "src/b.py"] for item in quality["couplings"]))
            self.assertTrue(any(item["name"] == "Ruff" for item in quality["staticAnalysis"]["tools"]))
            self.assertTrue(any(item["name"] == "Gradle" for item in quality["staticAnalysis"]["tools"]))
            self.assertTrue(any(item["name"] == "Android Lint" for item in quality["staticAnalysis"]["tools"]))


def _commit(root: Path, message: str) -> None:
    subprocess.run(["git", "add", "."], cwd=root, check=True, stdout=subprocess.DEVNULL)
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
    )


if __name__ == "__main__":
    unittest.main()
