# pdf-structure-parser — 文献 PDF 结构化解析 Skill

把科研 PDF 变成可继续处理、可逐字核验的结构化结果。聚焦四个质量点：

| 质量点 | 实现 |
|---|---|
| **提得全** | 词级提取正文/图表题注/脚注/参考文献；页眉页脚与页码单独分离，不混进正文 |
| **排得对** | 按左边缘 x0 判栏、栏内自上而下栏间自左向右；先除页眉页脚再判栏，防页码伪造栏缝 |
| **拆得清** | 章节层级（编号+关键词+字体高度）、图表题注、公式编号、参考文献、表格定位 |
| **核得回** | 每个 paragraph/figure/table/reference 带 `page`+`bbox`；无文字层页进 `unreadable` 如实标注 |

## 快速开始

```bash
# 解析
python3 parse_pdf.py paper.pdf --out structure.json
# 核验
python3 verify_parse.py structure.json --out check.json
# 一键（解析+核验+A/B 增益）
python3 reproduce.py paper.pdf --out out/
# A/B 对照（裸 Agent vs 本 Skill）
python3 benchmark.py paper.pdf --out out/
```

## 依赖

- Python 3（**仅标准库**，无 pip 依赖）。
- 系统工具 `pdftotext`（poppler-utils，平台 `pdf-text-tool` 资源）。
- 可选：`pdftoppm` + `tesseract`，用于扫描页 OCR；缺失时诚实降级为 `unreadable` 标注。

## 输出 schema

`paper2arm/pdf-structure/v1`：`document`（title/authors/abstract）、`sections`
（heading/level/paragraphs 且每段带 page/bbox）、`figures`、`tables`、
`equations`、`references`、`headers_footers`、`footnotes`、`unreadable`、`stats`。
运行契约另要求 `case_id` + 案例 `output_contract` 全部字段 + status/sources/
uncertainty/change_log（由 Agent 在 `result.json` 补齐，见 SKILL.md）。

## 适用范围与限制

- 适用：有文字层的单栏/双栏学术 PDF（会议/期刊/arXiv 常见版式）。
- 已知限制：跨栏摘要（极少见）与正文同字号的未编号子标题的层级区分有限；图片型表格标注为 image 需 OCR 复核；扫描页需 OCR。这些情况都会在输出中如实标注，而非猜测。

## 最小示例

见 `example/`（`structure.json` 为示意输出，已标明 example）。
