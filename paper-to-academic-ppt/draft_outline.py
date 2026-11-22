#!/usr/bin/env python3
"""draft_outline.py — turn a parsed-paper structure into a deck spec skeleton.

This is the deterministic "narrative extraction" step. It reads the enriched
structure JSON from parse_pdf.py (sections + figures + tables with numbers,
types, image regions and citation cross-references) and emits a deck spec with:

  * a coherent main line (problem -> method -> results -> conclusion), not a
    paragraph dump;
  * one claim per slide, with figures/tables attached to the slide that
    discusses them (via cited_in or page range);
  * schematic vs data labels and "本文 vs 基线" markers so a schematic is never
    presented as experimental data and others' results are never passed off as
    the paper's own.

Usage:
    python3 draft_outline.py structure.json --out deck_spec.json \
        --paper paper.pdf [--max-slides N] [--audience ...] [--duration-min M]
"""

import argparse
import json
import re

ROLE_SCORE = {
    "abstract": ("skip", 1),
    "introduction": ("background", 2),
    "background": ("background", 2),
    "related": ("background", 3),
    "why": ("background", 3),
    "motivation": ("background", 3),
    "method": ("method", 4),
    "model": ("method", 4),
    "approach": ("method", 4),
    "architecture": ("method", 4),
    "algorithm": ("method", 4),
    "training": ("method", 4),
    "result": ("results", 5),
    "experiment": ("results", 5),
    "evaluation": ("results", 5),
    "analysis": ("results", 5),
    "translation": ("results", 5),
    "parsing": ("results", 5),
    "variation": ("results", 5),
    "ablation": ("results", 5),
    "discussion": ("discussion", 6),
    "conclusion": ("conclusion", 7),
    "limitation": ("limitations", 8),
    "future work": ("limitations", 8),
    "acknowledg": ("skip", 9),
    "reference": ("skip", 9),
    "appendix": ("skip", 9),
    "supplement": ("skip", 9),
    "visualization": ("results", 5),
}

TYPE_ZH = {"schematic": "示意图", "data": "数据/结果", "table": "数据表", "figure": "图"}

TABLE_HEADER_HINT = re.compile(
    r"\b(F1|PPL|BLEU|params?|steps?|WSJ|cost|FLOPs?|TFLOPS|accuracy|metric|perplexity"
    r"|size|weight|epochs?|component|raw|count|fraction|bytes?|documents?)\b", re.I)


REAL_SECTION_WORDS = {
    "introduction", "background", "abstract", "conclusion", "summary", "discussion",
    "methods", "method", "results", "result", "acknowledgements", "acknowledgments",
    "references", "appendix", "overview", "motivation", "limitations", "related",
    "evaluation", "experiments", "analysis", "training", "implementation", "future",
    "conclusions", "materials", "datasets", "data", "models", "model", "performance",
    "methodology", "approach", "contributions", "objective", "objectives", "findings",
    "outcome", "preliminaries", "notation", "setup", "formulation", "benchmarks",
    "settings", "works", "work", "study", "problem", "results", "ethics", "privacy",
}


def looks_like_table_header(heading):
    """Detect bold table-header rows misdetected as headings (e.g. 'Parser
    Training WSJ 23 F1' or 'Component Raw Size Weight Epochs Effective')."""
    words = heading.split()
    if TABLE_HEADER_HINT.search(heading) and len(words) <= 7:
        return True
    if 4 <= len(words) <= 7:
        return all(w[:1].isupper() or w.isdigit() for w in words)
    return False


def is_table_like_section(sec):
    """A section whose paragraphs are actually table cells (many short lines or
    very numeric-dense text)."""
    paras = sec.get("paragraphs", [])
    if len(paras) >= 3:
        short = sum(1 for p in paras if len(p.get("text", "").strip()) < 20)
        if short >= len(paras) * 0.4:
            return True
    text = " ".join(p.get("text", "") for p in paras)
    if len(text) < 60:
        return False
    digits = sum(c.isdigit() for c in text)
    return digits / len(text) > 0.12


