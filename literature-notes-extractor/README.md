# literature-notes-extractor

把一篇论文转成**与章节对齐、字段齐全、锚点可回链、可检索复用**的结构化笔记。对应任务四要素：

| 任务要素 | 本 Skill 的做法 |
|---|---|
| 对得上 | `section_notes` 逐节沿用论文原章节标题与顺序，保留目的/方法/结果/结论与章节承接 |
| 留得住 | `paper_card` 七字段：研究问题、数据、方法、主要发现、结论、局限、前提条件 |
| 找得回 | 每条笔记带 `page`+`paragraph`+`quote` 锚点；`notes_check.py` 会**把引文与原文逐字核对** |
| 用得上 | `knowledge_points` 可检索知识点（concept/variable/method/conclusion），`id` 稳定、去重 |

## 文件

- `SKILL.md` — 平台加载的工作流
- `note_schema.md` — 字段字典 + 锚点格式 + 知识点类型词表（可复用）
- `notes_check.py` — 确定性校验器（章节对齐/字段齐全/锚点回链/引文核对/知识点去重）
- `parse_pdf.py` — 版面感知 PDF 解析（正文/章节/图表/参考文献 + 页码/bbox 证据）
- `benchmark.py` — 与"裸 LLM 通篇摘要"的 A/B 对照
- `run.sh` — 入口点

## 依赖

- Python 3.8+（标准库），无 pip 依赖、无网络。
- `poppler-utils` 用于 PDF 解析，评测镜像已预装。

## 用法

```bash
# 1) 解析论文
python3 parse_pdf.py paper.pdf --out structure.json
# 2) 让 Agent 按 SKILL.md 生成 result.json
# 3) 校验（含引文与原文核对；迭代到 issues == 0）
python3 notes_check.py result.json --structure structure.json --out check.json
./run.sh check result.json --structure structure.json
```

## 方法要点

1. **章节对齐**：`section_notes` 的标题直接取自解析器输出的章节，顺序不变，不套通用模板。
2. **前提条件单列**：`preconditions` 显式记录让结论成立的数据范围/假设/设定，避免把受限结论泛化。
3. **锚点可核验**：`--structure` 时校验器会把每条 `quote` 与该页原文逐字比对，锚错页/引文不符会被标记。
4. **知识点归并**：`term` 归一化去重，同义写进 `synonyms`，术语冲突记入 `uncertainty`。

## 限制（如实说明）

- 章节内容提炼与知识点选择由 LLM 完成，`notes_check.py` 只做结构/字段/引文逐字核对等确定性检查，无法判定"提炼是否到位"，需人工复核。
- 引文核对是词法级（归一化子串匹配）；原文换行/连字符/数学符号造成的细微差异可能误报，需按 `check.json` 复核。
- 扫描版无文字层 PDF 返回 `uncertainty` 并建议 OCR，不虚构正文。

## 自测

```bash
./run.sh --selftest
python3 benchmark.py --out /tmp/notes-bench   # A/B：裸 LLM 有 N 个问题，本 Skill 0 个
python3 notes_check.py example/skill-result.json
```
