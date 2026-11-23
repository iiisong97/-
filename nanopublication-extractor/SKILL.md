---
name: nanopublication-extractor
description: >-
  Extracts atomic, evidence-bound nanopublications from a scientific paper for
  agent reading tasks. Splits each key conclusion into single independently
  verifiable assertions, binds each to a minimal source quote with page/bbox
  location, records subject-predicate-object, provenance (paper/authors/year/
  version/identifiers), confidence basis and a stable id, and exports a
  machine-readable nanopub/v1 JSON. Use whenever a case asks to read a paper
  and produce assertions, triples, knowledge units, or structured evidence
  extraction (Nanopublication, knowledge-graph, claim extraction, QA with
  sources).
---

# Nanopublication extractor

A deterministic, evidence-first skill that turns a paper's key conclusions into
Nanopublication-structured assertions. It enforces the four qualities the task
demands: 拆得细 (atomic), 对得上 (evidence-aligned), 追得回 (traceable), 读得懂
(machine-readable). The field definitions and controlled predicate vocabulary
are in `nanopub_schema.md`.

## When to use

Use this skill for every case that asks to read a paper and return assertions,
triples, knowledge units, structured extraction, or QA-with-sources. Do NOT use
it for plain summarisation or translation.

## Inputs

- `/input/case.json` — the case definition. Contains `case_id`, the task
  requirements, the list of output fields (often under a key such as
  `output_contract`, `expected_outputs`, `outputs`, or `fields`), and the path
  to the source material.
- `/input/task.md` — the task brief (when provided).
- The source PDF(s), whose path is given in `case.json` (or discoverable under
  `/input`).

## Workflow (follow in order)

1. **Read the case.** Open `/input/case.json`. Record `case_id` and every field
   the task requires you to return (the "contract"). Keep each field name
   exactly as written; never omit a contract field. If the case provides an
   `interface-example`, follow its field names and serialization exactly.

2. **Locate and parse the paper.** Find the PDF path from `case.json`, then run
   (deterministic, no network; needs poppler-utils which is preinstalled):
   ```bash
   python3 /app/submission/parse_pdf.py "<PDF>" --out /app/work/structure.json
   ```
   This yields `document` (title/authors/abstract/page_count), `sections[]`
   (heading/level/page/bbox/paragraphs), `references[]`, `tables[]`, `figures[]`,
   `plaintext_pages` (clean per-page text), `uncertainty[]`. Use it — do not
   re-read the raw PDF.

3. **Select the key conclusions.** Focus on the abstract, introduction's
   contribution list, results/discussion, and conclusion. Skip the reference
   list and acknowledgements. Aim for the paper's main claims, not every
   sentence: for a typical paper this is 10–30 assertions.

4. **Split each conclusion into atomic assertions (拆得细).** One assertion =
   one predicate = one independently true/false proposition.
   - Break compound and causal sentences into separate assertions.
   - Preserve conditionals, quantifiers, scope and comparison direction
     ("only", "at least", "in the WMT 2014 setting", "A outperforms B") in
     `assertion.text` or `condition`.
   - Copy numbers, units, method names and entities verbatim — never round or
     paraphrase them.
   - Never put a whole paragraph into one `assertion.text`.

5. **Bind evidence to each assertion (对得上).** For each assertion, quote the
   MINIMAL sufficient fragment that supports it (`evidence.quote`), and record
   `evidence.location` (`page` required; `section`/`bbox` when available) from
   the element in `structure.json` you took it from. Classify the support:
   - `confidence.level = "direct"` — the quote states the claim itself;
   - `"indirect"` — the claim is inferred from the quote (say how in `basis`);
   - `"conflicting"` — two parts of the paper disagree (quote both, explain).

6. **Build the triple and provenance (追得回).**
   - `assertion.subject` = the entity the claim is about; `assertion.predicate`
     = one term from the controlled vocabulary in `nanopub_schema.md`;
     `assertion.object` = the value/entity. Never reverse the direction.
   - `provenance` = paper title, authors, year, version, identifiers (DOI/arXiv)
     from `structure.json`'s `document`/front matter; keep it consistent with
     the top-level `paper` object.
   - `id` = stable identifier. Compute it deterministically, e.g.
     `sha1(subject + "|" + predicate + "|" + object + "|" + paper_title)[:16]`,
     prefixed `np-`. The same assertion must get the same id on every run.

7. **Write the result.** Create `/app/output/result.json` following
   `nanopub_schema.md`:
   - `schema: "nanopub/v1"`, `case_id`, `paper{...}`,
     `nanopublications[]` (each with `id`, `assertion`, `condition`, `evidence`,
     `confidence`, `provenance`),
   - `status` (`success`|`partial`|`failed`),
   - `sources` (page+quote for the key conclusions),
   - `uncertainty` (not reported / cannot determine / conflict, each with a
     reason — never turn them into facts),
   - `change_log` (one line per substantive decision).
   Also copy the exact field names from the case's `output_contract`; if the
   contract names a different container (e.g. `assertions`, `claims`), put the
   same per-assertion objects under that key instead of `nanopublications`.

8. **Run the guardrail checker.** After writing, validate:
   ```bash
   python3 /app/submission/nanopub_check.py /app/output/result.json --out /app/work/check.json
   ```
   Read `/app/work/check.json`. Fix every flag (missing field, non-atomic
   assertion, predicate outside the controlled vocabulary, evidence quote
   missing the assertion's numbers, missing provenance/id) and re-check until
   `issues == 0`.

## Rules (must follow)

- **Evidence first.** Every assertion must point to a page (and bbox where
  possible) and quote the source verbatim. "未报告 / not reported" and "无法判断
  / cannot determine" are valid outputs; do not state them as facts.
- **Never fabricate.** Do not invent numbers, subjects, relations, evidence
  quotes, or source metadata. If the PDF has no text layer, report it in
  `uncertainty`; do not invent a body.
- **Direction and scope are preserved.** Do not reverse a comparison, drop a
  hedge, quantifier, or condition, or turn an indirect inference into a direct
  claim.
- **Honest partial output.** If a field cannot be completed, fill what you can,
  set `status: "partial"`, and explain in `uncertainty`.
- **Do not submit prepared answers.** The parser and checker must actually run
  on the real case PDF; `result.json` must reflect that run.
- **Determinism.** Re-running on the same PDF must give the same assertions and
  ids.

## Self-check

Before finishing, verify: (1) `result.json` is valid JSON and `issues == 0` in
`/app/work/check.json`; (2) every contract field from `case.json` is present;
(3) each assertion has subject/predicate/object, evidence quote+page,
provenance, confidence and id; (4) numbers in each assertion appear in its
evidence quote; (5) uncertain/conflicting items are listed, not guessed.

## Resource limits

`parse_pdf.py` and `nanopub_check.py` are stdlib-only (poppler-utils only for
parsing). Parsing and checking cost no model requests; reserve the 64-request /
900 s budget for the semantic splitting and evidence-binding steps.
