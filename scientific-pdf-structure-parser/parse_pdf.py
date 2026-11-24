#!/usr/bin/env python3
"""parse_pdf.py — 文献 PDF 结构化解析（多栏阅读顺序 + 章节结构 + 证据定位）。

Deterministic, stdlib-only. Uses `pdftotext -bbox-layout` (poppler) to obtain
word-level coordinates, then reconstructs, per page:
  * running headers / footers / page numbers (repeated lines -> separated);
  * footnotes (bottom-band, non-repeated lines -> separated);
  * multi-column reading order (pdftotext "flow" = column; left->right, top->down);
  * paragraph blocks (pdftotext "block");
  * section headings (numbered / roman / keyword);
  * figure / table / equation captions;
  * references (after a References/Bibliography heading);
  * title (largest text on page 1) and author/affiliation block (page-1 front matter);
  * pages with no text layer -> `unreadable` (scanned).

Every text unit carries a `page` and, where available, a `bbox` so the result
can be traced back to the original paper (核得回).

Usage:
    python3 parse_pdf.py input.pdf --out structure.json
"""

import argparse
import json
import os
import re
import subprocess
import tempfile
from collections import Counter, defaultdict

XHTML = "{http://www.w3.org/1999/xhtml}"

# --------------------------------------------------------------------------
# 1. low-level extraction
# --------------------------------------------------------------------------

def _words_to_text(words):
    return " ".join(w["text"] for w in words)


