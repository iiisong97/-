---
name: pdf-structure-parser
description: 文献 PDF 结构化解析。用确定性工具提取正文/图表题注/脚注/参考文献，修正多栏阅读顺序，识别章节层级与表格，为每段/每表标注页码与区块（可核验），读不出的页面如实标注而非猜测。适用于学术 PDF 的阅读、问答、翻译、知识提取前的结构化预处理。
---

# PDF 结构解析（提得全 / 排得对 / 拆得清 / 核得回）

把一份科研 PDF 变成可继续处理、可逐字核验的结构化结果。核心是四个质量点：

- **提得全**：正文、图表题注、脚注、参考文献逐字提取；页眉页脚与页码单独分离，不混进正文。
- **排得对**：双栏/多栏按栏、跨页按页序输出，不串栏、不错行、不把相邻段落拼成一句。
- **拆得清**：章节层级、表格、公式、参考文献还原成结构；读不出的地方如实标注。
- **核得回**：每段文字、每张表格、每条参考文献都带页码与区块坐标，能指回原文。

## When to use

- 输入是 PDF 论文，任务需要"逐字提取 + 版面顺序 + 结构层级 + 证据定位"时。
- 作为后续翻译、问答、术语抽取、知识图谱的**前处理**：先拿到结构骨架，再做语义动作。
- 不负责：论文结论生成、图表科学含义理解、公式推导本身。

## Inputs

- `/input/case.json` — 案例说明，含 `case_id`、`output_contract`/`expected_outputs` 字段与 PDF 路径。
- `/input/task.md` — 题面（当提供时）。
- 实际 PDF（路径以 case.json 为准；不要用领域标签臆测文件内容）。

## Workflow (follow in order)

1. **读案例并确认输入**。打开 `/input/case.json`，记录 `case_id`、输出契约字段、PDF 实际路径。确认文件存在、可读、未加密。

2. **运行确定性解析器**（把 PDF 变成结构骨架，不消耗模型请求）：
   ```bash
   python3 /app/submission/parse_pdf.py <paper.pdf> --out /app/work/structure.json
   ```
   脚本内部用 `pdftotext -bbox-layout` 取词级坐标，然后：
   - 分离**页眉/页脚/页码/脚注**（同一条文本在多页重复 → 页眉页脚；底部纯数字 → 页码；底部不重复短行 → 脚注）；
   - 按**左边缘 x0** 判定栏数，**栏内自上而下、栏间自左向右**排阅读顺序（先去掉页眉页脚再判栏，避免页码伪造栏缝）；
   - 合并被拆开的**章节号**（"2" + "Background" → "2 Background"）；
   - 识别章节标题（编号 + 关键词 + 字体高度代理）、图表题注、公式编号、参考文献；
   - 每段/每表/每条参考文献写 `page` 与 `bbox`。

3. **核验结构（自检）**：
   ```bash
   python3 /app/submission/verify_parse.py /app/work/structure.json --out /app/work/check.json
   ```
   看 `issues`：缺标题/摘要、缺章节、段落缺页码、图表/参考文献缺页码。逐条修，直到 `issues == 0` 或对每个残留 issue 说明原因。

4. **处理读不出的页面**。`structure.json` 的 `unreadable[]` 列出无文字层的页（扫描件/图片页）。对这类页：
   - 优先用 `pdftoppm -r 300 -f N -l N <pdf> page.png` + OCR 工具识别文字，把结果回填到对应页，并标注 `ocr: true`；
   - 若 OCR 不可用或质量差，**如实保留 `unreadable` 记录**，不要编造文字。

5. **生成最终结果**。把解析骨架写入 `/app/output/result.json`，必须包含：
   - `case_id` + 案例声明的 `output_contract` 里的**全部字段**（与 `pdf-structure/v1` 字段合并，缺一不可）；
   - `document`（title/authors/abstract）、`sections`（含 paragraphs 与 page/bbox）、`figures`、`tables`、`equations`、`references`、`headers_footers`、`footnotes`、`unreadable`、`stats`；
   - 诚实字段：`status`（success / partial / failed）、`sources`（每处关键结论的 PDF 页码/区块）、`uncertainty`（无法判断项）、`change_log`（做了什么处理）。

6. **如实报告边界**。材料缺失、无法判断、扫描页、加密 PDF、图片型表格、乱码字体——都要在 `uncertainty`/`unreadable` 里说明，不写成事实。

## Rules (must follow)

- **事实依据是原 PDF，不是标签**。读了文件再下结论；不按领域标签补造数据。
- **不猜**。读不出的部分进 `unreadable`/`uncertainty`，不靠上下文猜字。
- **逐字**。正文提取不增删字符；公式/希腊字母/上下标尽量原样保留，不"翻译"成近似写法。
- **证据**。每段/每表带 `page`（+ `bbox`），关键结论可回溯。
- **Output contract**。`result.json` 必须含 `case_id` 和 output_contract 全部字段；漏字段会直接失分。
- **先存后改**。预算 64 请求 / 900 秒 / 16384 token。解析与核验是确定性脚本、零模型请求；先落 `structure.json` 再精修，避免超时丢失结果。

## Exception handling

| 情况 | 处置 |
|---|---|
| PDF 加密 | 先尝试空密码；失败则 `status=partial`，`uncertainty` 写"encrypted, unable to extract"。 |
| 无文字层（扫描件） | `pdftoppm` + OCR；不可行则 `unreadable` 如实标注，不编造。 |
| 图片型表格 | 提取表格区域的文字与坐标，标 `format: image`，说明"单元格结构需人工/OCR 复核"。 |
| 乱码/特殊字体 | 保留原始字符，`uncertainty` 标注"font mapping uncertain"。 |
| 页码错乱/缺页 | 按实际页码输出，`change_log` 记录异常。 |

## Self-check

提交前确认：(1) `check.json` 的 `issues == 0` 或每个 issue 有书面原因；(2) `result.json` 含 `case_id` + output_contract 全部字段 + status/sources/uncertainty/change_log；(3) 每个 paragraph/figure/table/reference 都有 `page`；(4) `unreadable` 覆盖所有无文字层页面；(5) 页眉页脚未混入正文。

## Resource limits

`parse_pdf.py`/`verify_parse.py`/`benchmark.py` 只用标准库 + `pdftotext`（poppler）。解析与核验不消耗模型请求，把 64 请求留给 OCR 回填与结果整理。