def should_skip_section(sec):
    heading = sec.get("heading", "")
    if sec.get("number") is None:
        if heading.rstrip().endswith(":"):
            return True
        if looks_like_table_header(heading):
            return True
        if is_table_like_section(sec):
            return True
        words = heading.split()
        if len(words) == 1 and words[0].lower() not in REAL_SECTION_WORDS:
            return True
    return False


def classify(heading):
    low = heading.lower()
    for key, val in ROLE_SCORE.items():
        if key in low:
            return val
    return ("background", 5)


def assign_roles(sections):
    """Hierarchy-aware role assignment: subsections inherit their top-level
    section's role (e.g. '6.2 Model Variations' inherits '6 Results' = results),
    which keyword matching alone cannot infer."""
    top_role = {}
    for sec in sections:
        num = str(sec.get("number") or "")
        if num and "." not in num:
            top_role[num] = classify(sec.get("heading", ""))[0]
    for sec in sections:
        num = str(sec.get("number") or "")
        if num and "." in num:
            parent = num.split(".")[0]
            sec["_role"] = top_role.get(parent, classify(sec.get("heading", ""))[0])
        else:
            sec["_role"] = top_role.get(num, classify(sec.get("heading", ""))[0])
    return sections


def clean_heading(s):
    return re.sub(r"^\d{1,3}(?:\.\d{1,3}){0,3}[.)]?\s+", "", s).strip()


def truncate(text, n=260):
    text = (text or "").strip()
    if len(text) <= n:
        return text
    return text[: n - 1].rsplit(" ", 1)[0] + " …"


def is_fragment(text):
    """Reject short or math-only fragments produced when inline equations are
    split out of a sentence (e.g. '2 . 0', '( y , ..., y )', 'in Table')."""
    t = (text or "").strip()
    # token-label markup from figure visualizations ("<EOS>", "<pad>") is not
    # prose; reject it before it can become a slide bullet
    if "<" in t or ">" in t:
        return True
    if len(t) < 28:
        return True
    alpha = sum(c.isalnum() for c in t)
    return alpha / max(len(t), 1) < 0.40


def remerge(text, page, plaintext_pages, headings=None):
    """Recover the clean sentence (inline numbers intact) that this fragmented
    XML paragraph belongs to, by matching its own distinctive leading words in
    the SAME page's plaintext. Unlike the heading-boundary approach, this stays
    within the paragraph's own content, so it cannot mis-attribute text across
    sections. Returns the original text when no confident match is found."""
    pg = (plaintext_pages or {}).get(str(page), "")
    if not pg or not text:
        return text
    key = re.sub(r"\s+", " ", text).strip()
    words = key.split()
    prefix = " ".join(words[:8])
    if len(prefix) < 15:
        return text
    pg_norm = re.sub(r"\s+", " ", pg)
    for sent in re.split(r"(?<=[.!?])\s+", pg_norm):
        s = sent.strip()
        if prefix[:20] in s or prefix in s:
            # reject line-break hyphenation ("fol- lowing") and over-long
            # column-mixed matches; keep the original fragment instead
            if re.search(r"[A-Za-z]-\s+[A-Za-z]", s) or len(s) > 400:
                return text
            # strip merged section headings (may be several, e.g.
            # "6 Results 6.1 Machine Translation") from the sentence start
            for _ in range(6):
                stripped = False
                for h in (headings or []):
                    hn = re.sub(r"\s+", " ", (h or "")).strip()
                    if hn and s.startswith(hn) and len(s) > len(hn) + 8:
                        s = s[len(hn):].strip()
                        stripped = True
                        break
                if not stripped:
                    break
            if len(s) >= 25:
                return s
    return text


CAPTION_START = re.compile(r"^\s*(figure|table)\s*\d+\s*[:.]", re.I)


