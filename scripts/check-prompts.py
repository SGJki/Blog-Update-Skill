#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, text=True, capture_output=True)


def assert_ok(name: str, result: subprocess.CompletedProcess[str]) -> None:
    if result.returncode != 0:
        raise AssertionError(f"{name} expected PASS, got {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")


def assert_fail(name: str, result: subprocess.CompletedProcess[str]) -> None:
    if result.returncode == 0:
        raise AssertionError(f"{name} expected FAIL, got PASS\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")


def write_fixture(tmpdir: Path, name: str, text: str) -> Path:
    path = tmpdir / name
    path.write_text(text, encoding="utf-8")
    return path


def valid_post(title: str = "V10 Draft") -> str:
    return f"""---
title: \"{title}\"
published: 2026-08-20
description: \"A concrete description long enough for the Fuwari article metadata.\"
tags: [\"AI\", \"Tools\"]
category: DevOps
draft: true
---

# {title}

This draft keeps concrete implementation detail while staying safe for publication review.
"""


def check_skill_contract() -> None:
    skill = read("skill.md")
    skill_upper = read("SKILL.md")
    readme = read("README.md")

    required = [
        "Blog Update V10",
        "New articles are first written as staging drafts with `draft: true`",
        "Existing articles are changed only after showing a unified diff",
        "`uv` is optional",
        "Subagents are optional tools, not the default workflow",
        "scan-sensitive-content.py",
        "report-only by default",
    ]
    for needle in required:
        if needle not in skill:
            raise AssertionError(f"skill.md missing {needle!r}")

    stale = [
        "STOP and ask the user to install uv",
        "All content must go through review-agent",
        "draft: false\n---",
        "Step 6.5: Body Validation Pass (scripted via uv)",
    ]
    for needle in stale:
        if needle in skill:
            raise AssertionError(f"skill.md still contains stale V9 text {needle!r}")

    if skill != skill_upper:
        raise AssertionError("SKILL.md content is not synced with skill.md")
    if "V10" not in readme or "Sensitive Content Scan" not in readme:
        raise AssertionError("README.md does not describe V10 validators")


def check_fixtures() -> None:
    with tempfile.TemporaryDirectory(prefix="blog-update-v10-") as raw_tmp:
        tmpdir = Path(raw_tmp)

        good = write_fixture(tmpdir, "good.md", valid_post())
        before = good.read_text(encoding="utf-8")
        assert_ok("frontmatter draft true report-only", run([sys.executable, "scripts/validate-frontmatter.py", str(good)]))
        after = good.read_text(encoding="utf-8")
        if before != after:
            raise AssertionError("validate-frontmatter.py wrote changes without --fix")
        assert_ok("markdown complete draft", run([sys.executable, "scripts/validate-post.py", str(good)]))
        assert_ok("sensitive scan clean", run([sys.executable, "scripts/scan-sensitive-content.py", str(good)]))

        long_desc = write_fixture(tmpdir, "long-desc.md", valid_post().replace(
            "A concrete description long enough for the Fuwari article metadata.",
            "This description is intentionally far too long for the recommended Fuwari frontmatter description field because it keeps talking well beyond the normal summary length and should be shortened by the deterministic fixer when explicitly requested.",
        ))
        assert_ok("frontmatter long desc advisory", run([sys.executable, "scripts/validate-frontmatter.py", str(long_desc)]))
        if "intentionally far too long" not in long_desc.read_text(encoding="utf-8"):
            raise AssertionError("report-only frontmatter validation changed long description")
        assert_ok("frontmatter --fix", run([sys.executable, "scripts/validate-frontmatter.py", str(long_desc), "--fix"]))
        fixed_long_desc = long_desc.read_text(encoding="utf-8")
        desc_line = next(line for line in fixed_long_desc.splitlines() if line.startswith("description:"))
        fixed_desc = desc_line.split(":", 1)[1].strip().strip('"')
        if len(fixed_desc) > 150:
            raise AssertionError("--fix did not shorten long description")
        if "draft: true" not in fixed_long_desc:
            raise AssertionError("--fix changed draft true")

        unclosed = write_fixture(tmpdir, "unclosed.md", valid_post() + "\n```python\nprint('x')\n")
        assert_fail("unclosed fence", run([sys.executable, "scripts/validate-post.py", str(unclosed)]))

        missing_link = write_fixture(tmpdir, "missing-link.md", valid_post() + "\nSee [missing](./missing.md).\n")
        assert_fail("missing internal link", run([sys.executable, "scripts/validate-post.py", str(missing_link)]))

        secret = write_fixture(tmpdir, "secret.md", valid_post() + "\nAuthorization: Bearer sk-live-secret-token-value-123456\n")
        assert_fail("secret scan", run([sys.executable, "scripts/scan-sensitive-content.py", str(secret)]))

        private_ip = write_fixture(tmpdir, "private-ip.md", valid_post() + "\nThe service called http://10.0.0.5:8080/debug during the run.\n")
        assert_fail("private ip scan", run([sys.executable, "scripts/scan-sensitive-content.py", str(private_ip)]))

        placeholder = write_fixture(tmpdir, "placeholder.md", valid_post() + "\nUse Authorization: Bearer <token> or YOUR_API_KEY in examples.\n")
        assert_ok("placeholder scan", run([sys.executable, "scripts/scan-sensitive-content.py", str(placeholder)]))


def main() -> int:
    check_skill_contract()
    check_fixtures()
    print("V10 fixture checks: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
