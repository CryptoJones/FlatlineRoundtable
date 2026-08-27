#!/usr/bin/env python3
"""Measure how many tokens a lane spends thinking, so max_tokens is a number
rather than a guess.

    python3 scripts/measure-reasoning.py Cerebex SELMA          # short brief
    python3 scripts/measure-reasoning.py --brief long.md SELMA  # a real one
    python3 scripts/measure-reasoning.py --samples 10 Cerebex

WHY THIS EXISTS

On an OpenAI-compatible endpoint, `max_tokens` caps reasoning and answer
TOGETHER. A reasoning model whose thinking overruns the cap returns HTTP 200
with empty content and finish_reason "length" -- a lane that delivered nothing,
for a reason the response does not spell out.

Reasoning cost is also a distribution, not a constant, and a wide one. Measured
on a single unchanged 24k-token brief:

    Cerebex      reasoning    20 - 21606     (three orders of magnitude)
    SELMA        reasoning 10153 - 17620
    Neuromancer  reasoning  3253 -  6293

So a lane can answer nine times and come back empty on the tenth. Sizing
max_tokens off one observation -- which is how 4000 was first picked, wrongly --
gets you a number that works until it doesn't. Take several samples and leave
headroom above the worst.

For a free lane a high ceiling costs nothing: max_tokens is a cap, not a target,
and the context windows here are 130k-260k. For a metered lane it inflates the
worst-case pre-flight estimate, so size those to the measurement instead.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required — pip install pyyaml")

DEFAULT_CONFIG = os.path.expanduser(
    "~/.config/flatline-roundtable/FlatlineRoundtable.yaml")
DEFAULT_BRIEF = (
    "Explain, in detail, when a cache is the wrong answer. Cover invalidation, "
    "staleness, coherence, and operational cost. Be thorough."
)


def sample(lane, brief, max_tokens, key):
    body = {"model": lane["model"], "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": brief}]}
    body.update(lane.get("extra_body") or {})
    req = urllib.request.Request(
        lane["base_url"].rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=300) as r:
        data = json.load(r)
    if "error" in data:
        raise RuntimeError(str(data["error"])[:120])
    choice = data["choices"][0]
    usage = data.get("usage") or {}
    reasoning = (usage.get("completion_tokens_details") or {}).get(
        "reasoning_tokens", 0)
    completion = usage.get("completion_tokens") or 0
    return {
        "reasoning": reasoning,
        "answer": max(0, completion - reasoning),
        "finish": choice.get("finish_reason"),
        "empty": not (choice["message"].get("content") or "").strip(),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("lanes", nargs="+", help="lane names from the config")
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--brief", help="file to send; omit for a short built-in one")
    ap.add_argument("--samples", type=int, default=4)
    ap.add_argument("--ceiling", type=int, default=32000,
                    help="max_tokens to measure UNDER — high, so thinking is "
                         "observed rather than truncated")
    a = ap.parse_args()

    cfg = yaml.safe_load(open(a.config))
    defaults = cfg.get("defaults") or {}
    brief = open(a.brief).read() if a.brief else DEFAULT_BRIEF
    print(f"brief: {len(brief)} chars   ceiling: {a.ceiling}   "
          f"samples: {a.samples}\n")

    for name in a.lanes:
        raw = next((l for l in cfg["lanes"] if l["name"] == name), None)
        if raw is None:
            print(f"  {name}: no such lane"); continue
        lane = {**defaults, **raw}
        if lane.get("harness") != "http":
            print(f"  {name}: not an http lane — usage is only reported there")
            continue
        if not lane.get("key_entry"):
            print(f"  {name}: no key_entry"); continue
        key = subprocess.run(["pass", "show", lane["key_entry"]],
                             capture_output=True, text=True,
                             check=True).stdout.splitlines()[0]

        rs, ans, empties, errs = [], [], 0, 0
        for _ in range(a.samples):
            try:
                s = sample(lane, brief, a.ceiling, key)
            except Exception as e:
                errs += 1
                print(f"  {name}: {str(e)[:70]}")
                time.sleep(2)
                continue
            rs.append(s["reasoning"]); ans.append(s["answer"])
            empties += s["empty"]
            time.sleep(1)

        if not rs:
            print(f"  {name:<14} no samples ({errs} errors)\n"); continue
        needed = max(rs) + max(ans)
        current = lane.get("max_tokens", defaults.get("max_tokens", 2000))
        verdict = "OK" if current >= needed else "TOO LOW"
        print(f"  {name:<14} reasoning {min(rs)}-{max(rs)}  "
              f"answer {min(ans)}-{max(ans)}")
        print(f"  {'':<14} worst observed need {needed}, "
              f"config has {current}  -> {verdict}")
        if empties:
            print(f"  {'':<14} {empties}/{len(rs)} came back EMPTY even at "
                  f"{a.ceiling}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
