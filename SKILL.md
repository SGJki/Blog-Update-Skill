---
name: blog-update
description: Use when the user invokes /blog-update or asks to turn the current technical discussion into a Fuwari blog post.
---

# Blog Update V10

Turn technical session material into a Fuwari blog article with a minimal, safety-first workflow. The default path is one main editor producing one complete draft, then deterministic checks, then an explicit user-confirmed write for existing posts.

## When to Use

- User invokes `/blog-update` or `/blog-update <topic>`.
- User asks to save, publish, merge, or convert the current technical discussion into a blog post.

## Boundaries

- Use only the visible conversation, files the user provides, and files in the configured blog/project paths. Do not claim access to all historical sessions unless the user explicitly provides those files or asks to inspect local session rollout files.
- Do not automatically commit, push, deploy, or publish.
- Do not write to the user's blog content until the target and operation are clear.
- Existing articles are changed only after showing a unified diff and receiving explicit user confirmation.
- New articles are first written as staging drafts with `draft: true`.

## Configuration

Read the deployed skill config when available:

```json
{
  "blogBasePath": "path/to/src/content/posts",
  "fileExtension": ".md"
}
```

If the config is missing, ask for the blog post directory. Use `.md` as the default extension.

`uv` is optional. If it is installed, run scripts with `uv run` so PEP 723 dependencies are available. If it is absent, run the stdlib validators with `python3` and report which dependency-backed checks were skipped. Missing `uv` is not a hard stop.

## V10 Workflow

### 1. Resolve Intent

Determine:

- topic/title
- target slug and file path
- create vs update mode
- tags and category
- whether the user expects a draft, a merge, or only a preview

For `/blog-update` without a topic, infer a topic from the visible session and ask the user to confirm before writing.

### 2. Build a Source Brief

Before drafting, make an internal source brief from the available material. Keep it concise and concrete:

- working title and audience
- 5-12 facts that must survive into the article
- commands, errors, paths, configs, decisions, and tradeoffs worth preserving
- claims that need soft wording because evidence is incomplete
- material to exclude or anonymize
- links/images that should remain, with local existence checked when possible

This replaces the V9 Evidence Ledger ceremony. It is an internal drafting aid, not a visible checklist unless that is the best article format.

### 3. Draft the Complete Article

The main editor writes one complete Markdown draft:

```yaml
---
title: "<topic>"
published: <YYYY-MM-DD>
description: "<30-150 char summary>"
tags: ["<tag1>", "<tag2>"]
category: <category>
draft: true
---

# <topic>

<body>
```

Rules:

- `title` and the first H1 must match exactly.
- New article drafts default to `draft: true`.
- Do not include raw session role markers, tool transcripts, approval prompts, private tokens, cookies, internal URLs, or absolute user paths unless the user explicitly asks and the material has been sanitized.
- Preserve useful technical specificity. Do not replace concrete failures, commands, or decisions with generic prose.
- Use fenced code blocks with explicit language identifiers. Use `text` for logs and ASCII diagrams.

### 4. Validate Once the Draft Is Complete

Run validators against the complete draft, including frontmatter and H1:

```bash
python3 scripts/scan-sensitive-content.py <draft-file>
python3 scripts/validate-post.py <draft-file>
python3 scripts/validate-frontmatter.py <draft-file>
```

If `uv` is available, dependency-backed checks may also run:

```bash
uv run scripts/validate-codeblocks.py <draft-file>
uv run scripts/validate-frontmatter.py <draft-file>
```

Blocking failures must be fixed before the article is offered to the user:

- malformed or missing frontmatter
- no H1 or title/H1 mismatch
- unclosed fenced code block
- broken internal relative `.md` links
- raw session/tool artifacts
- likely secrets, credentials, cookies, private keys, private network addresses, private URLs, email addresses, or absolute user paths

Advisory findings should be reported but do not block by themselves:

- tag count/style preferences
- heading style preferences beyond parseable structure
- bare external URLs
- image alt text quality
- terminology/spelling suggestions

### 5. Write or Merge Safely

New article:

1. Write to a staging path under the blog directory when available, or to the target path only if the user requested direct creation.
2. Keep `draft: true` until the user asks to publish.
3. Report the path and validation results.

Existing article:

1. Read the current article.
2. Merge the new draft with the existing content, preserving existing frontmatter unless the user asked to change it.
3. Generate and show a unified diff.
4. Wait for explicit user confirmation before applying the diff.
5. Re-run validators after applying.

### 6. Optional Assistance

Use the prompt files only when they reduce real risk:

| Prompt | Use when |
|---|---|
| `prompts/implement-agent.md` | Source material is long/noisy and extraction needs a separate pass. |
| `prompts/merge-agent.md` | Existing article merge is large or structurally complex. |
| `prompts/review-agent.md` | Validators pass but semantic accuracy, tone, or evidence coverage is still risky. |

Subagents are optional tools, not the default workflow. All writes remain under the main editor's control.

## Script Reference

| Script | Gate | Purpose | Deps |
|---|---|---|---|
| `scripts/scan-sensitive-content.py` | Blocking | Detect likely secrets, credentials, cookies, private network references, emails, and absolute user paths. | stdlib |
| `scripts/validate-post.py` | Blocking + advisory | Validate complete Markdown draft structure, fences, session leaks, and internal links. | stdlib |
| `scripts/validate-frontmatter.py` | Blocking + advisory | Validate Fuwari frontmatter and title/H1 consistency. Defaults to report-only; `--fix` is required to write. | `pyyaml>=6.0` |
| `scripts/validate-codeblocks.py` | Blocking when runnable | Parse supported code blocks with real parsers. | `pyyaml>=6.0`, bash when available |

## Frontmatter Policy

- The validator is report-only by default.
- `--fix` may canonicalize safe fields, but it must not flip `draft: true` to `false`.
- `published` is valid when it is a real `YYYY-MM-DD` date. It should not be rewritten to today unless `--fix` is explicitly used on an invalid or missing date.
- Tags/category warnings are advisory unless they make the frontmatter unparseable.

## Red Flags

Stop and ask the user before proceeding when:

- the target path is unclear or outside the configured blog posts directory
- the session contains plausible secrets or private operational details that cannot be confidently sanitized
- updating an existing article would delete substantial existing content
- the user asks to publish or set `draft: false` without reviewing the resulting article
- three revision attempts still leave blocking validation failures

## Completion Report

Tell the user:

- created/updated file path
- whether the article is still a draft
- validators run and any skipped checks
- whether a diff was applied or is waiting for confirmation
- any remaining advisory findings
