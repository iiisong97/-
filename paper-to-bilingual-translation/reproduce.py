#!/usr/bin/env python3
"""reproduce.py — one-command deterministic pipeline.

    python3 reproduce.py <paper.pdf> --out DIR [--selftest]

Runs parse → extract-terms → segment. The actual translation is done by the
Agent; with --selftest the script also fills a deliberately *broken* synthetic
translation (missing numbers/citations, inconsistent terms) to prove the
verification checks fire — this synthetic run is for testing only and is never a
real answer.
"""

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        raise SystemExit(r.returncode)
    return r.stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paper")
    ap.add_argument("--out", required=True)
    ap.add_argument("--selftest", action="store_true",
                    help="add a synthetic broken translation and run verification")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    struct = os.path.join(args.out, "structure.json")
    glossary = os.path.join(args.out, "glossary.json")
    units = os.path.join(args.out, "units.json")

    print(run([sys.executable, os.path.join(HERE, "parse_pdf.py"),
               args.paper, "--out", struct]))
    print(run([sys.executable, os.path.join(HERE, "extract_terms.py"),
               struct, "--out", glossary]))
    print(run([sys.executable, os.path.join(HERE, "segment.py"),
               struct, "--out", units]))

    if args.selftest:
        # synthetic: drop the first digit and first citation of every unit to
        # prove verification catches it; also leave terms untranslated.
        data = json.load(open(units, encoding="utf-8"))
        import re
        for u in data["units"]:
            src = u.get("source", "")
            u["translation"] = re.sub(r"\d", "", src[:120])  # drop digits
        selftest_units = os.path.join(args.out, "selftest_units.json")
        with open(selftest_units, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        gl = json.load(open(glossary, encoding="utf-8"))
        for t in gl["terms"][:5]:
            t["translation"] = "测试译名"
        selftest_gl = os.path.join(args.out, "selftest_glossary.json")
        with open(selftest_gl, "w", encoding="utf-8") as fh:
            json.dump(gl, fh, ensure_ascii=False, indent=2)
        print(run([sys.executable, os.path.join(HERE, "verify_translation.py"),
                   selftest_units, "--glossary", selftest_gl,
                   "--out", os.path.join(args.out, "verification.json")]))
        v = json.load(open(os.path.join(args.out, "verification.json"),
                           encoding="utf-8"))
        s = v["summary"]
        assert s["numbers_missing"] > 0, "verification should catch dropped digits"
        print(f"selftest OK: verification caught {s['numbers_missing']} dropped "
              f"numbers and {s['citations_missing']} citations (synthetic).")


if __name__ == "__main__":
    main()
