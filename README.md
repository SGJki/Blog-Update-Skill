# Blog Update Skill

Intelligently merge Claude session content into fuwari-framework blog posts. Uses scripted Python validators (invoked via `uv run`) for deterministic structural checks, reserving LLM judgment for semantic review.

## Usage

```bash
# Create new article
/blog-update <topic> --tags [tag1,tag2] --category <category>

# Update existing article (auto-read existing tags/category)
/blog-update <topic>
```

## File Structure

```
blog-update/
├── skill.md                  # Skill spec (deployed as SKILL.md)
├── prompts/
│   ├── implement-agent.md      # Content generation (6-rule Extraction Contract)
│   ├── merge-agent.md          # Multi-granularity merge
│   └── review-agent.md         # 9-dimension quality review (v3)
├── scripts/                   # Deterministic validators (uv run)
│   ├── validate-post.py            # Body: B1/B2/B3/B4/D1/C2 (stdlib)
│   ├── validate-codeblocks.py      # Code syntax: C1 (pyyaml)
│   └── validate-frontmatter.py     # Frontmatter: 10 checks + 6 auto-fixes (pyyaml)
├── config.json                # User configuration (NOT overwritten by deploy)
├── LICENSE
└── README.md
```

**Deploy note:** source repo uses lowercase `skill.md`; Claude Code loader expects uppercase `SKILL.md`. Copy as `cp skill.md ~/.claude/skills/blog-update/SKILL.md`. Do NOT overwrite the deployed `config.json` (it contains the user's local `blogBasePath`).

## Workflow

```
Main Session
    │
    ├─ Step 1: Read config.json; verify `uv` installed
    ├─ Step 2: Determine topic/tags/category + mode (new/merge)
    ├─ Step 3: Collect raw session context
    ├─ Step 4: Generate body (follow prompts/implement-agent.md)
    ├─ Step 5: Merge with existing file if present (follow prompts/merge-agent.md)
    ├─ Step 6: Write to file → review (follow prompts/review-agent.md)
    ├─ Step 6.5: Body validation via scripts (validate-post.py + validate-codeblocks.py)
    │           └─ FAIL → loop back to Step 4 (shared 3-iteration budget)
    ├─ Step 7: Generate frontmatter + H1, strip implement-agent's trailing HTML
    │           comments, write final file
    ├─ Step 7.5: Frontmatter validation via scripts (validate-frontmatter.py)
    │           └─ FAIL (non-auto-fixable) → STOP and ask user
    └─ Step 8: Report completion
```

Steps 4–6.5–6 share ONE 3-iteration budget. Step 7.5 has its own internal auto-fix loop (max 3 iterations, does not count against the main budget).

## Merge Algorithm

See [prompts/merge-agent.md](prompts/merge-agent.md) for the full multi-granularity algorithm (title → paragraph → richness comparison).

## Validators

| Script | Step | Coverage | Deps |
|--------|------|----------|------|
| `scripts/validate-post.py` | 6.5 | B1 heading, B2 code blocks, B3 lists, B4 paragraph, D1 session-noise, C2 links | stdlib |
| `scripts/validate-codeblocks.py` | 6.5 | C1-syntax: actual parser checks (python `ast.parse`, json `json.loads`, yaml `yaml.safe_load`, bash `bash -n`) | pyyaml>=6.0 |
| `scripts/validate-frontmatter.py` | 7.5 | 10 frontmatter checks + 6 auto-fixes on 6-field fuwari schema | pyyaml>=6.0 |

All invoked via `uv run` (PEP 723 inline metadata auto-installs deps on first run).

## Configuration

Location: `~/.claude/skills/blog-update/config.json`

```json
{
  "blogBasePath": "your/blog/posts/path",
  "fileExtension": ".md"
}
```

## Version History

| Version | Major Changes |
|---------|--------------|
| V1 | Basic blog update |
| V2 | Subagent architecture separation |
| V3 | Smart multi-granularity merge |
| V4 | CSO optimization, prompts split, <200 lines |
| V5 | Merge algorithm enhancement, Red Flags safety check |
| V6 | Full English localization |
| V7 | Main-session-only architecture (no subagents); 6-rule Extraction Contract (E1–E6); review-agent v3 with 9 dimensions across 3 categories |
| V8 | Scripted validation: Step 6.5 body validators + Step 7.5 frontmatter validator (`uv` + PEP 723). review-agent P0 narrowed to A3-only (structural checks B2/D1 delegated to scripts for deterministic reliability). |
