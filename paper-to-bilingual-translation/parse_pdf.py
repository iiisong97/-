#!/usr/bin/env python3
"""parse_pdf.py — layout-aware scientific PDF parser (poppler-based, stdlib only).

Produces a structured JSON document from a scientific PDF:

  - full text in reading order (single/multi-column aware)
  - section hierarchy with per-paragraph page + bounding-box evidence
  - tables (row/column reconstruction) with captions and evidence
  - figures with captions and page evidence
  - equations (detected via math fonts / symbol density) with page evidence
  - references list
  - honest uncertainty flags (scanned pages, image tables, unreadable regions)

Design goal: deterministic and verifiable. Every element carries
(page, bbox, source text) so the result can be checked against the original PDF.

Usage:
    python3 parse_pdf.py INPUT.pdf [--out result.json] [--txt fulltext.txt]
"""

import argparse
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from collections import defaultdict, Counter

# ---------------------------------------------------------------------------
# Typographic / layout constants (pdftohtml -zoom 1.5 coordinate space)
# ---------------------------------------------------------------------------
TITLE_MIN_SIZE = 20.0
BOLD_HINTS = ("medi", "bold", "semibold", "demi", "heavy", "black")
ITALIC_HINTS = ("ital", "obl", "slanted")
MATH_FONT_HINTS = ("cmsy", "cmex", "math", "cmr", "msam", "msbm", "cmtex", "stix",
                   "cmmi", "cmti", "cmbx", "math1", "math2")
MONO_FONT_HINTS = ("courier", "mono", "typewriter", "sftt", "consola")
HEADER_BAND = 55.0
FOOTER_BAND = 55.0
MARGIN_SIDE = 55.0

NUM_HEADING_RE = re.compile(r"^(\d{1,3}(?:\.\d{1,3}){0,3})[.)\u3001]?\s+(.+)$")
ROMAN_HEADING_RE = re.compile(r"^([IVXLC]{1,8})[.)]?\s+(.+)$")
LETTER_HEADING_RE = re.compile(r"^([A-Z])[.)]?\s+(.+)$")
CAPTION_RE = re.compile(r"^\s*(fig(?:ure)?\.?\s*\d+|table\.?\s*\d+|scheme\.?\s*\d+)",
                        re.IGNORECASE)
ABSTRACT_RE = re.compile(r"^abstract$", re.IGNORECASE)
REF_HEADING_RE = re.compile(r"^references?$", re.IGNORECASE)
REF_ENTRY_RE = re.compile(r"^\[(\d{1,3})\]\s*(.*)$")
EQUATION_NUM_RE = re.compile(r"\((\d{1,3}(?:\.\d{1,3})?)\)\s*$")
PURE_NUMERIC_RE = re.compile(r"^[\d\s.,\u00d7\u00b7\u2212+\u2013%-]+$")
MATH_SYMBOL_RE = re.compile(
    r"[\u2200-\u22FF\u2220-\u2299\u00d7\u2212\u00b1\u221e\u222b\u2202\u2211\u221a"
    r"\u2264\u2265\u2260\u2248\u03b1-\u03c9\u0391-\u03a9]")
HEADING_KEYWORDS = {
    "abstract", "references", "acknowledgments", "acknowledgements", "appendix",
    "supplementary", "introduction", "conclusion", "conclusions", "methods",
    "method", "results", "discussion", "background", "related work",
    "future work", "contributions",
}


