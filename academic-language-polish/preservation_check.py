#!/usr/bin/env python3
"""preservation_check.py — deterministic guardrails for academic language polishing.

The #1 failure of a bare LLM "polish" is that it silently changes claims:
it drops a hedge ("may" -> ""), edits a number, loses a citation marker, or
renames a figure. This script gives the agent a machine-checkable answer to the
question "did the polish change the meaning?".

Usage:
    python3 preservation_check.py ORIGINAL.txt POLISHED.txt [--out report.json]

Output (JSON):
    protected:      numbers+units, citation markers, figure/table/equation refs
                    found in ORIGINAL and whether each survives in POLISHED
    hedges:         hedging tokens in ORIGINAL that are missing in POLISHED
                    (a missing hedge often means a claim was strengthened)
    sentence_edit:  per-sentence edit ratio; high rewrite ratio flags meaning-drift risk
    term_variants:  repeated terms that appear in multiple spellings/case forms
    verdicts:       human-actionable "ok" / "check" list

Everything is stdlib-only and deterministic.
"""

import argparse
import json
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from collections import Counter, defaultdict

# ---------------------------------------------------------------------------
# Token patterns (English scientific text; CJK handled separately below)
# ---------------------------------------------------------------------------
CITATION_RE = re.compile(r"\[[0-9]+(?:[,\-–][0-9]+)*\]|\(([A-Z][A-Za-z\u00c0-\u017f-]+(?:\s+(?:et\s+al\.?|and|&)\s+[A-Z][A-Za-z\u00c0-\u017f-]+)?,\s*\d{4}[a-z]?)\)")
FIG_REF_RE = re.compile(r"\b(?:Fig(?:ure)?s?\.?|Table|Scheme|Algorithm|Eq(?:uation)?s?\.?)\s*\d+[a-z]?(?:\s*[–\-]\s*\d+[a-z]?)?", re.IGNORECASE)
EQ_REF_RE = re.compile(r"\((\d{1,3}(?:\.\d{1,3})?)\)")
NUMBER_UNIT_RE = re.compile(
    r"-?\d+(?:[.,]\d+)*(?:\s*(?:%|‰|°C|°F|K\b|eV|keV|MeV|GeV|V\b|mV|kV|A\b|mA|μA|"
    r"Hz|kHz|MHz|GHz|Ω|mΩ|Pa|kPa|MPa|GPa|J\b|kJ|MJ|W\b|kW|MW|GW|"
    r"s\b|ms|μs|ns|min\b|h\b|d\b|yr\b|yrs?\b|"
    r"m\b|mm|cm|km|μm|nm|pm|Å|"
    r"g\b|mg|μg|ng|kg|"
    r"L\b|mL|μL|nL|M\b|mM|μM|nM|mol\b|mmol|μmol|"
    r"rpm|g/L|mg/L|μg/mL|bp\b|kb\b|Mb\b|Gb\b|"
    r"mol/L|M⊙|kB\b|MB\b|GB\b|TB\b))"
)

HEDGES_EN = [
    "may", "might", "could", "can be", "appears to", "seem to", "seems to",
    "suggest", "suggests", "suggested", "suggesting", "indicate", "indicates",
    "indicated", "likely", "possibly", "possibly be", "probably", "perhaps",
    "presumably", "potentially", "arguably", "tends to", "tend to",
    "in part", "partially", "somewhat", "relatively", "approximately",
    "about", "around", "roughly", "generally", "typically", "often",
    "frequently", "usually", "reportedly", "preliminary", "preliminarily",
    "to our knowledge", "to the best of our knowledge", "we propose",
    "we hypothesize", "hypothesized", "apparent", "apparently", "tentative",
    "putative", "candidate", "is thought to", "are thought to",
    "is believed to", "are believed to", "cannot exclude", "cannot rule out",
    "remains unclear", "remains to be", "warrants further",
]

