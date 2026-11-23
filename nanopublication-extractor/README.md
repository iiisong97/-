# nanopublication-extractor

把一篇论文的关键结论拆成**原子断言**、为每条断言绑定**最小充分证据片段与原文位置**、补齐**来源元数据**并导出**可机器读取**的 nanopub/v1 结构。对应任务四要素：

| 任务要素 | 本 Skill 的做法 |
|---|---|
| 拆得细 | 一条断言一个谓词一个可判断真假的命题；复合句拆开；条件/量词/数字逐字保留 |
| 对得上 | 每条断言绑定逐字引用的证据片段 + 页码/区块定位；区分直接证据与间接推论 |
| 追得回 | 断言 → 证据 → 论文/作者/年份/版本/标识符 全链路；断言 id 由确定性哈希生成 |
| 读得懂 | 输出 `nanopub/v1` JSON，字段与受控词表见 `nanopub_schema.md`，可被程序直接解析 |

## 文件

- `SKILL.md` — 平台加载的工作流
- `nanopub_schema.md` — 字段字典 + 受控关系词表（可复用）
- `nanopub_check.py` — 确定性校验器（原子性/证据对齐/可追溯/可读性）
- `parse_pdf.py` — 版面感知 PDF 解析（正文/章节/图表/参考文献 + 页码/bbox 证据）
- `benchmark.py` — 与"裸 LLM 整段搬运"的 A/B 对照
- `run.sh` — 入口点

## 依赖

- Python 3.8+（标准库），无 pip 依赖、无网络。
- `poppler-utils`（`pdftohtml`、`pdftotext`）用于 PDF 解析，评测镜像已预装。

## 用法

```bash
# 1) 解析论文 → 结构化证据
python3 parse_pdf.py paper.pdf --out structure.json
# 2) 让 Agent 按 SKILL.md 拆分断言并写 result.json
# 3) 校验（迭代到 issues == 0）
python3 nanopub_check.py result.json --out check.json
# 一键入口
./run.sh check result.json
```

## 方法要点

1. **最小充分证据**：证据片段只需足够支撑该条断言，而非整段；引用逐字、页码必填。
2. **受控关系词表**：谓词限定在 `nanopub_schema.md` 的词表内，禁止方向颠倒。
3. **确定性 id**：`np-<sha1(subject|predicate|object|paper_title)[:16]>`，重复运行不变。
4. **直接 vs 间接**：`confidence.level` 显式区分"原文明说"与"由原文推断"，间接项必须在 `basis` 说明推理路径。

## 限制（如实说明）

- 断言拆分与证据选择最终由 LLM 完成，`nanopub_check.py` 只做结构/词表/数字对齐等确定性检查，无法判定语义层面的"证据是否充分"，需人工复核。
- 证据相关性检查是词法级（数字/关键 token 是否出现在证据片段中），语义等价但不含原数字的改写需靠 `confidence.basis` 说明。
- 扫描版无文字层 PDF 会返回 `uncertainty` 并建议 OCR，不虚构正文。

## 自测

```bash
./run.sh --selftest
python3 benchmark.py --out /tmp/np-bench   # A/B：裸 LLM 有 N 个问题，本 Skill 0 个
python3 nanopub_check.py example/skill-result.json
```