def parse_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# poppler interface
# ---------------------------------------------------------------------------
def pdftohtml_xml(pdf_path):
    cmd = ["pdftohtml", "-xml", "-stdout", "-i", "-noroundcoord", pdf_path]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError("pdftohtml failed: " + (proc.stderr or proc.stdout or "unknown"))
    text = proc.stdout
    start = text.find("<?xml")
    if start < 0:
        start = text.find("<pdf2xml")
    if start < 0:
        raise RuntimeError("pdftohtml produced no XML")
    return ET.fromstring(text[start:])


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
class Line:
    __slots__ = ("top", "left", "width", "height", "font", "text", "font_size",
                 "family", "color", "bold", "italic", "mono", "mathy")

    def __init__(self, top, left, width, height, font, text, fontspec):
        self.top = top
        self.left = left
        self.width = width
        self.height = height
        self.font = font
        self.text = text
        self.font_size = parse_float(fontspec.get("size"), 0.0)
        self.family = fontspec.get("family", "")
        self.color = fontspec.get("color", "#000000")
        fam = self.family.lower()
        self.bold = any(h in fam for h in BOLD_HINTS)
        self.italic = any(h in fam for h in ITALIC_HINTS)
        self.mono = any(h in fam for h in MONO_FONT_HINTS)
        self.mathy = any(h in fam for h in MATH_FONT_HINTS)

    @property
    def right(self):
        return self.left + self.width

    @property
    def bottom(self):
        return self.top + self.height

    @property
    def center_x(self):
        return self.left + self.width / 2.0

    @property
    def bbox(self):
        return [round(self.left, 1), round(self.top, 1),
                round(self.width, 1), round(self.height, 1)]

    @property
    def stripped(self):
        return self.text.strip()


class Block:
    __slots__ = ("lines", "page", "kind", "col")

    def __init__(self, lines, page):
        self.lines = lines
        self.page = page
        self.kind = "body"
        self.col = -1

    @property
    def text(self):
        return " ".join(l.stripped for l in self.lines).strip()

    @property
    def top(self):
        return min(l.top for l in self.lines)

    @property
    def bottom(self):
        return max(l.bottom for l in self.lines)

    @property
    def left(self):
        return min(l.left for l in self.lines)

    @property
    def right(self):
        return max(l.right for l in self.lines)

    @property
    def width(self):
        return self.right - self.left

    @property
    def height(self):
        return self.bottom - self.top

    @property
    def center_x(self):
        return (self.left + self.right) / 2.0

    @property
    def bbox(self):
        return [round(self.left, 1), round(self.top, 1),
                round(self.width, 1), round(self.height, 1)]

    @property
    def max_font_size(self):
        return max((l.font_size for l in self.lines), default=0.0)

    @property
    def is_bold(self):
        return any(l.bold for l in self.lines)

    @property
    def n_math_symbols(self):
        return sum(len(MATH_SYMBOL_RE.findall(l.text)) for l in self.lines)

    @property
    def is_mathy(self):
        return all(l.mathy for l in self.lines) or self.n_math_symbols >= 2


# ---------------------------------------------------------------------------
# Heading detection (body-size relative)
# ---------------------------------------------------------------------------
def is_heading_line(line, body_size):
    if line.font_size >= TITLE_MIN_SIZE:
        return True
    txt = line.stripped
    low = txt.lower()
    if line.bold and line.font_size >= body_size - 1.0 and len(txt) <= 110:
        return True
    if line.font_size >= body_size + 4.0 and len(txt) <= 110:
        return True
    # Bold numbered / keyword headings even if not much larger.
    if line.bold and (NUM_HEADING_RE.match(txt) or ROMAN_HEADING_RE.match(txt)
                      or low in HEADING_KEYWORDS):
        return True
    return False


def classify_block(block, body_size):
    txt = block.text
    if not txt:
        return "empty"
    low = txt.strip().lower()
    if block.page == 1 and block.max_font_size >= TITLE_MIN_SIZE and len(txt) < 200:
        return "title"
    first = block.lines[0]
    if is_heading_line(first, body_size) and len(txt) <= 110:
        if ABSTRACT_RE.match(low):
            return "abstract-heading"
        if REF_HEADING_RE.match(low):
            return "references-heading"
        return "heading"
    if CAPTION_RE.match(txt.strip()):
        return "caption"
    return "body"


# ---------------------------------------------------------------------------
# Block grouping
# ---------------------------------------------------------------------------
def typo_kind(line, body_size):
    if is_heading_line(line, body_size):
        return "heading"
    if line.mathy:
        return "math"
    return "body"


