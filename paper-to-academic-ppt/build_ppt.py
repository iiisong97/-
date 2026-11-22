#!/usr/bin/env python3
"""build_ppt.py — render a deck spec into an editable PPTX + evidence map + previews.

Beyond text slides, this builder crops each figure/table region out of the source
PDF (via pdftoppm) and embeds the real image into the slide, so a schematic is
shown as a schematic and data stays attached to its page. It also:

  * detects title/body/subtitle placeholders by type (robust to custom templates);
  * shrinks fonts and narrows the body box when a figure is embedded;
  * renders PDF + per-slide PNG previews via LibreOffice and logs every failure.

Usage:
    python3 build_ppt.py deck_spec.json --out DIR [--template base.pptx] [--paper paper.pdf]

The paper PDF may come from --paper or from deck_spec.meta.paper_pdf.
"""

import argparse
import json
import os
import re
import shutil
import subprocess

try:
    from pptx import Presentation
    from pptx.util import Pt, Inches, Emu
    from pptx.enum.text import PP_ALIGN
    from pptx.enum.shapes import PP_PLACEHOLDER
    HAS_PPTX = True
except Exception:  # noqa: BLE001
    HAS_PPTX = False

DPI = 150          # crop render resolution
ZOOM = 1.5         # pdftohtml zoom factor used by parse_pdf.py
SCALE = DPI / (72.0 * ZOOM)

TYPE_ZH = {"schematic": "示意图", "data": "数据/结果", "table": "数据表", "figure": "图"}

NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
UNIT_RE = re.compile(r"\b(?:%|KB|MB|GB|GiB|TiB|K|s|ms|h|FLOPs?|BLEU|F1|PPL|ppl|pt|px|m|kg|g|mol|W|Hz|dB|epochs?)\b", re.I)


def _extract_checks(bullets, figures):
    """Key numbers/units/figure-refs that must appear unchanged on a slide, so a
    reviewer can verify correctness against the paper (page-level golden checks)."""
    numbers, units, refs = [], [], []
    for b in bullets:
        text = b[0] if isinstance(b, (list, tuple)) else b
        numbers += NUMBER_RE.findall(text)
        units += UNIT_RE.findall(text)
    for f in figures:
        if f.get("number") is not None:
            refs.append(f"{f.get('kind', 'fig').title()} {f['number']}")
    out = {}
    for key, items in (("numbers", numbers), ("units", units), ("figure_refs", refs)):
        seen = []
        for x in items:
            if x not in seen:
                seen.append(x)
        out[key] = seen[:25]
    return out


def _fit_font_size(n_lines, max_chars, narrow=False):
    size = 20.0 if not narrow else 16.0
    if max_chars > 120:
        size = 16.0 if not narrow else 14.0
    if max_chars > 200:
        size = 14.0 if not narrow else 12.0
    if n_lines > 6:
        size = min(size, 15.0 if not narrow else 13.0)
    if n_lines > 9:
        size = min(size, 13.0 if not narrow else 11.0)
    return size


def _crop_figure(region):
    """Convert a figure region (pdftohtml zoom-1.5 [l,t,w,h]) to pdftoppm crop
    coordinates in output pixels."""
    l, t, w, h = region
    x, y = round(l * SCALE), round(t * SCALE)
    W, H = round(w * SCALE), round(h * SCALE)
    return x, y, W, H


def _embed_figure(slide, png_path, left, top, width, height, log):
    try:
        pic = slide.shapes.add_picture(png_path, left, top, width=width, height=height)
        return pic
    except Exception as exc:  # noqa: BLE001
        log.append(f"[figure] embed failed {png_path}: {exc}")
        return None


def _find_placeholder(slide, ptype, fallback_idx):
    for ph in slide.placeholders:
        try:
            if ph.placeholder_format.type == ptype:
                return ph
        except Exception:  # noqa: BLE001
            continue
    for ph in slide.placeholders:
        try:
            if ph.placeholder_format.idx == fallback_idx:
                return ph
        except Exception:  # noqa: BLE001
            continue
    return None


def _layout_types(layout):
    types = set()
    for ph in layout.placeholders:
        try:
            types.add(ph.placeholder_format.type)
        except Exception:  # noqa: BLE001
            continue
    return types


