---
name: paper-to-academic-ppt
description: >-
  Turn a scientific paper into an editable academic slide deck with a coherent
  main line, page-level evidence mapping, real figure/table crops embedded in the
  slides, speaker notes, and rendered previews. Use when a case asks to organize
  a paper or research material into a presentation (PPT/PPTX) for a talk, defense
  or group meeting, under a given template, audience, duration and slide-count
  constraint. Extracts the paper's problem -> method -> results -> conclusion
  narrative instead of pasting paragraphs in order, and maps every slide back to
  the paper's figures/tables/sections/pages.
---

# Paper → academic PPT

Convert a paper into slides the way a researcher would: first decide the story,
then decide what each page must claim, then attach the real figure/table, then
write what to say out loud. The deck must be editable, template-compliant,
renderable and checkable — not a list of pasted paragraphs.

## When to use

Use when the case asks to build a presentation (PPT/PPTX) from a paper or
research material. Do **not** use for literature summaries that are not
presentations, figure redrawing/beautification, or writing polishing (separate
tasks).

## Inputs

- `/input/case.json` — `case_id`, the paper PDF path, the template PPTX (when the
  case provides a master/layout template or a starting deck), the audience /
  duration / max-slide-count, and the output fields (the contract).
- `/input/task.md` — the task brief (when provided).

## Workflow (follow in order)

1. **Read the case.** Record `case_id`, the PDF, the template, the audience, the
   time budget and the slide-count limit, and every contract field. If the
   template or paper is referenced but missing, record it in `uncertainty`.

2. **Parse the paper for evidence** (deterministic):
   ```bash
   python3 /app/submission/parse_pdf.py "<PAPER.pdf>" --out /app/work/structure.json
   ```
   This yields sections, paragraphs, figures and tables (each with `number`,
   `type` = schematic/data/table, `page`, image `region`, `cited_in`/`cited_pages`
   cross-references, and table `result_role` = comparison_own_vs_baseline /
   supporting_data), plus `plaintext_pages` for re-merging inline math.

3. **Draft the main line** (deterministic skeleton):
   ```bash
   python3 /app/submission/draft_outline.py /app/work/structure.json \
       --out /app/work/deck_spec.json --paper "<PAPER.pdf>" --max-slides N
   ```
   `N` = the case's slide limit (default 14). This produces a problem → background
   → method → results → conclusion skeleton with figures/tables attached to the
   slide that cites them, schematic vs data labels, and a 本文 vs 基线 warning on
   comparison tables.

4. **Refine the deck spec (the actual thinking).** Edit `/app/work/deck_spec.json`:
   - **Re-merge inline math.** The draft's bullets come from the layout parse, so
     sentences that contained inline formulas are split (e.g. "in Table" + "2",
     "BLEU score of" + "28.4"). Use `structure.json → plaintext_pages` to recover
     the original sentence and put the exact number/unit back into the bullet.
   - **One claim per page**; the title states the claim, the bullets carry the
     supporting numbers/units (unchanged from the paper).
   - **Label 本文 vs 基线.** On result/comparison slides, mark which row is the
     paper's own result and which are baselines/others; never present a baseline
     or a schematic as the paper's own data.
   - **Do not move evidence.** Keep each figure/table on the slide that discusses
     it (the draft already aligns `cited_in`); if you move one, update its
     `evidence` page/ref.
   - **Speaker notes add value.** Write transition, emphasis (the key number),
     and backup evidence to cite if asked — not a repeat of the slide text.

5. **Build the deck** (editable PPTX + embedded figures + previews):
   ```bash
   python3 /app/submission/build_ppt.py /app/work/deck_spec.json \
       --out /app/output/ppt --paper "<PAPER.pdf>" [--template /input/TEMPLATE.pptx]
   ```
   If the case provides a template, pass it with `--template` (its slide size and
   placeholder layout are honoured; the default 16:9 size is only used when no
   template is given). This writes:
   - `deck.pptx` (editable; figure/table regions are cropped from the PDF and
     embedded with aspect ratio preserved)
   - `evidence_map.json` (slide → paper evidence + embed status)
   - `golden_standard.json` (per-page golden standard: claim + evidence + the
     numbers/units/figure-refs a reviewer checks against the paper)
   - `previews/*.png`, `deck.pdf`, `figures/*.png`, `render.log`

6. **Record the verifiable gain** (fair A/B on the same paper):
   ```bash
   python3 /app/submission/benchmark.py "<PAPER.pdf>" --out /app/work --max-slides N
   ```
   This produces `/app/work/benchmark.json` comparing a naive paragraph-paste
   baseline with this Skill on evidence coverage, figure coverage, notes coverage,
   main-line order and overflow risk — same input, same tools, same slide limit.

7. **Check rendering.** Read `render.log` and open one preview. If text overflows
   or a slide is broken, shorten the bullets / split the slide and rebuild. If
   LibreOffice is missing, report the preview gap in `uncertainty`.

8. **Write the result.** Create `/app/output/result.json` with:
   - `case_id` and **every contract field** from `case.json`
   - the deck spec (slide titles + claims + figure refs) and the `deck.pptx` path
   - `evidence` — slide → paper figure/table/section/page/quote mapping
   - `golden_standard` — the per-page claim/evidence/checks reference (from
     `golden_standard.json`)
   - `benchmark` — the A/B comparison from `benchmark.json`
   - `sources` — where each key claim comes from
   - `uncertainty` — image-only figures, equation-as-image, encrypted PDF, missing
     template fonts, slide-count overflow, anything needing human confirmation
   - `change_log` — one line per substantive decision

## Rules (must follow)

- **Main line, not paragraph order.** The deck tells the paper's own contribution
  (problem → method → evidence → conclusion), not its section order.
- **One claim per page.** Keep bullets short; the notes carry the detail. Respect
  the slide-count limit.
- **Evidence before everything.** Every figure/table/number on a slide must map to
  the paper's figure/table/section/page. Never relabel, renumber, or present a
  schematic as data or a baseline as the paper's own result.
- **Do not alter facts.** Numbers, units, method names and conclusions stay
  exactly as in the paper; re-merge inline math from `plaintext_pages`.
- **Honest uncertainty.** Image-only figures, unextractable tables, encrypted
  PDFs and missing template fonts go into `uncertainty`, not into a made-up
  slide. If a figure crop fails, keep the caption + page reference and say so.
- **No fabricated answers.** The deck must be generated from the real case PDF;
  do not submit prepared slides or invented scores.

## Self-check

Before finishing: (1) `deck.pptx` opens and every slide has a title and speaker
notes; (2) `previews/*.png` exist and no slide overflows; (3) `evidence_map.json`
covers every slide and every embedded figure reports `embedded: true`; (4)
`result.json` contains every contract field; (5) every figure/table reference and
number matches the paper.

## Resource limits

The scripts are stdlib + `python-pptx` (declared in `requirements.txt`) +
poppler-utils + LibreOffice. Parsing, drafting, cropping and rendering are
deterministic; spend the model budget on claim refinement and speaker notes.