def group_lines_into_blocks(lines, body_size):
    if not lines:
        return []
    lines = sorted(lines, key=lambda l: (l.top, l.left))
    blocks = []
    cur = [lines[0]]
    for line in lines[1:]:
        prev = cur[-1]
        gap = line.top - prev.bottom
        avg_h = max(2.0, (line.height + prev.height) / 2.0)
        x_overlap = min(prev.right, line.right) - max(prev.left, line.left)
        x_overlap_ratio = x_overlap / max(1.0, min(prev.width, line.width))
        big_gap = gap > avg_h * 2.2
        side_jump = gap > avg_h * 0.9 and x_overlap_ratio < 0.15
        typo_change = typo_kind(line, body_size) != typo_kind(prev, body_size)
        font_jump = abs(line.font_size - prev.font_size) > 3.5
        if big_gap or side_jump or typo_change or font_jump:
            blocks.append(cur)
            cur = [line]
        else:
            cur.append(line)
    blocks.append(cur)
    return blocks


# ---------------------------------------------------------------------------
# Column detection
# ---------------------------------------------------------------------------
def detect_columns(blocks, page_width):
    body = [b for b in blocks if b.width > 30 and b.max_font_size < TITLE_MIN_SIZE]
    if not body:
        return [(MARGIN_SIDE, page_width - MARGIN_SIDE)]
    left_edge = min(b.left for b in body)
    right_edge = max(b.right for b in body)
    text_span = right_edge - left_edge
    if text_span < page_width * 0.45:
        return [(left_edge, right_edge)]

    # Find a low-density vertical gutter in the middle of the text span.
    best_split = None
    best_score = float("inf")
    total_height = sum(b.height for b in body)
    mid = (left_edge + right_edge) / 2.0
    for split_x in range(int(mid - text_span * 0.30), int(mid + text_span * 0.30), 10):
        density = sum(b.height for b in body if b.left < split_x < b.right)
        if density < best_score:
            best_score = density
            best_split = split_x
    if best_split is not None and best_score < total_height * 0.08:
        return [(left_edge, best_split), (best_split, right_edge)]
    return [(left_edge, right_edge)]


# ---------------------------------------------------------------------------
# Table detection / reconstruction
# ---------------------------------------------------------------------------
def looks_like_table(block):
    if len(block.lines) < 2:
        return False
    starts = [l.left for l in block.lines]
    if max(starts) - min(starts) > 25:
        return False
    for l in block.lines:
        if len(re.split(r"\s{2,}", l.stripped)) >= 3:
            return True
    return False


def block_to_markdown_table(block):
    rows = []
    for l in block.lines:
        cells = [c.strip() for c in re.split(r"\s{2,}", l.stripped) if c.strip()]
        if cells:
            rows.append(cells)
    if not rows:
        return ""
    ncols = max(len(r) for r in rows)
    rows = [r + [""] * (ncols - len(r)) for r in rows]
    lines = ["| " + " | ".join(rows[0]) + " |",
             "| " + " | ".join(["---"] * ncols) + " |"]
    for r in rows[1:]:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main parsing
