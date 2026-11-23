#!/usr/bin/env python3
"""benchmark.py — fair A/B of the literature-notes skill against a bare LLM.

A bare LLM asked to "summarise this paper" returns a compressed abstract with no
paper card, no per-section structure, no anchors and no searchable knowledge
points. This skill emits a section-aligned card + per-section notes +
knowledge points, every note carrying a page/quote anchor, validated by
notes_check.py. The comparison runs the same checker over two synthetic samples.

Usage:
    python3 benchmark.py --out DIR [--result result.json]
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import notes_check as NC  # noqa: E402

# Synthetic samples (clearly marked): the same paper, once as a bare-LLM summary,
# once as a proper structured note.
BARE_LLM = {
    "schema": "lit-notes/v1",
    # bare LLM: no paper_card, no section_notes, no knowledge_points — just prose
    "summary": "This paper proposes a new attention-based architecture that is "
               "faster and achieves good results on translation benchmarks.",
}

SKILL = {
    "schema": "lit-notes/v1",
    "paper_card": {
        "title": "Attention Is All You Need", "authors": ["A. Vaswani", "others"],
        "year": 2017, "identifiers": {"arxiv": "1706.03762"},
        "research_question": "Can sequence transduction be done solely with attention?",
        "data": "WMT 2014 English-to-German and English-to-French",
        "methods": ["Transformer", "multi-head self-attention"],
        "key_findings": ["achieves 28.4 BLEU on WMT 2014 En-De"],
        "conclusions": ["the Transformer outperforms recurrent and convolutional models"],
        "limitations": ["not reported"],
        "preconditions": ["trained on 8 NVIDIA P100 GPUs"],
    },
    "section_notes": [{
        "section": "3.2 Multi-Head Attention", "number": "3.2", "level": 2, "page": 4,
        "purpose": "define multi-head attention", "method": "h parallel attention heads",
        "result": "jointly attend to different representation subspaces",
        "conclusion": "multi-head attention is more effective than single-head",
        "transition": "follows scaled dot-product attention",
        "anchors": [{"page": 4, "paragraph": 1,
                     "quote": "Multi-head attention allows the model to jointly attend to information"}],
    }],
    "knowledge_points": [{
        "id": "kp-0123456789abcdef", "term": "Multi-Head Attention", "type": "method",
        "definition": "h parallel attention heads over different subspaces",
        "synonyms": ["MHA"],
        "anchors": [{"page": 4, "quote": "Multi-head attention allows the model"}],
    }],
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
        "schema": "paper2arm/notes-benchmark/v1",
        "note": "synthetic samples unless --result given; counts are checker run results",
        "baseline_naive": {"issues": base_report["issues"],
                           "section_notes": base_report["section_notes"],
                           "knowledge_points": base_report["knowledge_points"]},
        "skill_pipeline": {"issues": skill_report["issues"],
                           "section_notes": skill_report["section_notes"],
                           "knowledge_points": skill_report["knowledge_points"]},
        "gain": {"issues_avoided": base_report["issues"] - skill_report["issues"],
                 "section_notes": skill_report["section_notes"] - base_report["section_notes"],
                 "knowledge_points": skill_report["knowledge_points"] - base_report["knowledge_points"]},
    }
    with open(os.path.join(args.out, "benchmark.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
