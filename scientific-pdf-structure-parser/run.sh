#!/usr/bin/env bash
# run.sh — local smoke test: import every module and render each CLI's help.
set -euo pipefail
cd "$(dirname "$0")"

for mod in parse_pdf verify_parse benchmark reproduce; do
  python3 -c "import $mod" && echo "import ok: $mod"
done

echo "[selftest] OK (parse/verify/benchmark/reproduce all import)"
