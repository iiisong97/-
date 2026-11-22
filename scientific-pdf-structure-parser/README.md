# scientific-pdf-structure-parser

A layout-aware, deterministic parser for scientific PDFs. It turns a PDF into a
structured, evidence-backed JSON document so an agent can read, answer,
translate and check a paper without the usual multi-column / table / math
errors of naive text extraction.

## What it solves

| Failure of naive PDF reading | What this skill does |
|---|---|
| Multi-column text read across columns | Detects columns per page and emits text in reading order |
| Headings merged into body text | Separates headings from body by typography (bold + size relative to body) |
| Tables collapsed into scrambled text | Detects aligned grids and reconstructs Markdown tables |
| Math dropped or mangled | Detects math-font regions and records display equations separately |
| No way to verify a claim | Every element carries `page` + `bbox` and source text |
| Scanned pages silently guessed | Flags no-text-layer pages as uncertainty instead of hallucinating |

## Dependencies

- Python 3.8+ (standard library only)
- poppler-utils (`pdftohtml`, `pdftotext`) — preinstalled in the runtime

## Usage

```bash
python3 parse_pdf.py INPUT.pdf --out result.json --txt fulltext.txt
# or
./run.sh INPUT.pdf --out result.json
```

## Output schema

```jsonc
{
  "schema": "paper2arm/pdf-structure/v1",
  "status": "success | partial | failed",
  "document": {"page_count": N, "title": "...", "abstract": "..."},
  "sections": [{"number": "3.2.1", "heading": "...", "level": 3,
                "page": 4, "bbox": [l,t,w,h],
                "paragraphs": [{"text": "...", "page": 4, "bbox": [...],
                                "lines": [{"text": "...", "bbox": [...]}]}]}],
  "tables": [{"page": 5, "bbox": [...], "caption": "...", "markdown": "|...|"}],
  "figures": [{"page": 3, "bbox": [...], "caption": "Figure 1: ..."}],
  "equations": [{"page": 4, "bbox": [...], "text": "...", "number": "1"}],
  "references": [{"index": 1, "text": "...", "page": 15, "bbox": [...]}],
  "uncertainty": [{"page": N, "type": "...", "note": "..."}],
  "page_map": {"1": {"columns": [...], "blocks": [...]}}
}
```

Coordinates are in `pdftohtml -zoom 1.5` space (top-left origin, px).

## Method notes

1. Text lines and their per-line font (size, family, weight) come from
   `pdftohtml -xml`, which exposes the same geometry a reader sees.
2. Font specs are merged globally because poppler declares them per page.
3. Body font size is estimated as the median regular-weight line size; headings
   are then detected as bold-or-larger lines relative to that baseline, plus
   numbered/keyword patterns.
4. Columns are found by projecting text and locating a low-density vertical
   gutter; each block is assigned to a column and ordered top-to-bottom within
   columns, left-to-right across columns.
5. Tables are aligned-line grids; display equations are centered/numbered
   math-font regions; inline math stays in the body.

## Limits (reported honestly, not silently)

- Scanned/image PDFs have no text layer: reported via `uncertainty`, not guessed.
- Image-only tables are reported as such (no cells are hallucinated).
- Very unusual layouts (poster-style) may need per-case tweaks.

## Self-test

```bash
./run.sh --selftest          # import + CLI check (no PDF)
./run.sh sample.pdf --out sample.json   # real run
```
