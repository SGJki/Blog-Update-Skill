---
name: blog-update
description: Use when user invokes /blog-update to publish session content as a fuwari-framework blog post, or asks to save technical discussion as a blog article
---

# Blog Update (Smart Merge)

Intelligently merge technical discussion from the session into a fuwari-framework blog post, without requiring the user to manually choose append/update/preserve.

## When to Use

- User invokes `/blog-update <topic>` — merges session content matching the topic into a blog post
- User invokes `/blog-update` without topic — auto-infers topic, tags, category from session content
- User asks to save session content as a blog post

## When NOT to Use

- Session has no meaningful technical content (only greetings, short Q&A, no code/discussion)
- User explicitly declines the auto-inferred topic

## Coordination Flow

### Step 1: Check Configuration
Read `~/.claude/skills/blog-update/config.json` to get `blogBasePath` and `fileExtension`. Use defaults if missing.

### Step 2: Determine topic, tags, category, and mode

**Topic provided (`/blog-update <topic>`):**
- Check if file exists at `blogBasePath/<topic-slug>.md`
- File exists → merge mode: auto-extract tags/category from existing frontmatter
- File not exists → new file mode: ask user for `--tags [..] --category <..>` (or use `--tags`/`--category` from command if provided)

**Topic not provided (`/blog-update` without arguments):**
1. Scan the entire session for technical discussion, code, configuration, error solving, etc.
2. Identify the dominant theme and infer:
   - **topic**: a concise title (e.g. "Git Rebase 工作流")
   - **tags**: 2–5 relevant tags (e.g. `["Git", "DevOps"]`)
   - **category**: one category (e.g. `DevOps`)
3. Present inferred values to the user for confirmation or adjustment
4. After confirmation, check if the corresponding file exists → merge or create mode

### Step 3: Extract Session Context
- **Topic was provided**: Extract content from the session related to the given topic (technical discussion, code, configuration, etc.)
- **Topic was auto-inferred**: Session context was already scanned in Step 2 — use the extracted content directly

### Step 4: Launch implement-agent (background)
Pass topic and session_context. Generates raw markdown content from session.

### Step 5: Launch merge-agent (background)
Pass new content from implement-agent and existing file path (if it exists). Performs multi-granularity smart merge.

### Step 6: Write merged content to file IMMEDIATELY, then launch review-agent (background)

**Critical ordering:** Write merged content to file BEFORE launching review-agent. review-agent reads the file to verify content — if Write happens after launch, review-agent reads the OLD file.

```
merge-agent output → Write to file → launch review-agent → reads NEW file ✓
```

- PASS: Proceed to Step 7
- FAIL: Feed issues back to implement-agent for revision, loop Step 4–6 (max 3 times)

### Step 7: Generate frontmatter and write final content
Main session generates frontmatter inline using the template below, generates the H1 heading (since implement-agent must NOT output H1), and prepends both to the file (Edit or Write). No subagent needed — frontmatter and H1 are deterministic.

**Order of operations:**

1. Take `topic` as-is → use for `title` field AND as the H1 heading text
2. Generate the 6-field frontmatter (see template below)
3. Generate H1: `# <topic as-is>` (must match `title` character-for-character)
4. Concatenate: `frontmatter + "\n\n" + H1 + "\n\n" + body` → write to file

**Critical:** the H1 text MUST be character-identical to `title`. The Step 7.5
Check #8 verifies this. If they differ, the skill will hard-stop and ask the
user to reconcile.

**fuwari frontmatter template (field names must match exactly):**
```yaml
---
title: <topic as-is>
published: <YYYY-MM-DD>
description: "<1-2 sentence summary of the content>"
tags: ["<tag1>", "<tag2>"]
category: <category>
draft: false
---
```

**Common field name mistakes to avoid:**
- `date:` → use `published:`
- `categories:` (plural) → use `category:` (singular)
- `published: true/false` → use `draft: false`
- `tags: [Git, Tools]` (unquoted) → use `tags: ["Git", "Tools"]` (quoted strings)
- Generating H1 from body's first sentence instead of from `topic` → use `topic` exactly

### Step 7.5: Frontmatter Validation Pass (scripted via uv)

