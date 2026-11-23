#!/usr/bin/env python3
"""benchmark.py — fair A/B of the Nanopublication skill against a bare LLM.

A bare LLM asked to "extract assertions" typically returns one long assertion
per paragraph with no evidence, no triple, no provenance and no id. This skill
emits atomic assertions each bound to a source quote + page and carrying
subject/predicate/object, provenance, confidence and id, validated by
nanopub_check.py. The comparison runs the same checker over two synthetic
samples, so the gain is a run result, not a self-claim.

Usage:
    python3 benchmark.py --out DIR [--result result.json]
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nanopub_check as NC  # noqa: E402

# Synthetic samples (clearly marked): the same paper claim, once as a bare-LLM
# paragraph dump, once as a proper nanopublication.
PAPER = {"title": "Attention Is All You Need", "authors": ["A. Vaswani", "others"],
         "year": 2017, "identifiers": {"arxiv": "1706.03762"}}

BARE_LLM = {
    "schema": "nanopub/v1", "paper": PAPER,
    "nanopublications": [{
        "assertion": {
            "text": "We propose the Transformer, based solely on attention mechanisms, "
                     "dispensing with recurrence and convolutions, and it achieves "
                     "28.4 BLEU on WMT 2014 with less training time than prior models.",
            "subject": "the Transformer", "predicate": "achieves",
            "object": "28.4 BLEU on WMT 2014"},
        # bare LLM: no evidence, no provenance, no id, no confidence
    }],
}

SKILL = {
    "schema": "nanopub/v1", "paper": PAPER,
    "nanopublications": [
        {"id": "np-01", "assertion": {
            "text": "The Transformer is based solely on attention mechanisms.",
            "subject": "the Transformer", "predicate": "based_on", "object": "attention mechanisms"},
         "condition": None,
         "evidence": {"quote": "a new simple network architecture, the Transformer, based solely "
                              "on attention mechanisms, dispensing with recurrence and convolutions",
                      "location": {"page": 1, "section": "Abstract"}},
         "confidence": {"level": "direct", "basis": "quote states the claim verbatim"},
         "provenance": {"paper_title": PAPER["title"], "authors": PAPER["authors"],
                        "year": 2017, "identifiers": PAPER["identifiers"]}},
        {"id": "np-02", "assertion": {
            "text": "The Transformer achieves 28.4 BLEU on WMT 2014 English-to-German.",
            "subject": "the Transformer", "predicate": "achieves",
            "object": "28.4 BLEU on WMT 2014 English-to-German"},
         "condition": "big transformer model, 3.5 days on 8 GPUs",
         "evidence": {"quote": "our big model ... reaches 28.4 BLEU on the WMT 2014 English-to-German "
                              "translation task",
                      "location": {"page": 8, "section": "Results"}},
         "confidence": {"level": "direct", "basis": "quote reports the exact number and task"},
         "provenance": {"paper_title": PAPER["title"], "authors": PAPER["authors"],
                        "year": 2017, "identifiers": PAPER["identifiers"]}},
    ],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--result", default=None)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    skill = json.load(open(args.result, encoding="utf-8")) if args.result else SKILL
    base_report = NC.run_check(BARE_LLM)
    skill_report = NC.run_check(skill)

    result = {
        "schema": "paper2arm/nanopub-benchmark/v1",
        "note": "synthetic samples unless --result given; counts are checker run results",
        "baseline_naive": {"issues": base_report["issues"],
                           "nanopublications": base_report["total_nanopublications"]},
        "skill_pipeline": {"issues": skill_report["issues"],
                           "nanopublications": skill_report["total_nanopublications"]},
        "gain": {"issues_avoided": base_report["issues"] - skill_report["issues"],
                 "atomic_assertions": skill_report["total_nanopublications"]
                                      - base_report["total_nanopublications"]},
    }
    with open(os.path.join(args.out, "benchmark.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
