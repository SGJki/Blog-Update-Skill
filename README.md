# Blog Update Skill

将 Claude 会话内容智能合并到 fuwari-framework 博客文章。

## 使用方法

```bash
# 新建文章
/blog-update <topic> --tags [tag1,tag2] --category <category>

# 更新已存在文章（自动读取现有 tags/category）
/blog-update <topic>
```

## 文件结构

```
blog-update/
├── skill.md              # 主技能文件 (Overview + Workflow)
├── prompts/             # Subagent prompts
│   ├── implement-agent.md  # 内容生成
│   ├── merge-agent.md      # 智能合并
│   ├── review-agent.md     # 质量审查
│   └── format-agent.md    # 格式化
└── config.json          # 用户配置
```

## 工作流程

```
Main Session
    │
    ├─ Step 1: 检查配置，获取 blogBasePath
    ├─ Step 2: 检查文件存在 → 收集 tags/category
    ├─ Step 3: 提取会话上下文
    ├─ Step 4: implement-agent (生成内容)
    ├─ Step 5: merge-agent (多粒度智能合并)
    ├─ Step 6: review-agent (质量审查)
    │         └─ FAIL → 返回 Step 4 修订 (最多 3 次)
    ├─ Step 7: format-agent (生成 frontmatter)
    └─ Step 8: 主会话写入文件，报告完成
```

## 合并算法

### Level 1: 标题相似度 (Jaccard)
- > 70%: 同一主题，保留现有
- < 60%: 不同主题，新增
- 60-70%: [边缘-1]

### Level 2: 段落相似度 (TF-IDF + 余弦)
- > 60%: 内容重复，保留现有
- < 30%: 完全不同，新增
- 30-60%: [边缘-2]

### Level 3: 内容丰富度对比
- 句子数量 (30%)
- 代码示例数 (40%)
- 技术术语密度 (30%)

详见 [prompts/merge-agent.md](prompts/merge-agent.md)

## 边缘情况

当遇到 `[边缘-N]` 标记的情况时：
1. 用户决策处理方式
2. 记录到 merge-agent.md 的边缘情况处理记录表
3. 评估是否更新算法规则

## 配置文件

位置: `~/.claude/skills/blog-update/config.json`

```json
{
  "blogBasePath": "your/blog/posts/path",
  "fileExtension": ".md"
}
```

## 版本历史

| 版本 | 主要变化 |
|------|---------|
| V1 | 基础博客更新 |
| V2 | Subagent 架构分离 |
| V3 | 智能多粒度合并 |
| V4 | CSO 优化，prompts 拆分，<200 lines |
| V5 | 合并算法增强，Red Flags 安全检查 |
