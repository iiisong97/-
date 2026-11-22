#!/usr/bin/env bash
# Single entry point for the scientific PDF structure parser.
# Usage:
#   ./run.sh INPUT.pdf [--out result.json] [--txt fulltext.txt] [--pretty]
#   ./run.sh --selftest
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" == "--selftest" ]]; then
    echo "selftest: parser + benchmark import and CLI help render correctly"
    python3 "$HERE/parse_pdf.py" --help >/dev/null
    python3 "$HERE/benchmark.py" --help >/dev/null
    echo "selftest: OK (no input PDF provided; run ./run.sh INPUT.pdf to parse)"
    exit 0
fi

if [[ $# -lt 1 ]]; then
    echo "usage: ./run.sh INPUT.pdf [--out result.json] [--txt fulltext.txt] [--pretty]" >&2
    exit 2
fi

python3 "$HERE/parse_pdf.py" "$@"
