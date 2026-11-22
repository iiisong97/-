---
name: academic-language-polish
description: >-
  Minimal-edit academic language polishing with deterministic meaning-preservation
  guardrails. Use when a case asks to polish, revise, proofread, or translate
  academic prose (journal paper, thesis, grant proposal, review response, or
  abstract). Produces a polished full text plus a sentence-level edit log
  (original → revised → type → reason), a terminology table, and a machine
  verification that numbers, units, citations, figure/table/equation references
  and hedges were preserved (claims were neither strengthened nor weakened).
---

# Academic language polish

Polish academic prose the way a careful human editor would: fix hard errors,
match the register, unify terminology, and — most importantly — **do not change
what the author claims**. A bare LLM tends to "improve" a sentence by rewriting
it, silently dropping hedges ("may" → ""), editing numbers, losing citation
markers, or renaming figures. This skill forbids that and enforces it with a
deterministic checker.

## When to use

Use whenever the case asks you to polish, revise, proofread, copyedit, or
translate academic text, and whenever it asks for a terminology table, a
bilingual comparison, or a change list. **Do not use** (and do not rewrite) when
the task is a pure content question or a literature search.

## Inputs

- `/input/case.json` — `case_id`, the source text (inline or a file path), the
  target genre/audience (journal paper / thesis / grant proposal / review
  response / abstract), the style/format constraints, and the list of output
  fields (the "contract", often under `output_contract` / `expected_outputs` /
  `outputs` / `fields`) that `result.json` must include.
- `/input/task.md` — the task brief (when provided).

## Workflow (follow in order)

1. **Read the case.** Record `case_id`, the source text, the target genre, and
   every contract field. Locate the source file if it is given as a path; if a
   referenced material is missing, record that in `uncertainty` — do not invent
   it.

2. **Build a terminology table first.** Before editing, scan the source and list
   the terms that matter: defined abbreviations (`X (Y)`), repeated technical
   nouns, symbols with units. For each term decide one canonical form
   (case, hyphenation, first-use expansion). This table drives step 4.

3. **Edit sentence by sentence, minimally.** For each sentence:
   - Fix only hard errors: subject–verb agreement, tense/aspect, articles,
     prepositions, number, dangling modifiers, punctuation, run-on sentences.
   - Adjust register to the target genre; remove colloquial, promotional, or
     absolute wording, and fix person/voice misuse.
   - **Preserve exactly**: numbers and units, citation markers `[n]`, figure/
     table/equation references, negation scope, conditionals, quantifiers, and
     every hedge (`may`, `might`, `could`, `suggest`, `indicate`, `likely`,
     `approximately`, 可能/表明/提示/初步 …).
   - **Do not strengthen or weaken a claim.** If the author wrote "suggests",
     do not write "demonstrates". If in doubt whether an edit changes meaning,
     leave the sentence and record it as a human-confirmation item.

4. **Sweep terminology consistency.** After editing, re-read the polished text
   and make every occurrence of a term match the table from step 2 (fix
   cross-section drift, synonym mixing, inconsistent hyphenation/case).

5. **Run the guardrail checker** (deterministic, no network):
   ```bash
   python3 /app/submission/preservation_check.py /app/work/original.txt /app/work/polished.txt --out /app/work/preservation.json
   ```
   (Write the original and polished texts to those files first.) Read
   `/app/work/preservation.json`:
   - `protected.*.preserved=false` → the edit lost a number/unit/citation/ref:
     restore it.
   - `hedges_missing` → a hedge disappeared: restore the original strength.
   - `claim_strength` → a strong verb was swapped for a weak one (weakening) or
     vice versa (strengthening): restore the original verb strength.
   - `negation_lost` → the source negates but the polished text does not:
     restore the negation scope.
   - `quantifiers_dropped` → a strict quantifier (only / at least / at most /
     all / none …) was dropped: restore it.
   - `sentence_edit[].flag == heavy_rewrite` → the sentence changed too much:
     re-edit with a smaller change.
   Iterate until the report is clean.

6. **Do a read-back check.** Read the polished sentence and the original side by
   side. Ask: "does the polished sentence still say exactly what the author
   said?" For translation tasks, back-translate the polished target into the
   source language and check meaning.

7. **Write the result.** Create `/app/output/result.json` with:
   - `case_id`
   - **every contract field** from `case.json`
   - the polished full text (editable, same format as input: plain text /
     Markdown / LaTeX fragment)
   - `edits[]` — one entry per change: `{index, original, revised, type, reason}`
     (type ∈ grammar / syntax / collocation / punctuation / register /
     terminology / clarity; reason must let a third party judge the change)
   - `terminology[]` — the table from step 2
   - `preservation` — the checker report
   - `sources` — where each number/citation/claim in the polished text comes from
   - `uncertainty` — items that need human confirmation, material gaps
   - `change_log` — one line per substantive decision
   Also write any editable artifacts (e.g. `.docx`/`.md`) under `/app/output`.

8. **Record the gain (evidence).** Run
   ```bash
   python3 /app/submission/benchmark.py --out /app/work/benchmark
   ```
   and copy its `gain` (check categories + violations detectable) into
   `result.json` under a `benchmark` field. This is the runnable A/B evidence
   that the guardrails catch meaning changes a bare LLM cannot detect.

## Rules (must follow)

- **Minimal edit.** Fix the error; do not rewrite the sentence. A changed word
  is only justified if it removes an error, fixes register, or unifies a term.
- **Never change claim strength.** Preserve hedges, quantifiers, negation scope,
  conditionals, numbers, units, citations, and figure/table/equation references.
- **Every edit is logged and reversible.** No silent edits.
- **Honest uncertainty.** Ambiguous meaning, conflicting materials, or
  terminology the case does not define go into `uncertainty` as
  human-confirmation items — never silently resolved.
- **No fabrication.** Do not invent facts, citations, or results that are not in
  the source. Do not submit prepared answers: the skill must run on the real case.
- **Determinism.** Re-running on the same input must give the same edits.

## Self-check

Before finishing, verify: (1) `result.json` is valid and contains every contract
field; (2) `preservation` has no `preserved=false` and no missing hedges; (3) no
`heavy_rewrite` flags remain; (4) every edit has original/revised/type/reason;
(5) uncertain items are listed, not guessed.

## Resource limits

The checker is one stdlib-only Python file. Polish itself is an LLM task; budget
model requests for the editing and the read-back check, not for the guardrails.
