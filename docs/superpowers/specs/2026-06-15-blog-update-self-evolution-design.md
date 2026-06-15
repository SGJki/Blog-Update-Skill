# Blog-Update Skill 自进化体系设计

**Date**: 2026-06-15
**Status**: Design — awaiting user review
**Author**: sgjki + Claude (brainstorming session)

---

## 0. TL;DR

给 blog-update skill 接一套基于 hermes 方法论的自进化闭环：trace → reward → 结晶 → probationary → trial 攒 η → 晋升/淘汰 → retrieval 注入 → 改变行为。用纯文件存储、Replay-First 评估、用户在 crystallize 环节批准。目标：让 skill 从自己的历史 invocation 中长出可维护的 validator 规则 / prompt 补丁 / Step 2 推断启发式。

---

## 1. 范围

### 1.1 可进化的"面"

| 面 | 候选 type | 是否纳入 |
|----|-----------|----------|
| Validators（`scripts/validate-*.py`） | `validator_rule` | ✅ |
| Subagent prompts（`prompts/{implement,merge,review}-agent.md`） | `prompt_patch` | ✅ |
| Step 2 推断逻辑（`skill.md` Step 2 区域） | `step2_heuristic` | ✅ |
| 主流程编排（`skill.md` Step 1, 3-8） | — | ❌ blast radius 太大 |
| Step 7 frontmatter 生成 | — | ❌ 不在本次范围 |

### 1.2 不在本次范围

- L1/L2/L3 多层记忆（hermes 的分层记忆架构）——单一 traces.jsonl 即可
- 外部 MemOS 集成、JSON-RPC server、sidecar 进程
- 跨用户/跨项目共享记忆
- Embedding-based retrieval（先用 Jaccard）

---

## 2. 架构概览

### 2.1 新增组件

| 组件 | 位置 | 职责 |
|------|------|------|
| `scripts/trace-capture.py` | skill 内 | `/blog-update` Step 8 末尾调用，append 一条 trace 到 `traces.jsonl` |
| `scripts/retrieval-inject.py` | skill 内 | `/blog-update` Step 1 后调用，输出 `active.json`（top-K 历史 trace + 激活候选） |
| `scripts/replay-eval.py` | skill 内 | `/blog-update-evolve` 阶段 3 调用，对候选跑回放评估 |
| `scripts/beta-posterior.py` | skill 内 | 计算 η、执行状态机转换（probationary→promoted/eliminated） |
| `scripts/heuristic-check.py` | skill 内 | 候选落盘前的语法/安全性兜底 |
| `prompts/crystallize-agent.md` | skill 内 | 第 4 个 subagent，提议候选 patch |

### 2.2 状态目录布局

放在 blog 项目仓库内（不在 skill 目录内）：

```
<blog repo root>/.blog-update-self/
├── traces.jsonl       # append-only, 1 line = 1 /blog-update invocation
├── candidates.jsonl   # append-only, 1 line = 1 candidate (all states)
├── state.json         # last_evolve_trace_count, last_evolve_timestamp, promoted_ids[]
├── active.json        # 当前 invocation 的注入内容 + 激活候选 ID（每次 invocation 覆盖写）
├── warnings.log       # 所有非致命异常的 append-only 日志
└── evolve.lock        # evolve 期间持有，防止并发 invocation 撞 active.json
```

**目录发现**：从 `config.json:blogBasePath` 向上查找 git toplevel；找不到则 fallback 到 `blogBasePath/..`。

