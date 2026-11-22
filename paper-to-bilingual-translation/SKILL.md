---
name: paper-to-bilingual-translation
description: >-
  Translate a scientific paper (or a specified section/paragraph range) into a
  verifiable bilingual result. Extracts a domain glossary and enforces it, builds
  a fixed paragraph-level alignment skeleton (段号 ↔ 原文 ↔ 页码), translates
  segment-by-segment with context, then runs a deterministic verification that
  flags any dropped numbers/units/formulas/citations/negation and any
  inconsistent term translation. Use when a case asks to translate a paper,
  section, abstract or figure/table captions, or to produce a bilingual
  aligned document with evidence back to the source. Not for summaries,
  paraphrases, or writing-polish tasks.
---

# Paper → bilingual translation

Translate scientific text the way a careful translator does: fix the terminology
first, translate paragraph by paragraph with context, keep every number and
citation intact, and then re-check the facts against the source — instead of
dumping a fluent-but-unverifiable rewrite.

## When to use

Use when the case asks to translate a paper/section/abstract/captions into a
bilingual result, or to answer a reading question *with* a translation and its
source. Do **not** use for summarisation, paraphrasing, or non-translation
reading tasks.

## Inputs

- `/input/case.json` — `case_id`, the paper PDF, the target language, the
  section/paragraph range to translate, and the output fields (the contract).
- `/input/task.md` — the task brief (when provided).

## Workflow (follow in order)

1. **Read the case.** Record `case_id`, the PDF path, the target language, the
   requested range (whole paper / abstract / a section / figure captions), and
   every contract field. If the paper or range is missing, record it in
   `uncertainty`.

2. **Parse the paper** (deterministic evidence base):
   ```bash
   python3 /app/submission/parse_pdf.py "<PAPER.pdf>" --out /app/work/structure.json
   ```
   This gives sections, paragraphs, figure/table captions, and `plaintext_pages`
   (clean page text with inline numbers intact).

3. **Extract the glossary** (deterministic candidates):
   ```bash
   python3 /app/submission/extract_terms.py /app/work/structure.json --out /app/work/glossary.json
   ```
   This yields candidate acronyms and repeated title-case phrases.

4. **Lock the terminology (the actual thinking).** Edit `/app/work/glossary.json`:
   - For every candidate term, set `translation` to the Chinese term, **or**
     explicitly keep the English term (e.g. proper nouns, "BLEU", "Transformer")
     and write the keep-reason in a note.
   - Decide ONE translation per concept; do not allow two translations of the
     same term. This table will be executed and verified, not merely referenced.

5. **Build the alignment skeleton**:
   ```bash
   python3 /app/submission/segment.py /app/work/structure.json --out /app/work/units.json
   ```
   Every paragraph/heading/caption becomes a unit with a fixed `para_id`, `page`
   and `section`. Fill the skeleton in place — this guarantees no paragraph is
   missed, duplicated or misplaced (段落全).

6. **Translate unit by unit.** For each unit in `/app/work/units.json`:
   - Use the **locked glossary** for every term occurrence; keep the term's
     locked translation identical everywhere (术语稳).
   - Re-merge split sentences from `structure.json → plaintext_pages` when the
     XML layout broke a sentence across inline formulas (e.g. "score of ." →
     "score of 28.4").
   - Preserve **exactly**: numbers and units, `[N]` citation markers, "Figure N" /
     "Table N" / "Equation (N)" references, and negation/limitation wording
     (关系准). In Chinese, render negation with 不/非/无/未/不能/无法 and
     limitation with 仅/除非/如果/在…条件下.
   - Put the translation in `translation`; add `notes` (译法依据, e.g. why a
     term was kept or why a sentence was restructured); set `uncertain: true`
     and add an `uncertainty_note` when a passage is genuinely ambiguous —
     never gloss over it (可核验).

7. **Verify deterministically**:
   ```bash
   python3 /app/submission/verify_translation.py /app/work/units.json \
       --glossary /app/work/glossary.json --out /app/work/verification.json
   ```
   Read `verification.json`; it lists dropped numbers/citations/figure-refs,
   dropped technical units (nm/Hz/GB/BLEU/GPU…), missing negation markers, and
   inconsistent terms (with the para_ids of each occurrence). For each flag:
   fix the translation, or record the item as "intentionally kept" with a
   reason (do not silently ignore).

8. **Write the result.** Create `/app/output/result.json` with:
   - `case_id` and **every contract field** from `case.json`
   - `translation` — the filled `units` (paragraph-level bilingual alignment:
     para_id, page, section, source, translation, notes, uncertain)
   - `glossary` — the locked term table with occurrences + consistency
   - `verification` — the verification report
   - `sources` — where each claim/paragraph comes from (page + section)
   - `uncertainty` — image-only formulas, scanned/OCR pages, ambiguous
     referents, untranslatable proper nouns, anything needing human confirmation
   - `change_log` — one line per substantive decision (term locked, sentence
     re-merged, flagged item fixed or kept)

9. **Record the gain (evidence).** Run
   ```bash
   python3 /app/submission/benchmark.py "<PAPER.pdf>" --out /app/work/benchmark
   ```
   and copy its `gain` (aligned units, glossary terms, verification checks,
   protected tokens detectable) into `result.json` under a `benchmark` field.
   This is the runnable A/B evidence that the Skill is "more complete and more
   verifiable" than a bare Agent — include it, do not just claim it.

## Rules (must follow)

- **It is a translation, not a summary or rewrite.** Every source paragraph must
  map to a target paragraph with the same content; do not drop or merge
  paragraphs.
- **Numbers, units, formulas, citation numbers and figure/table references stay
  exactly as in the source.** Re-merge inline math from `plaintext_pages`.
- **The glossary is executed.** The locked translation appears verbatim at every
  occurrence; verification flags any drift.
- **Negation and limitation are marked, not softened.** 不/非/无/未 and 仅/除非/
  如果 must appear where the source has them.
- **Honest uncertainty.** Image-only equations, OCR'd scans, ambiguous pronouns
  and mixed-language passages go into `uncertainty`, not into a confident
  translation. A partial translation states its limits.
- **No fabricated answers.** Translate the real PDF; never submit prepared
  translations or invented scores/logs.

## Self-check

Before finishing: (1) every unit has a `translation` (or an explicit skip reason);
(2) `verification.json` shows no unexplained missing numbers/citations/negation;
(3) every locked glossary term is consistent; (4) `result.json` contains every
contract field and case_id; (5) each uncertain passage is marked.

## Resource limits

The scripts are stdlib + poppler-utils. Parsing, glossary extraction, segmentation
and verification are deterministic; spend the model budget on locking terms and
translating/verifying the units.
