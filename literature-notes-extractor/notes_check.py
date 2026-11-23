#!/usr/bin/env python3
"""notes_check.py — deterministic guardrails for structured literature notes.

Validates a result.json against lit-notes/v1 and the four qualities in the task:
对得上 (section alignment), 留得住 (field completeness), 找得回 (anchor
traceability + quote verification against the paper), 用得上 (searchable
knowledge points). Stdlib only; stdout only.

Usage:
    python3 notes_check.py result.json [--structure structure.json] [--out rpt.json]
"""

import argparse
import json
import re
import sys

KP_TYPES = {"concept", "variable", "method", "conclusion"}

CARD_FIELDS = ["research_question", "data", "methods", "key_findings",
               "conclusions", "limitations", "preconditions"]

SECTION_FIELDS = ["purpose", "method", "result", "conclusion"]


def normalize(text):
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def collect_plaintext(structure):
    """Flatten per-page plaintext from parse_pdf.py output for quote verification."""
    pages = {}
    pp = (structure or {}).get("plaintext_pages") or {}
    for p, txt in pp.items():
        pages[str(p)] = normalize(txt)
    return pages


def check_paper_card(card):
    flags = []
    for f in CARD_FIELDS:
        v = card.get(f)
        if not v:
            flags.append(f"paper_card.{f} missing")
        elif isinstance(v, (list, tuple)) and not [x for x in v if (x or "").strip()]:
            flags.append(f"paper_card.{f} empty")
        elif isinstance(v, str) and not v.strip():
            flags.append(f"paper_card.{f} empty")
    return flags


def verify_quote(quote, page, plaintext_pages):
    """Return None if the quote is verifiable against the paper, else a flag."""
    q = normalize(quote)
    if not q:
        return "anchor.quote missing"
    if not plaintext_pages:
        return None  # no structure given: cannot verify, do not fabricate a verdict
    ptext = plaintext_pages.get(str(page), "")
    if not ptext:
        return f"anchor.page {page} not in structure plaintext"
    if q not in ptext:
        return f"anchor quote not found on page {page}"
    return None


def run_check(data, structure=None):
    issues = []
    per = []
    plaintext = collect_plaintext(structure) if structure is not None else {}

    card = data.get("paper_card") or {}
    issues += check_paper_card(card)

    # 对得上：章节笔记按论文原章节，含四要素与锚点
    secs = data.get("section_notes") or []
    if not secs:
        issues.append("section_notes missing/empty")
    for i, s in enumerate(secs):
        f = []
        if not (s.get("section") or "").strip():
            f.append("missing section heading")
        for sf in SECTION_FIELDS:
            if not (s.get(sf) or "").strip():
                f.append(f"missing {sf}")
        anchors = s.get("anchors") or []
        if not anchors:
            f.append("missing anchors")
        else:
            for a in anchors:
                if not a.get("page"):
                    f.append("anchor missing page")
                    continue
                v = verify_quote(a.get("quote"), a.get("page"), plaintext)
                if v:
                    f.append(v)
        for x in f:
            issues.append(f"section_notes[{i}]: {x}")
        per.append({"index": i, "kind": "section", "flags": f})

    # 用得上：知识点可检索、可去重
    kps = data.get("knowledge_points") or []
    seen_terms = {}
    for i, kp in enumerate(kps):
        f = []
        term = (kp.get("term") or "").strip()
        if not term:
            f.append("missing term")
        else:
            tkey = normalize(term)
            if tkey in seen_terms:
                f.append(f"duplicate term (first at kp[{seen_terms[tkey]}])")
            else:
                seen_terms[tkey] = i
        if kp.get("type") not in KP_TYPES:
            f.append("type not in {concept|variable|method|conclusion}")
        if not (kp.get("definition") or "").strip():
            f.append("missing definition")
        if not kp.get("id"):
            f.append("missing id")
        anchors = kp.get("anchors") or []
        if not anchors:
            f.append("missing anchors")
        else:
            for a in anchors:
                if not a.get("page"):
                    f.append("anchor missing page")
                    continue
                v = verify_quote(a.get("quote"), a.get("page"), plaintext)
                if v:
                    f.append(v)
        for x in f:
            issues.append(f"knowledge_points[{i}]: {x}")
        per.append({"index": i, "kind": "kp", "flags": f})

    if not data.get("paper_card"):
        issues.append("paper_card missing")

    verdicts = ["ok: notes pass section-alignment + completeness + anchor + knowledge-point checks"] \
        if not issues else issues
    return {
        "section_notes": len(secs),
        "knowledge_points": len(kps),
        "issues": len(issues),
        "verdicts": verdicts,
        "per_item": per,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("result")
    ap.add_argument("--structure", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    data = json.load(open(args.result, encoding="utf-8"))
    structure = json.load(open(args.structure, encoding="utf-8")) if args.structure else None
    report = run_check(data, structure)
    if args.out:
        json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
