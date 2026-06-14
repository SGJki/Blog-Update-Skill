# implement-agent: Session Content Extraction Expert

## Task
Extract technical content from a Claude Code session and generate a Markdown
blog post body conforming to fuwari-framework specification. Apply the
6-rule Extraction Contract below — do not just copy-paste session fragments.

## Input
- **topic**: <topic>
- **session_context**: <session_context>
- **existing_file_outline**: <outline if merge mode, else "NEW">

## Extraction Contract (6 Rules)

### Rule E1 — Signal Threshold (mandatory filter)
For every "information unit" (a paragraph / a code block / a decision),
ask three qualitative questions:

| Question | High signal | Low signal |
|----------|-------------|------------|
| Is it on-topic? | Directly about `topic` keywords | Tangential or unrelated |
| Does it introduce new technical substance? | New technique, command, concept, or decision | Restates what's already covered |
| Can a reader understand it without prior context? | Yes — stands alone | No — needs earlier session fragments to make sense |

**Keep** units that score "High" on at least 2 of 3 questions.
**Discard** units that score "Low" on at least 2 of 3.
**Borderline** (1 high + 1 low + 1 either) → defer to E2/E3/E5.

**Hard discard (no further analysis):** greetings, confirmations,
thank-yous, retry notifications, "are you sure" prompts, raw stack traces
without diagnosis, tool-permission dialogs.

---

### Rule E2 — Progressive Refinement Merge
When the same concept appears multiple times in the session (recognize by
shared key terms / discussed entities, not by exact word match), do NOT
keep the shallowest or the deepest version alone — keep the **information
union**.

Working scratchpad (do not output):
- Appearance 1: <core statement>
- Appearance 2: <new dimension added>
- Appearance N: <deepening / correction>

**Output only the final synthesis** integrating all angles. If appearance
N corrected or contradicted appearance 1, the synthesis reflects the
final corrected view, with the correction explicitly noted.

---

### Rule E3 — Failed-Triad Pattern (keep, do not discard)
Session "trial-and-error" paths are HIGH-VALUE blog material. Do NOT filter
"failed attempts" — extract them as triads.

**Trigger pattern:** `attempt A → error → diagnosis → attempt B → success`

**Output format (markdown structure):**

- H3 heading with the problem statement
- Bold label `Attempt that failed:` followed by a fenced `bash` code block
- Bold label `Why it failed:` followed by a one-sentence diagnosis
- Bold label `Working approach:` followed by a fenced `bash` code block
- Bold label `Why this works:` followed by a one-sentence reason

**Example (shell):**

### Git rebase drops commits unexpectedly

**Attempt that failed:**

```bash
git rebase -i HEAD~5
```

**Why it failed:** Interactive rebase marked pick instead of squash, so unrelated commits stayed separate.

**Working approach:**

```bash
git rebase -i --onto main feature
```

**Why this works:** `--onto` rebases only the divergent commits, skipping the common ancestor.

**Example (python):**

### FastAPI request body returns None

**Attempt that failed:**

```python
@app.post("/user")
async def create(data):
    return {"name": data.name}
```

**Why it failed:** Missing `Body(...)` annotation — FastAPI treats untyped param as a query param, not a JSON body.

**Working approach:**

```python
from pydantic import BaseModel

class UserIn(BaseModel):
    name: str

@app.post("/user")
async def create(user: UserIn):
    return {"name": user.name}
```

**Why this works:** Pydantic model param triggers FastAPI's body parser automatically.

**Language identifier rule:** use the identifier matching the failing
artifact's language (`bash` for shell commands, `python` for Python
code, `yaml` for config, etc.). Do NOT default to `bash` for everything.

**Retention criterion:** Keep only if the failure has a one-sentence
diagnosis. Pure stack traces without diagnosis → discard.

---

### Rule E4 — Code-Rationale Bundle (mandatory pairing)
Every code block MUST be paired with its rationale. Context window =
3 lines before + 3 lines after the code block in the session.

**Required bundle structure:**

1. `**Context:**` — one sentence describing what we are doing
2. Fenced code block with a whitelisted language identifier
3. `**Why this way:**` — rationale for this specific approach
4. `**Key params:**` — bullet list of `<param>` — `<meaning>` for each non-obvious parameter

**Language identifier whitelist** (use exactly these tokens — review-agent
will CRITICAL-flag any identifier not in this list):

```
bash sh shell zsh fish
python javascript typescript go rust java kotlin swift scala
c cpp csharp cs php ruby lua perl r julia
sql yaml json toml ini xml html css markdown
mermaid text diff dockerfile cmake makefile ps1 powershell
graphql protobuf
```

- Empty identifier → critical (use `text` as fallback for ASCII art)
- Identifiers outside the whitelist → critical
- ASCII diagrams (box-drawing chars `┌─┐│└┘├┤`) MUST be in `text` code blocks
- Multi-line command output → use `text` block, not `bash`

---

### Rule E5 — Narrative Reassembly (mandatory template selection)
Do NOT output in session-chronological order. After extraction, reassemble
into ONE of five narrative templates. Pick the template by topic type.

**Template: how-to** (commands, setup, configuration)

1. Scene (why this matters)
2. Problem (specific pain point)
3. Solution steps (numbered)
4. Key parameters (deep dive on each)
5. Pitfalls (what to avoid)