### 2.3 数据流闭环

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   /blog-update invocation                                       │
│   ├─ Step 1: read config.json                                   │
│   ├─ Step 1.5: retrieval-inject.py → active.json  ◀─────────┐  │
│   ├─ Step 2: 推断 topic/tags/category (注入 similar_traces) │  │
│   ├─ Step 4: implement-agent (注入 past pitfalls)           │  │
│   ├─ Step 6.5: validator 临时 patched 副本（probationary 激活）│  │
│   ├─ Step 8: trace-capture.py ──→ traces.jsonl  ◀─────┐    │  │
│   └─ (next invocation) post-hoc 回填 edit_distance ─────────┐ │  │
│                                                              │ │  │
│   /blog-update-evolve (manual or auto after 10 traces)       │ │  │
│   ├─ 阶段1: 收集 evolve-context.json                         │ │  │
│   ├─ 阶段2: crystallize-agent 提议候选                       │ │  │
│   ├─ 阶段3: heuristic_check + replay_eval                    │ │  │
│   ├─ 阶段4: 用户批准 → probationary                          │ │  │
│   ├─ 阶段5: 扫现有 probationary，η 驱动 promote/eliminate    │ │  │
│   └─ promoted → 应用 patch + git commit ─────────────────┐   │ │  │
│                                                          │   │ │  │
│   retrieval-inject 读 promoted + probationary 候选 ───────┼───┘ │  │
│                                                          │     │  │
│   post-hoc: git diff 回填上条 trace ◀──────────────────────────┘
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. Trace Schema 与捕获

### 3.1 触发

`skill.md` Step 8 末尾主 session 调用：

```bash
uv run scripts/trace-capture.py \
  --post "<abs path>" \
  --topic "<topic>" \
  --topic-provided <bool> \
  --inferred-tags '["Git","DevOps"]' \
  --inferred-category "DevOps" \
  --mode <create|merge> \
  --template <how-to|concept|postmortem|comparison|faq> \
  --review-iters <int> \
  --validator-exits '<vp>,<vc>,<vf>' \
  --validator-issues '<json>' \
  --auto-fixes <int> \
  --final-status <PASS|FAIL|STOPPED> \
  [--score <1-5>]
```

`active_candidate_ids` 由 trace-capture.py 从 `active.json` 读取后写入 trace。

### 3.2 单条 trace 的 JSON schema

```json
{
  "trace_id": "2026-06-15T103000_git-rebase-workflow",
  "timestamp": "2026-06-15T10:30:00Z",
  "topic": "Git Rebase 工作流",
  "topic_provided": false,
  "inferred_tags": ["Git", "DevOps"],
  "inferred_category": "DevOps",
  "mode": "create",
  "post_path": "/abs/path/to/post.md",
  "template": "how-to",
  "validators": {
    "validate_post":        {"exit": 0, "criticals": 0, "majors": 0, "minors": 1},
    "validate_codeblocks":  {"exit": 1, "criticals": 1, "majors": 0, "minors": 0},
    "validate_frontmatter": {"exit": 0, "auto_fixes_applied": 2}
  },
  "review_iterations": 1,
  "final_status": "PASS",
  "post_hoc_edit_distance": null,
  "user_score": null,
  "active_candidate_ids": ["cand_007"]
}
```

### 3.3 回填机制

`post_hoc_edit_distance` 与 `user_score` 在本次 invocation 内拿不到，由下次 invocation 启动时回填：

- **post_hoc_edit_distance**：trace-capture.py 启动时 `git log --since=<prev_trace.ts> -- <prev_trace.post_path>` 拿 diff；用 char-level Levenshtein 计算；cap 在 1000；存为整数（已编辑字符数），归一化在 reward 公式里做。**首次 invocation**（无 prev_trace）跳过此回填，字段保持 null；reward 公式见 §4.2 处理 null（s3 视为缺省、不参与融合）。
- **user_score**：用户通过 `--score <1-5>` 可选参数注入；缺省保持 null。

---

## 4. Reward 公式

### 4.1 四路信号

| 信号 | 计算 | 权重 |
|------|------|------|
| `s1` validator 健康 | 对每个 validator 算 `1 - (criticals + 0.5·majors) / 5`，clamp 到 [0,1]；**三个 validator 取平均** | 0.30 |
| `s2` retry 效率 | `1 - review_iterations / 3` | 0.20 |
| `s3` post-hoc 稳定 | `1 - min(1, edit_distance / 1000)` | 0.30 |
| `s4` 用户打分 | `score / 5`（缺省时不参与） | 0.20 |

