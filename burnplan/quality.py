from __future__ import annotations

import subprocess
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Optional

from skyhook.scanner import RepoScan


COMMIT_MARKER = "__BURNPLAN_COMMIT__"


def analyze_quality(repo_root: Path, scan: RepoScan, since_days: int = 90, max_commits: int = 1000) -> Dict[str, Any]:
    commits = _read_git_log(repo_root, since_days, max_commits)
    static_analysis = discover_static_analysis(repo_root, scan)
    source = {
        "type": "git",
        "available": commits is not None,
        "sinceDays": since_days,
        "maxCommits": max_commits,
        "commitsAnalyzed": 0,
    }
    if commits is None:
        source["message"] = "Git history was not available, so quality analysis is limited."
        return {
            "source": source,
            "hotspots": [],
            "couplings": [],
            "volatileAreas": [],
            "staticAnalysis": static_analysis,
            "weakPoints": ["Git history was unavailable; run inside a git checkout for churn and coupling analysis."],
        }

    current_paths = {record.path for record in scan.files}
    file_meta = {record.path: record for record in scan.files}
    revisions: Counter[str] = Counter()
    area_revisions: Counter[str] = Counter()
    cochanges: Counter[tuple[str, str]] = Counter()
    last_touched: Dict[str, str] = {}
    authors: dict[str, set[str]] = defaultdict(set)
    analyzed = 0

    for commit in commits:
        files = sorted(
            {
                path
                for path in commit["files"]
                if path in current_paths and not path.startswith((".burnplan/", ".skyhook/"))
            }
        )
        if not files:
            continue
        analyzed += 1
        for path in files:
            revisions[path] += 1
            area_revisions[_area_for(path)] += 1
            authors[path].add(commit["author"])
            if path not in last_touched:
                last_touched[path] = commit["date"]
        for left, right in combinations(files[:80], 2):
            cochanges[(left, right)] += 1

    source["commitsAnalyzed"] = analyzed
    hotspots = []
    for path, count in revisions.most_common(30):
        record = file_meta.get(path)
        hotspots.append(
            {
                "path": path,
                "revisions": count,
                "lastTouched": last_touched.get(path, ""),
                "authors": sorted(authors.get(path, set()))[:8],
                "kind": record.kind if record else "",
                "language": record.language if record else "",
            }
        )

    couplings = [
        {"paths": [left, right], "changes": count}
        for (left, right), count in sorted(cochanges.items(), key=lambda item: (-item[1], item[0][0], item[0][1]))[:30]
        if count >= 2
    ]
    volatile_areas = [
        {"area": area, "revisions": count}
        for area, count in sorted(area_revisions.items(), key=lambda item: (-item[1], item[0]))[:15]
    ]
    weak_points = _weak_points(hotspots, couplings, volatile_areas, scan)
    return {
        "source": source,
        "hotspots": hotspots,
        "couplings": couplings,
        "volatileAreas": volatile_areas,
        "staticAnalysis": static_analysis,
        "weakPoints": weak_points,
    }