# ---------------------------------------------------------------------------
def parse_pdf(pdf_path):
    root = pdftohtml_xml(pdf_path)
    # Font specs are declared per page but referenced globally, so merge them all.
    global_fontspecs = {}
    for fs in root.findall(".//fontspec"):
        global_fontspecs[fs.get("id")] = {
            "size": fs.get("size"), "family": fs.get("family", ""),
            "color": fs.get("color", "#000000"),
        }
    pages = []
    all_sizes = []
    for page_el in root.findall(".//page"):
        pw = parse_float(page_el.get("width"), 918.0)
        ph = parse_float(page_el.get("height"), 1188.0)
        lines = []
        for t in page_el.findall(".//text"):
            line = Line(parse_float(t.get("top")), parse_float(t.get("left")),
                        parse_float(t.get("width")), parse_float(t.get("height")),
                        t.get("font"), t.text or "",
                        global_fontspecs.get(t.get("font"), {}))
            lines.append(line)
            if not line.bold and not line.mono and 8.0 <= line.font_size < 20.0:
                all_sizes.append(line.font_size)
        pages.append({"number": int(page_el.get("number")), "width": pw,
                      "height": ph, "lines": lines})

    # Global body font size: median of regular-weight line sizes.
    body_size = 13.0
    if all_sizes:
        all_sizes.sort()
        body_size = all_sizes[len(all_sizes) // 2]

    doc = {
        "schema": "paper2arm/pdf-structure/v1",
        "status": "partial",
        "document": {"page_count": len(pages), "body_font_size": round(body_size, 1)},
        "sections": [],
        "tables": [],
        "figures": [],
        "equations": [],
        "references": [],
        "uncertainty": [],
        "page_map": {},
        "_pdf_path": pdf_path,
    }

    running_section = None
    in_abstract = False
    for page in pages:
        pn = page["number"]
        core_lines = []
        for l in page["lines"]:
            in_margin = (l.top < HEADER_BAND
                         or (page["height"] - l.bottom) < FOOTER_BAND
                         or l.left < MARGIN_SIDE
                         or (page["width"] - l.right) < MARGIN_SIDE)
            if not in_margin or l.font_size >= TITLE_MIN_SIZE:
                core_lines.append(l)

        blocks = [Block(bl, pn) for bl in group_lines_into_blocks(core_lines, body_size)]
        columns = detect_columns(blocks, page["width"])

        def column_index(b):
            if b.width > (page["width"] * 0.75) or len(columns) == 1:
                return -1
            cx = b.center_x
            for i, (x0, x1) in enumerate(columns):
                if x0 <= cx <= x1:
                    return i
            return min(range(len(columns)),
                       key=lambda i: abs((columns[i][0] + columns[i][1]) / 2 - cx))

        blocks = [b for b in blocks if b.text]
        for b in blocks:
            b.col = column_index(b)

        span = sorted([b for b in blocks if b.col == -1], key=lambda b: b.top)
        col_blocks = defaultdict(list)
        for b in blocks:
            if b.col != -1:
                col_blocks[b.col].append(b)
        ordered = list(span)
        for ci in sorted(col_blocks.keys()):
            ordered.extend(sorted(col_blocks[ci], key=lambda b: b.top))

        pmap = {"width": round(page["width"], 1), "height": round(page["height"], 1),
                "columns": [[round(c[0], 1), round(c[1], 1)] for c in columns],
                "blocks": []}

        def is_centered(b):
            if 0 <= b.col < len(columns):
                x0, x1 = columns[b.col]
                return abs(b.center_x - (x0 + x1) / 2) < (x1 - x0) * 0.30
            return abs(b.center_x - page["width"] / 2) < page["width"] * 0.20

        for b in ordered:
            kind = classify_block(b, body_size)
            # A mathy block is a *display* equation only when centered in its
            # column or carrying an equation number; otherwise inline math -> body.
            if kind == "body" and b.is_mathy and len(b.text) < 400:
                if is_centered(b) or EQUATION_NUM_RE.search(b.text):
                    kind = "equation"
            # Bold short lines that are really table cells (multi-column or pure
            # numeric) must not be emitted as section headings.
            if kind == "heading" and (looks_like_table(b) or PURE_NUMERIC_RE.match(b.text.strip())):
                kind = "table"
            if kind == "body" and looks_like_table(b):
                kind = "table"

            pmap["blocks"].append({
                "bbox": b.bbox, "kind": kind, "font_size": round(b.max_font_size, 1),
                "bold": b.is_bold, "col": b.col, "text_preview": b.text[:160],
            })

            if kind == "title":
                if not doc["document"].get("title"):
                    doc["document"]["title"] = b.text
                continue
            if kind == "abstract-heading":
                running_section = {"heading": b.text, "level": 1, "page": pn,
                                   "bbox": b.bbox, "paragraphs": [], "number": None}
                doc["sections"].append(running_section)
                in_abstract = True
                continue
            if kind == "references-heading":
                running_section = {"heading": b.text, "level": 1, "page": pn,
                                   "bbox": b.bbox, "paragraphs": [], "number": None,
                                   "is_refs": True}
                doc["sections"].append(running_section)
                in_abstract = False
                continue
            if kind == "heading":
                num = None
                m = (NUM_HEADING_RE.match(b.text) or ROMAN_HEADING_RE.match(b.text)
                     or LETTER_HEADING_RE.match(b.text))
                if m:
                    num = m.group(1)
                level = (b.text.count(".") + 1) if (num and "." in b.text) else 1
                running_section = {"heading": b.text, "level": level, "page": pn,
                                   "bbox": b.bbox, "paragraphs": [], "number": num}
                doc["sections"].append(running_section)
                in_abstract = False
                continue
            if kind == "caption":
                if re.match(r"^\s*fig", b.text, re.IGNORECASE):
                    doc["figures"].append({"page": pn, "bbox": b.bbox,
                                           "caption": b.text})
                else:
                    doc["tables"].append({"page": pn, "bbox": b.bbox,
                                          "caption": b.text, "markdown": None,
                                          "rows": None})
                continue
            if kind == "equation":
                num_m = EQUATION_NUM_RE.search(b.text)
                doc["equations"].append({"page": pn, "bbox": b.bbox, "text": b.text,
                                         "number": num_m.group(1) if num_m else None})
                continue
            if kind == "table":
                doc["tables"].append({
                    "page": pn, "bbox": b.bbox, "caption": None,
                    "markdown": block_to_markdown_table(b),
                    "rows": [re.split(r"\s{2,}", l.stripped) for l in b.lines]})
                continue

            # body paragraph
            para = {"text": b.text, "page": pn, "bbox": b.bbox,
                    "lines": [{"text": l.stripped, "bbox": l.bbox} for l in b.lines]}

            if in_abstract:
                if not doc["document"].get("abstract"):
                    doc["document"]["abstract"] = b.text
                else:
                    doc["document"]["abstract"] += " " + b.text

            if running_section is not None and running_section.get("is_refs"):
                for l in b.lines:
                    m = REF_ENTRY_RE.match(l.stripped)
                    if m:
                        doc["references"].append({"index": int(m.group(1)),
                                                  "text": m.group(2).strip(),
                                                  "page": pn, "bbox": l.bbox})
                running_section["paragraphs"].append(para)
            elif running_section is not None:
                running_section["paragraphs"].append(para)
            else:
                # Preamble body (authors / affiliations) — keep as first section.
                if not any(s.get("number") is None and s["heading"] == "Preamble"
                           for s in doc["sections"]):
                    running_section = {"heading": "Preamble", "level": 0, "page": pn,
                                       "bbox": b.bbox, "paragraphs": [], "number": None}
                    doc["sections"].insert(0, running_section)
                running_section["paragraphs"].append(para)

        doc["page_map"][str(pn)] = pmap

    # Scanned / no-text pages.
    for pn, pm in doc["page_map"].items():
        if not any(b["kind"] != "empty" for b in pm["blocks"]):
            doc["uncertainty"].append({
                "page": int(pn), "type": "no_text_layer",
                "note": "No extractable text layer; likely scanned/image PDF — OCR required."})

    # Keep all headings (a heading may legitimately have no direct paragraphs,
    # e.g. "6 Results" followed directly by "6.1 …"). Only strip internal flags.
    for s in doc["sections"]:
        s.pop("is_refs", None)

    if doc["document"].get("title") and doc["sections"]:
        doc["status"] = "success"
    elif doc["sections"] or doc["document"].get("title"):
        doc["status"] = "partial"
    enrich_evidence(doc)
    doc.pop("_pdf_path", None)
    return doc


# ---------------------------------------------------------------------------
# Evidence enrichment: figure/table numbers, types, citation cross-references,
# figure image regions, and table caption<->body merging. This turns the raw
# layout parse into the evidence base the PPT builder can trace every slide to.
# ---------------------------------------------------------------------------
FIG_NUM_RE = re.compile(r"\bfi?g(?:ure)?\.?\s*(\d+)\b", re.IGNORECASE)
TABLE_NUM_RE = re.compile(r"\btable\.?\s*(\d+)\b", re.IGNORECASE)

SCHEMATIC_HINTS = ("architecture", "diagram", "schematic", "overview",
                   "illustration", "example of", "visualization", "attention head",
                   "model architecture", "encoder and decoder", "pipeline", "flow")
DATA_HINTS = ("result", "bleu", "accuracy", "f1", "performance", "comparison",
              "achieves", "state-of-the-art", "ablation", "variation", "evaluation",
              "training cost", "benchmark", "metric", "perplexity", "ppl")


def _figure_number(caption):
    m = FIG_NUM_RE.search(caption or "")
    return int(m.group(1)) if m else None


def _table_number(caption):
    m = TABLE_NUM_RE.search(caption or "")
    return int(m.group(1)) if m else None


def _classify_evidence_type(caption):
    low = (caption or "").lower()
    if re.match(r"^\s*table", low):
        return "table"
    if any(w in low for w in SCHEMATIC_HINTS):
        return "schematic"
    if any(w in low for w in DATA_HINTS):
        return "data"
    return "figure"


def _estimate_figure_region(cap_bbox, page_blocks, columns=None):
    """Region of the figure image: the space directly above its caption.

    bbox order is [left, top, width, height] in pdftohtml zoom-1.5 coordinates.
    The caption is usually narrower than the figure, so expand horizontally to
    the text column the caption sits in.
    """
    left, top, width, height = cap_bbox
    if columns:
        cx = left + width / 2
        for (cl, cr) in columns:
            if cl - 10 <= cx <= cr + 10:
                left, width = cl, cr - cl
                break
    right = left + width
    above = []
    for b in page_blocks:
        bl, bt, bw, bh = b["bbox"]
        if bh <= 0 or b.get("kind") in ("caption", "empty"):
            continue
        if bt + bh <= top + 4:                       # ends at/above the caption
            if bl + bw > left - 40 and bl < right + 40:   # horizontal overlap
                above.append(bt + bh)                # block bottom
    if above:
        region_top = max(above) + 3
    else:
        region_top = 55
    region_height = top - region_top
    if region_height < 60:                            # no room above: fallback band
        region_top = max(55, top - 320)
        region_height = top - region_top
    return [left, region_top, width, region_height]


def _estimate_table_region(cap_bbox, page_blocks, columns=None):
    """Region of a table: its caption plus the body below it, down to the next
    non-table text block. bbox order is [left, top, width, height]."""
    left, top, width, height = cap_bbox
    if columns:
        cx = left + width / 2
        for (cl, cr) in columns:
            if cl - 10 <= cx <= cr + 10:
                left, width = cl, cr - cl
                break
    right = left + width
    below = []
    for b in page_blocks:
        bl, bt, bw, bh = b["bbox"]
        if bh <= 0 or b.get("kind") in ("caption", "empty", "table"):
            continue
        if bt >= top + height - 2 and bl + bw > left - 40 and bl < right + 40:
            below.append(bt)
    region_bottom = (min(below) - 3) if below else top + height + 400
    region_height = min(region_bottom - top, 800)
    return [left, top, width, region_height]


def _merge_table_bodies(tables):
    """Attach caption-less table-cell blocks to the captioned table above them."""
    primary = [t for t in tables if t.get("caption") and TABLE_NUM_RE.search(t["caption"])]
    anonymous = [t for t in tables if not (t.get("caption") and TABLE_NUM_RE.search(t["caption"]))]
    for anon in anonymous:
        cands = [p for p in primary
                 if p["page"] == anon["page"] and p["bbox"][1] < anon["bbox"][1]]
        if not cands:
            cands = [p for p in primary
                     if p["page"] == anon["page"] - 1]   # caption at top of prev page
        if cands:
            target = max(cands, key=lambda p: p["bbox"][1])
            if target.get("markdown") is None:
                target["markdown"] = anon.get("markdown") or ""
                target["rows"] = anon.get("rows")
            else:
                target["markdown"] = (target.get("markdown") or "") + "\n" + (anon.get("markdown") or "")
                target["rows"] = (target.get("rows") or []) + (anon.get("rows") or [])
            target["page"] = min(target["page"], anon["page"])
        elif (anon.get("rows") and len(anon["rows"]) > 2):
            primary.append(anon)                        # keep genuine unnumbered table
    return primary


def enrich_evidence(doc):
    # 1. merge caption-less table bodies into captioned tables
    doc["tables"] = _merge_table_bodies(doc["tables"])

    # 2. number, type, region for figures
    for fig in doc.get("figures", []):
        fig["number"] = _figure_number(fig.get("caption"))
        fig["type"] = _classify_evidence_type(fig.get("caption"))
        pm = doc.get("page_map", {}).get(str(fig.get("page")), {})
        fig["region"] = _estimate_figure_region(fig.get("bbox"), pm.get("blocks", []),
                                                pm.get("columns"))

    # 3. number + type + region for tables
    for tbl in doc.get("tables", []):
        tbl["number"] = _table_number(tbl.get("caption"))
        tbl["type"] = "table"
        low = (tbl.get("caption") or "").lower()
        tbl["result_role"] = ("comparison_own_vs_baseline"
                              if any(w in low for w in ("achieves", "state-of-the-art", "baseline", "comparison"))
                              else "supporting_data")
        pm = doc.get("page_map", {}).get(str(tbl.get("page")), {})
        tbl["region"] = _estimate_table_region(tbl.get("bbox"), pm.get("blocks", []),
                                               pm.get("columns"))

    # 4. cross-references: which sections cite each figure/table. Inline numbers
    #    are often split from the word "Figure"/"Table" in the XML layout, so use
    #    pdftotext -layout per page (contiguous "Figure 3" / "Table 2" strings).
    def _page_plain_text(pn, cache):
        if pn not in cache:
            try:
                out = subprocess.run(["pdftotext", "-f", str(pn), "-l", str(pn),
                                      "-layout", doc.get("_pdf_path", ""), "-"],
                                     capture_output=True, text=True, check=False).stdout
            except Exception:  # noqa: BLE001
                out = ""
            cache[pn] = out or ""
        return cache[pn]

    # page -> sections active on that page (sections that begin on the page,
    # plus the continuing section when none begins there)
    pages = sorted({s.get("page") or 1 for s in doc.get("sections", [])} | {1})
    page_sections = {}
    for pn in pages:
        active = [s.get("heading", "") for s in doc.get("sections", [])
                  if (s.get("page") or 1) == pn]
        if not active:
            prev = [s for s in doc.get("sections", []) if (s.get("page") or 1) < pn]
            if prev:
                active = [prev[-1].get("heading", "")]
        page_sections[pn] = active

    cache = {}
    for label, key, pat in (("figure", "figures", r"[Ff]ig(?:ure)?\.?\s*(\d+)"),
                            ("table", "tables", r"[Tt]able\.?\s*(\d+)")):
        for ev in doc.get(key, []):
            num = ev.get("number")
            if num is None:
                continue
            cited_pages, cited_sections = [], []
            for pn in pages:
                txt = _page_plain_text(pn, cache)
                if any(int(m.group(1)) == num for m in re.finditer(pat, txt)):
                    cited_pages.append(pn)
                    for h in page_sections.get(pn, []):
                        if h not in cited_sections:
                            cited_sections.append(h)
            ev["cited_in"] = cited_sections
            ev["cited_pages"] = cited_pages

    # 5. per-page plain text (pdftotext -layout), for the agent to re-merge
    #    inline-math fragments into clean claim sentences during refinement
    doc["plaintext_pages"] = {pn: cache[pn] for pn in pages}
    return doc


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Layout-aware scientific PDF parser")
    ap.add_argument("input")
    ap.add_argument("--out", help="write JSON here (default: stdout)")
    ap.add_argument("--txt", help="write plain reading-order text here")
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    try:
        doc = parse_pdf(args.input)
    except Exception as exc:  # noqa: BLE001
        doc = {"schema": "paper2arm/pdf-structure/v1", "status": "failed",
               "error": str(exc), "document": {}, "sections": [], "tables": [],
               "figures": [], "equations": [], "references": [],
               "uncertainty": [], "page_map": {}}

    json_text = json.dumps(doc, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(json_text + "\n")
    else:
        print(json_text)

    if args.txt:
        parts = []
        if doc["document"].get("title"):
            parts.append(doc["document"]["title"])
        if doc["document"].get("abstract"):
            parts.append(doc["document"]["abstract"])
        for s in doc["sections"]:
            parts.append(s["heading"])
            for p in s.get("paragraphs", []):
                parts.append(p["text"])
        with open(args.txt, "w", encoding="utf-8") as fh:
            fh.write("\n\n".join(parts) + "\n")


if __name__ == "__main__":
    main()