### 4.2 融合规则

- 全信号存在：`R = 0.30·s1 + 0.20·s2 + 0.30·s3 + 0.20·s4`
- s4 缺省：`R = (0.30·s1 + 0.20·s2 + 0.30·s3) / 0.80`（重新归一化）
- s3 缺省（首次 invocation，无 post_hoc_edit_distance）：`R = (0.30·s1 + 0.20·s2 + 0.20·s4) / 0.70`；s4 也缺省时再降为 `R = (0.30·s1 + 0.20·s2) / 0.50`

通用规则：把缺省信号的权重从分子移除、分母同步减去其权重。

### 4.3 η 更新（Beta 后验）

每个候选维护 `(α, β)`：

```
α += R
β += (1 - R)
η = α / (α + β)
```

**归因规则**：trace 里 `active_candidate_ids` 的所有候选都拿到本次 R 的**全量**更新（不做均摊）。理由：候选之间不互斥（一个 validator 新规则 + 一个 prompt patch 可同时激活），均摊会人为压低 η。

---

## 5. 候选 Schema 与生命周期

### 5.1 JSON schema

```json
{
  "candidate_id": "cand_007",
  "type": "validator_rule" | "prompt_patch" | "step2_heuristic",
  "target": {
    "file": "scripts/validate-post.py",
    "anchor": "WHITELIST_LANGS",
    "operation": "append" | "replace_block" | "insert_after_line"
  },
  "patch": "<content depends on type>",
  "trigger": null,
  "rationale": "≤2 sentences, why this candidate",
  "status": "proposed" | "probationary" | "promoted" | "eliminated" | "rejected" | "eliminated_post_promote",
  "eta": {"alpha": 0.0, "beta": 0.0},
  "trials": 0,
  "replay_eval": {
    "precision": 0.85,
    "recall": 0.60,
    "fp_samples": ["posts/foo.md:42"],
    "sample_count": 10,
    "ran_at": "2026-06-15T10:00:00Z"
  },
  "approval": {"user": "sgjki", "decision": "approve", "timestamp": "..."},
  "dedup_hash": "sha1(...)",
  "promoted_commit_sha": null,
  "promoted_at": null,
  "created_at": "...",
  "updated_at": "..."
}
```

### 5.2 type × patch 语义

| type | target.file | patch 形态 | operation |
|------|-------------|-----------|-----------|
| `validator_rule` | `scripts/validate-*.py` | 新函数源码 / 新常量列表项 / 新 regex pattern | `append` 到 anchor |
| `prompt_patch` | `prompts/{implement,merge,review}-agent.md` | markdown 片段（一条新规则或 Noise Blacklist 新模式） | `insert_after_line` 锚到 H2/H3 |
| `step2_heuristic` | `skill.md` Step 2 区域 | markdown 提示语句 | `insert_after_line` 锚到 Step 2 末尾 |

### 5.3 状态机

```
                  ┌── heuristic_check pass + replay_eval precision≥0.5
                  │   + user approve
crystallize-agent ─┤
   提议候选        │
                  ├── heuristic_check fail ─────→ rejected (audit only)
                  │
                  └── replay_eval precision<0.5  ─→ rejected
                                │
                                ▼
                          probationary
                                │
                       trial 累积, η 更新
                                │
                                ▼
                    ┌───────────┴───────────────┐
                    │                           │
            trial≥5 AND η>0.70          trial≥5 AND η<0.30
                    │                           │
                    ▼                           ▼
               promoted                  eliminated
              (应用 patch + git commit)
                                                │
                                                ▼
                                    5≤trial<10 AND 0.30≤η≤0.70
                                                │
                                                ▼
                                        继续 probationary
                                                │
                                    trial≥10 仍 inconclusive
                                                │
                                                ▼
                                            eliminated
```

### 5.4 阈值与上限

