#!/usr/bin/env python3
"""segment.py — build the translation-unit skeleton (paragraph-level alignment).

Reads the enriched structure JSON and emits one translation unit per paragraph,
with para_id, page, section and source text. The translating Agent fills in the
"translation" (and optional "notes"/"uncertain") fields; because the skeleton is
fixed, no paragraph is missed, duplicated or misplaced — the paragraph alignment
(段号 ↔ 原文 ↔ 页码) is structural, not remembered.

Long paragraphs are additionally split into sentence spans so the Agent can
translate sentence-by-sentence with the paragraph as context.

Usage:
    python3 segment.py structure.json --out units.json
"""

import argparse
import json
import re

SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")


def sentences(text):
    return [s.strip() for s in SENT_SPLIT.split(text) if s.strip()]


AFFILIATION_KW = ("google", "university", "institute", "laboratory", "lab ",
                 "mellon", "toronto", "montreal", "montréal", "department",
                 "college", "carnegie", "deepmind", "openai")


def _is_front_matter(sec):
    """Skip the copyright preamble and the author/affiliation block: these are
    not scientific content and must not become translation units. Only page 1
    can be front matter, so the References section is never caught here."""
    if (sec.get("page") or 1) != 1:
        return False
    h = (sec.get("heading") or "").strip().lower()
    if h == "preamble":
        return True
    body = " ".join(p.get("text", "") for p in sec.get("paragraphs", [])).lower()
    if "@" in body or "http" in body or ".edu" in body or ".com" in body:
        return True
    return any(kw in body for kw in AFFILIATION_KW)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("structure")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    doc = json.load(open(args.structure, encoding="utf-8"))
    units = []
    pid = 0

    # title + abstract as the first two units (they matter for terminology)
    title = doc.get("document", {}).get("title", "")
    if title:
        pid += 1
        units.append({"para_id": pid, "page": 1, "section": "Title",
                      "source": title, "translation": "", "notes": "", "uncertain": False})
    abstract = doc.get("document", {}).get("abstract", "")
    if abstract:
        pid += 1
        units.append({"para_id": pid, "page": 1, "section": "Abstract",
                      "source": abstract, "translation": "", "notes": "", "uncertain": False})

    for sec in doc.get("sections", []):
        if _is_front_matter(sec):
            continue
        heading = sec.get("heading") or ""
        page = sec.get("page")
        # a heading itself is a unit (it must be translated consistently too)
        if heading and not re.match(r"^(Preamble|.*@.*)$", heading):
            pid += 1
            units.append({"para_id": pid, "page": page, "section": heading,
                          "source": heading, "translation": "", "notes": "",
                          "uncertain": False, "is_heading": True})
        for p in sec.get("paragraphs", []):
            text = (p.get("text") or "").strip()
            if not text:
                continue
            pid += 1
            units.append({"para_id": pid, "page": p.get("page", page),
                          "section": heading, "source": text, "translation": "",
                          "notes": "", "uncertain": False,
                          "sentences": sentences(text)})

    # captions (figure/table) as units — chart titles must be translated too
    for kind in ("figures", "tables"):
        for it in doc.get(kind, []):
            cap = it.get("caption")
            if not cap:
                continue
            pid += 1
            units.append({"para_id": pid, "page": it.get("page"),
                          "section": f"{kind[:-1].title()} {it.get('number') or ''}".strip(),
                          "source": cap, "translation": "", "notes": "",
                          "uncertain": False, "is_caption": True})

    out = {"schema": "paper2arm/translation-units/v1",
           "note": "Fill 'translation' for each unit. Keep para_id/page/section fixed "
                   "so the bilingual alignment is structural.",
           "units": units}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"wrote {len(units)} translation units to {args.out}")


if __name__ == "__main__":
    main()
