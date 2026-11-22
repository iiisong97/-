#!/usr/bin/env python3
"""reproduce.py — one-command end-to-end: paper PDF -> editable academic deck.

Usage:
    python3 reproduce.py PAPER.pdf --out DECK_DIR [--template T.pptx] [--max-slides N]

Runs the full deterministic pipeline:
    1. parse_pdf.py      -> structure.json   (evidence base)
    2. draft_outline.py  -> deck_spec.json   (main-line skeleton)
    3. build_ppt.py      -> deck.pptx + evidence_map.json + previews/*.png

The auto-draft is a skeleton; refine deck_spec.json before the final build for
the specific audience/time budget (see SKILL.md step 4).
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def run(cmd):
    print("+", " ".join(cmd), file=sys.stderr)
    return subprocess.run(cmd, check=False).returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paper")
    ap.add_argument("--out", required=True)
    ap.add_argument("--template", default=None)
    ap.add_argument("--max-slides", type=int, default=12)
    ap.add_argument("--skip-build", action="store_true",
                    help="stop after drafting deck_spec.json (for the agent to refine it)")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    structure = os.path.join(args.out, "structure.json")
    spec = os.path.join(args.out, "deck_spec.json")

    rc = run([sys.executable, os.path.join(HERE, "parse_pdf.py"),
              args.paper, "--out", structure])
    if rc != 0:
        return rc
    rc = run([sys.executable, os.path.join(HERE, "draft_outline.py"),
              structure, "--out", spec, "--paper", args.paper,
              "--max-slides", str(args.max_slides)])
    if rc != 0:
        return rc
    if args.skip_build:
        print(f"draft ready: {spec} (edit it, then run build_ppt.py)")
        return 0
    cmd = [sys.executable, os.path.join(HERE, "build_ppt.py"), spec, "--out", args.out,
           "--paper", args.paper]
    if args.template:
        cmd += ["--template", args.template]
    return run(cmd)


if __name__ == "__main__":
    sys.exit(main())