- promote: trial ≥ 5 AND η > 0.70
- eliminate: trial ≥ 5 AND η < 0.30
- inconclusive 期: 5 ≤ trial < 10 AND 0.30 ≤ η ≤ 0.70
- trial ≥ 10 仍 inconclusive → 强制 eliminated
- promoted 候选总数硬上限：50（防止累积；超过则 crystallize-agent 必须 propose "合并/精简" 类候选）

### 5.5 patch 长度上限

| type | 上限 |
|------|------|
| `validator_rule` | 100 行 |
| `prompt_patch` | 30 行 |
| `step2_heuristic` | 5 行 |

### 5.6 dedup hash

`sha1(type + "\x00" + target.file + "\x00" + normalize_whitespace(patch))`

crystallize-agent 提议的候选 dedup hash 与既有候选冲突 → 静默丢弃。

### 5.7 promoted 的语义

promoted **不是 η 跟踪的终点**，而是"patch 永久写入"的临界点。具体语义：

1. patch 永久应用到目标文件（不是临时副本）
2. `git add <target.file> && git commit -m "chore(self-evolve): promote cand_007 — <rationale>"`
3. candidate.status = promoted，写入 `promoted_commit_sha` + `promoted_at`
4. **继续在 active_candidates 中**——retrieval-inject 仍把 promoted 候选 ID 注入到 active.json，trace-capture 继续记录、η 继续累计
5. **不再走临时 patched 副本机制**——patch 已在原文件，validator 直接跑原版即可
6. η 后续只用于监控（§8.3 的"建议 revert"分支），不再触发状态转换

### 5.8 eliminated 的副作用

1. 应用 patch 到目标文件
2. `git add <target.file> && git commit -m "chore(self-evolve): promote cand_007 — <rationale>"`
3. 写入 candidate status=promoted + git commit SHA
4. 从 probationary 池移除

### 5.8 eliminated 的副作用

- patch 永不应用
- 从 retrieval-inject 候选池移除
- 保留在 `candidates.jsonl` 作为审计 + 防 crystallize-agent 重复提议

### 5.9 heuristic_check 兜底

候选落盘前必须通过：

- patch 能 parse（Python `ast.parse`；markdown 走行数计数 + 起止符配对）
- target.file 存在、anchor 找得到
- operation 类型与 type 兼容
- patch 长度 ≤ 上限
- 不含 dangerous token：`os.system`, `subprocess`, `eval(`, `exec(`, `__import__`, `rm -rf`, `open(..., 'w')` 之外的文件写入（白名单 `pathlib.Path.write_text` 例外）

---

## 6. Crystallize 流程（/blog-update-evolve）

### 6.1 触发

- 手动：用户调用 `/blog-update-evolve`
- 自动：主 session 在 `/blog-update` 启动时检查 `len(traces.jsonl) - state.last_evolve_trace_count >= 10`，若是则 evolve 完成后再继续 invocation（或先 invocation、下次 evolve——后者更省事，**取后者**）

### 6.2 五阶段流程

#### 阶段 1：收集上下文

主 session 读：
- 最近 N=10 条 trace（按 timestamp 倒序）
- 所有当前 probationary 候选 + η
- 当前 promoted 候选 ID 集（dedup + 防重叠 anchor）
- 三个 validator 脚本 + 三个 prompt 文件 + skill.md Step 2 区域
- 既有候选的 dedup hash 集

打包为 `evolve-context.json`（临时文件，evolve 完删除）。

#### 阶段 2：crystallize-agent 生成候选

launch 后台 subagent（同 implement-agent 风格），输入 evolve-context.json。

**输出契约**（写在 `prompts/crystallize-agent.md`）：
- 0-3 个候选，每个含：type / target / patch / trigger / rationale（≤2 句）
- 必须基于 trace 里**实际出现过的失败模式**
- 必须自检 dedup hash 不冲突
- 输出格式：JSON 数组
- **不写文件**，只输出 JSON

