from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class QualityConfig:
    since_days: int = 90
    max_commits: int = 1000


@dataclass
class GuidanceConfig:
    max_lines: int = 120


@dataclass
class BurnPlanConfig:
    version: int = 1
    output_dir: str = ".burnplan"
    map_dir: str = ".skyhook"
    quality: QualityConfig = field(default_factory=QualityConfig)
    guidance: GuidanceConfig = field(default_factory=GuidanceConfig)


def default_config() -> BurnPlanConfig:
    return BurnPlanConfig()


def load_config(repo_root: Path, config_path: Optional[str] = None) -> BurnPlanConfig:
    path = Path(config_path) if config_path else repo_root / ".burnplan" / "config.yaml"
    if not path.exists():
        return default_config()
    raw = path.read_text(encoding="utf-8")
    data = _parse_minimal_yaml(raw)
    cfg = default_config()
    if "version" in data:
        cfg.version = int(data["version"])
    if "outputDir" in data:
        cfg.output_dir = str(data["outputDir"])
    if "output_dir" in data:
        cfg.output_dir = str(data["output_dir"])
    if "mapDir" in data:
        cfg.map_dir = str(data["mapDir"])
    if "map_dir" in data:
        cfg.map_dir = str(data["map_dir"])
    quality = data.get("quality", {})
    if isinstance(quality, dict):
        cfg.quality.since_days = int(quality.get("sinceDays", quality.get("since_days", cfg.quality.since_days)))
        cfg.quality.max_commits = int(quality.get("maxCommits", quality.get("max_commits", cfg.quality.max_commits)))
    guidance = data.get("guidance", {})
    if isinstance(guidance, dict):
        cfg.guidance.max_lines = int(guidance.get("maxLines", guidance.get("max_lines", cfg.guidance.max_lines)))
    return cfg


def _parse_minimal_yaml(raw: str) -> Dict[str, Any]:
    """Parse the small YAML subset used by .burnplan/config.yaml."""
    root: Dict[str, Any] = {}
    stack: List[tuple[int, Dict[str, Any]]] = [(-1, root)]
    last_key_at_indent: Dict[int, str] = {}

    for original in raw.splitlines():
        line = original.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        text = line.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        current = stack[-1][1]

        if text.startswith("- "):
            key = last_key_at_indent.get(indent - 2)
            if key is None:
                continue
            parent = stack[-2][1] if len(stack) >= 2 and stack[-1][0] == indent - 2 else stack[-1][1]
            if not isinstance(parent.get(key), list):
                parent[key] = []
            parent[key].append(_parse_scalar(text[2:].strip()))
            continue

        if ":" not in text:
            continue
        key, value = text.split(":", 1)
        key = key.strip()
        value = value.strip()
        last_key_at_indent[indent] = key
        if value == "":
            child: Dict[str, Any] = {}
            current[key] = child
            stack.append((indent, child))
        elif value == "[]":
            current[key] = []
        else:
            current[key] = _parse_scalar(value)
    return root


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    lower = value.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    if lower == "null":
        return None
    try:
        return int(value)
    except ValueError:
        return value
