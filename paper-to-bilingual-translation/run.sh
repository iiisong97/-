#!/usr/bin/env bash
# run.sh — self-test for the translation Skill (no real translation; verifies
# the deterministic scripts import and their CLIs work).
set -euo pipefail
cd "$(dirname "$0")"

echo "[selftest] scripts import + CLI check"
python3 - <<'PY'
import importlib, sys
for m in ("parse_pdf", "extract_terms", "segment", "verify_translation",
          "reproduce", "benchmark"):
    importlib.import_module(m)
    print("  import ok:", m)
PY

for m in extract_terms segment verify_translation benchmark; do
    python3 "$m.py" --help >/dev/null 2>&1 || { echo "FAIL $m --help"; exit 1; }
done
python3 reproduce.py --help >/dev/null 2>&1 || { echo "FAIL reproduce --help"; exit 1; }

echo "[selftest] OK (parse/draft/build all import and CLI render)"