异常处理：
- 输出不是合法 JSON → 整批丢弃，warning，跳到阶段 5
- 输出候选数 > 3 → 截断前 3 个
- dedup hash 冲突 → 静默丢弃该条

#### 阶段 3：heuristic_check + replay_eval

对每个候选依次跑：

1. **heuristic_check**（同步、纯 stdlib）：
   - 任一失败 → status=rejected，不进入下一步

2. **replay_eval**（`uv run scripts/replay-eval.py`，按 type 分流）：

| type | 回放方法 | 产出字段 |
|------|----------|---------|
| `validator_rule` | patch 拼到 validator 临时副本，跑 `blogBasePath/*.md` 全集；TP = 与过去 trace 中 criticals 对齐的真问题；FP = 误报合规内容 | precision, recall, fp_samples[] |
| `prompt_patch` | patch 套到目标 prompt 副本；选 3-5 条过去 trace 的 session_context；LLM 跑 patched review/implement-agent；比较能否抓到 baseline 漏掉的真问题 | precision, recall, sample_count |
| `step2_heuristic` | patch 套到 skill.md Step 2 副本；选 3-5 条 trace；主 session LLM 重做 Step 2 推断；用 post_hoc_edit_distance 作代理 | avg_improvement, sample_count |

任一 replay_eval 失败（脚本崩溃 / 无样本）→ status=rejected。
**precision < 0.5** → status=rejected。

#### 阶段 4：用户批准门

主 session 把通过 replay_eval 的候选格式化为 diff：

```
候选 cand_007  [validator_rule]
target: scripts/validate-post.py :: WHITELIST_LANGS (append)
patch: +"rust-analyzer"
rationale: 过去 3 条 trace 都把 rust-analyzer 代码块误判为未知 lang
replay: precision=0.85, recall=0.60, fp_samples=[]
[Y] approve  [N] reject  [E] edit patch
```

- approve → status=probationary, eta=(0,0), trials=0
- reject → status=rejected
- edit → 用户改 patch，重跑 replay_eval，再问

#### 阶段 5：扫现有 probationary

`beta-posterior.py promote-check`：
- 满足 promote → 应用 patch + git commit + status=promoted
- 满足 eliminate → status=eliminated
- inconclusive → 维持 probationary

写 `state.json`：`last_evolve_trace_count = len(traces.jsonl)`、`last_evolve_timestamp`、`promoted_ids[]`。

---

## 7. Retrieval 注入

### 7.1 触发

`skill.md` Step 1（读 config.json）之后、Step 2 之前：

```bash
uv run scripts/retrieval-inject.py \
  --topic "<topic or empty>" \
  --session-digest "<最近 200 字 session 摘要>" \
  --output active.json
```

### 7.2 输出 active.json

```json
{
  "injected_at": "...",
  "similar_traces": [
    {
      "trace_id": "...",
      "topic": "Git Rebase",
      "template": "how-to",
      "final_status": "PASS",
      "user_score": 4,
      "key_issues": ["validate_codeblocks C1-syntax @line 42"]
    }
  ],
  "active_candidates": [
    {
      "candidate_id": "cand_007",
      "type": "validator_rule",
      "target": "scripts/validate-post.py :: WHITELIST_LANGS",
      "patch_preview": "+rust-analyzer",
      "trigger": null,
      "status": "probationary"
    }
  ]
}
```

### 7.3 Top-K 相似度算法

- keyword Jaccard：把 `topic + session_digest` 切词，与每条历史 trace 的 `topic + inferred_tags + inferred_category` 做 Jaccard
- 排序后取 K=3
- 纯 stdlib，不引入 embedding 依赖

### 7.4 消费点

