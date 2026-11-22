# paper-to-bilingual-translation Skill

把真实科研论文翻译成**可核验的双语对照结果**，而不是只给大意或改写。围绕题面四大质量点设计：

| 质量点 | 本 Skill 的做法 |
|-|-|
| 术语稳 | `extract_terms.py` 抽取候选术语 → Agent 逐条锁定译名 → `verify_translation.py` 校验全篇译名一致（术语表被"真正执行"，而非写在提示里） |
| 段落全 | `segment.py` 生成固定的段落级翻译骨架（段号↔原文↔页码），逐段填充，不漏段/不重段/不错位 |
| 关系准 | `verify_translation.py` 检查数字、单位、`[N]` 引用、Figure/Table/Equation 编号、否定与限定标记是否被保留 |
| 可核验 | 每段译文带 `para_id`+`page`+`section`+`notes`（译法依据），译不准处标 `uncertain` |

## 文件

- `SKILL.md` — 完整调用流程与规则（Agent 执行入口）
- `parse_pdf.py` — 版面解析（段落/图注/表头 + `plaintext_pages` 干净正文）
- `extract_terms.py` — 术语候选抽取（缩写、全称配对、高频标题短语）
- `segment.py` — 段落级翻译骨架
- `verify_translation.py` — 译文确定性核验 + 人工确认清单（数字/引用/图表编号/否定限定/**技术单位**/术语一致逐处定位）
- `benchmark.py` — A/B 公平对照（裸 Agent vs 本 Skill 的段落对齐/术语表/核验项/可检出受保护 token 数）
- `reproduce.py` — 一键复现（parse→terms→segment，`--selftest` 证明核验生效）

## 依赖

- 仅 Python 标准库；需要 `poppler-utils`（`pdftotext` / `pdftohtml`，即赛题 `pdf-text-tool` 资源）。

## 最小调用示例（示意，非正式案例）

```bash
# 1) 解析原文
python3 parse_pdf.py paper.pdf --out work/structure.json
# 2) 抽取术语
python3 extract_terms.py work/structure.json --out work/glossary.json
# 3) 生成翻译骨架（Agent 逐段填写 translation）
python3 segment.py work/structure.json --out work/units.json
# 4) 翻译后核验
python3 verify_translation.py work/units.json --glossary work/glossary.json \
    --out work/verification.json
# 5) A/B 增益对照（证明"更全/更可核验"的运行证据）
python3 benchmark.py paper.pdf --out work/benchmark
```

示意输出（标明为示例）：

```json
{"units": [{"para_id": 3, "page": 2, "section": "Introduction",
  "source": "Recurrent neural networks ...", "translation": "循环神经网络……",
  "notes": "RNN 锁定译名『循环神经网络』", "uncertain": false}]}
```

## 局限

- 扫描件/图片公式/图片表格需 OCR（赛题 `ocr-tool`）；文字层缺失时在 `uncertainty` 中声明，不臆造。
- 术语锁定依赖 Agent 的专业判断；脚本保证"锁定的译名被一致执行并核验"。
- 目标语言默认为中文；其它语言在 `case.json` 中声明即可。
