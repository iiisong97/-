#!/usr/bin/env bash
# Entry point for the literature-notes guardrails.
# Usage:
#   ./run.sh check result.json [--structure structure.json] [--out report.json]
#   ./run.sh --selftest
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" == "--selftest" ]]; then
    python3 "$HERE/notes_check.py" --help >/dev/null
    python3 "$HERE/benchmark.py" --help >/dev/null
    python3 "$HERE/parse_pdf.py" --help >/dev/null
    echo "selftest: OK (notes_check.py + benchmark.py + parse_pdf.py import/CLI render)"
    exit 0
fi

if [[ "${1:-}" == "check" ]]; then
    shift
    exec python3 "$HERE/notes_check.py" "$@"
fi

echo "usage: ./run.sh check result.json [--structure structure.json] [--out report.json]" >&2
echo "       ./run.sh --selftest" >&2
exit 2
