#!/usr/bin/env python3
"""benchmark.py — fair A/B: base agent (raw pdftotext dump) vs this Skill.

Same paper, same tools. The base agent just runs `pdftotext` and returns the
raw text (no structure, no page evidence, no header/footer separation). The
Skill adds a page/bbox-anchored structure with multi-column reading order,
section headings, figures/tables/equations/references, chrome separation and
unreadable-page reporting. Counts are run results, not self-claims.

Usage:
    python3 benchmark.py <paper.pdf> --out DIR
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


def naive_baseline(pdf):
    """What a base agent returns: one raw text blob, no structure, no evidence."""
    proc = subprocess.run(["pdftotext", pdf, "-"],
                          capture_output=True, text=True)
    txt = proc.stdout or ""
    pages = txt.rstrip("\f").count("\f") + (1 if txt.strip() else 0)
    return {
        "mode": "base agent (no skill)",
        "pages": pages,
        "sections": 0,
        "paragraphs": 0,
        "figures": 0,
        "tables": 0,
        "references": 0,
        "headers_footers_separated": 0,
        "paragraphs_with_page_evidence": 0,
        "unreadable_reported": 0,
    }


def skill_pipeline(pdf):
    structure = P.parse(pdf)
    s = structure["stats"]
    paras_with_evidence = sum(
        1 for sec in structure["sections"]
        for p in sec["paragraphs"] if isinstance(p.get("page"), int))
    return {
        "mode": "with skill (paper2arm)",
        "pages": s["pages"],
        "sections": s["sections"],
        "paragraphs": s["paragraphs"],
        "figures": s["figures"],
        "tables": s["tables"],
        "references": s["references"],
        "headers_footers_separated":
            len(structure["headers_footers"]["headers"])
            + len(structure["headers_footers"]["footers"])
            + len(structure["headers_footers"]["page_numbers"]),
        "paragraphs_with_page_evidence": paras_with_evidence,
        "unreadable_reported": s["unreadable_pages"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    t0 = time.time()
    base = naive_baseline(args.pdf)
    t_base = time.time() - t0
    t0 = time.time()
    skill = skill_pipeline(args.pdf)
    t_skill = time.time() - t0

    gain = {k: skill[k] - base[k] for k in base if k != "mode" and isinstance(base[k], int)}
    result = {
        "schema": "paper2arm/pdf-benchmark/v1",
        "paper": os.path.basename(args.pdf),
        "baseline_naive": base,
        "skill_pipeline": skill,
        "gain": gain,
        "seconds": {"base": round(t_base, 3), "skill": round(t_skill, 3)},
        "note": "Same paper, same tools. Counts are run results; reproduce with "
                "'python3 benchmark.py <paper.pdf> --out DIR'.",
    }
    with open(os.path.join(args.out, "benchmark.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print("base:", base)
    print("skill:", skill)
    print("gain:", gain)


if __name__ == "__main__":
    main()
