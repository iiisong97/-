#!/usr/bin/env python3
"""nanopub_check.py — deterministic guardrails for Nanopublication extraction.

Validates a result.json against the nanopub/v1 schema and the four quality
criteria in the task: 拆得细 (atomicity), 对得上 (evidence alignment),
追得回 (traceability), 读得懂 (machine-readability). Stdlib only; stdout only.

Usage:
    python3 nanopub_check.py result.json            # print report to stdout
    python3 nanopub_check.py result.json --out rpt.json
"""

import argparse
import json
import re
import sys

CONTROLLED_PREDICATES = {
    # 比较
    "outperforms", "underperforms", "equals", "exceeds", "comparable_to", "superior_to",
    # 因果
    "causes", "leads_to", "results_in", "improves", "increases", "decreases", "reduces",
    "prevents", "enables", "requires", "inhibits", "accelerates",
    # 关联
    "correlates_with", "associated_with", "predicts",
    # 结构
    "is_a", "has_part", "part_of", "contains", "composed_of", "located_in", "encodes", "expresses",
    # 测量
    "measured_as", "achieves", "yields", "reports", "obtains", "estimates",
    # 方法
    "evaluated_by", "compared_with", "trained_on", "based_on", "uses", "employs",
    # 时序
    "precedes", "follows",
}

CONFIDENCE_LEVELS = {"direct", "indirect", "conflicting"}

NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*(?:\s*(?:%|×|x|K|M|B|ms|s|h|GB|TB|MB|FLOPs?|BLEU|F1|PPL|ppl))?")
STOP = {"the", "a", "an", "of", "and", "or", "to", "in", "on", "for", "with", "by", "is",
        "are", "was", "were", "be", "been", "that", "this", "these", "those", "we", "our",
        "it", "its", "as", "at", "from", "than", "which", "such", "can", "may", "not",
        "本文", "我们", "该", "其中", "以及", "通过", "之间", "对于", "一种", "一个"}


def normalize(text):
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def numbers(text):
    return [m.lower() for m in NUMBER_RE.findall(text or "")]


def check_nanopub(np):
    flags = []
    a = np.get("assertion") or {}
    text = (a.get("text") or "").strip()
    if not text:
        return ["missing assertion.text"]

    # 拆得细：单条可判断真假的断言，整段塞进一个字段即失败
    if len(text) > 240:
        flags.append(f"assertion too long ({len(text)} chars): likely not atomic")
    if text.count("；") >= 2 or text.count(";") >= 2:
        flags.append("compound assertion (>=2 semicolon clauses)")
    if re.search(r"\band\b", text, re.I) and len(text) > 140:
        flags.append("possible compound assertion (long + 'and')")

    if not a.get("subject"):
        flags.append("missing assertion.subject")
    pred = a.get("predicate")
    if not pred:
        flags.append("missing assertion.predicate")
    elif pred not in CONTROLLED_PREDICATES:
        flags.append(f"predicate not in controlled vocab: {pred}")
    if not a.get("object"):
        flags.append("missing assertion.object")

    # 对得上：证据片段 + 位置
    ev = np.get("evidence") or {}
    quote = (ev.get("quote") or "").strip()
    if not quote:
        flags.append("missing evidence.quote")
    loc = ev.get("location") or {}
    if not loc.get("page"):
        flags.append("missing evidence.location.page")

    # 证据相关性：断言中的关键数字必须出现在证据片段中
    nums = numbers(text)
    qn = normalize(quote)
    miss = [n for n in nums if n not in qn]
    if nums and len(miss) >= len(nums):
        flags.append("evidence quote lacks assertion numbers: " + ", ".join(miss[:6]))

    # 追得回：来源元数据 + 标识符
    prov = np.get("provenance") or {}
    if not prov.get("paper_title"):
        flags.append("missing provenance.paper_title")
    if not prov.get("authors"):
        flags.append("missing provenance.authors")
    if not prov.get("year"):
        flags.append("missing provenance.year")
    if not np.get("id"):
        flags.append("missing id")

    # 置信度依据
    conf = np.get("confidence") or {}
    if conf.get("level") not in CONFIDENCE_LEVELS:
        flags.append("missing/invalid confidence.level (direct|indirect|conflicting)")
    if not conf.get("basis"):
        flags.append("missing confidence.basis")
    return flags


def run_check(data):
    nps = data.get("nanopublications") or data.get("assertions") or []
    issues = []
    per = []
    for i, np in enumerate(nps):
        flags = check_nanopub(np)
        per.append({"index": i, "flags": flags})
        for f in flags:
            issues.append(f"np[{i}]: {f}")

    if not nps:
        issues.append("no nanopublications found (keys: nanopublications/assertions)")

    # 读得懂：paper 元数据
    paper = data.get("paper") or {}
    if not paper.get("title"):
        issues.append("paper.title missing")
    if not paper.get("authors"):
        issues.append("paper.authors missing")

    verdicts = ["ok: all nanopublications pass structural + evidence + provenance checks"] \
        if not issues else issues
    return {
        "total_nanopublications": len(nps),
        "issues": len(issues),
        "verdicts": verdicts,
        "per_nanopublication": per,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("result")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    data = json.load(open(args.result, encoding="utf-8"))
    report = run_check(data)
    if args.out:
        json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
