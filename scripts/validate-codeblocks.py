# /// script
# requires-python = ">=3.8"
# dependencies = ["pyyaml>=6.0"]
# ///
"""Code block syntax validation for blog-update skill (Step 6.5).

Checks each fenced code block in body for actual syntax errors using
deterministic parsers. This catches errors that review-agent's mental
lex is unreliable at detecting (unbalanced brackets in long shell
one-liners, Python indentation errors, JSON trailing commas, YAML
indentation drift).

Supported languages (deterministic parsers):
  python             - ast.parse()       [stdlib, always available]
  json               - json.loads()      [stdlib]
  yaml               - yaml.safe_load()  [pyyaml dep, declared in PEP 723]
  bash/sh/shell/zsh  - `bash -n`         [feature-detected; skip if absent]

Languages with no safe pure-Python parser are skipped silently:
  javascript, typescript, go, rust, java, kotlin, swift, c, cpp, etc.

Non-executable languages are skipped silently:
  text, diff, mermaid, markdown, ini, toml

Template placeholder exemption: blocks containing placeholders like
`<your-name>`, `YOUR_API_KEY`, `<<token>>`, or a standalone `...` line
are skipped to avoid false positives on illustrative pseudo-code.

JSON fragment exemption: a JSON block that does not start with `{` or
`[` is treated as a fragment (common in docs) and skipped silently.

Usage:
  uv run scripts/validate-codeblocks.py <post-file>
  uv run scripts/validate-codeblocks.py <post-file> --json

Exit codes:
  0 = no CRITICAL and no MAJOR (MINOR allowed)
  1 = at least one CRITICAL or MAJOR
  2 = ERROR (file missing, etc.)
"""
import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


SEVERITY_ORDER = {"CRITICAL": 0, "MAJOR": 1, "MINOR": 2}

# Map blog-side lang id -> parser key. Only entries here are checked;
# everything else is skipped silently.
PARSABLE_LANGS = {
    "python": "python",
    "json": "json",
    "yaml": "yaml",
    "bash": "bash",
    "sh": "bash",
    "shell": "bash",
    "zsh": "bash",
}

# Template placeholder patterns. If any match, the block is treated as
# illustrative pseudo-code and skipped. Patterns are deliberately
# conservative — `{var}` alone is NOT matched because it collides with
# legitimate Python f-strings and bash brace expansion.
TEMPLATE_PATTERNS = [
    re.compile(r"<[a-z][a-z0-9_-]*-[a-z][a-z0-9_-]*>"),  # <your-name>, <my-key>
    re.compile(r"<[A-Z][A-Z0-9_]*>"),                     # <API_KEY>, <TOKEN>
    re.compile(r"<<[a-z_][a-z0-9_]*>>", re.IGNORECASE),   # <<placeholder>>
    re.compile(r"\bYOUR_[A-Z][A-Z0-9_]*\b"),              # YOUR_API_KEY
    re.compile(r"\bREPLACE_[A-Z][A-Z0-9_]*\b"),           # REPLACE_ME
    re.compile(r"^\s*\.\.\.\s*$", re.MULTILINE),          # standalone ... line
]


def extract_code_blocks(text):
    """Yield (lang, content, start_line) for each fenced code block in body.

    start_line is 1-based and FILE-RELATIVE (counts frontmatter lines).
    Points at the first content line after the opening fence.
    """
    all_lines = text.split("\n")
    # Find frontmatter boundary so line numbers stay file-relative.
    body_start = 0
    if all_lines and all_lines[0].strip() == "---":
        for i in range(1, len(all_lines)):
            if all_lines[i].strip() == "---":
                body_start = i + 1
                break

    in_code = False
    lang = None
    start_line = 0
    content_lines = []

    for i, line in enumerate(all_lines):
        if i < body_start:
            continue
        m = re.match(r"^```(\S*)\s*$", line)
        if m:
            if not in_code:
                in_code = True
                lang = m.group(1).lower() or ""
                # i is 0-based file index; +2 = +1 for 1-based, +1 to skip opening fence
                start_line = i + 2
                content_lines = []
            else:
                yield lang, "\n".join(content_lines), start_line
                in_code = False
                lang = None
                content_lines = []
        elif in_code:
            content_lines.append(line)