def _clean_sentence(s):
    if CAPTION_START.match(s):
        return False
    # token-label markup from figure visualizations (e.g. "<EOS>", "<pad>") is
    # not prose; drop it instead of turning it into a slide bullet
    if "<" in s or ">" in s:
        return False
    if len(s) < 20 or len(s) > 400:
        return False
    alpha = sum(c.isalpha() for c in s)
    return alpha / max(len(s), 1) >= 0.45


def _split_sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.replace("\n", " "))
            if s.strip()]


def section_chunks(sections, plaintext_pages):
    """Map each section to its clean plaintext chunk, using heading-line
    boundaries. This keeps inline numbers intact (unlike the XML parse) while
    attributing text to the correct section (unlike a page-wide dump)."""
    plaintext_pages = plaintext_pages or {}
    marks = []
    for sec in sections:
        p = sec.get("page") or 0
        h = re.sub(r"\s+", " ", (sec.get("heading") or "")).strip().lower()
        lines = plaintext_pages.get(str(p), "").splitlines()
        if not h or not lines:
            continue
        idx = None
        for i, line in enumerate(lines):
            if h in re.sub(r"\s+", " ", line).lower():
                idx = i
                break
        if idx is not None:
            marks.append((p, idx, sec))
    marks.sort(key=lambda m: (m[0], m[1]))
    chunks = {}
    for j, (p, idx, sec) in enumerate(marks):
        lines = plaintext_pages.get(str(p), "").splitlines()
        end = len(lines)
        for p2, idx2, _ in marks[j + 1:]:
            if p2 == p and idx2 > idx:
                end = idx2
                break
        chunk = re.sub(r"\s+", " ", " ".join(lines[idx + 1:end])).strip()
        chunks[id(sec)] = chunk
    return chunks


def clean_sentences_for_group(secs, plaintext_pages, chunks=None):
    """Clean claim sentences for a grouped section, taken from per-section
    plaintext chunks (inline numbers intact)."""
    if chunks is None:
        chunks = section_chunks(secs, plaintext_pages)
    seen, out = set(), []
    for sec in secs:
        for sent in _split_sentences(chunks.get(id(sec), "")):
            if _clean_sentence(sent) and sent not in seen:
                seen.add(sent)
                out.append(sent)
    return out


