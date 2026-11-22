#!/usr/bin/env python3
"""benchmark.py — fair, reproducible A/B comparison for the paper→PPT Skill.

Builds a naive "paragraph-paste" baseline on the SAME paper and compares it with
the Skill pipeline, so the quality/efficiency gain is verifiable by anyone.

Usage:
    python3 benchmark.py paper.pdf --out DIR [--max-slides N]

Output: DIR/benchmark.json (baseline vs skill metrics + a summary). Deterministic:
same input + same tools → same numbers.

Metrics (higher is better unless noted):
  n_slides            slide count (respects --max-slides)
  evidence_coverage   fraction of slides traceable to a figure/table/section/page
  figure_coverage     fraction of paper figures attached to a slide
  notes_coverage      fraction of slides with speaker notes
  main_line_order     whether problem→method→results→conclusion appears in order
  overflow_risk       proxy for text overflow (LOWER is better): mean bullet chars
"""

import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import parse_pdf as P  # noqa: E402


def naive_baseline_spec(structure, max_slides):
    """One slide per section, raw paragraphs, no figures, no notes, no evidence."""
    slides = []
    for sec in structure.get("sections", []):
        if len(slides) >= max_slides:
            break
        text = " ".join(p.get("text", "") for p in sec.get("paragraphs", [])).strip()
        if not text:
            continue
        slides.append({
            "layout": "content",
            "title": sec.get("heading", "Section"),
            "bullets": [[t, 0] for t in
                        [text[i:i + 400] for i in range(0, min(len(text), 1600), 400)]],
            "figures": [], "notes": "", "evidence": [], "sections": [],
        })
    return slides


def metrics(slides, structure, max_slides):
    n = len(slides)
    n_evid = sum(1 for s in slides if s.get("evidence"))
    n_notes = sum(1 for s in slides if s.get("notes"))
    n_figs = sum(1 for s in slides for f in s.get("figures", []) if f.get("kind") == "figure")
    total_figs = len(structure.get("figures", [])) or 1
    # main-line order: problem -> method -> results -> conclusion
    roles, seen = [], set()
    for s in slides:
        t = (s.get("title") or "").lower()
        for role, kws in (("problem", ("problem", "motivation", "问题", "动机")),
                          ("method", ("method", "model", "architecture", "training", "方法")),
                          ("results", ("result", "performance", "translation", "结果")),
                          ("conclusion", ("conclusion", "结论"))):
            if role not in seen and any(k in t for k in kws):
                seen.add(role)
                roles.append(role)
                break
    desired = ["problem", "method", "results", "conclusion"]
    order_score = 0.0
    for r in desired:
        if r in roles:
            order_score += 1.0
        else:
            break
    order_score /= len(desired)
    # overflow risk: mean bullet chars (lower = safer)
    chars = [len(b[0] if isinstance(b, (list, tuple)) else b)
             for s in slides for b in s.get("bullets", [])]
    overflow = (sum(chars) / max(len(chars), 1)) if chars else 0.0
    return {
        "n_slides": n,
        "within_limit": n <= max_slides,
        "evidence_coverage": round(n_evid / max(n, 1), 3),
        "figure_coverage": round(n_figs / total_figs, 3),
        "notes_coverage": round(n_notes / max(n, 1), 3),
        "main_line_order": round(order_score, 3),
        "overflow_risk_mean_chars": round(overflow, 1),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paper")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-slides", type=int, default=14)
    args = ap.parse_args()

    structure = P.parse_pdf(args.paper)
    base_slides = naive_baseline_spec(structure, args.max_slides)

    os.makedirs(args.out, exist_ok=True)
    struct_path = os.path.join(args.out, "_structure.json")
    spec_path = os.path.join(args.out, "_skill_spec.json")
    with open(struct_path, "w", encoding="utf-8") as fh:
        json.dump(structure, fh, ensure_ascii=False)
    t0 = time.time()
    r = subprocess.run([sys.executable, os.path.join(HERE, "draft_outline.py"),
                        struct_path, "--out", spec_path, "--paper", args.paper,
                        "--max-slides", str(args.max_slides)],
                       capture_output=True, text=True, check=False)
    skill_seconds = round(time.time() - t0, 2)
    skill_slides = json.load(open(spec_path, encoding="utf-8")).get("slides", []) \
        if r.returncode == 0 else []

    result = {
        "schema": "paper2arm/ppt-benchmark/v1",
        "input": {"paper": os.path.basename(args.paper), "max_slides": args.max_slides},
        "baseline_naive_paragraph_paste": metrics(base_slides, structure, args.max_slides),
        "skill_paper_to_ppt": metrics(skill_slides, structure, args.max_slides),
        "efficiency": {"skill_draft_seconds": skill_seconds,
                       "note": "Deterministic parse+draft wall-clock for this paper; "
                               "build/render (figure crops + PPTX + PDF/PNG) is extra."},
        "note": "Same paper, same tools, same slide limit. Reproduce with "
                "'python3 benchmark.py <paper.pdf> --out DIR --max-slides N'.",
    }
    with open(os.path.join(args.out, "benchmark.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print("baseline:", result["baseline_naive_paragraph_paste"])
    print("skill:   ", result["skill_paper_to_ppt"])


if __name__ == "__main__":
    main()
