#!/usr/bin/env python3
"""extract_terms.py — deterministic domain-term candidate extraction.

Reads the enriched structure JSON from parse_pdf.py and emits a glossary
skeleton: acronyms, acronym-definition pairs, and repeated title-case phrases.
The translating Agent fills in (and locks) each term's translation; a later
verification step checks the locked translation is used consistently — so the
term table is *executed*, not merely written in the prompt.

Usage:
    python3 extract_terms.py structure.json --out glossary.json
"""

import argparse
import json
import re
from collections import Counter

ACRONYM_RE = re.compile(r"\b[A-Z]{2,6}\b")
DEF_PAIR_RE = re.compile(
    r"\b([A-Z][a-zA-Z]+(?:[ -][A-Z][a-zA-Z]+){1,6})\s*\(([A-Z]{2,6})\)")
TITLE_PHRASE_RE = re.compile(r"\b[A-Z][a-zA-Z]+(?:[ -][A-Z][a-zA-Z]+){2,5}\b")

# Common non-domain terms to skip (English function/capitalized general words)
STOP = {
    "THE", "AND", "FOR", "WITH", "THAT", "THIS", "THESE", "THOSE", "FROM",
    "INTO", "OVER", "UNDER", "WHILE", "WHERE", "WHICH", "TABLE", "FIGURE",
    "SECTION", "APPENDIX", "CHAPTER", "THEY", "THEIR", "HAVE", "WERE", "ARE",
    "WAS", "HAS", "BEEN", "ALSO", "USING", "USED", "MORE", "LESS", "THAN",
    "EACH", "BOTH", "SUCH", "ONLY", "EVEN", "WHEN", "AFTER", "BEFORE",
    "NOVEMBER", "DECEMBER", "JANUARY", "UNIVERSITY", "COLLEGE", "LAB",
    "DEPARTMENT", "RESEARCH", "WORK", "PAPER", "MODEL", "DATA", "RESULTS",
    "METHOD", "METHODS", "EXPERIMENT", "EXPERIMENTS", "STUDY", "STUDIES",
}


def _text_of(doc):
    parts = [(doc.get("document", {}) or {}).get("title") or ""]
    parts.append((doc.get("document", {}) or {}).get("abstract") or "")
    for sec in doc.get("sections", []):
        parts.append(sec.get("heading") or "")
        for p in sec.get("paragraphs", []):
            parts.append(p.get("text") or "")
    for f in doc.get("figures", []) + doc.get("tables", []):
        parts.append(f.get("caption") or "")
    return "\n".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("structure")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    doc = json.load(open(args.structure, encoding="utf-8"))
    text = _text_of(doc)

    terms = {}

    # 1. acronyms (>= 2 occurrences)
    for m in ACRONYM_RE.finditer(text):
        a = m.group(0)
        if a in STOP or len(a) < 2:
            continue
        terms.setdefault(a, {"term": a, "kind": "acronym", "count": 0})
        terms[a]["count"] += 1

    # 2. definition pairs (phrase -> acronym)
    for m in DEF_PAIR_RE.finditer(text):
        phrase, acro = m.group(1), m.group(2)
        if acro in terms:
            terms[acro].setdefault("full_form", phrase)
        key = phrase.lower()
        terms.setdefault(phrase, {"term": phrase, "kind": "phrase", "count": 0})
        terms[phrase]["count"] += 1

    # 3. repeated title-case phrases (>= 3 occurrences)
    phrase_counts = Counter()
    for m in TITLE_PHRASE_RE.finditer(text):
        p = m.group(0)
        if any(w in STOP for w in p.split()):
            continue
        phrase_counts[p] += 1
    for p, c in phrase_counts.items():
        if c >= 3:
            key = p.lower()
            terms.setdefault(p, {"term": p, "kind": "phrase", "count": c})

    # keep acronyms with >=2 occurrences and phrases with >=3; drop rare noise
    candidates = []
    for t in terms.values():
        if t["kind"] == "acronym" and t["count"] < 2:
            continue
        t["translation"] = None          # Agent locks this; None => keep as-is or translate
        t["occurrences"] = t.pop("count")
        candidates.append(t)

    # sort: acronyms first, then phrases by frequency
    candidates.sort(key=lambda t: (t["kind"] != "acronym", -t["occurrences"]))

    out = {"schema": "paper2arm/glossary/v1",
           "note": "Candidate terms. The translating Agent must set 'translation' "
                   "for each (or explicitly keep the English term).",
           "terms": candidates[:200]}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"wrote {len(candidates)} term candidates to {args.out}")


if __name__ == "__main__":
    main()