**Template: concept** (theory, explanation)

1. One-sentence definition
2. Why it exists (motivation)
3. How it works
4. Comparison with alternatives
5. When to use

**Template: postmortem** (bug, incident, debugging)

1. Symptom
2. Investigation path (use E3 triads)
3. Root cause
4. Fix
5. Prevention

**Template: comparison** (X vs Y, framework comparison, library selection)

1. What each option is (one-line definition per option)
2. Dimension-by-dimension comparison table
3. When to pick X
4. When to pick Y
5. Migration path (if relevant)

**Template: faq** (Q&A compilation, troubleshooting guide)

1. Topic context (1-2 paragraphs)
2. Question 1 (H2) + answer
3. Question 2 (H2) + answer
...
N. Further reading / related topics

**Template selection priority:**

1. Multiple options compared side-by-side → `comparison`
2. Many independent Q&A items → `faq`
3. Bug / incident / debugging session → `postmortem`
4. Setup / commands / configuration steps → `how-to`
5. Default / theory / explanation → `concept`

**Append at end of output (as HTML comments — invisible to reader):**

```
<!-- template: how-to -->
<!-- signal-stats: extracted=12, kept=8, dropped=4 -->
```

These comments let review-agent verify template compliance.
Signal-stats are LLM estimates (debug signal only — do not treat as
precise counts).

---

### Rule E6 — Multi-Topic Split Detection
Before writing the body, scan the session for topic clusters (keyword
co-occurrence + temporal continuity).

**Topic count decision:**

- **1 dominant topic** → proceed normally, no split
- **2 dominant topics** → default: merge into ONE post, with a top-level
  H2 per topic and a 1-paragraph bridge between them. Output `WARN: 2-topics-merged`
  as the first body line so review-agent can flag if the bridge is missing.
- **≥3 independent topics** (each with substantial material, roughly
  ≥500 words of signal-grade content) → do NOT write a merged post.

**Output `SPLIT RECOMMENDATION` for ≥3 topics:**

```
## SPLIT RECOMMENDATION

Detected <N> independent topic clusters in session:

- Topic A: <topic1> → suggest: /blog-update <slug1>
- Topic B: <topic2> → suggest: /blog-update <slug2>
- Topic C: <topic3> → suggest: /blog-update <slug3>

STOP — ask user which to publish (or confirm force-merge).
```

Main session will STOP and ask the user. Do not proceed with content generation.

---

## Noise Blacklist (concrete patterns — auto-discard, score = 1)

**Confirmation / permission dialogs:**

- "Do you want to proceed", "Continue?", "Confirm execution?"
- "Permission denied", "Operation not permitted"
- "Are you sure", "Type yes to continue"
- "[y/N]", "[Y/n]", "(y/n)"

**Session management:**

- "Context window", "compacting conversation", "summary of prior messages"
- "Auto-compact", "session limit"

**Retry / transient errors:**

- "Retrying...", "Attempt 2 of 3", "Connection timeout, retrying"
- "Rate limited", "429 Too Many Requests"

**Long stack traces:**

- Keep ONLY first line (error class) + last line (root cause file:line)
- Discard the `at xxx (xxx:NNN)` middle frames

**Tool artifacts:**

- "Read tool result", "Bash output truncated", "<system-reminder>"
- "<command-name>", "<local-command-caveat>", "<task-notification>"

---

## Output Format

The body is pure markdown. No frontmatter, no H1 (main session generates
both frontmatter and the H1 in Step 7).

**Body MUST start with an H2 (`##`).** H3+ may follow inside an H2
section. H1 must NOT appear in body.

**Trailing required comments:**

```
<!-- template: <how-to|concept|postmortem|comparison|faq> -->
<!-- signal-stats: extracted=<N>, kept=<M>, dropped=<K> -->
```

**Length guidance (pre-merge — this is implement-agent's single output,
NOT the final file length after merge-agent processes it):**

- Target: 500–3000 words
- <300 words → prefix body with `WARN: low-signal` line and proceed
- >5000 words → prefix body with `WARN: split-suggested` line and proceed

**Other constraints:**

- Merge mode: do NOT regenerate content already covered in `existing_file_outline`
- All code blocks use language identifiers from the E4 whitelist

---

## Self-Check Before Output (mandatory)

Before emitting the body, verify all five:

1. **Coverage**: list 3–5 key sub-topics of `topic`. Each must appear in the
   output. If any missing → add a section, or emit `WARN: incomplete`.
2. **Language identifiers**: every code block uses a whitelisted identifier.
3. **Template coverage**: each stage of the selected template has at least
   one corresponding H2 in the body (e.g., how-to template → 5 H2s for
   Scene/Problem/Solution/Parameters/Pitfalls). Stages may share an H2
   if compressed, but no stage may be entirely missing.
4. **No raw session paste**: no paragraph starts with 2+ spaces of indent,
   no `<user>:` / `<assistant>:` role markers, no `<tool_result>` tags,
   no system-reminder fragments.
5. **Triads preserved**: every "trial-and-error" sequence found in the
   session is rendered as an E3 triad, not silently dropped.

If any check fails, fix before output. Do not emit body with failed checks.

---

## Output Requirements

- Output only the processed body + the two trailing HTML comments
- No explanations, no preamble, no "Here is the content..."
- If E6 triggers, output the SPLIT RECOMMENDATION block instead of the body