def _block_medh(b):
    """Median word height of a block = a font-size proxy (bold/larger => taller)."""
    hs = sorted(w["y1"] - w["y0"] for l in b["lines"] for w in l["words"])
    return hs[len(hs) // 2] if hs else 0.0


def run_bbox_layout(pdf_path):
    """Run `pdftotext -bbox-layout` and return the parsed XHTML root."""
    fd, html_path = tempfile.mkstemp(suffix=".html")
    os.close(fd)
    try:
        subprocess.run(
            ["pdftotext", "-bbox-layout", pdf_path, html_path],
            capture_output=True, text=True, check=False)
        import xml.etree.ElementTree as ET
        # pdftotext's XHTML is not strict XML: it may contain raw control
        # characters (0x01 etc.) that XML 1.0 forbids. Strip them first.
        raw = open(html_path, encoding="utf-8", errors="replace").read()
        raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", raw)
        root = ET.fromstring(raw)
        return root
    finally:
        try:
            os.unlink(html_path)
        except OSError:
            pass


def extract_pages(root):
    """Return a list of page dicts: width/height + ordered flows->blocks->lines->words."""
    pages = []
    for page_el in root.iter(XHTML + "page"):
        page = {
            "width": float(page_el.get("width", 0)),
            "height": float(page_el.get("height", 0)),
            "flows": [],
        }
        for flow_el in page_el.findall(XHTML + "flow"):
            flow = {"blocks": []}
            for block_el in flow_el.findall(XHTML + "block"):
                block = {
                    "x0": float(block_el.get("xMin", 0)),
                    "y0": float(block_el.get("yMin", 0)),
                    "x1": float(block_el.get("xMax", 0)),
                    "y1": float(block_el.get("yMax", 0)),
                    "lines": [],
                }
                for line_el in block_el.findall(XHTML + "line"):
                    line = {
                        "x0": float(line_el.get("xMin", 0)),
                        "y0": float(line_el.get("yMin", 0)),
                        "x1": float(line_el.get("xMax", 0)),
                        "y1": float(line_el.get("yMax", 0)),
                        "words": [],
                    }
                    for word_el in line_el.findall(XHTML + "word"):
                        line["words"].append({
                            "text": word_el.text or "",
                            "x0": float(word_el.get("xMin", 0)),
                            "y0": float(word_el.get("yMin", 0)),
                            "x1": float(word_el.get("xMax", 0)),
                            "y1": float(word_el.get("yMax", 0)),
                        })
                    line["text"] = _words_to_text(line["words"])
                    block["lines"].append(line)
                block["text"] = " ".join(l["text"] for l in block["lines"])
                flow["blocks"].append(block)
            page["flows"].append(flow)
        pages.append(page)
    return pages


def flatten_blocks(pages):
    """Flatten all blocks into a plain list (no ordering yet)."""
    flat = []
    for pi, page in enumerate(pages):
        page_no = pi + 1
        for fi, flow in enumerate(page["flows"]):
            for b in flow["blocks"]:
                if not b["text"].strip():
                    continue
                flat.append({
                    "page": page_no,
                    "page_width": page["width"],
                    "page_height": page["height"],
                    "flow": fi,
                    "x0": b["x0"], "y0": b["y0"], "x1": b["x1"], "y1": b["y1"],
                    "text": b["text"],
                    "lines": b["lines"],
                    "width": b["x1"] - b["x0"],
                    "cx": (b["x0"] + b["x1"]) / 2.0,
                })
    return flat


def order_body(body):
    """Order body blocks into reading order.

    Per page: full-width blocks (title/authors/abstract) read first, then each
    text column top-to-bottom, columns left-to-right. Column count is detected
    from the LEFT EDGES (x0) of NON-full-width blocks — a second column is a
    distinct left margin, not a narrow heading's short width. Runs AFTER chrome
    removal so page numbers/headers cannot fake a column gap.
    """
    by_page = defaultdict(list)
    for b in body:
        by_page[b["page"]].append(b)
    ordered = []
    for page_no in sorted(by_page):
        blocks = by_page[page_no]
        W = blocks[0]["page_width"] or 1

        def is_span(b):
            return b["width"] > 0.6 * W

        narrow = [b for b in blocks if not is_span(b)]
        two_col = False
        split = W / 2.0
        if len(narrow) >= 3:
            x0s = sorted(b["x0"] for b in narrow)
            gap, gsplit = 0.0, W / 2.0
            for i in range(1, len(x0s)):
                g = x0s[i] - x0s[i - 1]
                if g > gap:
                    gap, gsplit = g, (x0s[i] + x0s[i - 1]) / 2.0
            two_col = gap > 0.15 * W

        def col_of(b):
            if is_span(b):
                return 0
            if two_col:
                return 1 if b["x0"] < split else 2
            return 0

        blocks.sort(key=lambda b: (col_of(b), b["y0"], b["x0"]))
        ordered.extend(blocks)
    return ordered


# --------------------------------------------------------------------------
# 2. headers / footers / footnotes / page numbers
# --------------------------------------------------------------------------

def _norm(txt):
    return re.sub(r"\s+", " ", txt).strip().lower()


def _band_of(block, height):
    y = block["y0"]
    if y < 0.12 * height:
        return "top"
    if y > 0.88 * height:
        return "bottom"
    return "body"


PAGE_NUM_RE = re.compile(r"^\d{1,4}$")


def detect_chrome(blocks):
    """Separate running headers/footers, page numbers and single-page footnotes."""
    # count normalized line texts per band across pages
    top_counts = Counter()
    bottom_counts = Counter()
    top_blocks, bottom_blocks = [], []
    for b in blocks:
        band = _band_of(b, b["page_height"])
        if band == "top":
            top_counts[_norm(b["text"])] += 1
            top_blocks.append(b)
        elif band == "bottom":
            bottom_counts[_norm(b["text"])] += 1
            bottom_blocks.append(b)

    headers, footers, page_numbers, footnotes = set(), set(), set(), set()
    idx = {id(b): b for b in blocks}

    # repeated (>=2 pages) in a band => running header/footer
    for b in top_blocks:
        t = _norm(b["text"])
        if t and top_counts[t] >= 2:
            headers.add(id(b))
    for b in bottom_blocks:
        t = _norm(b["text"])
        if t and bottom_counts[t] >= 2:
            footers.add(id(b))
        elif t and PAGE_NUM_RE.match(t):
            page_numbers.add(id(b))
        elif t and len(t) <= 60:
            # bottom, not repeated, not a page number => likely footnote
            footnotes.add(id(b))

    def classify(b):
        i = id(b)
        if i in headers:
            return "header"
        if i in page_numbers:
            return "page_number"
        if i in footers:
            return "footer"
        if i in footnotes:
            return "footnote"
        return "body"

    chrome = {
        "headers": [], "footers": [], "page_numbers": [], "footnotes": [],
    }
    body = []
    for b in blocks:
        c = classify(b)
        if c == "header":
            chrome["headers"].append({"text": b["text"], "page": b["page"]})
        elif c == "footer":
            chrome["footers"].append({"text": b["text"], "page": b["page"]})
        elif c == "page_number":
            chrome["page_numbers"].append({"text": b["text"], "page": b["page"]})
        elif c == "footnote":
            chrome["footnotes"].append({
                "text": b["text"], "page": b["page"],
                "bbox": [b["x0"], b["y0"], b["x1"], b["y1"]]})
        else:
            body.append(b)
    return body, chrome


# --------------------------------------------------------------------------
# 3. headings and sections
# --------------------------------------------------------------------------

NUM_HEADING_RE = re.compile(r"^(\d+(?:\.\d+){0,2})\s+(\S.{0,80})$")
ROMAN_RE = re.compile(r"^(I{1,3}|IV|V|VI{0,3}|IX|X|XI{0,3}|XIV|XV)\s*\.?\s+(\S.{0,80})$")
UNITS = {
    "gib", "mib", "kib", "gb", "mb", "kb", "tb", "pb", "ghz", "mhz", "khz",
    "hz", "ms", "s", "ns", "nm", "um", "mm", "cm", "km", "kg", "g", "mg",
    "w", "mw", "kw", "%", "x", "mi", "ft", "db", "fps", "bps", "rpm",
}
HEADING_KEYWORDS = {
    "abstract", "introduction", "related work", "background", "method",
    "methods", "materials and methods", "methodology", "experiment",
    "experiments", "experimental setup", "results", "results and discussion",
    "discussion", "conclusion", "conclusions", "conclusion and future work",
    "references", "bibliography", "appendix", "acknowledgments",
    "acknowledgements", "limitations", "future work", "evaluation",
    "setup", "implementation", "data", "dataset", "datasets",
}


def heading_info(text):
    """Return (level, heading_text) if `text` looks like a heading, else None."""
    t = text.strip()
    if not t:
        return None
    m = NUM_HEADING_RE.match(t)
    if m:
        num, title = m.group(1), m.group(2)
        top = int(num.split(".")[0])
        if top > 20:
            return None
        tlow = _norm(title)
        # reject numeric data / units / non-title fragments ("825.18 GiB",
        # "5.91 KiB", "0.0 0.2 positional …")
        if tlow in UNITS or re.match(r"^[\d\W]+$", title):
            return None
        if re.match(r"^\d+(?:[.,]\d+)?\s", title):
            return None
        if re.match(r"https?://", title, re.I) or title.startswith("www."):
            return None
        level = min(len(num.split(".")), 3)
        return level, t
    m = ROMAN_RE.match(t)
    if m:
        return 1, t
    low = _norm(t)
    if low in HEADING_KEYWORDS and len(t.split()) <= 8:
        return 1, t
    return None


BARE_NUM_RE = re.compile(r"^\d{1,3}(?:\.\d{1,2}){0,2}$")


def merge_split_headings(body, body_h):
    """Merge a bare section number ("2") with the heading on the same line that
    pdftotext split into a separate block ("2" + "Background" -> "2 Background")."""
    merged = []
    i = 0
    while i < len(body):
        b = body[i]
        t = b["text"].strip()
        nxt = body[i + 1] if i + 1 < len(body) else None
        if (BARE_NUM_RE.fullmatch(t) and nxt is not None
                and abs(nxt["y0"] - b["y0"]) < 10
                and nxt["text"].strip()
                and nxt["text"].strip()[0].isupper()
                and _block_medh(nxt) > body_h * 1.1):
            combined = dict(nxt)
            combined["text"] = t + " " + nxt["text"].strip()
            merged.append(combined)
            i += 2
            continue
        merged.append(b)
        i += 1
    return merged


def build_sections(body, pages, body_h=None, title=""):
    """Group body blocks into sections by headings; keep page+bbox per paragraph."""
    if body_h is None:
        hs = sorted(_block_medh(b) for b in body if b["text"].strip())
        body_h = hs[len(hs) // 2] if hs else 9.0
    sections = []
    current = {"heading": "Front matter", "level": 0, "page": 1,
               "paragraphs": [], "id": "sec-front"}
    pre_abstract = []
    abstract_done = False
    back_matter = False  # after References: no more heading detection

    for b in body:
        bt = b["text"].strip()
        if bt == title:
            continue
        h = heading_info(bt)
        if h is None and not back_matter and _looks_like_unheaded_heading(b, body_h):
            h = (1, bt)
        if h is not None and _is_standalone_heading(b):
            if _norm(bt) in ("references", "bibliography"):
                back_matter = True
            level, htext = h
            if current["paragraphs"] or current["heading"] != "Front matter":
                sections.append(current)
            current = {
                "heading": htext, "level": level, "page": b["page"],
                "paragraphs": [], "id": "sec-%d" % (len(sections) + 1),
            }
            if _norm(htext) == "abstract":
                abstract_done = True
            continue

        para = {
            "id": "p%d" % len(current["paragraphs"]),
            "text": b["text"],
            "page": b["page"],
            "bbox": [round(b["x0"], 1), round(b["y0"], 1),
                     round(b["x1"], 1), round(b["y1"], 1)],
        }
        current["paragraphs"].append(para)

    if current["paragraphs"] or current["heading"] != "Front matter":
        sections.append(current)
    return sections


def _is_standalone_heading(b):
    """A heading is a short block: <= 12 words and no trailing sentence period
    (except abbreviations)."""
    t = b["text"].strip()
    if len(t.split()) > 12:
        return False
    # reject lines that end with a sentence-ending period and are long sentences
    if t.endswith(".") and len(t.split()) > 4:
        return False
    return True


def _looks_like_unheaded_heading(b, body_h):
    """Detect unnumbered section headings (e.g. "Model Architecture", "Training")
    by font-size proxy + shape: taller than body text, short, title-case,
    no ending period, not a caption."""
    t = b["text"].strip()
    nw = len(t.split())
    if not (1 <= nw <= 8):
        return False
    if t.endswith((".", ",", ":", ";")) and nw > 2:
        return False
    if FIG_TAB_RE.match(t) or EQ_RE.match(t):
        return False
    if _block_medh(b) < body_h * 1.2:
        return False
    # title-case: first char upper, and not all-lowercase body-like
    if not t[0].isupper():
        return False
    # reject obvious table/author/caption fragments
    if "@" in t or "·" in t or "∗" in t:
        return False
    if re.match(r"https?://", t, re.I) or t.startswith("www."):
        return False
    digits = sum(c.isdigit() for c in t)
    if digits >= 3 and digits / max(len(t), 1) > 0.25:
        return False
    return True


# --------------------------------------------------------------------------
# 4. captions / equations / references
# --------------------------------------------------------------------------

FIG_TAB_RE = re.compile(
    r"^(Fig(?:ure)?\.?|Tab(?:le)?\.?)\s*(\d+)[:.\s]*(.*)$", re.IGNORECASE)
EQ_RE = re.compile(r"^(?:Equation|Eq\.?)\s*\(?(\d+)\)?[:.\s]*(.*)$", re.IGNORECASE)


def extract_captions(body):
    figures, tables, equations = [], [], []
    for b in body:
        t = b["text"].strip()
        m = FIG_TAB_RE.match(t)
        if m:
            kind, num, rest = m.group(1).lower(), m.group(2), m.group(3)
            rec = {"id": "%s %s" % ("Figure" if kind.startswith("fig") else "Table", num),
                   "caption": (rest or t), "page": b["page"],
                   "bbox": [round(b["x0"], 1), round(b["y0"], 1),
                            round(b["x1"], 1), round(b["y1"], 1)]}
            (figures if kind.startswith("fig") else tables).append(rec)
            continue
        m = EQ_RE.match(t)
        if m:
            equations.append({
                "id": "Eq. (%s)" % m.group(1), "content": (m.group(2) or t),
                "page": b["page"],
                "bbox": [round(b["x0"], 1), round(b["y0"], 1),
                         round(b["x1"], 1), round(b["y1"], 1)]})
    return figures, tables, equations


def extract_references(body):
    """Return reference entries: blocks after a References/Bibliography heading."""
    refs = []
    in_refs = False
    for b in body:
        low = _norm(b["text"])
        if low in ("references", "bibliography"):
            in_refs = True
            continue
        if in_refs:
            # a new numbered section ends the reference list
            if heading_info(b["text"]) is not None:
                break
            if b["text"].strip():
                refs.append({
                    "id": "r%d" % (len(refs) + 1),
                    "text": b["text"].strip(),
                    "page": b["page"],
                    "bbox": [round(b["x0"], 1), round(b["y0"], 1),
                             round(b["x1"], 1), round(b["y1"], 1)]})
    return refs


# --------------------------------------------------------------------------
# 5. title / authors / abstract
# --------------------------------------------------------------------------

def detect_title_and_authors(pages):
    """Title = largest text on page 1; authors = remaining page-1 blocks before
    the abstract heading."""
    if not pages:
        return "", [], ""
    p1 = pages[0]
    title = ""
    title_score = -1.0
    author_blocks = []

    flows = sorted(p1["flows"], key=lambda f: min(
        (b["x0"] for b in f["blocks"]), default=0))
    blocks = sorted((b for f in flows for b in f["blocks"]),
                    key=lambda b: (b["y0"], b["x0"]))

    # title: block with largest median word height on page 1 (font-size proxy),
    # excluding running headers (arXiv/DOI/date lines) and tiny blocks.
    def _is_meta_line(t):
        return bool(re.match(r"(arxiv\s*:)|(doi\s*[:.])|(https?://)", t, re.I)) \
            or re.match(r"^\[cs\.[A-Z]+\]", t)

    for b in blocks:
        if _is_meta_line(b["text"].strip()):
            continue
        heights = [w["y1"] - w["y0"] for l in b["lines"] for w in l["words"]]
        if not heights:
            continue
        med = sorted(heights)[len(heights) // 2]
        if med > title_score:
            title_score = med
            title = b["text"].strip()

    # authors/affiliations: top page-1 blocks that are not the title and come
    # before the abstract; keep them as front matter.
    if title:
        for b in blocks:
            t = b["text"].strip()
            if not t or t == title:
                continue
            low = _norm(t)
            if low == "abstract":
                break
            if len(t) <= 200 and ("," in t or "@" in t or "university" in low
                                  or "department" in low or "school" in low
                                  or "institute" in low or "laboratory" in low):
                author_blocks.append(t)

    return title, author_blocks, ""


def extract_abstract(body):
    """Join paragraphs between the Abstract heading and the first numbered section."""
    parts = []
    in_abs = False
    for b in body:
        t = b["text"].strip()
        low = _norm(t)
        if low == "abstract":
            in_abs = True
            continue
        if low.startswith("abstract ") or low.startswith("abstract\n"):
            # "Abstract" heading merged with its text into one block
            in_abs = True
            parts.append(t[len("Abstract"):].strip())
            continue
        if in_abs:
            h = heading_info(t)
            if h is not None and _is_standalone_heading(b):
                break
            if t:
                parts.append(t)
    return " ".join(parts)


# --------------------------------------------------------------------------
# 6. unreadable pages (scanned / no text layer)
# --------------------------------------------------------------------------

def detect_unreadable(pages):
    unreadable = []
    for pi, page in enumerate(pages):
        page_no = pi + 1
        words = [w for f in page["flows"] for b in f["blocks"]
                 for l in b["lines"] for w in l["words"]]
        if not words:
            unreadable.append({
                "page": page_no,
                "reason": "no text layer (scanned page / image-only); run OCR",
            })
    return unreadable


# --------------------------------------------------------------------------
# 7. main
# --------------------------------------------------------------------------

def parse(pdf_path):
    root = run_bbox_layout(pdf_path)
    pages = extract_pages(root)
    flat = flatten_blocks(pages)
    body, chrome = detect_chrome(flat)
    body = order_body(body)

    title, authors, _ = detect_title_and_authors(pages)
    abstract = extract_abstract(body)
    hs = sorted(_block_medh(b) for b in body if b["text"].strip())
    body_h = hs[len(hs) // 2] if hs else 9.0
    body = merge_split_headings(body, body_h)
    sections = build_sections(body, pages, body_h=body_h, title=title)
    figures, tables, equations = extract_captions(body)
    references = extract_references(body)
    unreadable = detect_unreadable(pages)

    # merge front-matter paragraphs into document.authors if not captured
    if not authors:
        fm = [p["text"] for p in sections[0]["paragraphs"]] if sections else []
        # only treat the very first section as front matter when it precedes Abstract
        if fm and (sections[0]["heading"] == "Front matter"):
            authors = fm

    return {
        "schema": "paper2arm/pdf-structure/v1",
        "document": {
            "title": title,
            "authors": authors,
            "abstract": abstract,
        },
        "sections": sections,
        "figures": figures,
        "tables": tables,
        "equations": equations,
        "references": references,
        "headers_footers": {
            "headers": list(dict.fromkeys(h["text"] for h in chrome["headers"])),
            "footers": list(dict.fromkeys(f["text"] for f in chrome["footers"])),
            "page_numbers": [p["text"] for p in chrome["page_numbers"]],
        },
        "footnotes": chrome["footnotes"],
        "unreadable": unreadable,
        "stats": {
            "pages": len(pages),
            "sections": len(sections),
            "paragraphs": sum(len(s["paragraphs"]) for s in sections),
            "figures": len(figures),
            "tables": len(tables),
            "equations": len(equations),
            "references": len(references),
            "footnotes": len(chrome["footnotes"]),
            "unreadable_pages": len(unreadable),
        },
        "status": "success",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", help="input PDF path")
    ap.add_argument("--out", required=True, help="output structure.json path")
    args = ap.parse_args()

    structure = parse(args.pdf)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(structure, fh, ensure_ascii=False, indent=2)
    s = structure["stats"]
    print("parsed %d pages: %d sections / %d paragraphs / %d figures / "
          "%d tables / %d equations / %d references / %d unreadable"
          % (s["pages"], s["sections"], s["paragraphs"], s["figures"],
             s["tables"], s["equations"], s["references"],
             s["unreadable_pages"]))


if __name__ == "__main__":
    main()
