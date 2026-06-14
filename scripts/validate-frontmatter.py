# /// script
# requires-python = ">=3.8"
# dependencies = ["pyyaml>=6.0"]
# ///
"""Frontmatter validation pass for blog-update skill (Step 7.5).

Validates fuwari 6-field frontmatter (title, published, description,
tags, category, draft) plus title/H1 consistency with body.

10 checks with 6 auto-fixes, per skill.md spec. Auto-fixes are applied
in-place; non-auto-fixable failures print a FAIL report and pause.

Usage:
  uv run scripts/validate-frontmatter.py <post-file>
  uv run scripts/validate-frontmatter.py <post-file> --dry-run

Exit codes:
  0 = PASS (all checks OK, possibly after auto-fixes)
  1 = FAIL (non-auto-fixable check failed, or auto-fix loop exceeded)
  2 = ERROR (file missing, parse error, bad invocation)
"""
import argparse
import datetime
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.stderr.write(
        "ERROR: pyyaml not installed.\n"
        "Run via: uv run scripts/validate-frontmatter.py <file>\n"
        "uv auto-installs deps from PEP 723 metadata.\n"
    )
    sys.exit(2)


TECH_DICT = {
    "Git", "GitHub", "GitLab", "Python", "JavaScript", "TypeScript", "Go", "Rust",
    "Java", "Kotlin", "Swift", "Scala", "AI", "ML", "LLM", "Web", "DevOps", "Auth",
    "Authentication", "Authorization", "Tools", "RPC", "DB", "Database", "HTTP",
    "HTTPS", "API", "REST", "GraphQL", "Docker", "Kubernetes", "Linux", "MacOS",
    "Windows", "Architecture", "Frontend", "Backend", "Fullstack", "JWT", "OAuth",
    "SSL", "TLS", "CSS", "HTML", "JSON", "XML", "YAML", "TOML", "SQL", "NoSQL",
    "Redis", "MySQL", "PostgreSQL", "MongoDB", "Vue", "React", "Angular", "Svelte",
    "Astro", "Hugo", "Hexo", "Node", "Deno", "Bun", "Vite", "Webpack",
}

# 6 canonical fuwari fields, in serialization order.
CANONICAL_FIELDS = ["title", "published", "description", "tags", "category", "draft"]

# Check #1 only hard-stops on these (description is auto-fixable via Check #9).
REQUIRED_FIELDS = ["title", "published", "tags", "category", "draft"]
NON_FIXABLE = {"1", "5", "6", "8"}


def levenshtein(a, b):
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]


def split_frontmatter(text):
    if not text.startswith("---"):
        return "", text
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.DOTALL)
    if not m:
        return "", text
    return m.group(1), m.group(2)


def find_h1(body):
    in_code = False
    for line in body.split("\n"):
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = re.match(r"^#\s+(.+?)\s*$", line)
        if m:
            return m.group(1)
    return None


def find_first_paragraph(body):
    lines = body.split("\n")
    in_code = False
    para = []
    for line in lines:
        if line.startswith("```"):
            in_code = not in_code
            if para:
                break
            continue
        if in_code:
            continue
        stripped = line.strip()
        if not stripped:
            if para:
                break
            continue
        if stripped.startswith("#"):
            continue
        # Skip horizontal rules — they look like paragraphs to a naive
        # scanner but carry no descriptive content.
        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", stripped):
            continue
        # Skip table rows — not prose, not suitable for a description.
        if stripped.startswith("|"):
            continue
        para.append(stripped)
    return " ".join(para) if para else ""


def truncate_at_word(text, max_chars=150):
    if len(text) <= max_chars:
        return text
    # Reserve 1 char for the trailing ellipsis so the result is always
    # <= max_chars. Returning max_chars+1 (e.g. 151) re-triggers the
    # >150 branch in check_description on the next iteration, causing
    # the auto-fix loop to exhaust its retries.
    truncated = text[:max_chars - 1]
    last_space = truncated.rfind(" ")
    if last_space > 30:
        truncated = truncated[:last_space]
    return truncated + "…"


