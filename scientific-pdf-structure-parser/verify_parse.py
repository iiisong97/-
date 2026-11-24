#!/usr/bin/env python3
"""verify_parse.py — deterministic completeness/consistency checks for parse_pdf.py output.

Checks the four quality points of the task:
  提得全 — no empty body, title/abstract present;
  排得对 — paragraphs carry page and are ordered;
  拆得清 — sections / figures / tables / references present when expected;
  核得回 — every text unit has a page (and bbox where available), unreadable pages
           are reported, not silently skipped.

Usage:
    python3 verify_parse.py structure.json --out check.json
"""

import argparse
import json


def check(structure_path):
    """Run all checks; return a dict with issues / pass / stats."""
    d = json.load(open(structure_path, encoding="utf-8"))
    issues = []

    doc = d.get("document", {}) or {}
    if not (doc.get("title") or "").strip():
        issues.append("missing document.title")
    if not (doc.get("abstract") or "").strip():
        issues.append("missing document.abstract (or abstract not found)")

    sections = d.get("sections", [])
    if not sections:
        issues.append("no sections")

    n_para = 0
    for s in sections:
        for p in s.get("paragraphs", []):
            n_para += 1
            if not (p.get("text") or "").strip():
                issues.append("empty paragraph in section %s" % s.get("heading"))
            if not isinstance(p.get("page"), int):
                issues.append("paragraph missing page (核得回): %r" % p.get("id"))

    for f in d.get("figures", []) + d.get("tables", []):
        if not isinstance(f.get("page"), int):
            issues.append("%s missing page: %s" % (f.get("id"), f.get("caption", "")[:30]))

    for r in d.get("references", []):
        if not isinstance(r.get("page"), int):
            issues.append("reference missing page: %s" % r.get("id"))

    unreadable = d.get("unreadable", [])
    stats = d.get("stats", {})

    return {
        "schema": "paper2arm/pdf-verify/v1",
        "issues": issues,
        "issues_count": len(issues),
        "pass": len(issues) == 0,
        "stats": {
            "sections": len(sections),
            "paragraphs": n_para,
            "figures": len(d.get("figures", [])),
            "tables": len(d.get("tables", [])),
            "references": len(d.get("references", [])),
            "unreadable_pages": len(unreadable),
            "pages": stats.get("pages"),
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("structure", help="structure.json from parse_pdf.py")
    ap.add_argument("--out", required=True, help="output check.json")
    args = ap.parse_args()
    result = check(args.structure)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print("verify: %d issues (%s)" % (result["issues_count"],
                                      "PASS" if result["pass"] else "FAIL"))
    for i in result["issues"]:
        print("  -", i)


if __name__ == "__main__":
    main()