After Step 7 generates frontmatter and writes the file, the main session invokes a Python script that performs all 10 checks programmatically. This catches schema errors that review-agent cannot see — review runs in Step 6, before frontmatter exists. Frontmatter bugs in real outputs (tag typos like `Authentation`, `draft: False` capitalized, missing `description`, title/H1 mismatch) all escaped review-agent in past versions because review-agent literally could not see the frontmatter.

**Why scripted, not LLM-as-parser:** frontmatter is a fixed 6-field YAML schema. Delegating parse-and-check to the LLM (the old behavior) reproduces the same class of bugs the check was meant to catch — LLM miscounts list items, hallucinates edit-distance, and silently accepts malformed YAML. PyYAML parses the file deterministically; the check logic is plain Python.

**Invocation** (run from the skill's base directory):

```bash
uv run scripts/validate-frontmatter.py "<absolute-path-to-post>"
```

`uv run` reads the PEP 723 inline metadata at the top of the script and auto-installs `pyyaml>=6.0` on first run (cached thereafter — instant). No manual pip install, no venv management. The script:

- Reads the post file, parses frontmatter via `yaml.safe_load`
- Runs all 10 checks below in order
- Applies auto-fixes (up to 3 iterations, see dependency map below)
- Writes the fixed file in-place (only if any auto-fix was applied)
- Prints a PASS or FAIL report to stdout
- Exit codes: `0` = PASS, `1` = FAIL (skill must pause), `2` = ERROR (file missing / unparseable YAML)

**Fallback (if uv is not installed):** the main session runs the 10 checks manually by reading the file and applying the table below. Warn the user that this fallback is less reliable (LLM-as-parser is the failure mode this step was created to eliminate). Recommend installing uv.

**Checks** (run in order, top to bottom):

| # | Check | Rule | Auto-fix? |
|---|-------|------|-----------|
| 1 | Required fields present | `title`, `published`, `tags`, `category`, `draft` all exist (description handled by #9) | No — STOP and ask user |
| 2 | `published` format | Strict `YYYY-MM-DD` (e.g., `2026-04-07`) | Yes — replace with today's date |
| 3 | `draft` value | Lowercase `false` (PyYAML parses `false`/`False`/`no` all as Python `False`; serializer always writes lowercase) | Yes — rewrite to `false` |
| 4 | `tags` format | 2–5 entries, all strings (serializer always emits double-quoted form `["A", "B"]`) | Yes — coerce non-strings to strings |
| 5 | `tags` count | Between 2 and 5 inclusive | No — STOP if <2 or >5 |
| 6 | `tags` spelling | Flag tags within Levenshtein edit distance 1–2 of a dictionary word (typo signature). Skip non-ASCII tags (CJK etc.) and tags length ≤3 (short acronyms are inherently noisy). Dictionary: Git, GitHub, GitLab, Python, JavaScript, TypeScript, Go, Rust, Java, Kotlin, Swift, Scala, AI, ML, LLM, Web, DevOps, Auth, Authentication, Authorization, Tools, RPC, DB, Database, HTTP, HTTPS, API, REST, GraphQL, Docker, Kubernetes, Linux, MacOS, Windows, Architecture, Frontend, Backend, Fullstack, JWT, OAuth, SSL, TLS, CSS, HTML, JSON, XML, YAML, TOML, SQL, NoSQL, Redis, MySQL, PostgreSQL, MongoDB, Vue, React, Angular, Svelte, Astro, Hugo, Hexo, Node, Deno, Bun, Vite, Webpack | No — report suspects, ask user to confirm or correct |
| 7 | `tags` duplication | No duplicate entries (case-insensitive) | Yes — dedupe (preserve first-seen order) |
| 8 | `title` / H1 consistency | `frontmatter.title` character-identical to first `# H1` in body. Code blocks (` ``` `) are skipped when searching for H1, so a `# comment` inside a fence is not mistaken for the body's H1. | No — STOP, ask user which to keep. Note: this should not trigger if Step 7 is followed correctly; if it triggers, Step 7 was bypassed |
| 9 | `description` non-empty | 30–150 chars, no leading/trailing whitespace. Missing field, empty string, and <30 chars are all treated identically — auto-generate. | Yes — if missing/empty/short, take first non-heading non-codeblock paragraph from body, truncate to 150 chars at word boundary, append "…" if truncated. If >150 chars, truncate the same way. If leading/trailing whitespace, strip. |
| 10 | `category` value | Single scalar value, not a list | Yes — unwrap `["X"]` to `X` |

**Execution flow (handled by the script):**

1. Read the file just written in Step 7
2. Parse YAML frontmatter via PyYAML (fail with parse error if malformed)
3. Run all 10 checks; collect failures
4. If any non-auto-fixable check (#1, #5, #6, #8) fails → STOP and report
5. Apply auto-fixes; re-run all checks; repeat up to 3 iterations
6. After max iterations or convergence: if still failing on auto-fixable → STOP; otherwise PASS
7. If any auto-fix was applied, rewrite the file in-place with the canonical 6-field serialized form (preserves any extra fields the user added beyond the canonical 6)

**Auto-fix dependency map** (which checks interact — handled implicitly by the script's re-validation loop):

- Check #3 (draft value) is independent — fixing it cannot break #2, #4, #6
- Check #4 (tags format) implies Check #5 (tags count) and Check #7 (dedup) — re-validate these after #4
- Check #2 (published date) is independent
- Check #10 (category unwrap) is independent

**Auto-fix does NOT count against the max-3 retry loop** in Step 6.
Auto-fix is deterministic, low-risk, and does not require review-agent
re-run.

**Frontmatter Validation Report** (printed by the script to stdout):

On success:

```
Frontmatter Validation: PASS (N auto-fixes applied)
  - <summary of each auto-fix>
```

On failure:

```
Frontmatter Validation: FAIL
  - Check #<N> failed: <check name>
    <specific detail>
  Action required: reconcile manually or adjust topic/tags/category and re-run
  Skill paused — waiting for user input.
```

**Testing the script standalone:**

```bash
# Dry-run (report only, no file changes):
uv run scripts/validate-frontmatter.py <post-file> --dry-run

# Apply fixes in-place:
uv run scripts/validate-frontmatter.py <post-file>
```

### Step 8: Report Completion
Confirm to the user: file path, operation type (create/merge), and merge statistics.

## Subagent Reference

| Agent | Mode | Prompt File | Responsibility |
|-------|------|-------------|----------------|
| implement-agent | Background | prompts/implement-agent.md | Generate raw markdown from session context |
| merge-agent | Background | prompts/merge-agent.md | Multi-granularity merge of new + existing content |
| review-agent | Background | prompts/review-agent.md | Quality gate — content + format review |

Frontmatter generation is done by the main session (Step 7) — no subagent needed for a 6-field YAML template.

**All write operations are performed by the main session, never by subagents.**

## Non-Obvious Error Handling

| Scenario | Response |
|----------|----------|
| Write before review skipped | **STOP.** review-agent must read the newly written file — always write before launching review |
| merge-agent fails | Fallback to implement-agent content as final content |
| Empty content | Warn user, ask whether to continue |

## Quick Reference

| Scenario | Command |
|----------|---------|
| Auto-infer from session | `/blog-update` (infers topic, tags, category) |
| Create new article | `/blog-update <topic> --tags [tag1,tag2] --category <category>` |
| Update existing article | `/blog-update <topic>` (auto-reads tags/category from frontmatter) |

## Red Flags — STOP and Reassess

- Session content is clearly unrelated to the provided topic
- Auto-inferred topic is too vague or session has no clear theme
- User requests "skip review" or "write directly"
- File path contains sensitive information
- Loop exceeds 3 times and still cannot pass review
- User shows impatience ("hurry up", "don't be too strict")

## Common Mistakes

| Mistake | Correct Approach |
|---------|------------------|
| Subagent performs write | Write is always done by main session |
| Skip review | All content must go through review-agent |
| Loop forever | Max 3 loops, then hand off to user |
| Empty content write | Warn user to confirm before creating |

## Rationalization Counter

| Excuse | Reality |
|--------|---------|
| "review is too slow, just write it" | Review catches format errors that break fuwari frontmatter rendering — a broken blog post is worse than a slow one |
| "this is simple, no review needed" | Simple content still needs correct heading structure and code block formatting |
| "I manually checked it" | Manual check misses frontmatter field name errors (e.g. `date:` vs `published:`, `categories:` vs `category:`) |
| "looping wastes time" | 3 loops max catches real issues; beyond that, hand off to user is the right call |
