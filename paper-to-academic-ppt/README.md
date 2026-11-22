# paper-to-academic-ppt

Turn a scientific paper into an editable, evidence-backed academic slide deck.
The pipeline separates **narrative extraction** (what story the paper tells),
**page design** (one claim per slide, with the real figure/table attached), and
**rendering** (editable PPTX + PDF/PNG previews), so the deck can be checked
against the paper.

## What it solves

| Failure of a bare LLM "PPT" | What this skill does |
|---|---|
| Paragraphs pasted in order, no main line | `draft_outline.py` groups subsections and extracts problem → background → method → results → conclusion |
| Figure/table numbers mismatched or moved | `parse_pdf.py` numbers and types each figure/table and records `cited_in`/`cited_pages`; `draft_outline.py` attaches each to the slide that cites it |
| Schematic shown as data / others' results shown as own | `type` = schematic/data/table and `result_role` = comparison_own_vs_baseline; the deck flags 本文 vs 基线 |
| Figures described but not shown | `build_ppt.py` crops each figure/table region from the PDF (pdftoppm) and embeds it, aspect ratio preserved |
| Numbers/units altered in transit | bullets keep numbers as parsed; SKILL.md instructs re-merging inline math from `plaintext_pages` |
| Long text overflows a narrow box | wraps text, shrinks font, narrows the body box when a figure is embedded |
| No speaker notes, or notes repeat the slide | SKILL.md requires notes to add transition/emphasis/backup evidence |
| Can't open / font breaks on another machine | renders PDF + per-slide PNG via LibreOffice and logs every failure |
| No way to verify the gain vs a naive agent | `benchmark.py` produces a reproducible A/B record (evidence/figure/notes coverage, main-line order, overflow risk) |
| Reviewer can't check each page against the paper | `golden_standard.json` lists per-slide claim + evidence + numbers/units/figure-refs to verify |

## Files

- `SKILL.md` — the workflow the harness agent follows
- `parse_pdf.py` — layout-aware parser + evidence enrichment (numbers, types,
  regions, citation cross-references, table merging, `plaintext_pages`)
- `draft_outline.py` — structure → deck-spec skeleton (main line, evidence
  attachment, spurious-heading filtering)
- `build_ppt.py` — deck spec → editable PPTX + embedded figures/tables +
  evidence map + golden standard + rendered previews; honours a template's size
  and placeholder layout
- `benchmark.py` — fair A/B comparison (naive paragraph-paste vs this Skill) on
  the same paper
- `reproduce.py` — one-command end-to-end entry point
- `run.sh` — CLI wrapper

## Dependencies

- Python 3.8+ with `python-pptx` (see `requirements.txt`)
- poppler-utils (`pdftohtml`, `pdftotext`, `pdftoppm`)
- LibreOffice (`soffice`) for PDF/PNG previews

## Usage (end to end)

```bash
python3 reproduce.py paper.pdf --out deck/ --max-slides 14 [--template template.pptx]
# or step by step:
python3 parse_pdf.py paper.pdf --out structure.json
python3 draft_outline.py structure.json --out deck_spec.json --paper paper.pdf
python3 build_ppt.py deck_spec.json --out deck/ --paper paper.pdf --template template.pptx
```

Outputs (all under `deck/`): `deck.pptx` (editable), `evidence_map.json`
(slide → paper evidence + embed status), `figures/*.png` (crops), `deck.pdf`,
`previews/*.png`, `render.log`.

## Output schema

- `deck_spec.json` — `{meta, slides[{layout,title,bullets,figures,notes,evidence,sections}]}`;
  `figures` entries carry `kind/number/page/caption/type/region/result_role/cited_in`
- `evidence_map.json` — `{slides[{slide,title,figures[{embedded,png,…}],evidence,notes_present}]}`
- `deck.pptx` — editable; `previews/*.png` — rendered pages

## Method notes

1. **Evidence first**: each figure/table gets a page + region + type + citation
   cross-reference, so a slide's evidence is traceable, not remembered.
2. **Main-line extraction**: subsections inherit their top-level section's role,
   and one slide is built per top-level section, so the deck follows the paper's
   contribution rather than its table of contents.
3. **Real evidence on the page**: figure/table regions are cropped from the PDF
   and embedded with aspect ratio preserved.
4. **Render check**: LibreOffice → PDF, then pdftoppm → per-slide PNG previews.

## Limits (reported honestly)

- It does **not** redraw figures or beautify graphics (out of scope).
- Inline math is split from sentences by the layout parse; the deck spec keeps
  `plaintext_pages` so the agent re-merges exact numbers into bullets during
  refinement (the deterministic draft is a skeleton, not the final wording).
- Image-only figures are cropped as an image; if a crop fails, the slide keeps
  the caption + page reference and reports it in `evidence_map.json`.
- Encrypted PDFs fail at the parse step and are reported, not guessed.
- Bold table-header rows can occasionally be misread as headings; the draft
  filters common cases, and the agent should drop any remaining spurious slides.

## Self-test

```bash
./run.sh --selftest
python3 reproduce.py testdata/attention.pdf --out deck/
```