| 注入字段 | 用在哪 | 怎么用 |
|----------|--------|--------|
| `similar_traces` | Step 2（topic 推断） | 主 session 附在推断 prompt 里；让 inferred_tags/category 与历史一致 |
| `similar_traces` | Step 4（implement-agent 输入） | session_context 头部追加 "Past pitfalls on similar topics:" + key_issues |
| `active_candidates` (validator_rule, status=probationary) | Step 6.5 之前 | 创建 validator 临时 patched 副本 `_validate-post.patched.py`，跑完恢复 |
| `active_candidates` (validator_rule, status=promoted) | 不需要特殊处理 | patch 已在原文件，validator 直接跑原版即可 |
| `active_candidates` (prompt_patch, 任意 status) | Step 2 / Step 4 prompt 构造 | patch 内容拼到 prompt；probationary 与 promoted 都激活 |
| `active_candidates` (step2_heuristic, 任意 status) | Step 2 prompt 构造 | patch 内容拼到 Step 2 区域 |
| `active_candidates[*].candidate_id` | trace-capture | 全部写入本次 trace 的 `active_candidate_ids`（无论 status）——保证 probationary 和 promoted 都拿到 reward 归因 |

### 7.5 Validator 临时 patched 副本机制

- retrieval-inject.py 在 `scripts/` 下创建 `_validate-post.patched.py`（拷贝原文件 + 应用所有 active validator 候选的 patch）
- 主 session Step 6.5 调用 `uv run scripts/_validate-post.patched.py`（而非原版）
- Step 8 末尾 trace-capture.py 删除所有 `_validate-*.patched.py`
- 原文件保持干净，直到候选 promoted 才永久修改

### 7.6 probationary vs promoted

- promoted：patch 永久写入原文件 + git commit
- probationary：每次 invocation 临时 patched，trial 期间累积 η；eliminated 后彻底消失

---

## 8. 错误处理、回滚与边界

### 8.1 文件损坏

- `traces.jsonl` 一行解析失败 → 跳过 + 写 warnings.log，不阻塞
- `candidates.jsonl` 损坏 → retrieval-inject 跳过所有候选 + warning；crystallize 仍可基于 traces 跑
- `state.json` 损坏 → 重建：扫 candidates.jsonl 找 status=promoted，重算 last_evolve_trace_count
- `active.json` 损坏 / 缺失 → retrieval-inject 返回空注入，invocation 走 baseline

### 8.2 候选冲突

两个候选目标同一 anchor：
- 都 probationary → 都激活，patch 顺序按 candidate_id 字典序
- 一个 promoted 一个 probationary → promoted 永久写入原文件，probationary 在副本上叠加
- 两个都 promoted → crystallize-agent 阶段就 reject 第二个（"target anchor already modified by promoted cand_X"）

### 8.3 Promoted 之后变差

promoted 之后 η 继续累计（见 §5.7），但**无自动 demote**。兜底：
- promoted 候选保留累计 η 与 promoted_commit_sha
- 若 **promoted 之后** trial ≥ 10 且 η 跌破 0.30：下次 `/blog-update-evolve` 时主 session **建议**用户手动 `git revert <promoted_commit_sha>`（生成命令，**不自动执行**）
- 用户 revert 后，candidate status 改为 `eliminated_post_promote`，patch 不再激活（git revert 已经从文件里移除）

### 8.4 用户手动编辑被 patched 的文件

- 用户改了 `scripts/validate-post.py`，某 promoted 候选的 anchor 找不到 → retrieval-inject warning + **该候选暂停激活**（不归因 reward），等下次 evolve 重新评估
- probationary 候选 anchor 失效 → 临时副本生成失败 → trace-capture 写入时该 candidate_id 不在 active 列表

### 8.5 Git 操作失败

- promoted 时 `git commit` 失败（dirty tree / pre-commit hook 拒绝）→ **不回滚 patch**，但 status 保持 probationary，warning，下次 evolve 重试 commit

### 8.6 Crystallize-agent 异常

- 非 JSON → 整批丢弃，跳阶段 5
- >3 候选 → 截断
- dedup 冲突 → 静默丢弃

### 8.7 冷启动