HEDGES_ZH = [
    "可能", "或许", "也许", "大概", "大约", "约", "左右", "似乎", "好像",
    "表明", "提示", "暗示", "倾向于", "往往", "通常", "一般", "初步",
    "据我们所知", "在一定程度上", "相对", "部分", "某些", "疑似", "估计",
    "推测", "尚未", "有待", "仍需", "需要进一步", "不能排除", "尚不清楚",
    "可能的原因", "潜在", "候选",
]

# --- claim-strength / negation / strict-quantifier conservation ---------------
# Claim verbs are keyed by LEMMA so that grammar fixes (show -> shows) are not
# mistaken for a strength change; only a lemma-level swap is a real change.
STRONG_FORMS = {
    "demonstrate": ["demonstrate", "demonstrates", "demonstrated", "demonstrating"],
    "show": ["show", "shows", "shown", "showed", "showing"],
    "prove": ["prove", "proves", "proved", "proven", "proving"],
    "confirm": ["confirm", "confirms", "confirmed", "confirming"],
    "establish": ["establish", "establishes", "established", "establishing"],
    "reveal": ["reveal", "reveals", "revealed", "revealing"],
    "determine": ["determine", "determines", "determined", "determining"],
    "verify": ["verify", "verifies", "verified", "verifying"],
    "identify": ["identify", "identifies", "identified", "identifying"],
    "find": ["find", "finds", "found", "finding"],
    "observe": ["observe", "observes", "observed", "observing"],
    "measure": ["measure", "measures", "measured", "measuring"],
    "validate": ["validate", "validates", "validated", "validating"],
}
WEAK_FORMS = {
    "suggest": ["suggest", "suggests", "suggested", "suggesting"],
    "indicate": ["indicate", "indicates", "indicated", "indicating"],
    "imply": ["imply", "implies", "implied", "implying"],
    "hint": ["hint", "hints", "hinted", "hinting"],
    "propose": ["propose", "proposes", "proposed", "proposing"],
    "hypothesize": ["hypothesize", "hypothesizes", "hypothesized", "hypothesizing"],
    "speculate": ["speculate", "speculates", "speculated", "speculating"],
    "appear": ["appear", "appears", "appeared", "appearing"],
    "seem": ["seem", "seems", "seemed", "seeming"],
}

NEGATION_EN = ["not", "no", "never", "cannot", "can't", "without", "unless",
               "nor", "neither", "unlikely", "unable", "fails", "fail",
               "failed", "lack", "lacks", "lacked", "absent", "none",
               "impossible", "exclude", "excludes", "excluded", "rule out",
               "rules out", "ruled out"]
NEGATION_ZH = ["不", "非", "无", "未", "没有", "无法", "不能", "从未", "缺",
               "否", "难以", "失败", "排除", "不能排除", "不可能", "尚未"]

STRICT_QUANTIFIERS = ["only", "at least", "at most", "exactly", "all", "none",
                      "both", "neither", "always", "never", "solely",
                      "exclusively", "uniquely", "merely", "purely",
                      "仅", "只有", "至少", "至多", "恰好", "全部", "均",
                      "无一", "始终", "从未", "仅仅", "纯", "唯一", "唯独"]


def normalize(text):
    text = unicodedata.normalize("NFKC", text)
    # Collapse whitespace and typographic dashes/quotes for matching.
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = re.sub(r"\s+", " ", text)
    return text


def findall_span(pattern, text):
    return [(m.group(0), m.start(), m.end()) for m in pattern.finditer(text)]


def extract_protected(text):
    """Return dict of protected-token lists with counts."""
    out = {"numbers_units": [], "citations": [], "fig_table_refs": [], "equation_refs": []}
    for tok, _, _ in findall_span(NUMBER_UNIT_RE, text):
        out["numbers_units"].append(tok.strip())
    for tok, _, _ in findall_span(CITATION_RE, text):
        out["citations"].append(tok.strip())
    for tok, _, _ in findall_span(FIG_REF_RE, text):
        out["fig_table_refs"].append(tok.strip())
    for m in EQ_REF_RE.finditer(text):
        # Only count "(n)" as an equation reference if surrounded by non-digit chars
        # to avoid matching "(123)" inside numbers. Keep simple: short numbers only.
        out["equation_refs"].append(m.group(1))
    return out


