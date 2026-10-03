# Blog Update Skill

Convert technical agent sessions into Astro MDX knowledge-garden entries. V11
keeps the V10 safety workflow while adding the current `blog | note | report`
content contract, type-specific routes, and project-level static-output checks.

## Usage

```text
/blog-update <topic> --type blog --tags [tag1,tag2] --category <category>
/blog-update <topic> --type note
/blog-update <topic> --type report
```

When the type is omitted or ambiguous, propose a candidate and ask before
writing. New entries are staged with `draft: true`.

## Workflow

```text
visible session
    -> internal source brief
    -> complete MDX entry with Astro frontmatter
    -> sensitive + structural + frontmatter validators
    -> npm project checks and public-output checks
    -> new draft or existing-entry unified diff
    -> explicit confirmation before applying an existing-entry change
```

The main editor owns all writes. Optional prompt files assist extraction, merge,
or semantic review; they do not authorize subagent writes.

## Current project contract

Entries live in `src/content/entries/*.mdx` and use:

```yaml
title: <title>
description: <summary>
type: blog # blog | note | report
lang: zh-CN # zh-CN | en
published: 2026-10-02
draft: true
category: <category>
tags: [<tag1>, <tag2>]
readingTime: 8
```

`blog` entries may be Featured. `note` and `report` entries remain in their
own lists even if an invalid `featured: true` flag is present. Reports may add
`coverage` and structured `sources`. The public selectors exclude drafts from
pages, Garden, RSS, and Pagefind.

## File structure

```text
blog-update/
├── SKILL.md / skill.md       # synchronized loader entrypoints
├── config.json               # absolute Astro project configuration
├── prompts/
│   ├── implement-agent.md    # optional evidence extraction
│   ├── merge-agent.md        # optional existing-entry merge
│   └── review-agent.md       # optional semantic/evidence review
└── scripts/
    ├── scan-sensitive-content.py
    ├── validate-post.py
    ├── validate-frontmatter.py
    ├── validate-codeblocks.py
    └── check-prompts.py
```

## Configuration

```json
{
  "projectRoot": "/Volumes/mySSD/Projects/Web/SGJki-blog",
  "contentDir": "src/content/entries",
  "fileExtension": ".mdx",
  "format": "astro-mdx",
  "packageManager": "npm"
}
```

`projectRoot` in `config.json` is the source of truth for the blog root — an
absolute path to the Astro blog repository, not the caller's working
directory. The skill resolves `contentDir` and entry paths against it and
checks for `package.json`, `src/content/config.ts`, and the content directory
there. If `projectRoot` is absent or relative, it falls back to resolving from
the current working directory. A legacy
`blogBasePath` pointing to an old posts directory must be reported before use.

## Validators

| Script | Gate | Coverage |
|---|---|---|
| `scan-sensitive-content.py` | Blocking | Secrets, credentials, private URLs/hosts, emails, absolute user paths |
| `validate-post.py` | Blocking + advisory | Markdown/MDX headings, fenced blocks, session leaks, relative `.md`/`.mdx` links |
| `validate-frontmatter.py` | Blocking + advisory | Astro fields, `type`, `lang`, dates, report sources, title/H1 agreement |
| `validate-codeblocks.py` | Blocking when runnable | Python, JSON, YAML, and shell syntax |

After skill validators, run from the project root:

```bash
npm run check
npm run test
npm run build
npm run verify:html
npm run verify:public
```

Run `npm run test:e2e` for browser-behavior changes. `uv` is optional; use
`python3` when it is unavailable and report skipped dependency-backed checks.

## Safety invariants

- New content stays `draft: true`.
- Existing entries require a displayed diff and explicit confirmation.
- Canonical basenames and body evidence are preserved.
- No automatic commit, push, deploy, or publish.
- Redirects and bulk migration are separate tasks.
- `SKILL.md` and `skill.md` must remain byte-for-byte synchronized.

## Verification

```bash
PYTHONPYCACHEPREFIX=/tmp/blog-update-skill-pycache python3 -m py_compile scripts/*.py
python3 scripts/check-prompts.py
```

The skill-creator quick validator should also be run when available.

## Version history

| Version | Major changes |
|---|---|
| V10 | Minimal safety-first workflow, draft-by-default, sensitive-content gate |
| V11 | Astro MDX entries, `blog`/`note`/`report` contract, project checks, public-output validation |
