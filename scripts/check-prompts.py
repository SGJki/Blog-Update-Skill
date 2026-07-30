#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def require(text: str, needle: str, rel: str) -> None:
    if needle not in text:
        raise SystemExit(f"FAIL {rel}: missing required text: {needle!r}")


def forbid(text: str, needle: str, rel: str) -> None:
    if needle in text:
        raise SystemExit(f"FAIL {rel}: forbidden stale text remains: {needle!r}")


def main() -> int:
    skill = read("skill.md")
    implement = read("prompts/implement-agent.md")
    merge = read("prompts/merge-agent.md")
    review = read("prompts/review-agent.md")
    readme = read("README.md")

    require(skill, "Evidence Ledger", "skill.md")
    require(skill, "Fast path (default)", "skill.md")
    require(skill, "Subagents are tools, not mandatory ceremony", "skill.md")

    require(implement, "Evidence-First Extraction", "prompts/implement-agent.md")
    require(implement, "Failure evidence override", "prompts/implement-agent.md")
    require(implement, "you may not replace", "prompts/implement-agent.md")
    forbid(implement, "Signal Threshold (mandatory filter)", "prompts/implement-agent.md")
    forbid(implement, '"Permission denied", "Operation not permitted"', "prompts/implement-agent.md")

    require(merge, "More evidential", "prompts/merge-agent.md")
    require(merge, "Do not replace concrete evidence", "prompts/merge-agent.md")

    require(review, "Evidence Retention", "prompts/review-agent.md")
    require(review, "10 dimensions", "prompts/review-agent.md")
    require(review, "Article could apply to any project", "prompts/review-agent.md")

    require(readme, "Evidence-first workflow", "README.md")
    require(readme, "V9", "README.md")

    print("Prompt checks: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
