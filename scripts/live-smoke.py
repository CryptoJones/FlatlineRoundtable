#!/usr/bin/env python3
"""Ask one live endpoint whether the response shape still matches the fixtures.

Run from CI only via workflow_dispatch, and allowed to fail: a vendor being down
is not a defect in this repo. The golden fixtures answer "is it still what it was
when captured"; this answers "is it still right today", which no committed file
can.

Needs OPENROUTER_API_KEY in the environment. Reads nothing from the local config,
so it works on a runner with no ~/.config and no `pass`.
"""
import json
import os
import pathlib
import sys
import urllib.request

FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "responses"
URL = "https://openrouter.ai/api/v1/chat/completions"
# A free model, so a manual smoke run costs nothing.
MODEL = "openai/gpt-oss-120b"

# The fields roundtable actually reads. Everything else may change freely.
REQUIRED_TOP = ("provider", "usage", "choices")
REQUIRED_USAGE = ("prompt_tokens", "completion_tokens")
REQUIRED_CHOICE = ("finish_reason", "message")


def main() -> int:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print("no OPENROUTER_API_KEY — nothing to smoke")
        return 0

    body = {"model": MODEL, "max_tokens": 60,
            "messages": [{"role": "user", "content": "Reply with exactly: OK"}]}
    req = urllib.request.Request(
        URL, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        live = json.load(r)

    if "error" in live:
        print(f"vendor returned an error body: {str(live['error'])[:200]}")
        return 1

    missing = []
    for k in REQUIRED_TOP:
        if k not in live:
            missing.append(k)
    for k in REQUIRED_USAGE:
        if k not in (live.get("usage") or {}):
            missing.append(f"usage.{k}")
    choice = (live.get("choices") or [{}])[0]
    for k in REQUIRED_CHOICE:
        if k not in choice:
            missing.append(f"choices[0].{k}")
    if "content" not in (choice.get("message") or {}):
        missing.append("choices[0].message.content")

    if missing:
        print("LIVE SHAPE DRIFT — fields roundtable reads are gone:")
        for m in missing:
            print(f"  missing: {m}")
        print("\nRecapture with scripts/capture-fixtures.py and read the diff.")
        return 1

    print(f"live shape OK  (provider={live.get('provider')}, model={live.get('model')})")
    fixture = FIXTURES / (MODEL.replace("/", "_").replace(":", "-") + ".json")
    if fixture.exists():
        old = set(json.loads(fixture.read_text()))
        new = set(live)
        for gone in sorted(old - new):
            print(f"  note: fixture has top-level {gone!r}, live response does not")
        for added in sorted(new - old):
            print(f"  note: live response has new top-level {added!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
