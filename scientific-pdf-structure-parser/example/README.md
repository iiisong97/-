# 最小调用示例（example）

> 以下均为**示意**，不冒充正式案例结果。正式案例与对照由平台提供。

## 输入

一篇 1 页示例论文 `example.pdf`（标题 / 作者 / 摘要 / 若干章节 / 一张表 / 两条参考文献）。

## 调用

```bash
python3 parse_pdf.py example.pdf --out structure.json
python3 verify_parse.py structure.json --out check.json
```

## 示意输出

- `structure.json`：结构化解析结果（本目录已存一份示意，`note` 字段已标明为示例）。
  每个 paragraph / table / reference 都带 `page`（及 `bbox`），可回溯原文。
- `check.json`：`issues == 0`（PASS）。

## 复现

```bash
python3 reproduce.py example.pdf --out /tmp/out
# 输出 /tmp/out/structure.json + check.json + benchmark.json
```

（提交包不含二进制 PDF；运行时由平台提供真实 PDF。）