def extract_hedges(text):
    low = text.lower()
    found = []
    for h in HEDGES_EN:
        for m in re.finditer(r"\b" + re.escape(h) + r"\b", low):
            found.append((h, m.start()))
    for h in HEDGES_ZH:
        for m in re.finditer(re.escape(h), text):
            found.append((h, m.start()))
    found.sort(key=lambda x: x[1])
    return [h for h, _ in found]


def _present_set(tokens, text, word_boundary=True):
    low = text.lower()
    out = set()
    for t in tokens:
        pat = (r"\b" + re.escape(t) + r"\b") if word_boundary else re.escape(t)
        if re.search(pat, low):
            out.add(t)
    return out


def _lemmas_present(forms_map, text):
    low = text.lower()
    out = set()
    for lemma, forms in forms_map.items():
        if any(re.search(r"\b" + re.escape(f) + r"\b", low) for f in forms):
            out.add(lemma)
    return out


def claim_strength_check(orig_norm, pol_norm):
    """Detect a claim being strengthened or weakened by a lemma-level verb swap.
    Grammar fixes (show -> shows) map to the same lemma and are ignored."""
    o_strong = _lemmas_present(STRONG_FORMS, orig_norm)
    p_strong = _lemmas_present(STRONG_FORMS, pol_norm)
    o_weak = _lemmas_present(WEAK_FORMS, orig_norm)
    p_weak = _lemmas_present(WEAK_FORMS, pol_norm)
    dropped_strong = o_strong - p_strong
    added_weak = p_weak - o_weak
    dropped_weak = o_weak - p_weak
    added_strong = p_strong - o_strong
    flags = []
    if dropped_strong and added_weak:
        flags.append("possibly weakened: strong verb(s) %s dropped, weak verb(s) %s added"
                     % (sorted(dropped_strong)[:5], sorted(added_weak)[:5]))
    if dropped_weak and added_strong:
        flags.append("possibly strengthened: weak verb(s) %s dropped, strong verb(s) %s added"
                     % (sorted(dropped_weak)[:5], sorted(added_strong)[:5]))
    return flags


def negation_check(orig_norm, pol_norm):
    """Flag if the source has a negation but the polished text has none."""
    o_neg = bool(_present_set(NEGATION_EN, orig_norm) | _present_set(NEGATION_ZH, orig_norm, word_boundary=False))
    p_neg = bool(_present_set(NEGATION_EN, pol_norm) | _present_set(NEGATION_ZH, pol_norm, word_boundary=False))
    return ["negation possibly lost: source negates, polished text does not"] if o_neg and not p_neg else []


def quantifier_check(orig_norm, pol_norm):
    """Strict quantifiers (only/at least/at most/all/none/…) must survive."""
    missing = []
    for q in STRICT_QUANTIFIERS:
        in_orig = re.search(re.escape(q), orig_norm, re.I)
        if in_orig and not re.search(re.escape(q), pol_norm, re.I):
            missing.append(q)
    return [f"strict quantifier dropped: {', '.join(sorted(set(missing))[:8])}"] if missing else []


def sentence_split(text):
    # Split on sentence-ending punctuation followed by whitespace+capital/number,
    # or CJK full stop.
    parts = re.split(r"(?<=[.!?。！？])\s+(?=[A-Z0-9\u4e00-\u9fff])", text)
    return [p.strip() for p in parts if p.strip()]


