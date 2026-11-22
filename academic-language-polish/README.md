# academic-language-polish

A minimal-edit academic polishing skill with deterministic meaning-preservation
guardrails. It targets the single highest-risk failure of LLM copyediting: a
"polish" that silently strengthens a claim, drops a hedge, edits a number, or
loses a citation.

## What it solves

| Failure of a bare LLM polish | What this skill does |
|---|---|
| Hedge dropped ("may suggest" → "demonstrate") | Deterministic hedge-presence check on the polished output |
| Strong verb swapped for weak (or weak → strong) | Claim-strength verb-swap check (strengthening AND weakening) |
| Negation scope lost | Negation-presence check (EN + 中文) |
| Strict quantifier dropped ("only"/"at least"/"all") | Quantifier-survival check |
| Number / unit edited | Number+unit extraction and survival check |
| Citation `[n]` lost | Citation-marker survival check |
| "Figure 3" renamed or dropped | Figure/table/equation reference survival check |
| Whole sentence rewritten (meaning drift) | Per-sentence edit-ratio flag for >55% rewrite |
| Term drifts across sections ("Self-attention" vs "self attention") | Case/spelling variant detector |
| No trace of what changed | Every edit logged as original → revised → type → reason |

## Files

- `SKILL.md` — the workflow the harness agent follows
- `preservation_check.py` — deterministic guardrail checker (stdlib-only)
- `benchmark.py` — A/B of the guardrails vs a bare LLM (run evidence)
- `run.sh` — entry point

## Dependencies

- Python 3.8+ (standard library only). No pip packages, no network.

## Usage

```bash
# After producing polished.txt from original.txt:
python3 preservation_check.py original.txt polished.txt --out preservation.json
# or
./run.sh preservation original.txt polished.txt
```

## Method notes

1. **Terminology table first**: the agent fixes the canonical form of each term
   before editing, then sweeps the polished text for consistency.
2. **Sentence-level minimal edit**: fix only hard errors and register; a changed
   word must be justified.
3. **Guardrails**: `preservation_check.py` re-extracts protected tokens and
   hedges from the original and verifies they survive (substring match on
   normalized text), and computes a per-sentence SequenceMatcher ratio to flag
   heavy rewrites.
4. **Read-back**: the polished sentence is re-read against the original to catch
   meaning drift the checker cannot see.

## Limits (reported honestly)

- The checker is lexical, not semantic: it catches missing tokens/hedges, but a
  subtle synonym swap that keeps all tokens still needs the read-back step.
- It is tuned for English + Chinese scientific prose; other languages need the
  hedge list extended.
- Sentence alignment is greedy best-match; heavily reordered multi-sentence
  paragraphs may be mis-flagged and must be reviewed by the agent.

## Self-test

```bash
./run.sh --selftest          # import + CLI check
./run.sh preservation original.txt polished.txt
```
