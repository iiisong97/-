# 最小调用示例（合成/公开样例，非隐藏正式案例）

- 输入：公开论文 arXiv:1706.03762《Attention Is All You Need》(双栏 15 页)
- 调用：`python3 reproduce.py paper.pdf --out deck/ --max-slides 14`
- 运行时输出（由 Skill 在评测沙箱现场生成，本提交不预置二进制）：
  - `deck/deck.pptx` —— 可编辑演示文件（图/表区域从 PDF 裁剪并嵌入，模板尺寸/占位符被保留）
  - `deck/evidence_map.json` + `deck/golden_standard.json` —— 页级证据映射与逐页金标准（claim + 证据 + 数字/单位/图号校验项）
  - `deck/deck.pdf` + `deck/previews/*.png` —— 真实渲染预览
  - `benchmark.json` —— 与「段落粘贴」朴素基线的同输入 A/B 对照（可复现）

本示例提交的是文本形态的示意输入/输出：
- `deck_spec.json` —— 主线骨架（示意输入）
- `evidence_map.json` / `golden_standard.json` —— 页级证据映射与金标准（示意输出）
- `benchmark.json` —— A/B 对照（示意输出）

均仅用于说明接口与完整流程，不冒充任何正式案例结果；deck.pptx/PDF/PNG/figures 由评测运行 Skill 时现场生成。
