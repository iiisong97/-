#!/usr/bin/env python3
"""verify_translation.py — deterministic post-translation verification.

Checks that a translation preserved the facts that matter in scientific text:
numbers, units, citation markers, figure/table/equation references, negation and
limitation markers, and locked glossary-term translations. Emits a report plus a
"needs human review" list; it flags, not guesses — the Agent must then confirm,
fix, or record the item as intentionally kept.

Usage:
    python3 verify_translation.py units.json --glossary glossary.json \
        --out verification.json
"""

import argparse
import json
import re

NUM_RE = re.compile(r"\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")
CITATION_RE = re.compile(r"\[\s*\d+(?:\s*[,，\-–—]\s*\d+)*\s*\]")
FIGTAB_RE = re.compile(r"\b(?:Fig(?:ure)?\.?|Table|Equation|Eq\.?)\s*\(?\d+")
NEG_EN = {"not", "no", "cannot", "can't", "without", "never", "nor", "neither",
          "unlikely", "unable", "fails", "lack", "lacks", "absent"}
NEG_ZH = {"不", "非", "无", "未", "没有", "不能", "无法", "从不", "无法", "缺",
          "否", "难以", "失败"}
LIMIT_EN = {"only", "unless", "provided", "assuming", "limited", "restricted"}
LIMIT_ZH = {"仅", "只有", "除非", "如果", "当", "前提", "在……下", "限于",
            "假设", "给定", "限于", "条件"}

# Technical tokens that Chinese scientific writing conventionally KEEPS in Latin
# script; if present in the source they must survive (or be flagged for review).
KEPT_UNITS = ["nm", "µm", "μm", "mm", "cm", "km", "Hz", "kHz", "MHz", "GHz",
              "THz", "ms", "µs", "μs", "ns", "MB", "GB", "TB", "KB", "FLOPs",
              "FLOPS", "BLEU", "GPU", "TPU", "FPS", "dB", "eV", "keV", "MeV",
              "GeV", "°C", "°F", "×10", "i.e.", "e.g.", "w.r.t.", "arXiv"]


def _kept_tokens(source):
    found = []
    for u in KEPT_UNITS:
        if re.search(r"(?<![A-Za-z])" + re.escape(u) + r"(?![A-Za-z])", source):
            found.append(u)
    return found


def _protected_items(source):
    nums = NUM_RE.findall(source)
    cits = CITATION_RE.findall(source)
    figs = FIGTAB_RE.findall(source)
    neg = [w for w in re.findall(r"[A-Za-z']+", source) if w.lower() in NEG_EN]
    limit = [w for w in re.findall(r"[A-Za-z']+", source) if w.lower() in LIMIT_EN]
    return {"numbers": nums, "citations": cits, "fig_refs": figs,
            "negation": neg, "limitation": limit}


def _has_negation_zh(translation):
    return any(m in translation for m in NEG_ZH)


def _has_limit_zh(translation):
    return any(m in translation for m in LIMIT_ZH)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("units")
    ap.add_argument("--glossary", default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    units = json.load(open(args.units, encoding="utf-8")).get("units", [])
    glossary = {}
    if args.glossary:
        gl = json.load(open(args.glossary, encoding="utf-8")).get("terms", [])
        glossary = {t["term"]: t for t in gl if t.get("translation")}

    per_unit = []
    missing_numbers, missing_citations, missing_figs = [], [], []
    missing_negation, missing_limitation, missing_units = [], [], []

    for u in units:
        src = u.get("source", "")
        trans = u.get("translation", "")
        if not trans:
            continue
        prot = _protected_items(src)
        trans_compact = re.sub(r"\s+", "", trans)
        issues = []
        for n in prot["numbers"]:
            if n not in trans:
                issues.append(f"number {n} missing")
                missing_numbers.append({"para_id": u.get("para_id"), "number": n,
                                        "source": src[:60]})
        for c in prot["citations"]:
            # tolerate whitespace differences like [13, 7] vs [13,7]
            if re.sub(r"\s+", "", c) not in trans_compact:
                issues.append(f"citation {c} missing")
                missing_citations.append({"para_id": u.get("para_id"), "citation": c})
        for f in prot["fig_refs"]:
            # the reference digit must survive (translation may render 图/表/式)
            digit = re.search(r"\d+", f)
            if digit and digit.group(0) not in trans:
                issues.append(f"figure/table/equation ref {f} missing")
                missing_figs.append({"para_id": u.get("para_id"), "ref": f})
        if prot["negation"] and not _has_negation_zh(trans):
            issues.append(f"negation not marked in translation ({prot['negation']})")
            missing_negation.append({"para_id": u.get("para_id"),
                                     "negation": prot["negation"]})
        if prot["limitation"] and not _has_limit_zh(trans):
            issues.append(f"limitation marker not marked ({prot['limitation']})")
            missing_limitation.append({"para_id": u.get("para_id"),
                                       "limitation": prot["limitation"]})
        for tk in _kept_tokens(src):
            if tk not in trans:
                issues.append(f"technical token {tk} dropped")
                missing_units.append({"para_id": u.get("para_id"), "token": tk})
        if issues:
            per_unit.append({"para_id": u.get("para_id"), "issues": issues})

    # term consistency: the locked translation must appear for each occurrence
    term_report = []
    for term, t in glossary.items():
        locked = t.get("translation")
        if not locked:
            continue
        occ = [u for u in units if term.lower() in u.get("source", "").lower()]
        if not occ:
            continue
        # consistent if each translated unit uses the locked translation (or keeps the term)
        variants, consistent = set(), True
        for u in occ:
            trans = u.get("translation", "")
            if locked not in trans and term.lower() not in trans.lower():
                consistent = False
                variants.add(trans[:50])
        term_report.append({"term": term, "translation": locked,
                            "occurrences": len(occ),
                            "para_ids": [u.get("para_id") for u in occ],
                            "consistent": consistent,
                            "variants_found": sorted(variants)[:3]})

    needs_review = []
    for t in term_report:
        if not t["consistent"]:
            needs_review.append({"type": "term_inconsistent", "detail": t})

    out = {
        "schema": "paper2arm/translation-verify/v1",
        "protected": {
            "numbers_missing": missing_numbers,
            "citations_missing": missing_citations,
            "fig_refs_missing": missing_figs,
            "negation_missing": missing_negation,
            "limitation_missing": missing_limitation,
            "kept_units_missing": missing_units,
        },
        "term_consistency": term_report,
        "per_unit_issues": per_unit,
        "needs_human_review": needs_review,
        "summary": {
            "units_total": len(units),
            "units_translated": sum(1 for u in units if u.get("translation")),
            "units_with_issues": len(per_unit),
            "numbers_missing": len(missing_numbers),
            "citations_missing": len(missing_citations),
            "fig_refs_missing": len(missing_figs),
            "negation_missing": len(missing_negation),
            "kept_units_missing": len(missing_units),
            "terms_inconsistent": sum(1 for t in term_report if not t["consistent"]),
        },
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"verification: {out['summary']['units_translated']}/{out['summary']['units_total']} "
          f"translated, {out['summary']['units_with_issues']} units with issues, "
          f"{out['summary']['terms_inconsistent']} terms inconsistent")


if __name__ == "__main__":
    main()
