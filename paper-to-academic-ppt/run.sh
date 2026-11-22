#!/usr/bin/env bash
# Entry point for paper-to-academic-ppt.
# Usage:
#   ./run.sh parse PAPER.pdf --out structure.json
#   ./run.sh draft structure.json --out deck_spec.json [--max-slides N]
#   ./run.sh build deck_spec.json --out DECK_DIR [--template T.pptx]
#   ./run.sh --selftest
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case "${1:-}" in
  --selftest)
    python3 "$HERE/parse_pdf.py" --help >/dev/null
    python3 "$HERE/draft_outline.py" --help >/dev/null
    python3 "$HERE/build_ppt.py" --help >/dev/null
    echo "selftest: OK (parse/draft/build all import and CLI render)"
    ;;
  parse)
    shift; exec python3 "$HERE/parse_pdf.py" "$@"
    ;;
  draft)
    shift; exec python3 "$HERE/draft_outline.py" "$@"
    ;;
  build)
    shift; exec python3 "$HERE/build_ppt.py" "$@"
    ;;
  *)
    echo "usage: ./run.sh {parse|draft|build|--selftest} ..." >&2
    exit 2
    ;;
esac
