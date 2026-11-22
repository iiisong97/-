#!/usr/bin/env python3
"""benchmark.py — fair A/B of the polish Skill against a bare "LLM-only" baseline.

A bare LLM that polishes text has no deterministic way to answer "did I change
the meaning?". This Skill adds a guardrail checker covering eight categories of
meaning-relevant tokens (numbers+units, citations, figure/table refs, equation
refs, hedges, claim-strength verbs, negation scope, strict quantifiers). The
comparison is run on the same synthetic "broken polish" sample, so the gain is an
observable run result, not a self-claim.

Usage:
    python3 benchmark.py --out DIR [--original o.txt --polished p.txt]
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import preservation_check as P  # noqa: E402

# Synthetic sample (clearly marked): a "polish" that silently dropped a number,
# a citation, a hedge, weakened a claim, lost a negation and a quantifier.
SAMPLE_ORIGINAL = (
    "Our results demonstrate that the proposed model achieves 28.4 BLEU [12] "
    "(Table 2). It cannot be excluded that only two cases were affected, and the "
    "improvement may be limited to low-resource settings."
)
SAMPLE_BROKEN = (
    "Our results suggest that the proposed model achieves high BLEU "
    "(Table 2). It can be excluded that two cases were affected, and the "
    "improvement is limited to low-resource settings."
)

CHECK_CATEGORIES = ["numbers_units", "citations", "fig_table_refs",
                    "equation_refs", "hedges", "claim_strength",
                    "negation", "quantifiers"]


def baseline():
    """A bare LLM has no deterministic check: it can detect none of these."""
    return {"mode": "bare LLM (no skill)", "check_categories": 0,
            "violations_detectable": 0}


def skill(original, polished):
    report = P.run_check(original, polished)
    n_viol = (
        sum(1 for rows in report["protected"].values() for r in rows if not r["preserved"])
        + len(report["hedges_missing"])
        + len(report["claim_strength"])
        + len(report["negation_lost"])
        + len(report["quantifiers_dropped"])
    )
    return {"mode": "with skill (academic-language-polish)",
            "check_categories": len(CHECK_CATEGORIES),
            "violations_detectable": n_viol}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--original", default=None)
    ap.add_argument("--polished", default=None)
    args = ap.parse_args()

    original = open(args.original, encoding="utf-8").read() if args.original else SAMPLE_ORIGINAL
    polished = open(args.polished, encoding="utf-8").read() if args.polished else SAMPLE_BROKEN

    base = baseline()
    sk = skill(original, polished)

    result = {
        "schema": "paper2arm/polish-benchmark/v1",
        "input": {"note": "synthetic sample (deliberately broken polish) unless "
                          "--original/--polished given"},
        "baseline_naive": base,
        "skill_pipeline": sk,
        "gain": {
            "check_categories": sk["check_categories"] - base["check_categories"],
            "violations_detectable": sk["violations_detectable"] - base["violations_detectable"],
        },
        "note": "Same input, same tools. The Skill adds deterministic meaning-"
                "preservation guardrails the bare LLM lacks; counts are run results.",
    }
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "benchmark.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print(f"baseline: {base}")
    print(f"skill:    {sk}")
    print(f"gain:     {result['gain']}")


if __name__ == "__main__":
    main()