def sentences(text, n=2):
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return [truncate(p, 220) for p in parts[:n] if p]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("structure")
    ap.add_argument("--out", required=True)
    ap.add_argument("--paper", default=None, help="source PDF (for figure cropping at build time)")
    ap.add_argument("--max-slides", type=int, default=14)
    ap.add_argument("--audience", default="lab meeting")
    ap.add_argument("--duration-min", type=int, default=15)
    args = ap.parse_args()

    s = json.load(open(args.structure, encoding="utf-8"))
    doc = s.get("document", {})
    slides = []

    # ---- 1. title slide: paper title + one-sentence contribution ----
    abstract = doc.get("abstract") or ""
    contrib = sentences(abstract, 1) or ["（摘要未解析）"]
    slides.append({
        "layout": "title",
        "title": doc.get("title", "Untitled"),
        "subtitle": f"{args.audience} · {args.duration_min} min · 主线：{contrib[0]}",
        "bullets": [[c, 0] for c in contrib],
        "notes": ("开场：用一句话说出这篇论文回答的问题与结论，不要读标题；"
                  "随后预告主线：问题 → 方法 → 证据 → 结论。"),
        "evidence": [{"type": "abstract", "ref": "Abstract", "page": 1,
                      "quote": truncate(abstract, 200)}],
        "sections": [],
    })

    # ---- 2. problem slide ----
    if abstract:
        slides.append({
            "layout": "content",
            "title": "问题与动机",
            "bullets": [["研究问题：" + truncate(abstract, 260), 0]],
            "notes": "讲清 gap：已有方法差在哪，本文为什么现在做；若摘要不足以支撑，请回读引言补足。",
            "evidence": [{"type": "section", "ref": "Abstract", "page": 1,
                          "quote": truncate(abstract, 160)}],
            "sections": [],
        })

    # ---- 3. section slides (background/method/results/discussion/conclusion) ----
    sections = assign_roles(s.get("sections", []))
    all_headings = sorted({sec.get("heading") or "" for sec in sections},
                          key=len, reverse=True)
    bucket = {"background": [], "method": [], "results": [],
              "discussion": [], "conclusion": [], "limitations": []}
    for sec in sections:
        heading = sec.get("heading", "")
        role = sec.get("_role", "background")
        if role == "skip":
            continue
        # drop author/affiliation blocks on page 1 (before Abstract/Introduction)
        if sec.get("number") is None and sec.get("page") == 1 and heading.lower() != "abstract":
            continue
        if should_skip_section(sec):
            continue
        text = " ".join(p.get("text", "") for p in sec.get("paragraphs", [])).strip()
        if not text:
            continue
        if sec.get("number") is None and len(text) < 400:
            continue
        bucket[role].append((sec, text))

    def add_section_slides(role, label):
        # group subsections under their top-level section (one slide per main
        # section, so the deck follows the paper's main line instead of listing
        # every 3.1/3.2/3.2.1 subsection as a separate page)
        groups, order = {}, []
        for sec, text in bucket[role]:
            num = str(sec.get("number") or "")
            key = num.split(".")[0] if "." in num else (num or sec.get("heading"))
            if key not in groups:
                groups[key] = {"top": sec, "secs": [], "paras": []}
                order.append(key)
            groups[key]["secs"].append(sec)
            groups[key]["paras"].extend(sec.get("paragraphs", []))
        for key in order:
            if len(slides) >= args.max_slides - 1:   # reserve the final takeaway slide
                break
            g = groups[key]
            top = g["top"]
            heading = clean_heading(top.get("heading", "")) or label
            # v2 paragraph-based bullets (correct section attribution); do NOT
            # use the plaintext heading-boundary chunks — they mis-attribute text
            # across columns/sections on real papers (caused the 65-pt regression).
            seen, bullets = set(), []
            plain = s.get("plaintext_pages")
            for para in g["paras"][:8]:
                clean = remerge(para.get("text", ""), para.get("page"), plain,
                                all_headings)
                t = truncate(clean, 180)
                if t and not is_fragment(t) and t not in seen:
                    seen.add(t)
                    bullets.append([t, 1])
                if len(bullets) >= 4:
                    break
            notes = (f"本页对应论文「{top.get('heading')}」（第 {top.get('page')} 页起）。"
                     "讲每一点时指向右侧图/表，不逐字复述；本页只承载一个核心主张。")
            slides.append({"layout": "content", "title": heading, "bullets": bullets,
                           "figures": [], "notes": notes,
                           "evidence": [{"type": "section", "ref": top.get("heading", heading),
                                         "page": top.get("page"),
                                         "quote": truncate(" ".join(p.get("text", "") for p in g["paras"]), 120)}],
                           "sections": [{"heading": s2.get("heading"), "page": s2.get("page")}
                                        for s2 in g["secs"]]})

    add_section_slides("background", "背景")
    add_section_slides("method", "方法")
    add_section_slides("results", "结果")
    add_section_slides("discussion", "讨论")
    add_section_slides("limitations", "局限")
    add_section_slides("conclusion", "结论")

    # ---- 4. attach figures/tables to the slide that discusses them ----
    evidence_items = []
    for kind, items in (("figure", s.get("figures", [])), ("table", s.get("tables", []))):
        for it in items:
            if it.get("number") is None and kind == "figure":
                continue
            cap = it.get("caption") or f"{kind.title()} (page {it.get('page')})"
            entry = {
                "kind": kind, "number": it.get("number"), "page": it.get("page"),
                "caption": truncate(cap, 240), "type": it.get("type", kind),
                "region": it.get("region"), "result_role": it.get("result_role"),
                "cited_in": it.get("cited_in", []),
            }
            if kind == "table":
                entry["rows"] = it.get("rows")
                entry["markdown"] = (it.get("markdown") or "")[:800]
            evidence_items.append(entry)

    def slide_for(entry):
        cited = entry.get("cited_in") or []
        for idx, sl in enumerate(slides):
            if idx < 2:
                continue
            for sec in sl.get("sections", []):
                h = sec.get("heading", "")
                if any(h and (h in c or c in h) for c in cited):
                    return idx
        # fallback: figure page close to a section slide's page range
        p = entry.get("page")
        best, best_gap = None, 10**6
        for idx, sl in enumerate(slides):
            for sec in sl.get("sections", []):
                gap = abs((sec.get("page") or 0) - p)
                if gap < best_gap:
                    best_gap, best = gap, idx
        # only accept the fallback if it is actually close; otherwise return None
        # so the caller builds a dedicated evidence slide (e.g. appendix figures)
        return best if (best is not None and best_gap <= 2) else None

    def evidence_title(entry):
        kind_zh = "图" if entry.get("kind") == "figure" else "表"
        num = entry.get("number")
        if num is not None:
            return f"{kind_zh} {num}（第 {entry.get('page')} 页）"
        return f"{TYPE_ZH.get(entry['type'], '图表')}证据（第 {entry.get('page')} 页）"

    for entry in evidence_items:
        idx = slide_for(entry)
        if idx is None:
            slides.append({"layout": "content",
                           "title": evidence_title(entry),
                           "bullets": [[entry["caption"], 0]] if entry.get("caption") else [],
                           "figures": [], "notes": "本页展示论文图表；先说明横纵轴/条件，再讲结论。",
                           "evidence": [], "sections": []})
            idx = len(slides) - 1
        # cap figures/tables per slide to avoid overload
        n_figs = len(slides[idx].setdefault("figures", []))
        if n_figs >= 2:
            slides.append({"layout": "content", "title": evidence_title(entry),
                           "bullets": [], "figures": [], "notes": "", "evidence": [],
                           "sections": []})
            idx = len(slides) - 1
        slides[idx].setdefault("figures", []).append(entry)
        ref = f"{entry['kind'].title()} {entry['number']}" if entry.get("number") else entry["kind"].title()
        slides[idx].setdefault("evidence", []).append({
            "type": entry["kind"], "ref": ref, "page": entry.get("page"),
            "quote": entry["caption"], "role": entry.get("result_role") or entry.get("type"),
        })
        # 本文 vs 基线 note for comparison tables
        if entry.get("result_role") == "comparison_own_vs_baseline":
            slides[idx]["bullets"].append(
                ["⚠️ 对比表：区分「本文结果」与「基线/他人结果」，勿将他人结果当本文", 1])

    # ---- 5. final takeaway (only when the paper has no explicit conclusion) ----
    if not bucket.get("conclusion"):
        slides.append({
            "layout": "conclusion",
            "title": "结论与局限",
            "bullets": [["核心贡献：见方法/结果页", 0],
                        ["已知局限：材料未报告的部分请在此标注，不夸大", 0]],
            "notes": "收尾：复述核心贡献，主动说明局限与下一步，回答提问。",
            "evidence": [],
            "sections": [],
        })

    out = {
        "schema": "paper2arm/deck-spec/v1",
        "meta": {"paper_pdf": args.paper, "audience": args.audience,
                 "duration_min": args.duration_min, "max_slides": args.max_slides},
        "slides": slides[: args.max_slides],
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    n_fig = sum(1 for sl in out["slides"] for f in sl.get("figures", []) if f["kind"] == "figure")
    n_tab = sum(1 for sl in out["slides"] for f in sl.get("figures", []) if f["kind"] == "table")
    print(f"wrote {len(out['slides'])} slides (figures embedded: {n_fig}, tables: {n_tab}) to {args.out}")


if __name__ == "__main__":
    main()