def normalize_tags(tags):
    seen = set()
    out = []
    for t in tags:
        if not isinstance(t, str):
            t = str(t)
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def serialize_value_scalar(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        escaped = v.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return str(v)


def serialize_description(desc):
    escaped = desc.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def serialize_frontmatter(fm):
    title = fm["title"]
    title_str = title if isinstance(title, str) else str(title)

    pub = fm["published"]
    if isinstance(pub, datetime.date):
        pub_str = pub.strftime("%Y-%m-%d")
    elif isinstance(pub, str):
        pub_str = pub
    else:
        pub_str = str(pub)

    desc = fm.get("description", "")
    if not isinstance(desc, str):
        desc = str(desc)

    tags = fm["tags"]
    if not isinstance(tags, list):
        tags = [tags]
    tags_str = ", ".join(f'"{t}"' for t in tags)

    cat = fm["category"]
    if isinstance(cat, list):
        cat = cat[0] if cat else ""

    draft = fm["draft"]
    if isinstance(draft, bool):
        draft_str = "false" if not draft else "true"
    else:
        draft_str = "false" if str(draft).lower() in ("false", "no", "0") else "true"

    lines = [
        "---",
        f"title: {title_str}",
        f"published: {pub_str}",
        f"description: {serialize_description(desc)}",
        f"tags: [{tags_str}]",
        f"category: {cat}",
        f"draft: {draft_str}",
    ]

    extra = {k: v for k, v in fm.items() if k not in CANONICAL_FIELDS}
    for k, v in extra.items():
        if isinstance(v, list):
            list_str = ", ".join(serialize_value_scalar(t) for t in v)
            lines.append(f"{k}: [{list_str}]")
        else:
            lines.append(f"{k}: {serialize_value_scalar(v)}")

    lines.append("---")
    return "\n".join(lines)


def check_required_fields(fm):
    missing = [f for f in REQUIRED_FIELDS if f not in fm or fm[f] is None]
    if missing:
        return False, f"missing fields: {', '.join(missing)}", None
    return True, "", None


def check_published(fm):
    pub = fm.get("published")
    today = datetime.date.today().strftime("%Y-%m-%d")
    if isinstance(pub, datetime.date):
        return True, "", None
    if isinstance(pub, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", pub):
        try:
            datetime.datetime.strptime(pub, "%Y-%m-%d")
            return True, "", None
        except ValueError:
            pass
    return False, f"published={pub!r} not YYYY-MM-DD", {"published": today}


def check_draft(fm):
    draft = fm.get("draft")
    if draft is False or draft == "false":
        return True, "", None
    return False, f"draft={draft!r} not lowercase false", {"draft": False}


def check_tags_format(fm):
    tags = fm.get("tags")
    if not isinstance(tags, list):
        return False, f"tags is {type(tags).__name__}, not list", {"tags": [tags] if tags is not None else []}
    normalized = [str(t) for t in tags]
    if normalized != tags:
        return False, "tags contains non-string entries", {"tags": normalized}
    return True, "", None


def check_tags_count(fm):
    tags = fm.get("tags", [])
    n = len(tags)
    if n < 2:
        return False, f"only {n} tag(s), need >=2", None
    if n > 5:
        return False, f"{n} tags, need <=5", None
    return True, "", None


def check_tags_spelling(fm):
    """Flag only tags that look like TYPOS of dictionary words.

    Skip:
      - exact dict matches (pass)
      - non-ASCII tags (Chinese / CJK — assume intentional, never flag)
      - tags far from every dict word (legit custom term, e.g. "Akka")
    Flag:
      - tags within edit distance 1-2 of a dict word ("Authentation" → "Authentication")
    Skip:
      - tags length <= 3 (short acronyms like "JVM"/"TS" are inherently
        within edit-distance 2 of other short dict words; too noisy)
    """
    suspects = []
    for t in fm.get("tags", []):
        if not isinstance(t, str):
            continue
        if not t.isascii():
            continue
        if t in TECH_DICT:
            continue
        if len(t) <= 3:
            continue
        distances = {d: levenshtein(t, d) for d in TECH_DICT}
        closest = min(distances, key=distances.get)
        min_dist = distances[closest]
        if 0 < min_dist <= 2:
            suspects.append(f'"{t}" (closest dict entry: "{closest}", edit distance {min_dist})')
    if suspects:
        return False, f"possible typos: {', '.join(suspects)}", None
    return True, "", None


def check_tags_dedup(fm):
    tags = fm.get("tags", [])
    lower_tags = [t.lower() if isinstance(t, str) else str(t).lower() for t in tags]
    if len(lower_tags) != len(set(lower_tags)):
        return False, "duplicate tags (case-insensitive)", {"tags": normalize_tags(tags)}
    return True, "", None


def check_title_h1(fm, body):
    title = fm.get("title")
    h1 = find_h1(body)
    if title is None or h1 is None:
        return True, "", None
    if title != h1:
        return False, f'frontmatter title="{title}" vs body H1="{h1}"', None
    return True, "", None


def _auto_gen_description(body):
    """Generate a valid (30-150 char) description from body's first paragraph.

    Returns None if body's first paragraph is absent or itself <30 chars —
    in that case Check #9 is non-auto-fixable (cannot manufacture substance
    the body does not have). This prevents the auto-fix loop where a short
    body paragraph produces a short description that re-triggers Check #9.
    """
    para = find_first_paragraph(body)
    if not para:
        return None
    candidate = truncate_at_word(para, 150)
    if len(candidate) < 30:
        return None
    return candidate


def check_description(fm, body):
    # Missing description is auto-fixable here (do NOT also fail Check #1).
    desc = fm.get("description")
    if desc is None:
        candidate = _auto_gen_description(body)
        if candidate is None:
            return False, "description missing and body has no paragraph >=30 chars to auto-generate from", None
        return False, "description field missing", {"description": candidate}
    if not isinstance(desc, str):
        desc = str(desc)
    stripped = desc.strip()
    if len(stripped) == 0:
        candidate = _auto_gen_description(body)
        if candidate is None:
            return False, "description empty and body has no paragraph >=30 chars to auto-generate from", None
        return False, "description is empty string", {"description": candidate}
    if len(stripped) < 30:
        candidate = _auto_gen_description(body)
        if candidate is None:
            return False, f"description only {len(stripped)} chars and body has no paragraph >=30 chars", None
        return False, f"description only {len(stripped)} chars (need 30-150)", {"description": candidate}
    if len(stripped) > 150:
        return False, f"description {len(stripped)} chars (need <=150)", {"description": truncate_at_word(stripped, 150)}
    if stripped != desc:
        return False, "description has leading/trailing whitespace", {"description": stripped}
    return True, "", None


def check_category(fm):
    cat = fm.get("category")
    if isinstance(cat, list):
        unwrapped = cat[0] if cat else ""
        return False, f"category is list {cat}, should be scalar", {"category": unwrapped}
    return True, "", None


def run_all_checks(fm, body):
    return [
        ("1", "Required fields present", check_required_fields(fm)),
        ("2", "published format", check_published(fm)),
        ("3", "draft value", check_draft(fm)),
        ("4", "tags format", check_tags_format(fm)),
        ("5", "tags count", check_tags_count(fm)),
        ("6", "tags spelling", check_tags_spelling(fm)),
        ("7", "tags dedup", check_tags_dedup(fm)),
        ("8", "title / H1 consistency", check_title_h1(fm, body)),
        ("9", "description non-empty", check_description(fm, body)),
        ("10", "category scalar", check_category(fm)),
    ]


def validate(fm, body, max_iter=3):
    auto_fixes_log = []

    for _ in range(max_iter):
        results = run_all_checks(fm, body)

        for num, name, (ok, detail, _fix) in results:
            if not ok and num in NON_FIXABLE:
                return False, auto_fixes_log, f"Check #{num} ({name})", detail

        any_fix_applied = False
        for num, name, (ok, detail, fix) in results:
            if not ok and fix:
                for k, v in fix.items():
                    fm[k] = v
                auto_fixes_log.append(f"Check #{num} ({name}): {detail}")
                any_fix_applied = True

        if not any_fix_applied:
            # Verify all checks actually pass before declaring PASS. A check
            # can return (False, ..., None) — failed but no fix available
            # (e.g. Check #9 when body's first paragraph is too short to
            # generate a description). Without this re-check, such failures
            # silently report PASS.
            for num, name, (ok, detail, _fix) in results:
                if not ok:
                    return False, auto_fixes_log, f"Check #{num} ({name})", detail
            return True, auto_fixes_log, None, None

    results = run_all_checks(fm, body)
    for num, name, (ok, detail, fix) in results:
        if not ok:
            if fix:
                return False, auto_fixes_log, "Auto-fix loop", f"exceeded {max_iter} iterations, Check #{num} still auto-fixable"
            return False, auto_fixes_log, f"Check #{num} ({name})", detail

    return True, auto_fixes_log, None, None


def main():
    parser = argparse.ArgumentParser(description="Validate fuwari blog frontmatter.")
    parser.add_argument("file", help="Path to .md post file")
    parser.add_argument("--dry-run", action="store_true", help="Report only, don't write fixes")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.is_file():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(2)

    text = path.read_text(encoding="utf-8")
    fm_str, body = split_frontmatter(text)

    if not fm_str:
        print("Frontmatter Validation: FAIL")
        print("  - file has no frontmatter (must start with `---`)")
        print("  Action required: add fuwari frontmatter with 6 required fields")
        print("  Skill paused — waiting for user input.")
        sys.exit(1)

    try:
        fm = yaml.safe_load(fm_str)
    except yaml.YAMLError as e:
        print("Frontmatter Validation: FAIL")
        print(f"  - YAML parse error: {e}")
        print("  Action required: fix YAML syntax and re-run")
        sys.exit(1)

    if not isinstance(fm, dict):
        print("Frontmatter Validation: FAIL")
        print(f"  - frontmatter parsed as {type(fm).__name__}, expected mapping")
        sys.exit(1)

    passed, fixes, fail_check, fail_detail = validate(fm, body)

    if passed:
        if fixes and not args.dry_run:
            new_fm_str = serialize_frontmatter(fm)
            new_text = new_fm_str + "\n\n" + body.lstrip("\n")
            path.write_text(new_text, encoding="utf-8")
        print(f"Frontmatter Validation: PASS ({len(fixes)} auto-fixes applied)")
        for fix in fixes:
            print(f"  - {fix}")
        sys.exit(0)
    else:
        print("Frontmatter Validation: FAIL")
        print(f"  - {fail_check} failed")
        print(f"    {fail_detail}")
        print("  Action required: reconcile manually or adjust topic/tags/category and re-run")
        print("  Skill paused — waiting for user input.")
        sys.exit(1)


if __name__ == "__main__":
    main()
