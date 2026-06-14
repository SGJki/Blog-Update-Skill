# /// script
# requires-python = ">=3.8"
# dependencies = []
# ///
"""Body validation pass for blog-update skill (Step 6.5).

Checks markdown body for 6 deterministic dimensions (no LLM judgment):

  B1 - Heading structure (H1 in body, H2-jump-H2, level jumps, empty)
  B2 - Code blocks (empty/non-whitelist lang, unclosed fence, box-drawing)
  B3 - List format (mixed markers)
  B4 - Paragraph separation (leading spaces, trailing whitespace ratio)
  D1 - Filter effectiveness (session noise: tool artifacts, role markers,
       confirmation dialogs, stack-trace middle frames, greetings)
  C2 - Link integrity (bare URLs, image without alt, broken internal links)

review-agent no longer covers these dimensions — they are fully delegated
to this script for reliability (LLM miscounts fences, hallucinates
whitelist membership, misses subtle session-leak patterns).

Usage:
  uv run scripts/validate-post.py <post-file>
  uv run scripts/validate-post.py <post-file> --json

Exit codes:
  0 = no CRITICAL and no MAJOR (MINOR allowed)
  1 = at least one CRITICAL or MAJOR
  2 = ERROR (file missing, etc.)
"""
import argparse
import json
import re
import sys
from pathlib import Path


WHITELIST_LANGS = {
    "bash", "sh", "shell", "zsh", "fish",
    "python", "javascript", "typescript", "go", "rust", "java", "kotlin",
    "swift", "scala", "c", "cpp", "csharp", "cs", "php", "ruby", "lua",
    "perl", "r", "julia", "sql", "yaml", "json", "toml", "ini", "xml",
    "html", "css", "markdown", "mermaid", "text", "diff", "dockerfile",
    "cmake", "makefile", "ps1", "powershell", "graphql", "protobuf",
}

BOX_DRAWING = set("┌─┐│└┘├┤┬┴┼╔╗╚╝║═╠╣╩╦╬")

SEVERITY_ORDER = {"CRITICAL": 0, "MAJOR": 1, "MINOR": 2}


def strip_frontmatter(text):
    if not text.startswith("---"):
        return text
    m = re.match(r"^---\n.*?\n---\n?(.*)$", text, re.DOTALL)
    return m.group(1) if m else text


def check_b1_headings(lines):
    issues = []
    prev_level = 0
    prev_was_h2 = False
    in_code = False
    for i, line in enumerate(lines, 1):
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = re.match(r"^(#{1,6})\s*(.*?)\s*$", line)
        if not m:
            if line.strip():
                prev_was_h2 = False
            continue
        hashes, text = m.group(1), m.group(2)
        level = len(hashes)
        if level == 1:
            issues.append(("CRITICAL", i, "B1", "H1 in body (main session generates H1 from title)", line))
        if not text:
            issues.append(("CRITICAL", i, "B1", "Empty heading text", line))
        if prev_level > 0 and level > prev_level + 1:
            issues.append(("MAJOR", i, "B1", f"Heading level jumps H{prev_level} -> H{level}", line))
        if prev_was_h2 and level == 2:
            issues.append(("CRITICAL", i, "B1", "H2 directly followed by another H2 (no content/H3 between)", line))
        prev_level = level
        prev_was_h2 = (level == 2)
    return issues


def check_b2_codeblocks(lines):
    issues = []
    in_code = False
    fence_lang = None
    fence_start_line = 0
    for i, line in enumerate(lines, 1):
        m = re.match(r"^```(\S*)\s*$", line)
        if m:
            if not in_code:
                lang = m.group(1)
                if not lang:
                    issues.append(("CRITICAL", i, "B2", "Empty language identifier (use `text` for ASCII art)", line))
                elif lang.lower() not in WHITELIST_LANGS:
                    issues.append(("CRITICAL", i, "B2", f"Non-whitelist language identifier `{lang}`", line))
                in_code = True
                fence_lang = lang.lower()
                fence_start_line = i
            else:
                in_code = False
                fence_lang = None
            continue
        if in_code and fence_lang != "text":
            for ch in line:
                if ch in BOX_DRAWING:
                    issues.append(("MAJOR", i, "B2", f"Box-drawing char `{ch}` outside `text` code block (move to `text` fence)", line[:80]))
                    break
    if in_code:
        issues.append(("CRITICAL", len(lines), "B2", f"Unclosed code fence (opened at line {fence_start_line})", "<EOF>"))
    return issues


def check_b3_lists(lines):
    issues = []
    in_code = False
    groups = {}
    for i, line in enumerate(lines, 1):
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = re.match(r"^(\s*)([-*+])\s+\S", line)
        if not m:
            continue
        indent = len(m.group(1))
        marker = m.group(2)
        if indent not in groups:
            groups[indent] = {"markers": set(), "first_line": i}
        groups[indent]["markers"].add(marker)
    for indent, info in groups.items():
        if len(info["markers"]) > 1:
            issues.append(("MINOR", info["first_line"], "B3",
                           f"Mixed list markers ({', '.join(sorted(info['markers']))}) at indent {indent}", ""))
    return issues


