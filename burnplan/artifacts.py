from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .render import (
    render_agent_prompts_markdown,
    render_documentation_ledger_markdown,
    render_onboarding_markdown,
    render_quality_markdown,
)


def output_dir(repo_root: Path, configured: str, override: Optional[str] = None) -> Path:
    raw = override or configured
    path = Path(raw)
    if not path.is_absolute():
        path = repo_root / path
    return path


def write_ratchet_outputs(
    out_dir: Path,
    onboarding: Mapping[str, Any],
    quality: Mapping[str, Any],
    guidance: Mapping[str, Any],
    ledger: Mapping[str, Any],
    rules: Mapping[str, Any],
    doc_synthesis: Mapping[str, Any],
) -> None:
    for path, content in ratchet_output_contents(out_dir, onboarding, quality, guidance, ledger, rules, doc_synthesis).items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def ratchet_outputs_would_change(
    out_dir: Path,
    onboarding: Mapping[str, Any],
    quality: Mapping[str, Any],
    guidance: Mapping[str, Any],
    ledger: Mapping[str, Any],
    rules: Mapping[str, Any],
    doc_synthesis: Mapping[str, Any],
) -> bool:
    return any(
        _path_would_change(path, content)
        for path, content in ratchet_output_contents(out_dir, onboarding, quality, guidance, ledger, rules, doc_synthesis).items()
    )


def ratchet_output_contents(
    out_dir: Path,
    onboarding: Mapping[str, Any],
    quality: Mapping[str, Any],
    guidance: Mapping[str, Any],
    ledger: Mapping[str, Any],
    rules: Mapping[str, Any],
    doc_synthesis: Mapping[str, Any],
) -> Dict[Path, str]:
    return {
        out_dir / "onboarding.json": canonical_json(onboarding),
        out_dir / "onboarding.md": render_onboarding_markdown(onboarding),
        out_dir / "quality.json": canonical_json(quality),
        out_dir / "quality.md": render_quality_markdown(quality),
        out_dir / "agent-prompts.json": canonical_json(guidance),
        out_dir / "agent-prompts.md": render_agent_prompts_markdown(guidance),
        out_dir / "documentation-ledger.json": canonical_json(ledger),
        out_dir / "documentation-ledger.md": render_documentation_ledger_markdown(ledger),
        out_dir / "agent-rules.json": canonical_json(rules),
        out_dir / "doc-synthesis.json": canonical_json(doc_synthesis),
    }


def guidance_size_report(
    contents: Mapping[Path, str],
    out_dir: Path,
    max_lines: int,
) -> Dict[str, Any]:
    guidance_md = contents.get(out_dir / "agent-prompts.md", "")
    lines = guidance_md.count("\n") + (1 if guidance_md and not guidance_md.endswith("\n") else 0)
    return {
        "lines": lines,
        "budgetLines": max_lines,
        "overBudget": lines > max_lines,
    }


def load_json_artifact(out_dir: Path, name: str) -> Optional[Dict[str, Any]]:
    path = out_dir / name
    if not path.exists():
        return None
    return read_json(path)


def canonical_json(data: Mapping[str, Any]) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _path_would_change(path: Path, content: str) -> bool:
    if not path.exists():
        return True
    return path.read_text(encoding="utf-8") != content
