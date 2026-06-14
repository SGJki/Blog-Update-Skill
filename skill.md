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
Main session generates frontmatter inline using the template below and prepends it to the file (Edit or Write). No subagent needed — the frontmatter is deterministic.

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

### Step 7.5: Frontmatter Validation Pass (deterministic, no subagent)

After Step 7 generates frontmatter and writes the file, the main session runs a programmatic validation pass. This catches schema errors that review-agent cannot see — review runs in Step 6, before frontmatter exists. Frontmatter bugs in real outputs (tag typos like `Authentation`, `draft: False` capitalized, missing `description`, title/H1 mismatch) all escaped review-agent in past versions because review-agent literally could not see the frontmatter.

**Why deterministic:** frontmatter is a fixed 6-field YAML schema. It does not need LLM judgment. Running these checks as a programmatic pass avoids consuming the max-3 retry loop budget on trivially fixable issues.

**Checks (run in order, top to bottom):**

| # | Check | Rule | Auto-fix? |
|---|-------|------|-----------|
| 1 | Required fields present | `title`, `published`, `description`, `tags`, `category`, `draft` all exist | No — STOP and ask user |
| 2 | `published` format | Strict `YYYY-MM-DD` (e.g., `2026-04-07`) | Yes — replace with today's date |
| 3 | `draft` value | Lowercase `false` (not `False`, not `no`, not `0`, not `true`) | Yes — rewrite to `false` |
| 4 | `tags` format | 2–5 entries, all double-quoted strings: `["A", "B"]` | Yes — add quotes + normalize spacing |
| 5 | `tags` count | Between 2 and 5 inclusive | No — STOP if <2 or >5 |
| 6 | `tags` spelling | Min-edit-distance <2 from a tech-term dictionary (Git, Web, AI, DevOps, Auth, Authentication, Tools, RPC, DB, Architecture, etc.); flag suspects | No — report suspects, ask user to confirm or correct |
| 7 | `tags` duplication | No duplicate entries (case-insensitive) | Yes — dedupe |
| 8 | `title` consistency | `frontmatter.title` exactly equals first `# H1` in body | No — STOP, ask user which to keep |
| 9 | `description` non-empty | 30–150 chars, no leading/trailing whitespace | No — if empty, auto-generate from first paragraph of body |
| 10 | `category` value | Single scalar value, not a list | Yes — unwrap `["X"]` to `X` |

**Execution flow:**

1. Read the file just written in Step 7
2. Parse YAML frontmatter (between the two `---` fences)
3. Run all 10 checks in order
4. Apply auto-fixes; after each auto-fix, re-validate affected checks
5. Repeat auto-fix loop until stable (no more auto-fixable issues remain)
6. If any non-auto-fixable check fails → STOP and report to user with the specific failing check + a suggested action
7. If all checks pass → proceed to Step 8

**Auto-fix does NOT count against the max-3 retry loop** in Step 6. Auto-fix is deterministic, low-risk, and does not require review-agent re-run.

**Frontmatter Validation Report (printed to user):**

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
  Action required: <what user must decide>
  Skill paused — waiting for user input.
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