def check_b4_paragraph(lines):
    issues = []
    in_code = False
    trailing_count = 0
    total_text_lines = 0
    for i, line in enumerate(lines, 1):
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if not line.strip():
            continue
        total_text_lines += 1
        if re.match(r"^ {2,}\S", line) and not re.match(r"^(\s*)([-*+]\s|\d+\.\s|#{1,6}\s|>)", line):
            issues.append(("MINOR", i, "B4", "Line starts with 2+ leading spaces (session paste artifact)", line[:80]))
        if line != line.rstrip():
            trailing_count += 1
    if total_text_lines > 0 and trailing_count / total_text_lines > 0.20:
        issues.append(("MINOR", 0, "B4",
                       f"Trailing whitespace on {trailing_count}/{total_text_lines} lines (>20%)", ""))
    return issues


def check_d1_noise(lines):
    issues = []
    in_code = False
    tool_artifact_patterns = [
        (r"<system-reminder[^>]*>", "system-reminder tag"),
        (r"</system-reminder>", "system-reminder close tag"),
        (r"<tool_result", "tool_result tag"),
        (r"</tool_result>", "tool_result close tag"),
        (r"<command-name>", "command-name tag"),
        (r"<local-command-caveat>", "local-command-caveat tag"),
        (r"<task-notification>", "task-notification tag"),
    ]
    for i, line in enumerate(lines, 1):
        for pat, label in tool_artifact_patterns:
            if re.search(pat, line):
                issues.append(("CRITICAL", i, "D1", f"Tool artifact: {label}", line[:80]))

        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue

        if re.match(r"^<(user|assistant|system)>:", line):
            issues.append(("CRITICAL", i, "D1", "Role marker (session leak)", line[:80]))
        if re.search(r"\[y/N\]|\[Y/n\]|\(y/n\)|\bContinue\?|Confirm execution\?|Are you sure|Type yes to continue", line, re.IGNORECASE):
            issues.append(("CRITICAL", i, "D1", "Confirmation dialog (session leak)", line[:80]))
        if re.match(r"^\s+at\s+[\w\.]+\(", line):
            issues.append(("MAJOR", i, "D1", "Stack trace middle frame (keep only error class + root cause)", line[:80]))
        if re.match(r"^(Hi|Hello|Hey|Thanks|Thank you|谢谢|你好|嗨)\s*[,!.?\s]*$", line, re.IGNORECASE):
            issues.append(("MAJOR", i, "D1", "Greeting/thank-you (session leak)", line[:80]))
        if re.match(r"^\s*(Retrying|Attempt \d+ of \d+|Rate limited|429 Too Many Requests)", line, re.IGNORECASE):
            issues.append(("MAJOR", i, "D1", "Retry/transient error (session leak)", line[:80]))
    return issues


def check_c2_links(lines, post_path):
    issues = []
    in_code = False
    post_dir = post_path.parent
    for i, line in enumerate(lines, 1):
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue

        for m in re.finditer(r"(?<![<\(\[])(https?://[^\s\)\]\}]+)", line):
            url = m.group(1).rstrip(".,;:。，；")
            before = line[:m.start()]
            if before.endswith("<"):
                continue
            if before.endswith("(") and line[m.end():].lstrip().startswith(")"):
                continue
            issues.append(("MINOR", i, "C2", f"Bare URL (wrap in `<...>` or `[text](url)`): `{url[:60]}`", line[:80]))

        for m in re.finditer(r"!\[([^\]]*)\]\(([^)]+)\)", line):
            alt = m.group(1)
            if not alt.strip():
                issues.append(("MINOR", i, "C2", "Image without alt text", line[:80]))

        for m in re.finditer(r"\]\((\.{1,2}/[^)]+\.md)\)", line):
            target = m.group(1)
            target_path = (post_dir / target).resolve()
            if not target_path.exists():
                issues.append(("MAJOR", i, "C2", f"Internal link target missing: `{target}`", line[:80]))

        for m in re.finditer(r"\]\((https?://[^\)]+)\)", line):
            url = m.group(1)
            if not re.match(r"^https?://[\w\.\-]+(\:\d+)?(/[\w\.\-/]*)?(\?[^\s\)]*)?$", url):
                issues.append(("MAJOR", i, "C2", f"Malformed URL: `{url[:60]}`", line[:80]))
    return issues


def run_all_checks(lines, post_path):
    issues = []
    issues += check_b1_headings(lines)
    issues += check_b2_codeblocks(lines)
    issues += check_b3_lists(lines)
    issues += check_b4_paragraph(lines)
    issues += check_d1_noise(lines)
    issues += check_c2_links(lines, post_path)
    issues.sort(key=lambda x: (SEVERITY_ORDER[x[0]], x[1]))
    return issues


def main():
    parser = argparse.ArgumentParser(description="Validate fuwari blog body (B/D1/C2 dimensions).")
    parser.add_argument("file", help="Path to .md post file")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of markdown")
    parser.add_argument("--max-issues", type=int, default=30, help="Max issues to print (default 30)")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.is_file():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(2)

    text = path.read_text(encoding="utf-8")
    body = strip_frontmatter(text)
    lines = body.split("\n")

    issues = run_all_checks(lines, path)

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
            print("Body Validation: PASS (no B1/B2/B3/B4/D1/C2 issues)")
        else:
            print("Body Validation: FAIL")
            print(f"  CRITICAL: {critical}  MAJOR: {major}  MINOR: {minor}")
            print()
            shown = issues[:args.max_issues]
            for sev, line_no, dim, msg, snip in shown:
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
