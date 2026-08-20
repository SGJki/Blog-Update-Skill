#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = ["pyyaml>=6.0"]
# ///
"""Validate Fuwari frontmatter for a complete blog-update V10 draft.

Default mode is report-only. Use --fix to write deterministic, safe fixes.

Exit codes:
  0 = no blocking failures
  1 = one or more blocking failures
  2 = invocation or parse error
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - depends on environment
    yaml = None


REQUIRED_FIELDS = ["title", "published", "description", "tags", "category", "draft"]
CANONICAL_FIELDS = ["title", "published", "description", "tags", "category", "draft"]


def split_frontmatter(text: str) -> tuple[str, str]:
    match = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.DOTALL)
    if not match:
        return "", text
    return match.group(1), match.group(2)


def parse_scalar(value: str):
    value = value.strip()
    if not value:
        return ""
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def parse_frontmatter(fm_str: str) -> dict:
    if yaml is not None:
        data = yaml.safe_load(fm_str)
        if not isinstance(data, dict):
            raise ValueError(f"frontmatter parsed as {type(data).__name__}, expected mapping")
        return data

    data = {}
    for raw_line in fm_str.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise ValueError("PyYAML is unavailable and fallback parser only supports simple key: value frontmatter")
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            data[key] = [] if not inner else [parse_scalar(part.strip()) for part in inner.split(",")]
        else:
            data[key] = parse_scalar(value)
    return data


def find_h1(body: str) -> str | None:
    in_code = False
    for line in body.splitlines():
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        match = re.match(r"^#\s+(.+?)\s*$", line)
        if match:
            return match.group(1)
    return None


def first_paragraph(body: str) -> str:
    in_code = False
    collected: list[str] = []
    for line in body.splitlines():
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        stripped = line.strip()
        if not stripped:
            if collected:
                break
            continue
        if stripped.startswith("#") or stripped.startswith("|"):
            continue
        if re.fullmatch(r"[-*_]{3,}", stripped):
            continue
        collected.append(stripped)
    return " ".join(collected)


def valid_date(value) -> bool:
    if isinstance(value, dt.date):
        return True
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        dt.datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def truncate(text: str, limit: int = 150) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 3]
    space = cut.rfind(" ")
    if space >= 30:
        cut = cut[:space]
    return cut + "..."


def scalar_for_yaml(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dt.date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def serialize(fm: dict) -> str:
    ordered = {key: fm[key] for key in CANONICAL_FIELDS if key in fm}
    for key, value in fm.items():
        if key not in ordered:
            ordered[key] = value

    lines = ["---"]
    for key, value in ordered.items():
        if isinstance(value, list):
            lines.append(f"{key}: [{', '.join(scalar_for_yaml(item) for item in value)}]")
        else:
            lines.append(f"{key}: {scalar_for_yaml(value)}")
    lines.append("---")
    return "\n".join(lines)


def analyze(fm: dict, body: str) -> tuple[list[str], list[str], dict]:
    blocking: list[str] = []
    advisory: list[str] = []
    fixes: dict = {}

    missing = [field for field in REQUIRED_FIELDS if field not in fm]
    if missing:
        blocking.append(f"missing required field(s): {', '.join(missing)}")

    title = fm.get("title")
    h1 = find_h1(body)
    if not h1:
        blocking.append("missing first-level H1 in body")
    elif title is not None and str(title) != h1:
        blocking.append(f"title/H1 mismatch: title={title!r}, h1={h1!r}")

    if "published" in fm and not valid_date(fm.get("published")):
        blocking.append(f"published must be a real YYYY-MM-DD date, got {fm.get('published')!r}")
        fixes["published"] = dt.date.today().strftime("%Y-%m-%d")

    if "description" in fm:
        original_desc = fm.get("description")
        desc = str(original_desc or "").strip()
        if not desc:
            blocking.append("description must not be empty")
            para = first_paragraph(body)
            if len(para) >= 30:
                fixes["description"] = truncate(para)
        elif len(desc) < 30:
            advisory.append(f"description is short ({len(desc)} chars; recommended 30-150)")
        elif len(desc) > 150:
            advisory.append(f"description is long ({len(desc)} chars; recommended 30-150)")
            fixes["description"] = truncate(desc)
        elif desc != original_desc:
            fixes["description"] = desc

    tags = fm.get("tags")
    if "tags" in fm:
        if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
            blocking.append("tags must be a YAML list of strings")
            if isinstance(tags, list):
                fixes["tags"] = [str(tag) for tag in tags]
            elif tags is not None:
                fixes["tags"] = [str(tags)]
        else:
            seen = set()
            deduped = []
            for tag in tags:
                key = tag.lower()
                if key not in seen:
                    seen.add(key)
                    deduped.append(tag)
            if deduped != tags:
                advisory.append("duplicate tags found; --fix can dedupe them")
                fixes["tags"] = deduped
            if not 2 <= len(tags) <= 5:
                advisory.append(f"tags count is {len(tags)}; recommended 2-5")

    category = fm.get("category")
    if isinstance(category, list):
        blocking.append("category must be a scalar, not a list")
        fixes["category"] = category[0] if category else ""

    draft = fm.get("draft")
    if "draft" in fm and not isinstance(draft, bool):
        blocking.append(f"draft must be boolean true/false, got {draft!r}")

    return blocking, advisory, fixes


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Fuwari blog frontmatter.")
    parser.add_argument("file", help="Path to Markdown draft")
    parser.add_argument("--fix", action="store_true", help="Apply deterministic fixes in-place")
    parser.add_argument("--dry-run", action="store_true", help="Alias for default report-only mode")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.is_file():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 2

    text = path.read_text(encoding="utf-8")
    fm_str, body = split_frontmatter(text)
    if not fm_str:
        print("Frontmatter Validation: FAIL")
        print("  [BLOCKING] file has no frontmatter")
        return 1

    try:
        fm = parse_frontmatter(fm_str)
    except Exception as exc:
        print("Frontmatter Validation: ERROR")
        print(f"  {exc}")
        return 2

    blocking, advisory, fixes = analyze(fm, body)

    if fixes and args.fix:
        fm.update(fixes)
        new_text = serialize(fm) + "\n\n" + body.lstrip("\n")
        path.write_text(new_text, encoding="utf-8")
        blocking, advisory, fixes = analyze(fm, body)

    if blocking:
        print("Frontmatter Validation: FAIL")
        for issue in blocking:
            print(f"  [BLOCKING] {issue}")
    else:
        print("Frontmatter Validation: PASS")

    for issue in advisory:
        print(f"  [ADVISORY] {issue}")

    if fixes and not args.fix:
        print("  [ADVISORY] deterministic fixes available; rerun with --fix to write them")
        for key in sorted(fixes):
            print(f"    - {key}")
    elif args.fix:
        print("  fixes applied" if fixes else "  no fixes needed")

    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
