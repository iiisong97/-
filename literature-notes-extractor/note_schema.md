# 文献结构化笔记 字段字典（schema: lit-notes/v1）

本文件定义本 Skill 输出的机器可读取结构，对应任务四要素：对得上（章节对齐）、
留得住（字段齐全）、找得回（锚点回链）、用得上（可检索复用）。

## 输出结构

```json
{
  "schema": "lit-notes/v1",
  "case_id": "<来自 /input/case.json>",
  "paper_card": {
    "title": "…", "authors": ["…"], "year": 2020, "venue": "…",
    "identifiers": {"doi": "…", "arxiv": "…"},
    "research_question": "…",
    "data": "…",
    "methods": ["…"],
    "key_findings": ["…"],
    "conclusions": ["…"],
    "limitations": ["…"],
    "preconditions": ["…"]
  },
  "section_notes": [
    {
      "section": "3.2 Multi-Head Attention", "number": "3.2", "level": 2,
      "page": 4,
      "purpose": "…", "method": "…", "result": "…", "conclusion": "…",
      "transition": "…",
      "anchors": [{"page": 4, "paragraph": 2, "quote": "…"}]
    }
  ],
  "knowledge_points": [
    {"id": "kp-<hash>", "term": "Self-Attention", "type": "concept",
     "definition": "…", "synonyms": ["…"],
     "anchors": [{"page": 3, "quote": "…"}]}
  ],
  "status": "success|partial|failed",
  "sources": [{"page": 4, "quote": "…"}],
  "uncertainty": [{"item": "…", "reason": "…"}],
  "change_log": ["…"]
}
```

## 字段定义

| 字段 | 类型 | 要求 | 说明 |
|---|---|---|---|
| `paper_card.research_question` | string | 必填 | 论文要解决的问题（一句话） |
| `paper_card.data` | string | 必填 | 数据集/语料/样本及规模 |
| `paper_card.methods` | array | 必填 | 核心方法名（可多） |
| `paper_card.key_findings` | array | 必填 | 主要发现，含关键数字与单位，逐字保留 |
| `paper_card.conclusions` | array | 必填 | 结论 |
| `paper_card.limitations` | array | 必填 | 局限/不足；未报告须写明"未报告"并记入 uncertainty |
| `paper_card.preconditions` | array | 必填 | 让结论成立的前提条件（数据范围/假设/设定） |
| `section_notes[].section` | string | 必填 | **论文原章节标题**（去掉编号），须与解析出的章节一致 |
| `section_notes[].purpose/method/result/conclusion` | string | 必填 | 本节的目的/方法/结果/结论；无则写"本节无……" |
| `section_notes[].transition` | string | 可空 | 与上下节的承接关系 |
| `section_notes[].anchors` | array | 必填 | `page` 必填；`paragraph`/`quote` 尽量给出 |
| `knowledge_points[].term` | string | 必填 | 概念/变量/方法/结论名 |
| `knowledge_points[].type` | enum | 必填 | `concept`/`variable`/`method`/`conclusion` |
| `knowledge_points[].definition` | string | 必填 | 定义或说明，术语/缩写首次出现形式保留 |
| `knowledge_points[].synonyms` | array | 可空 | 同义/别名，用于归并与去重 |
| `knowledge_points[].id` | string | 必填 | `kp-<sha1(term)[:16]>`，跨次运行稳定 |

## 锚点格式（找得回）

每条 `anchors[].page` 必填；`quote` 为该论断的逐字原文片段，`paragraph` 为该节内段落序。
锚点粒度：论文卡片级 → 章节 + 页；章节级 → 页 + 段落；知识点级 → 页 + 引文。

## 知识点类型（受控词表）

- `concept`：概念/定义
- `variable`：变量/指标/符号
- `method`：方法/模型/算法
- `conclusion`：结论/发现

同一条知识点不得重复出现；同一术语出现两处定义不一致时，取更具体者并记入 `uncertainty`。