- `traces.jsonl` 不存在或为空 → retrieval-inject 返回空，全走 baseline
- 前 10 次 invocation 不触发自动 evolve；用户可手动 `/blog-update-evolve`（trace 少时可能产 0 候选）
- 10 次后开始有"记忆"

### 8.8 并发安全

- 假设单用户单 session
- evolve 期间持锁 `.self/evolve.lock`；新 invocation 看到锁就跳过注入、走 baseline
- traces.jsonl 用 O_APPEND 写入（POSIX 保证 ≤ PIPE_BUF 原子）

### 8.9 卸载 / 重置

- 删除 `.self/` → 系统回 baseline；promoted 候选保留在 git history
- 保留 promoted patch 但忘掉学习 → 只删 traces.jsonl + candidates.jsonl + state.json

---

## 9. `/blog-update-evolve` 命令

新增 skill 或 skill.md section。流程即 §6 的五阶段。

Quick Reference：

| 场景 | 命令 |
|------|------|
| 手动触发进化 | `/blog-update-evolve` |
| 给某次 invocation 打分 | `/blog-update --score <1-5>`（仅 invocation 时附带，回填到上一条 trace） |
| 查看当前候选状态 | `/blog-update-evolve --status` |
| 查看 promoted 历史 | `git log --grep 'chore(self-evolve)'` |

---

## 10. 测试策略

### 10.1 单元测试（pytest）

测试目录：`tests/unit/`

| 模块 | 测试要点 |
|------|---------|
| `beta-posterior.py` | η 计算正确性；状态转换阈值（>0.70 / <0.30 / 5≤trial<10 / trial≥10 强制淘汰）；α/β 累加 |
| `trace-capture.py` | JSON schema 校验；缺字段降级；post_hoc 回填；active_candidate_ids 写入 |
| `retrieval-inject.py` | Jaccard 排序；top-K 截断；trigger 匹配；anchor 失效降级 |
| reward 公式 | s1 取平均（非 min）；s4 缺省的重新归一化；权重边界（全 0 / 全 1） |
| `heuristic-check.py` | patch parse 失败、anchor 找不到、长度超限、dangerous token |
| dedup hash | sha1 稳定性；whitespace normalize |

### 10.2 集成测试

测试目录：`tests/integration/`

**Fixture**：`tests/fixtures/blog/` 模拟 fuwari 项目，10 篇 post（含已知问题），`tests/fixtures/traces.jsonl` 含 10 条手工 trace。

**Fixture post 清单（含已知问题）**：

| 文件 | 已知问题 |
|------|---------|
| `git-rebase.md` | WHITELIST_LANGS 缺 rust-analyzer → validate_post 报未知 lang |
| `fastapi-body.md` | description 字段缺失 → validate_frontmatter auto-fix |
| `docker-patterns.md` | dockerfile 代码块未闭 → validate_post 报 unclosed fence |
| `pydantic-v2.md` | tags 含 "Pydantic" 但 WHITELIST 没收录 → validate_frontmatter Check #6 报拼写 |
| `kotlin-coroutines.md` | tags 数量只有 1 → validate_frontmatter Check #5 报 count |
| `rust-async.md` | 含 `tokio::spawn` 代码块标 `rust` 但内容缺 `;` → validate_codeblocks 报 syntax |
| `vue-3.md` | 含 `javascript` 代码块但内容是 `vue` 模板 → validate_codeblocks 报 syntax |
| `linux-perms.md` | 含 `<system-reminder>` 残留 → validate_post D1 报 |
| `graphql-sdl.md` | WHITELIST 有 graphql 但用例是 schema 定义 → 应该 PASS baseline |
| `mermaid-diagrams.md` | box-drawing 字符在 `bash` 块而非 `text` 块 → validate_post 报 |

