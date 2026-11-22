---
name: scientific-pdf-structure-parser
description: >-
  Layout-aware scientific PDF parsing for agent reading tasks. Deterministically
  extracts reading-ordered text, section hierarchy, tables, figure captions,
  display equations and references from a scientific PDF, each element carrying
  page + bounding-box evidence. Use whenever a case asks the agent to read,
  parse, extract, translate, answer questions about, or structure a PDF document
  (multi-column papers, tables, formulas, references, scanned pages).
---

# Scientific PDF structure parser

A deterministic, poppler-based parser that turns a scientific PDF into a
structured, evidence-backed JSON document. It fixes the most common failures of
a bare LLM reading a PDF: wrong multi-column reading order, merged headings and
body, broken tables, dropped math, and unverifiable claims.

## When to use

Use this skill for every case whose task involves reading or parsing a PDF
document: text extraction, reading-order repair, section/heading recognition,
table reconstruction, formula extraction, figure/table caption listing,
reference extraction, question answering over the paper, or translation with
source evidence.

## Inputs

- `/input/case.json` — the case definition. It contains at least `case_id`,
  the task requirements, and the list of output fields (often under a key such
  as `output_contract`, `expected_outputs`, `outputs`, or `fields`) that the
  final `result.json` must include.
- `/input/task.md` — the task brief (when provided).
- The source PDF(s), whose path is given in `case.json` (or discoverable under
  `/input`).

## Workflow (follow in order)

1. **Read the case.** Open `/input/case.json`. Record `case_id` and every field
   the task requires you to return (the "contract"). If a field is ambiguous,
   keep the field name exactly as written and fill it with the best-supported
   value; never omit a contract field.

2. **Locate the PDF.** Find the PDF path from `case.json`. If a material is
   referenced but missing, record that as an uncertainty — do not invent content.

3. **Run the parser** (deterministic, no network):
   ```bash
   python3 /app/submission/parse_pdf.py "<PDF>" --out /app/work/structure.json
   ```
   (The script is self-contained, stdlib-only; it shells out to `pdftohtml -xml`
   and `pdftotext`, both from poppler-utils, which are preinstalled.)

4. **Answer the task using the structured output.** Read
   `/app/work/structure.json`. It contains:
   - `document.title`, `document.abstract`, `document.page_count`,
     `document.authors`, `document.affiliations`
   - `sections[]` with `heading`, `number`, `level`, `page`, `bbox`,
     `paragraphs[]` (each paragraph has `text`, `page`, `bbox`, and per-line
     `bbox`)
   - `tables[]` (`page`, `bbox`, `caption`, `markdown`, `rows`)
   - `figures[]` (`page`, `bbox`, `caption`)
   - `equations[]` (`page`, `bbox`, `text`, `number`)
   - `references[]` (`index`, `text`, `page`, `bbox`)
   - `headers_footers` (`headers[]`, `footers[]` — repeated running text/page numbers)
   - `plaintext_pages` (clean per-page text with inline numbers intact)
   - `uncertainty[]`, `page_map[]` (per-page blocks with kind/bbox)

   Prefer this structure over re-reading the raw PDF. When a case answer needs
   a specific fact, cite the `page` and `bbox` from the element you took it
   from, and quote the exact source text. **Populate every contract field from
   the parsed structure — do not leave a field empty or fill it with a generic
   summary when the parser has the evidence.**

5. **Write the result.** Create `/app/output/result.json` with:
   - `case_id` — from `case.json`
   - **every contract field** from the case, populated from the structure JSON
   - `status` — `"success"` | `"partial"` | `"failed"`
   - `sources` — a list of `{"page", "bbox", "quote"}` for the key conclusions
   - `uncertainty` — items you could not determine, with the reason
   - `change_log` — one line per substantive edit/decision
   Also write any editable artifacts (Markdown/HTML/tables) under `/app/output`.

6. **Record the gain (evidence).** Run
   ```bash
   python3 /app/submission/benchmark.py "<PDF>" --out /app/work/benchmark
   ```
   and copy its `gain` (structured elements + evidence coverage) into
   `result.json` under a `benchmark` field. This is the runnable A/B evidence
   that the parser adds structure and page/bbox traceability a raw read lacks.

## Rules (must follow)

- **Evidence first.** Every claim about the document must point back to a page
  (and, where possible, a `bbox`) and quote the source text. "未报告 / not
  reported" and "无法判断 / cannot determine" are valid answers; do not turn
  them into facts.
- **Never fabricate.** If the PDF has no text layer (scanned/image), report it
  via `uncertainty` and suggest OCR; do not invent a readable body. If a table
  is an image, say so instead of hallucinating cells.
- **Honest partial output.** If a field cannot be completed, fill what you can,
  mark `status: "partial"`, and explain in `uncertainty`.
- **Do not submit prepared answers.** The parser must actually run on the real
  case PDF; `result.json` must reflect that run.
- **Determinism.** Re-running on the same PDF must give the same structure.

## Self-check

Before finishing, verify: (1) `result.json` exists and is valid JSON;
(2) every contract field from `case.json` is present; (3) key conclusions have
a `page`/`bbox`/`quote` in `sources`; (4) unreadable/uncertain items are listed,
not guessed.

## Resource limits

The parser is one stdlib-only Python file and needs only poppler-utils. It runs
in well under the execution budget; no model requests are required for the
parsing itself (reserve them for the semantic task steps).
