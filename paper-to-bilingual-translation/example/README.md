# 最小调用示例（示意，非正式案例）

本目录是**示意输出**，仅说明接口与完整流程；正式案例由平台提供，答案不在此处。

```bash
# 1) 解析原文（→ 段落/图注/表头 + plaintext_pages）
python3 parse_pdf.py paper.pdf --out work/structure.json

# 2) 抽取术语（→ 候选术语表，Agent 逐条锁定译名）
python3 extract_terms.py work/structure.json --out work/glossary.json

# 3) 生成翻译骨架（→ 每段一个 para_id+page+section+source）
python3 segment.py work/structure.json --out work/units.json

# 4) 翻译后核验（→ 数字/引用/图表编号/否定/术语一致性检查）
python3 verify_translation.py work/units.json --glossary work/glossary.json \
    --out work/verification.json
```

示意输入（`units.json` 的一个单元）：

```json
{"para_id": 2, "page": 1, "section": "Abstract",
 "source": "The dominant sequence transduction models are based on ...",
 "translation": "（示例译文）……", "notes": "示意：锁定术语译名示例"}
```

示意输出（`verification.json` 摘要）：`units_translated: 4/4`、
`numbers_missing: 0`、`citations_missing: 0`、`terms_inconsistent: 2`（示意）。

> 本目录所有 JSON 均标记为 SYNTHETIC EXAMPLE，不冒充正式案例结果。