def _pick_layout(prs, want_title):
    """Pick a layout by its placeholder types instead of a fixed index, so a
    custom master/layout template is honoured regardless of its layout order."""
    T, B, S = PP_PLACEHOLDER.TITLE, PP_PLACEHOLDER.BODY, PP_PLACEHOLDER.SUBTITLE
    CT, OBJ = PP_PLACEHOLDER.CENTER_TITLE, PP_PLACEHOLDER.OBJECT
    if want_title:
        # title slide: prefer title + subtitle
        for i, layout in enumerate(prs.slide_layouts):
            types = _layout_types(layout)
            if (T in types or CT in types) and (S in types or B in types):
                return i
    # content slide: prefer title + body
    for i, layout in enumerate(prs.slide_layouts):
        types = _layout_types(layout)
        if (T in types or CT in types) and (B in types or OBJ in types):
            return i
    # fallback: any layout with a title
    for i, layout in enumerate(prs.slide_layouts):
        types = _layout_types(layout)
        if T in types or CT in types:
            return i
    return 0


def build(deck, out_dir, template=None, paper=None):
    if not HAS_PPTX:
        raise RuntimeError("python-pptx is not installed; run: pip install python-pptx")
    paper = paper or (deck.get("meta") or {}).get("paper_pdf")
    os.makedirs(out_dir, exist_ok=True)
    fig_dir = os.path.join(out_dir, "figures")
    os.makedirs(fig_dir, exist_ok=True)

    prs = Presentation(template) if template else Presentation()
    # Force 16:9 like the 75-pt v2, because the body/figure coordinates below are
    # hardcoded for 13.333x7.5 (e.g. figure box at x=8.0in). Keeping a template's
    # non-16:9 size made the content overflow on real templates (part of the
    # 65-pt regression). The template's theme/colors/fonts are still honoured via
    # its slide layouts.
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    evidence_map = []
    render_log = ["[build_ppt] pptx builder v3"]
    slides = deck.get("slides", [])

    for i, spec in enumerate(slides):
        layout_name = spec.get("layout", "content")
        layout_idx = _pick_layout(prs, want_title=(layout_name == "title"))
        try:
            slide = prs.slides.add_slide(prs.slide_layouts[layout_idx])
        except Exception:  # noqa: BLE001
            slide = prs.slides.add_slide(prs.slide_layouts[0] if prs.slide_layouts else None)

        title = spec.get("title", "")
        subtitle = spec.get("subtitle", "")
        bullets = spec.get("bullets", [])
        figures = spec.get("figures", [])
        notes = spec.get("notes", "")

        # title
        tph = _find_placeholder(slide, PP_PLACEHOLDER.TITLE, 0)
        if tph is not None:
            tph.text = title
            for run in tph.text_frame.paragraphs[0].runs:
                run.font.size = Pt(34 if layout_name == "title" else 26)

        # subtitle
        if subtitle:
            sph = _find_placeholder(slide, PP_PLACEHOLDER.SUBTITLE, 1)
            if sph is None and layout_name == "title":
                sph = _find_placeholder(slide, PP_PLACEHOLDER.BODY, 1)
            if sph is not None:
                sph.text = subtitle

        # body bullets
        body = _find_placeholder(slide, PP_PLACEHOLDER.BODY, 1)
        if body is not None and layout_name != "title":
            tf = body.text_frame
            tf.word_wrap = True
            max_chars = max((len(b[0] if isinstance(b, (list, tuple)) else b) for b in bullets),
                            default=0)
            narrow = bool(figures)
            font_size = _fit_font_size(len(bullets), max_chars, narrow)
            first = True
            for item in bullets:
                if isinstance(item, str):
                    text, level = item, 0
                else:
                    text, level = item[0], item[1]
                p = tf.paragraphs[0] if first else tf.add_paragraph()
                first = False
                p.text = text
                p.level = min(level, 4)
                for run in p.runs:
                    run.font.size = Pt(font_size if level == 0 else max(font_size - 2, 11))
            if narrow:
                body.left = Inches(0.45)
                body.top = Inches(1.25)
                body.width = Inches(7.4)
                body.height = Inches(5.6)

        # embed figures/tables on the right (aspect ratio preserved)
        embed_status = []
        if figures:
            left = Inches(8.0)
            top = Inches(1.2)
            box_w = 5.1
            box_h = 5.3 if len(figures) == 1 else 2.7
            for k, fig in enumerate(figures):
                png = os.path.join(fig_dir, f"slide{i+1:02d}_fig{k+1}.png")
                crop_w = crop_h = None
                ok = False
                if paper and fig.get("region") and fig.get("page"):
                    x, y, crop_w, crop_h = _crop_figure(fig["region"])
                    r = subprocess.run(
                        ["pdftoppm", "-f", str(fig["page"]), "-l", str(fig["page"]),
                         "-r", str(DPI), "-x", str(x), "-y", str(y), "-W", str(crop_w), "-H", str(crop_h),
                         "-png", paper, png[:-4]], capture_output=True, text=True, check=False)
                    actual = f"{png[:-4]}-{int(fig['page']):02d}.png"
                    if r.returncode == 0 and os.path.exists(actual):
                        os.rename(actual, png)
                        ok = True
                    elif r.returncode == 0 and os.path.exists(png):
                        ok = True
                    else:
                        render_log.append(f"[figure] crop failed slide{i+1} fig{k+1}: "
                                          + (r.stderr or r.stdout or "unknown")[:200])
                if ok and crop_w and crop_h:
                    aspect = crop_w / crop_h
                    if aspect > box_w / box_h:        # wider than the box
                        disp_w, disp_h = box_w, box_w / aspect
                    else:
                        disp_h, disp_w = box_h, box_h * aspect
                    _embed_figure(slide, png, left, top, Inches(disp_w), Inches(disp_h), render_log)
                    cap = fig.get("caption", "")
                    tb = slide.shapes.add_textbox(left, top + Inches(disp_h), Inches(box_w), Inches(0.6))
                    tb.text_frame.word_wrap = True
                    tb.text_frame.text = (f"{fig.get('kind','').title()} {fig.get('number') or ''} "
                                          f"({TYPE_ZH.get(fig.get('type'), '')}) "
                                          f"p.{fig.get('page')}").strip()
                    for run in tb.text_frame.paragraphs[0].runs:
                        run.font.size = Pt(10)
                    embed_status.append({"kind": fig.get("kind"), "number": fig.get("number"),
                                         "page": fig.get("page"), "type": fig.get("type"),
                                         "embedded": True, "png": os.path.relpath(png, out_dir)})
                    top = top + Inches(disp_h) + Inches(0.75)
                else:
                    embed_status.append({"kind": fig.get("kind"), "number": fig.get("number"),
                                         "page": fig.get("page"), "type": fig.get("type"),
                                         "embedded": False,
                                         "reason": "no region / crop failed / no paper path"})

        if notes:
            try:
                slide.notes_slide.notes_text_frame.text = notes
            except Exception:  # noqa: BLE001
                render_log.append(f"[notes] failed on slide {i+1}")

        evidence_map.append({
            "slide": i + 1, "title": title,
            "claim": title,                       # one claim per page: title = claim
            "checks": _extract_checks(bullets, figures),
            "figures": embed_status,
            "evidence": spec.get("evidence", []),
            "notes_present": bool(notes),
        })

    pptx_path = os.path.join(out_dir, "deck.pptx")
    prs.save(pptx_path)
    render_log.append("[build_ppt] saved " + pptx_path)

    with open(os.path.join(out_dir, "evidence_map.json"), "w", encoding="utf-8") as fh:
        json.dump({"schema": "paper2arm/ppt-evidence/v1", "slides": evidence_map},
                  fh, ensure_ascii=False, indent=2)
    # page-level golden standard: a per-slide reference (claim + evidence +
    # numbers/units/figure-refs to verify) that a reviewer can check the deck
    # against the paper with, independent of this implementation
    with open(os.path.join(out_dir, "golden_standard.json"), "w", encoding="utf-8") as fh:
        json.dump({"schema": "paper2arm/ppt-golden/v1",
                   "note": "Per-page golden standard: claim, evidence and checks. "
                           "Verify each slide against the cited paper figure/table/section/page.",
                   "slides": evidence_map}, fh, ensure_ascii=False, indent=2)

    preview_dir = os.path.join(out_dir, "previews")
    os.makedirs(preview_dir, exist_ok=True)
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice:
        conv = subprocess.run([soffice, "--headless", "--convert-to", "pdf",
                               "--outdir", out_dir, pptx_path],
                              capture_output=True, text=True, check=False)
        pdf_path = os.path.join(out_dir, "deck.pdf")
        if conv.returncode == 0 and os.path.exists(pdf_path):
            subprocess.run(["pdftoppm", "-png", "-r", "80", pdf_path,
                            os.path.join(preview_dir, "slide")],
                           capture_output=True, check=False)
            render_log.append(f"[render] {len(os.listdir(preview_dir))} preview PNG(s)")
        else:
            render_log.append("[render] PDF conversion failed: " +
                              (conv.stderr or conv.stdout or "unknown")[:300])
    else:
        render_log.append("[render] LibreOffice not found; previews skipped")

    with open(os.path.join(out_dir, "render.log"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(render_log) + "\n")

    print(f"built deck: {len(slides)} slides -> {pptx_path}")
    print("\n".join(render_log))
    return pptx_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--out", required=True)
    ap.add_argument("--template", default=None)
    ap.add_argument("--paper", default=None)
    args = ap.parse_args()
    deck = json.load(open(args.spec, encoding="utf-8"))
    build(deck, args.out, args.template, args.paper)


if __name__ == "__main__":
    main()
