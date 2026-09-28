#!/usr/bin/env python3
"""Fold toolpanel.py answer files into ONE transcript that --discuss/--revise can seed from.

toolpanel.py writes a plain-text file per lane, headed
`# LANE (model, harness) status=ok tool_calls=N finish=stop secs=S`, and
roundtable's second rounds read transcripts, not answer files. This bridges them:

    toolpanel-seed.py BRIEF_FILE OUT_JSON ANSWER_FILE...
    roundtable --discuss OUT_JSON --discuss-rounds 2 "focus text"

A lane whose status is not `ok` (EMPTY, FAILED, SKIPPED) is recorded with
answer=null, exactly as a failed lane is in a real transcript, so the discussion
shows it no opening and letters it after the lanes that answered.
"""
import json
import re
import sys
from pathlib import Path

HDR = re.compile(r"^# (?P<lane>\S+)(?: \((?P<model>.*?), (?P<harness>\w+)\))?(?: status=(?P<status>\w+))?")


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    brief_file, out_json, *answer_files = argv[1:]
    results = []
    for f in answer_files:
        text = Path(f).read_text()
        m = HDR.match(text)
        if not m:
            sys.exit(f"{f}: first line is not a toolpanel header (`# LANE (model, harness) status=...`)")
        body = text.split("\n", 1)[1].strip() if "\n" in text else ""
        ok = m.group("status") == "ok" and bool(body)
        results.append({"lane": m.group("lane"), "model": m.group("model"),
                        "harness": m.group("harness") or "http",
                        "answer": body if ok else None,
                        "error": None if ok else f"toolpanel status={m.group('status')}"})
    seed = {"brief": Path(brief_file).read_text(), "results": results, "round": 1,
            "note": "seeded from toolpanel.py answer files by toolpanel-seed.py"}
    Path(out_json).write_text(json.dumps(seed, indent=2))
    answered = sum(1 for r in results if r["answer"])
    print(f"{out_json}: {answered}/{len(results)} lanes with an opening")
    return 0 if answered else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
