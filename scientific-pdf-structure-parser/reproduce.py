#!/usr/bin/env python3
"""reproduce.py — one-command entry: parse a PDF, verify the structure, run A/B.

Usage:
    python3 reproduce.py input.pdf --out DIR [--selftest]

  --selftest  run the full pipeline on the bundled example PDF and print PASS/FAIL.
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import parse_pdf as P          # noqa: E402
import verify_parse as V       # noqa: E402
import benchmark as B          # noqa: E402


def run(pdf, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    structure_path = os.path.join(out_dir, "structure.json")
    check_path = os.path.join(out_dir, "check.json")

    structure = P.parse(pdf)
    with open(structure_path, "w", encoding="utf-8") as fh:
        json.dump(structure, fh, ensure_ascii=False, indent=2)

    # verify (duplicate the small check inline so we can report pass/fail)
    issues = []
    doc = structure.get("document", {}) or {}
    if not (doc.get("title") or "").strip():
        issues.append("missing title")
    if not structure.get("sections"):
        issues.append("no sections")
    for sec in structure.get("sections", []):
        for p in sec.get("paragraphs", []):
            if not isinstance(p.get("page"), int):
                issues.append("paragraph missing page")
    check = {"issues": issues, "issues_count": len(issues),
             "pass": not issues, "stats": structure.get("stats")}
    with open(check_path, "w", encoding="utf-8") as fh:
        json.dump(check, fh, ensure_ascii=False, indent=2)

    # benchmark
    bench = {
        "baseline_naive": B.naive_baseline(pdf),
        "skill_pipeline": B.skill_pipeline(pdf),
    }
    bench["gain"] = {k: bench["skill_pipeline"][k] - bench["baseline_naive"][k]
                     for k in bench["baseline_naive"]
                     if k != "mode" and isinstance(bench["baseline_naive"][k], int)}
    bench["schema"] = "paper2arm/pdf-benchmark/v1"
    with open(os.path.join(out_dir, "benchmark.json"), "w", encoding="utf-8") as fh:
        json.dump(bench, fh, ensure_ascii=False, indent=2)

    s = structure["stats"]
    print("parsed: %d pages / %d sections / %d paragraphs / %d refs" %
          (s["pages"], s["sections"], s["paragraphs"], s["references"]))
    print("verify: %s (%d issues)" % ("PASS" if check["pass"] else "FAIL",
                                      check["issues_count"]))
    print("gain:", bench["gain"])
    return check["pass"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--out", required=True)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        # text-only self-test: run the verifier on the bundled example structure.
        example = os.path.join(HERE, "example", "structure.json")
        if not os.path.exists(example):
            print("[selftest] no example/structure.json; skipping", file=sys.stderr)
            sys.exit(2)
        import verify_parse
        check = verify_parse.check(example)
        print("[selftest]", "PASS" if check["pass"] else "FAIL",
              "(%d issues)" % check["issues_count"])
        sys.exit(0 if check["pass"] else 1)

    run(args.pdf, args.out)


if __name__ == "__main__":
    main()
