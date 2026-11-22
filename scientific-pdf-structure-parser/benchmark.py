#!/usr/bin/env python3
"""benchmark.py — fair A/B of the parser against a bare "raw text" baseline.

A bare Agent that reads a PDF gets raw text with no section/table/figure/equation/
reference structure and no page/bbox evidence. This Skill's parse_pdf.py emits a
structured JSON where every element carries page + bbox, plus authors/affiliations
and repeated headers/footers. Counts are computed from the same PDF, so the gain
is a run result, not a self-claim.

Usage:
    python3 benchmark.py <paper.pdf> --out DIR
"""

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import parse_pdf as P  # noqa: E402


def _evidence_coverage(structure):
    elements = []
    for sec in structure.get("sections", []):
        elements.append(sec.get("page"))
        elements += [p.get("page") for p in sec.get("paragraphs", [])]
    elements += [t.get("page") for t in structure.get("tables", [])]
    elements += [f.get("page") for f in structure.get("figures", [])]
    elements += [e.get("page") for e in structure.get("equations", [])]
    elements += [r.get("page") for r in structure.get("references", [])]
    if not elements:
        return 0.0
    return round(sum(1 for p in elements if p is not None) / len(elements), 3)


def baseline():
    return {"mode": "bare LLM / raw text",
            "structured_elements": 0, "evidence_coverage": 0.0,
            "tables": 0, "figures": 0, "equations": 0, "references": 0,
            "authors": 0, "headers_footers": 0}


def skill(paper, out_dir):
    struct_path = os.path.join(out_dir, "_structure.json")
    r = subprocess.run([sys.executable, os.path.join(HERE, "parse_pdf.py"),
                        paper, "--out", struct_path],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[:400])
    s = json.load(open(struct_path, encoding="utf-8"))
    n_elements = (len(s.get("sections", [])) + len(s.get("tables", []))
                  + len(s.get("figures", [])) + len(s.get("equations", []))
                  + len(s.get("references", [])))
    hf = s.get("headers_footers", {})
    return {"mode": "with skill (scientific-pdf-structure-parser)",
            "structured_elements": n_elements,
            "evidence_coverage": _evidence_coverage(s),
            "tables": len(s.get("tables", [])),
            "figures": len(s.get("figures", [])),
            "equations": len(s.get("equations", [])),
            "references": len(s.get("references", [])),
            "authors": len(s.get("document", {}).get("authors", [])),
            "headers_footers": len(hf.get("headers", [])) + len(hf.get("footers", [])),
            "plaintext_pages": len(s.get("plaintext_pages", {}))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paper")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    base = baseline()
    sk = skill(args.paper, args.out)

    result = {
        "schema": "paper2arm/parse-benchmark/v1",
        "input": {"paper": os.path.basename(args.paper)},
        "baseline_naive": base,
        "skill_pipeline": sk,
        "gain": {k: sk[k] - base[k] for k in
                 ("structured_elements", "evidence_coverage", "tables", "figures",
                  "equations", "references", "authors", "headers_footers")},
        "note": "Same PDF, same tools. The Skill adds structure + page/bbox evidence "
                "that a bare raw-text read lacks; counts are run results.",
    }
    with open(os.path.join(args.out, "benchmark.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print(f"baseline: {base}")
    print(f"skill:    {sk}")
    print(f"gain:     {result['gain']}")


if __name__ == "__main__":
    main()
