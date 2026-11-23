---
name: literature-notes-extractor
description: >-
  Turns a scientific paper into section-aligned, field-complete, anchor-linked
  structured notes for agent reading tasks. Produces a paper card (research
  question, data, methods, findings, conclusions, limitations, preconditions),
  per-section notes that follow the paper's own headings and argument order,
  and searchable knowledge points (concepts/variables/methods/conclusions),
  every note carrying a page/paragraph/quote anchor back to the source. Use
  whenever a case asks to summarise, take structured notes on, or build a
  reusable card/knowledge base from a paper.
---

# Literature notes extractor

A deterministic, evidence-first skill that turns a paper into reusable
structured notes. It enforces the four qualities the task demands: 对得上
(section-aligned), 留得住 (field-complete), 找得回 (anchor-traceable), 用得上
(reusable). Field definitions and anchor format are in `note_schema.md`.

## When to use

Use this skill for every case that asks to summarise a paper, take structured
notes, build a paper card, extract knowledge points, or create a searchable
reading base. Do NOT use it for plain abstract rewriting or translation.

## Inputs

- `/input/case.json` — the case definition. Contains `case_id`, the task
  requirements, the list of output fields (often under `output_contract`,
  `expected_outputs`, `outputs`, or `fields`), and the path to the source
  material.
- `/input/task.md` — the task brief (when provided).
- The source PDF(s), whose path is given in `case.json` (or discoverable under
  `/input`).

## Workflow (follow in order)

1. **Read the case.** Open `/input/case.json`. Record `case_id` and every
   contract field; keep field names exactly as written and never omit one. If an
   `interface-example` is provided, follow its field names/serialization exactly.

2. **Parse the paper.** Run (deterministic, no network; poppler-utils
   preinstalled):
   ```bash
   python3 /app/submission/parse_pdf.py "<PDF>" --out /app/work/structure.json
   ```
   This yields `document` (title/authors/abstract), `sections[]`
   (heading/number/level/page/bbox/paragraphs), `plaintext_pages` (clean
   per-page text), `tables[]`, `figures[]`, `references[]`, `uncertainty[]`.
   Use it — do not re-read the raw PDF.

3. **Build the paper card (留得住).** From the abstract, introduction,
   methods, results and conclusion, fill `paper_card` per `note_schema.md`:
   `research_question`, `data`, `methods`, `key_findings`, `conclusions`,
   `limitations`, `preconditions`. Record the numbers, units, dataset sizes,
   and the conditions under which each conclusion holds (e.g. "on WMT 2014
   En-De", "assuming X"). If a field is not reported in the paper, write
   "未报告 / not reported" and add an `uncertainty` entry — do not invent it.

4. **Write per-section notes (对得上).** For each section in
   `structure.json`'s `sections[]` that carries real content (skip the abstract
   preamble and reference list), create one `section_notes[]` entry:
   - `section` = the paper's own heading text (number stripped), `number`,
     `level`, `page`;
   - `purpose` / `method` / `result` / `conclusion` = what this section does,
     how, what it finds, what it concludes (write "本节无……" when a slot does
     not apply);
   - `transition` = how it connects to the previous/next section;
   - `anchors[]` = `page` (required) + `paragraph` + verbatim `quote` taken from
     that section's paragraphs.
   Keep the section order identical to the paper — do not reorder into a generic
   template.

5. **Extract knowledge points (用得上).** Pull important concepts, variables,
   methods and conclusions into `knowledge_points[]`: `term`, `type`
   (`concept`/`variable`/`method`/`conclusion`), `definition` (keep the
   abbreviation's first-occurrence form), `synonyms`, `id`
   (`kp-<sha1(term)[:16]>`), and `anchors[]`. Deduplicate: one entry per term;
   if two places define a term differently, keep the more specific one and note
   the conflict in `uncertainty`.

6. **Write the result.** Create `/app/output/result.json` per `note_schema.md`:
   `schema: "lit-notes/v1"`, `case_id`, `paper_card`, `section_notes[]`,
   `knowledge_points[]`, `status` (`success`|`partial`|`failed`), `sources`
   (page+quote for key conclusions), `uncertainty` (not reported / cannot
   determine / conflict, each with a reason), `change_log`. Copy the case's
   `output_contract` field names exactly; if it names a different container,
   put the same objects under that key.

7. **Run the guardrail checker.** Validate structure and anchors, and verify
   every quote actually appears in the paper:
   ```bash
   python3 /app/submission/notes_check.py /app/output/result.json \
     --structure /app/work/structure.json --out /app/work/check.json
   ```
   Read `/app/work/check.json`. Fix every flag (missing card field, missing
   section slot, anchor without page, quote not found on that page, duplicate
   knowledge point) and re-check until `issues == 0`.

## Rules (must follow)

- **Evidence first.** Every note and knowledge point must carry a page (and
  quote where possible) taken from the parsed paper. "未报告 / not reported" and
  "无法判断 / cannot determine" are valid; do not state them as facts.
- **Section order is the paper's order.** Do not impose a generic summary
  template; `section_notes` must mirror the paper's headings and sequence.
- **Keep the preconditions.** Record the conditions, data scope and assumptions
  that make each finding valid; do not generalise a conditioned result.
- **Never fabricate.** Do not invent numbers, quotes, datasets, or source
  metadata. If the PDF has no text layer, report it in `uncertainty`.
- **Honest partial output.** If a field cannot be completed, fill what you can,
  set `status: "partial"`, explain in `uncertainty`.
- **Determinism.** Re-running on the same PDF must give the same notes and ids.

## Self-check

Before finishing, verify: (1) `result.json` is valid JSON and `issues == 0` in
`/app/work/check.json`; (2) every contract field is present; (3) `paper_card`
has all seven fields; (4) each section note has heading + four slots + anchor;
(5) each anchor quote is found on its page (the checker verifies this against
the paper); (6) uncertain/conflicting items are listed, not guessed.

## Resource limits

`parse_pdf.py` and `notes_check.py` are stdlib-only (poppler-utils only for
parsing). Parsing and checking cost no model requests; reserve the 64-request /
900 s budget for the semantic summarisation and anchor-binding steps.