| 测试 | 步骤 | 期望 |
|------|------|------|
| replay_eval validator_rule | 构造"加 rust-analyzer 到 WHITELIST"候选 | precision=1.0，fp_samples=[]，recall>0 |
| replay_eval prompt_patch | 构造"review-agent 加 system-reminder 检测规则"候选 | precision 合理，能区分好/坏 patch |
| 端到端 evolve | 10 条 fixture trace + crystallize-agent (mock) | ≥1 候选走完 proposed→probationary；阶段 5 状态机正确 |
| retrieval-inject → trace 归因 | 模拟一次 invocation | active.json 写入 + trace.active_candidate_ids 一致 |
| 文件损坏恢复 | 注入一行坏 JSON 到 traces.jsonl | invocation 仍能完成，warning 写入 warnings.log |

### 10.3 回归测试（守护 baseline）

`tests/regression/test_baseline.py`：

- 对 `blogBasePath/*.md` 全集跑 3 个 validator，与上次 commit 的 exit code 集 diff
- 任何变化必须对应一个 promoted 候选
- 没有对应候选的 exit code 变化 = 测试失败（防止手动改 validator 没走 evolve 流程）

### 10.4 烟雾测试

`scripts/smoke-evolve.sh`：

1. 复制 fixture blog 到 tmp dir
2. 注入 10 条 fixture trace
3. 跑 `/blog-update-evolve`
4. 验证：≥1 proposed 候选；replay_eval 跑通；批准后状态变 probationary；trial 5 次后 η 合理

### 10.5 Invariants（每个 PR 必须满足）

- 三个 validator 在 fixture 上 exit code 集不变（除非对应一个 promoted 候选）
- `traces.jsonl` 始终是合法 JSONL
- 任意时刻 `.self/` 删除后，blog-update 主流程仍能跑（退化 baseline）
- promoted 候选数 ≤ 50
- 所有 evolve 操作可逆（通过 git revert promoted commit + 删 `.self/`）

---

## 11. 迁移与上线

### 11.1 新增到现有 blog-update 安装

1. 拷贝新增 scripts（trace-capture, retrieval-inject, replay-eval, beta-posterior, heuristic-check）+ crystallize-agent.md 到 skill 目录
2. 改 skill.md：在 Step 1 后插 Step 1.5（retrieval-inject），Step 8 末尾插 trace-capture 调用
3. 新增 `/blog-update-evolve` skill（或 skill.md 新章节）
4. **不动** config.json——`.blog-update-self/` 自动在 blog repo root 创建
5. 第一次 `/blog-update` 后 `.self/traces.jsonl` 开始累积；前 10 次走纯 baseline

### 11.2 渐进开关

- 如果担心稳定性，加 config 字段 `selfEvolve: false` 默认关闭
- 设 false 时：跳过 retrieval-inject + trace-capture，skill 行为完全等同当前版本
- 用户验证一段时间后改 true 启用

---

## 12. 开放问题 / 未来工作

- Embedding-based retrieval（当 traces > 500 条时 Jaccard 信号衰减）
- L1/L2/L3 多层记忆（traces / candidates / abstract patterns 三层）
- 跨项目共享记忆（multi-blog 场景）
- Demote 机制（promoted 之后 η 跌得很厉害时自动 revert）
- 候选合并（多个相似候选结晶成一个）

---

## 13. 术语表

| 术语 | 定义 |
|------|------|
| trace | 一次 `/blog-update` invocation 的结构化记录 |
| reward (R) | 一次 trace 的标量分数 [0,1]，由 4 路信号加权融合 |
| η (eta) | 候选的 Beta 后验均值 = α/(α+β)，估计候选的"长期好坏" |
| candidate | 一个具体的可进化 patch 提议（validator_rule / prompt_patch / step2_heuristic） |
| crystallize | LLM 基于 trace 提议候选的过程 |
| probationary | 候选处于 trial 期，临时激活、累积 η |
| promoted | 候选 η 过阈、永久写入目标文件 |
| eliminated | 候选 η 不达标、永久弃用 |
| replay_eval | crystallize 时把候选拿到历史 corpus 上回放评估 |
| retrieval-inject | invocation 启动时把 top-K 历史 trace + 激活候选注入到上下文 |
