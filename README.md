# Blog Update Skill

Intelligently merge Claude session content into fuwari-framework blog posts.

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
├── skill.md              # Main skill file (Overview + Workflow)
├── prompts/             # Subagent prompts
│   ├── implement-agent.md  # Content generation
│   ├── merge-agent.md      # Smart merge
│   ├── review-agent.md     # Quality review
│   └── format-agent.md     # Formatting
└── config.json          # User configuration
```

## Workflow

```
Main Session
    │
    ├─ Step 1: Check config, get blogBasePath
    ├─ Step 2: Check file exists -> collect tags/category
    ├─ Step 3: Extract session context
    ├─ Step 4: implement-agent (generate content)
    ├─ Step 5: merge-agent (multi-granularity smart merge)
    ├─ Step 6: review-agent (quality review)
    │         └─ FAIL -> Return to Step 4 revision (max 3 times)
    ├─ Step 7: format-agent (generate frontmatter)
    └─ Step 8: Main session writes file, report completion
```

## Merge Algorithm

### Level 1: Title Similarity (Jaccard)
- > 70%: Same topic, keep existing
- < 60%: Different topic, add new
- 60-70%: [edge-1]

### Level 2: Paragraph Similarity (TF-IDF + Cosine)
- > 60%: Duplicate content, keep existing
- < 30%: Completely different, add new
- 30-60%: [edge-2]

### Level 3: Content Richness Comparison
- Sentence count (30%)
- Code example count (40%)
- Technical term density (30%)

See [prompts/merge-agent.md](prompts/merge-agent.md) for details.

## Edge Cases

When encountering `[edge-N]` markers:
1. User decides how to handle
2. Record to edge case handling record table in merge-agent.md
3. Evaluate whether to update algorithm rules

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
