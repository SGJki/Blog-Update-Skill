---
name: blog-update
description: Use when the user invokes /blog-update or asks to turn a technical discussion into an Astro MDX blog, note, or report entry for the configured knowledge garden.
---

# Blog Update V11 (Astro MDX)

Turn technical session material into an Astro content entry with a minimal,
safety-first workflow. The main editor produces one complete draft, deterministic
checks run against it, and existing entries change only after an explicit diff
confirmation.

## When to use

- The user invokes `/blog-update` or `/blog-update <topic>`.
- The user asks to save, publish, merge, or convert the current technical discussion into site content.

## Boundaries

- Use only the visible conversation, files the user provides, and files under the configured project root. Do not claim access to other sessions.
- Do not commit, push, deploy, or publish automatically.
- Do not write until the target entry, operation, and content type are clear.
- Existing entries require a unified diff and explicit confirmation before applying changes.
- New articles are first written as staging drafts with `draft: true` and remain drafts until the user explicitly asks to publish.
- Preserve the entry basename (canonical slug), body evidence, and existing metadata unless the user requests a change. Redirects are a separate task.

## Project discovery and configuration

Read `config.json` when available. The V11 configuration is relative to the
current project directory:

```json
{
  "projectRoot": ".",
  "contentDir": "src/content/entries",
  "fileExtension": ".mdx",
  "format": "astro-mdx",
  "packageManager": "npm"
}
```

Resolve the project root from the current working directory, then confirm that
`package.json`, `src/content/config.ts`, and the configured content directory
exist. A legacy `blogBasePath`/`.md` config is not a valid target for this
project; report it and use the discovered Astro project only after the user has
confirmed the target.

`uv` is optional for Python validators. If it is unavailable, use
`python3` and report dependency-backed checks that were skipped.

## Content contract

Every entry must use the current Astro schema contract:

```yaml
title: "<title>"
description: "<30-150 character summary>"
type: blog # blog | note | report
lang: zh-CN # zh-CN | en
published: 2026-10-02
draft: true
category: <category>
tags: [<tag1>, <tag2>]
readingTime: 8
```

- `blog` is a complete technical essay. It may use `featured`, `featuredOrder`, `featuredLabel`, and `image`.
- `note` is a short observation or experiment and never enters Featured.
- `report` is a dated source-first roundup and may use `coverage` and structured `sources` with URL values. It never enters Featured.
- `lang` defaults to `zh-CN`; set `en` explicitly for English content.
- `draft` entries must stay out of pages, Garden manifest, RSS, and Pagefind.
- `privateNote` is an internal schema field; never add it to generated content unless the user explicitly requests it, and never expose it in public output.

If `type` is omitted or ambiguous, propose a candidate and ask for confirmation
before writing. Do not silently classify a report or note as a blog.

The public selector is the final boundary: only public `blog` entries with
`featured: true` can be Featured, and the renderer filters invalid note/report
Featured flags again.

## Workflow

### 1. Resolve intent

Determine the topic/title, type, target basename, create/update mode, tags,
category, language, and whether the user wants a draft, preview, merge, or
publication. For `/blog-update` without a topic, infer a candidate from the
visible session and ask for confirmation before writing.

### 2. Build a source brief

Keep a concise internal brief containing the audience, 5–12 facts that must
survive, exact commands/errors/paths/config keys, decisions and tradeoffs,
claims needing soft wording, material to anonymize, and links/images to check.
Do not replace concrete evidence with generic prose.

### 3. Draft one complete MDX entry

Write frontmatter plus body. The Astro detail template supplies the page title,
so a body H1 is optional; if one is present it must match `title`. Remove a
duplicate legacy H1 when updating an existing entry. Preserve fenced code and
Mermaid content; use explicit language identifiers and `text` for logs or ASCII
diagrams. Escape only MDX-sensitive bare angle brackets outside code fences.

Do not include tool transcripts, approval prompts, raw tokens, cookies, private
URLs, private network addresses, or absolute user paths unless the material has
been sanitized and the user explicitly wants it.

### 4. Validate the complete draft

Run the skill validators:

```bash
python3 scripts/scan-sensitive-content.py <entry.mdx>
python3 scripts/validate-post.py <entry.mdx>
python3 scripts/validate-frontmatter.py <entry.mdx>
```

When available, also run:

```bash
uv run scripts/validate-codeblocks.py <entry.mdx>
```

Blocking failures include malformed or missing frontmatter, missing/mismatched
H1, invalid `type`/`lang`, invalid dates or report sources, unclosed fences,
broken relative links, session artifacts, likely secrets, and private network
material. Tag count, short summaries, and style preferences remain advisory.

Then run the configured Astro project checks from its root:

```bash
npm run check
npm run test
npm run build
npm run verify:html
npm run verify:public
```

Run `npm run test:e2e` when the change affects Garden filters, menus, details,
or another browser behavior. These checks prove that the entry reaches the
correct `/blog`, `/notes`, or `/reports` route and stays within public-output
boundaries.

### 5. Write or merge safely

For a new entry, write the `.mdx` file under `src/content/entries` with
`draft: true`, then report the path and checks. For an existing entry, read the
current file, merge only the requested material, show a unified diff, wait for
explicit confirmation, apply it, and rerun all applicable validators.

### 6. Optional assistance

Use the prompt files only when they reduce real risk:

| Prompt | Use when |
|---|---|
| `prompts/implement-agent.md` | Source material is long/noisy and extraction needs a separate pass. |
| `prompts/merge-agent.md` | Existing entry merge is large or structurally complex. |
| `prompts/review-agent.md` | Deterministic checks pass but semantic accuracy or evidence retention is still risky. |

Subagents are optional. The main editor owns the complete entry, validation,
diff, and all writes.

## Script reference

| Script | Gate | Purpose |
|---|---|---|
| `scripts/scan-sensitive-content.py` | Blocking | Detect likely secrets, credentials, private network references, emails, and absolute user paths. |
| `scripts/validate-post.py` | Blocking + advisory | Validate MDX/Markdown structure, fences, session leaks, and relative links. |
| `scripts/validate-frontmatter.py` | Blocking + advisory | Validate Astro entry fields and title/H1 consistency; report-only unless `--fix` is passed. |
| `scripts/validate-codeblocks.py` | Blocking when runnable | Parse supported Python, JSON, YAML, and shell blocks. |

## Red flags

Stop and ask the user when the target path is unclear or outside the configured
content directory, plausible secrets cannot be sanitized, an update would delete
substantial existing content, publication is requested without review, or three
revision attempts still leave blocking failures.

## Completion report

Report the created/updated path, content type, draft state, validators and
project checks run, skipped checks, diff status, and remaining advisory findings.