def has_template_placeholders(content):
    for pat in TEMPLATE_PATTERNS:
        if pat.search(content):
            return True
    return False


def check_python(content):
    if not content.strip():
        return None
    try:
        ast.parse(content)
        return None
    except SyntaxError as e:
        loc = f"line {e.lineno}" if e.lineno else "unknown line"
        return f"Python syntax error: {e.msg} ({loc})"


def check_json(content):
    stripped = content.strip()
    if not stripped:
        return None
    # JSON fragment exemption — many docs show key:value pairs without
    # surrounding braces. Strict parsing would false-positive on these.
    if not (stripped.startswith("{") or stripped.startswith("[")):
        return None
    try:
        json.loads(stripped)
        return None
    except json.JSONDecodeError as e:
        return f"JSON parse error: {e.msg} (line {e.lineno} col {e.colno})"


def check_yaml(content):
    if not HAS_YAML:
        return None
    if not content.strip():
        return None
    try:
        yaml.safe_load(content)
        return None
    except yaml.YAMLError as e:
        msg = str(e).split("\n")[0]
        return f"YAML parse error: {msg}"


def check_bash(content):
    if not content.strip():
        return None
    bash_bin = shutil.which("bash")
    if not bash_bin:
        return None  # Feature-absent: skip silently
    try:
        result = subprocess.run(
            ["bash", "-n", "-c", content],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            err = result.stderr.strip().split("\n")[0]
            return f"bash syntax error: {err}"
        return None
    except subprocess.TimeoutExpired:
        return None
    except Exception:
        return None


PARSER_FUNCS = {
    "python": check_python,
    "json": check_json,
    "yaml": check_yaml,
    "bash": check_bash,
}


def run_all_checks(post_path):
    issues = []
    text = post_path.read_text(encoding="utf-8")

    for lang, content, start_line in extract_code_blocks(text):
        if lang not in PARSABLE_LANGS:
            continue
        if has_template_placeholders(content):
            continue

        parser_key = PARSABLE_LANGS[lang]
        check_fn = PARSER_FUNCS.get(parser_key)
        if not check_fn:
            continue

        error = check_fn(content)
        if error:
            first_content_line = content.split("\n")[0][:80] if content else ""
            issues.append((
                "CRITICAL", start_line, "C1",
                f"[{lang}] {error}",
                first_content_line,
            ))

    issues.sort(key=lambda x: (SEVERITY_ORDER[x[0]], x[1]))
    return issues


def main():
    parser = argparse.ArgumentParser(
        description="Validate code block syntax (C1 dimension) in blog body."
    )
    parser.add_argument("file", help="Path to .md post file")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--max-issues", type=int, default=30)
    args = parser.parse_args()

    path = Path(args.file)
    if not path.is_file():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(2)

    issues = run_all_checks(path)

    critical = sum(1 for i in issues if i[0] == "CRITICAL")
    major = sum(1 for i in issues if i[0] == "MAJOR")
    minor = sum(1 for i in issues if i[0] == "MINOR")

    if args.json:
        out = {
            "file": str(path),
            "summary": {"critical": critical, "major": major, "minor": minor},
            "issues": [
                {"severity": s, "line": l, "dimension": d, "message": m, "snippet": snip}
                for s, l, d, m, snip in issues
            ],
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        if not issues:
            print("Code Block Validation: PASS (no C1 syntax errors)")
        else:
            print("Code Block Validation: FAIL")
            print(f"  CRITICAL: {critical}  MAJOR: {major}  MINOR: {minor}")
            print()
            for sev, line_no, dim, msg, snip in issues[:args.max_issues]:
                print(f"  [{sev}] L{line_no} {dim}: {msg}")
                if snip:
                    print(f"    `{snip}`")
            if len(issues) > args.max_issues:
                print(f"  ... and {len(issues) - args.max_issues} more issues suppressed")

    if critical or major:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