_STOP = {"the", "and", "for", "with", "that", "this", "are", "was", "were",
         "from", "which", "have", "been", "into", "their", "these", "also",
         "between", "such", "where", "while", "than", "after", "before",
         "over", "under", "using", "used", "based", "shown", "figure",
         "table", "results", "data", "method", "methods", "model", "models",
         "here", "there", "more", "most", "not", "but", "all", "each",
         "both", "only", "some", "any", "can", "could", "may", "might"}


def term_variant_check(text):
    """Find repeated terms that appear in multiple spellings/case forms."""
    words = re.findall(r"[A-Za-z][A-Za-z\-]{2,}", text)
    keyed = defaultdict(set)
    for w in words:
        low = w.lower()
        if low in _STOP:
            continue
        keyed[low].add(w)
    variants = {k: sorted(v) for k, v in keyed.items() if len(v) > 1}
    counts = Counter(w.lower() for w in words)
    return {k: v for k, v in variants.items() if counts[k] >= 3}


def run_check(original, polished):
    orig_norm = normalize(original)
    pol_norm = normalize(polished)

    report = {
        "protected": {},
        "hedges_missing": [],
        "sentence_edit": [],
        "term_variants": term_variant_check(polished),
        "verdicts": [],
    }

    # Protected tokens: check survival (as substring, normalized).
    prot = extract_protected(orig_norm)
    for kind, tokens in prot.items():
        rows = []
        for tok in tokens:
            present = tok.lower() in pol_norm.lower()
            rows.append({"token": tok, "preserved": present})
        report["protected"][kind] = rows
        missing = [r["token"] for r in rows if not r["preserved"]]
        if missing:
            report["verdicts"].append(f"check: {kind} missing from polished: {missing[:10]}")

    # Hedges: report those that vanished.
    for h in extract_hedges(orig_norm):
        if h.lower() not in pol_norm.lower():
            report["hedges_missing"].append(h)
    if report["hedges_missing"]:
        report["verdicts"].append(
            "check: hedges possibly removed (claim may have been strengthened): "
            + ", ".join(sorted(set(report["hedges_missing"]))[:15]))

    # Claim strength (strengthening AND weakening), negation scope, quantifiers.
    strength_flags = claim_strength_check(orig_norm, pol_norm)
    report["claim_strength"] = strength_flags
    for f in strength_flags:
        report["verdicts"].append("check: " + f)
    neg_flags = negation_check(orig_norm, pol_norm)
    report["negation_lost"] = neg_flags
    for f in neg_flags:
        report["verdicts"].append("check: " + f)
    quant_flags = quantifier_check(orig_norm, pol_norm)
    report["quantifiers_dropped"] = quant_flags
    for f in quant_flags:
        report["verdicts"].append("check: " + f)

    # Sentence edit ratio.
    orig_sents = sentence_split(orig_norm)
    pol_sents = sentence_split(pol_norm)
    for i, os_ in enumerate(orig_sents):
        if len(os_) < 12:
            continue
        best = 0.0
        for ps_ in pol_sents:
            best = max(best, SequenceMatcher(None, os_, ps_).ratio())
        report["sentence_edit"].append({
            "index": i, "ratio": round(best, 3),
            "flag": "heavy_rewrite" if best < 0.45 else "ok",
            "preview": os_[:80],
        })
    heavy = [r for r in report["sentence_edit"] if r["flag"] == "heavy_rewrite"]
    if heavy:
        report["verdicts"].append(
            f"check: {len(heavy)} sentence(s) rewritten >55% (review for meaning drift)")

    if not report["verdicts"]:
        report["verdicts"].append("ok: no protected token loss, no missing hedges, no heavy rewrites")

    return report


def main():
    ap = argparse.ArgumentParser(description="Guardrails for academic language polishing")
    ap.add_argument("original")
    ap.add_argument("polished")
    ap.add_argument("--out")
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    original = open(args.original, encoding="utf-8").read()
    polished = open(args.polished, encoding="utf-8").read()
    report = run_check(original, polished)

    text = json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    else:
        print(text)


if __name__ == "__main__":
    main()