def discover_static_analysis(repo_root: Path, scan: RepoScan) -> Dict[str, Any]:
    paths = {record.path for record in scan.files}
    tools: List[Dict[str, str]] = []

    if any(path.endswith("build.gradle") or path.endswith("build.gradle.kts") for path in paths):
        tools.append({"name": "Gradle", "marker": "build.gradle(.kts)"})
    if any(path.endswith(".kt") or path.endswith(".kts") for path in paths):
        tools.append({"name": "Kotlin compiler", "marker": "*.kt"})
    if any(path.endswith("src/main/AndroidManifest.xml") or path == "AndroidManifest.xml" for path in paths):
        tools.append({"name": "Android Lint", "marker": "AndroidManifest.xml"})

    for tool, marker in [
        ("Ruff", "ruff.toml"),
        ("Ruff", ".ruff.toml"),
        ("mypy", "mypy.ini"),
        ("mypy", ".mypy.ini"),
        ("Pyright", "pyrightconfig.json"),
        ("ESLint", "eslint.config.js"),
        ("ESLint", ".eslintrc.json"),
        ("ESLint", ".eslintrc.yml"),
        ("Prettier", ".prettierrc"),
        ("Detekt", "detekt.yml"),
        ("EditorConfig", ".editorconfig"),
        ("SwiftLint", ".swiftlint.yml"),
        ("golangci-lint", ".golangci.yml"),
        ("clj-kondo", ".clj-kondo/config.edn"),
    ]:
        if marker in paths:
            tools.append({"name": tool, "marker": marker})

    pyproject = repo_root / "pyproject.toml"
    if "pyproject.toml" in paths and pyproject.exists():
        text = _read_small(pyproject)
        if "[tool.ruff" in text:
            tools.append({"name": "Ruff", "marker": "pyproject.toml"})
        if "[tool.mypy" in text:
            tools.append({"name": "mypy", "marker": "pyproject.toml"})
        if "[tool.pytest" in text:
            tools.append({"name": "pytest", "marker": "pyproject.toml"})

    package_json = repo_root / "package.json"
    if "package.json" in paths and package_json.exists():
        text = _read_small(package_json)
        if "eslint" in text:
            tools.append({"name": "ESLint", "marker": "package.json"})
        if "prettier" in text:
            tools.append({"name": "Prettier", "marker": "package.json"})
        if "tsc" in text or "typescript" in text:
            tools.append({"name": "TypeScript", "marker": "package.json"})

    gradle_versions = repo_root / "gradle" / "libs.versions.toml"
    if "gradle/libs.versions.toml" in paths and gradle_versions.exists():
        text = _read_small(gradle_versions).lower()
        if "detekt" in text:
            tools.append({"name": "Detekt", "marker": "gradle/libs.versions.toml"})
        if "ktlint" in text:
            tools.append({"name": "ktlint", "marker": "gradle/libs.versions.toml"})
        if "android-application" in text or "android-library" in text or "com.android" in text:
            tools.append({"name": "Android Lint", "marker": "gradle/libs.versions.toml"})

    root_gradle = repo_root / "build.gradle.kts"
    if "build.gradle.kts" in paths and root_gradle.exists():
        text = _read_small(root_gradle).lower()
        if "detekt" in text:
            tools.append({"name": "Detekt", "marker": "build.gradle.kts"})
        if "ktlint" in text:
            tools.append({"name": "ktlint", "marker": "build.gradle.kts"})
        if "com.android" in text or "android" in text:
            tools.append({"name": "Android Lint", "marker": "build.gradle.kts"})

    unique = []
    seen = set()
    for tool in tools:
        if tool["name"] in seen:
            continue
        seen.add(tool["name"])
        unique.append(tool)
    return {
        "tools": unique,
        "message": "Static analysis tools are discovered but not executed by BurnPlan.",
    }


def _read_git_log(repo_root: Path, since_days: int, max_commits: int) -> Optional[List[Dict[str, Any]]]:
    try:
        result = subprocess.run(
            [
                "git",
                "log",
                f"--since={since_days}.days.ago",
                f"-n{max_commits}",
                "--name-only",
                f"--format={COMMIT_MARKER}%x09%H%x09%aI%x09%an",
            ],
            cwd=str(repo_root),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None

    commits: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(COMMIT_MARKER):
            if current is not None:
                commits.append(current)
            parts = line.split("\t", 3)
            current = {
                "sha": parts[1] if len(parts) > 1 else "",
                "date": parts[2] if len(parts) > 2 else "",
                "author": parts[3] if len(parts) > 3 else "",
                "files": [],
            }
            continue
        if current is not None:
            current["files"].append(line)
    if current is not None:
        commits.append(current)
    return commits


def _read_small(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:20000]
    except OSError:
        return ""


def _area_for(path: str) -> str:
    return path.split("/", 1)[0] if "/" in path else "."


def _weak_points(
    hotspots: List[Dict[str, Any]],
    couplings: List[Dict[str, Any]],
    volatile_areas: List[Dict[str, Any]],
    scan: RepoScan,
) -> List[str]:
    weak_points: List[str] = []
    if hotspots:
        top = hotspots[0]
        weak_points.append(f"{top['path']} has the highest recent churn with {top['revisions']} revisions.")
    if couplings:
        top = couplings[0]
        weak_points.append(
            f"{top['paths'][0]} and {top['paths'][1]} changed together {top['changes']} times; review the boundary or shared documentation."
        )
    if volatile_areas:
        top_area = volatile_areas[0]
        weak_points.append(f"{top_area['area']} is the most volatile area with {top_area['revisions']} recent revisions.")
    doc_kinds = {doc.doc_kind for doc in scan.docs}
    if "adr" not in doc_kinds:
        weak_points.append("No ADRs were detected; architectural decisions may be hard for agents to recover later.")
    if not ({"architecture", "c4", "design"} & doc_kinds):
        weak_points.append("No architecture or design overview was detected; add one before large cross-cutting changes.")
    if not weak_points:
        weak_points.append("No significant churn or documentation weak point was detected in the configured history window.")
    return weak_points[:8]
