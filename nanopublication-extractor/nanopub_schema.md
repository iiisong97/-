# Nanopublication 字段字典与受控词表

本文件定义本 Skill 输出的机器可读取结构。字段名与任务要求的语义项一一对应：
断言、主体与关系、证据片段、证据位置、来源元数据、置信度依据、标识符。

## 输出结构（schema: nanopub/v1）

```json
{
  "schema": "nanopub/v1",
  "case_id": "<来自 /input/case.json>",
  "paper": {
    "title": "…", "authors": ["…"], "year": 2020,
    "venue": "…", "identifiers": {"doi": "…", "arxiv": "…"}
  },
  "nanopublications": [
    {
      "id": "np-<确定性哈希>",
      "assertion": { "text": "…", "subject": "…", "predicate": "improves", "object": "…" },
      "condition": "… 或 null",
      "evidence": { "quote": "…最小充分片段…", "location": {"page": 3, "section": "…", "bbox": [x0,y0,x1,y1]} },
      "confidence": { "level": "direct|indirect|conflicting", "basis": "…" },
      "provenance": { "paper_title": "…", "authors": ["…"], "year": 2020, "version": "…", "identifiers": {"arxiv": "…"} }
    }
  ],
  "status": "success|partial|failed",
  "sources": [{"page": 3, "quote": "…"}],
  "uncertainty": [{"item": "…", "reason": "…"}],
  "change_log": ["…"]
}
```

## 字段定义

| 字段 | 类型 | 要求 | 说明 |
|---|---|---|---|
| `id` | string | 必填 | 断言级稳定标识符；由 subject+predicate+object+来源标识符的哈希生成，跨次运行不变 |
| `assertion.text` | string | 必填 | 一条**单一、可独立判断真假**的自然语言断言，保留条件、量词、时态 |
| `assertion.subject` | string | 必填 | 断言的实体主体（方法、模型、系统、量） |
| `assertion.predicate` | string | 必填 | 受控关系词表之一（见下） |
| `assertion.object` | string | 必填 | 断言的对象/取值 |
| `condition` | string/null | 可空 | 断言成立的条件、限定范围或上下文（如 "在 WMT 2014 英德上"） |
| `evidence.quote` | string | 必填 | 支撑该断言的最小充分原文片段，逐字引用 |
| `evidence.location` | object | 必填 | `page` 必填，`section`/`bbox` 尽量给出 |
| `confidence.level` | enum | 必填 | `direct`(直接证据)/`indirect`(间接推论)/`conflicting`(材料冲突) |
| `confidence.basis` | string | 必填 | 判定依据：为何该证据充分/为何只是推论 |
| `provenance` | object | 必填 | 论文、作者、年份、版本、标识符；与 `paper` 一致 |
| `status` | enum | 必填 | `success`/`partial`/`failed` |
| `uncertainty` | array | 必填 | 未报告、无法判断、材料冲突项，逐一说明原因 |

## 受控关系词表（predicate）

- **比较**：`outperforms`, `underperforms`, `equals`, `exceeds`, `comparable_to`, `superior_to`
- **因果**：`causes`, `leads_to`, `results_in`, `improves`, `increases`, `decreases`, `reduces`, `prevents`, `enables`, `requires`, `inhibits`, `accelerates`
- **关联**：`correlates_with`, `associated_with`, `predicts`
- **结构**：`is_a`, `has_part`, `part_of`, `contains`, `composed_of`, `located_in`, `encodes`, `expresses`
- **测量**：`measured_as`, `achieves`, `yields`, `reports`, `obtains`, `estimates`
- **方法**：`evaluated_by`, `compared_with`, `trained_on`, `based_on`, `uses`, `employs`
- **时序**：`precedes`, `follows`

未覆盖的关系用最接近的词表项并记入 `confidence.basis`；不得自造方向颠倒的关系（如把 "A 优于 B" 写成 "B 优于 A"）。

## 拆分判据（拆得细）

1. 一条断言只含一个谓词/一个可判断真假的命题；并列或因果复合句须拆成多条。
2. 条件、限定范围（only / at least / in … setting / when …）须保留在 `text` 或 `condition` 中，不得丢掉。
3. 数字、单位、比较对象、比较方向必须与原文逐字一致。
4. 整段摘要**不得**塞进一条断言的 `text` 字段。
