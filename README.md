# Blog Update Skill

Convert technical agent sessions into Fuwari blog posts. V10 uses a minimal, safety-first workflow: one main editor drafts a complete article, deterministic validators check it, and existing posts are changed only after a user-approved diff.

## Usage

```bash
# Create or preview a draft article
/blog-update <topic> --tags [tag1,tag2] --category <category>

# Infer the topic from the visible session, then ask for confirmation
/blog-update

# Merge into an existing article after showing a diff
/blog-update <topic>
```

## File Structure

```text
blog-update/
├── skill.md                      # Canonical V10 skill spec
├── SKILL.md                      # Loader-compatible copy in this worktree
├── prompts/
│   ├── implement-agent.md        # Optional extraction assist for long/noisy sources
│   ├── merge-agent.md            # Optional complex merge assist
│   └── review-agent.md           # Optional semantic/evidence review
├── scripts/
│   ├── scan-sensitive-content.py # Blocking safety scan, stdlib
│   ├── validate-post.py          # Markdown structure/session leak/link checks, stdlib
│   ├── validate-codeblocks.py    # Optional parser checks for code fences, pyyaml
│   ├── validate-frontmatter.py   # Report-only by default; --fix writes safe fixes
│   └── check-prompts.py          # V10 fixture/contract tests
├── config.json                   # Local deployment config
├── LICENSE
└── README.md
```

## Workflow

```text
source material / visible session
    -> internal source brief
    -> single complete draft with frontmatter + H1 + body
    -> sensitive scan + structural validators
    -> new draft path or existing-article unified diff
    -> explicit user confirmation before applying existing-article changes
```

Default behavior changed in V10:

- New articles start as `draft: true`.
- Sensitive Content Scan is a blocking gate before any article is offered as publishable.
- `uv` is optional. Use it when available for PEP 723 dependencies; otherwise run stdlib checks and report skipped dependency-backed checks.
- `validate-frontmatter.py` is report-only by default. It writes only with `--fix`.
- `--fix` must not change `draft: true` to `false`.
- Subagent prompts are optional assistive tools, not the default path.

## Validators

| Script | Gate | Coverage | Deps |
|---|---|---|---|
| `scripts/scan-sensitive-content.py` | Blocking | Likely secrets, auth headers, cookies, private keys, emails, private IP/URL/host references, absolute user paths | stdlib |
| `scripts/validate-post.py` | Blocking + advisory | H1 presence, duplicate H1, fence language/closure, session/tool leaks, internal `.md` links, style advisories | stdlib |
| `scripts/validate-frontmatter.py` | Blocking + advisory | Required Fuwari fields, valid date, boolean draft, title/H1 consistency, tags/category shape | pyyaml optional; simple fallback parser exists |
| `scripts/validate-codeblocks.py` | Blocking when runnable | Parser-backed checks for Python, JSON, YAML, Bash-like fences | pyyaml + local bash when available |

Recommended local verification:

```bash
python3 -m py_compile scripts/*.py
python3 scripts/check-prompts.py
git diff --check
```

## Configuration

Deployed config location:

```text
~/.claude/skills/blog-update/config.json
```

Example:

```json
{
  "blogBasePath": "your/blog/posts/path",
  "fileExtension": ".md"
}
```

Do not overwrite a user's deployed `config.json` during installation; it contains their local blog path.

## Deployment Note

Historically the repo used lowercase `skill.md` while some loaders expected uppercase `SKILL.md`. Keep both contents synchronized when editing this repo. In this worktree, `SKILL.md` may be a regular file instead of the historical symlink; do not change that type unless you explicitly intend to update the compatibility layer.

## Version History

| Version | Major Changes |
|---|---|
| V1 | Basic blog update |
| V2 | Subagent architecture separation |
| V3 | Smart multi-granularity merge |
| V4 | CSO optimization, prompts split, <200 lines |
| V5 | Merge algorithm enhancement, Red Flags safety check |
| V6 | Full English localization |
| V7 | Main-session-only architecture; 6-rule Extraction Contract; review-agent v3 |
| V8 | Scripted validation for body/code/frontmatter via `uv run` |
| V9 | Evidence-first workflow with optional subagents and Evidence Ledger |
| V10 | Minimal safety-first workflow: complete draft first, default `draft: true`, sensitive-content gate, report-only frontmatter validator, optional `uv`, diff/confirmation for existing posts |
