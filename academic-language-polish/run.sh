#!/usr/bin/env bash
# Entry point for academic-language-polish guardrails.
# Usage:
#   ./run.sh preservation ORIGINAL.txt POLISHED.txt [--out report.json]
#   ./run.sh --selftest
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" == "--selftest" ]]; then
    python3 "$HERE/preservation_check.py" --help >/dev/null
    python3 "$HERE/benchmark.py" --help >/dev/null
    echo "selftest: OK (preservation_check.py + benchmark.py import and CLI render)"
    exit 0
fi

if [[ "${1:-}" == "preservation" ]]; then
    shift
    exec python3 "$HERE/preservation_check.py" "$@"
fi

echo "usage: ./run.sh preservation ORIGINAL.txt POLISHED.txt [--out report.json]" >&2
echo "       ./run.sh --selftest" >&2
exit 2
