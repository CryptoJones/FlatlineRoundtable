#!/usr/bin/env python3
"""Recapture the golden response fixtures from live endpoints.

    python3 scripts/capture-fixtures.py

The stub server in the test suite is hand-written: it proves roundtable handles
the shape we *think* vendors return. These fixtures are the shape they actually
returned, so a vendor moving a field fails a test instead of failing a run.

Costs a handful of 60-token calls against whatever http lanes are active. Run it
when a test in TestGoldenResponses starts failing, then read the diff -- that
diff IS the drift you were trying to detect, so look at it before committing it.

Request ids and fingerprints are redacted; nothing account-specific is written.
"""
import json, os, pathlib, subprocess, urllib.request, yaml

CFG = os.path.expanduser("~/.config/flatline-roundtable/FlatlineRoundtable.yaml")
cfg = yaml.safe_load(open(CFG)); defaults = cfg.get("defaults") or {}
OUT = pathlib.Path("tests/fixtures/responses"); OUT.mkdir(parents=True, exist_ok=True)

WANT = ["SHODAN", "Neuromancer", "MasterControl", "Cerebex", "SELMA", "GLaDOS"]
PROMPT = "Reply with exactly: OK"

def redact(d):
    for k in ("id", "system_fingerprint"):
        if k in d:
            d[k] = f"<redacted-{k}>"
    if "created" in d:
        d["created"] = 0
    return d

for name in WANT:
    raw = next((l for l in cfg["lanes"] if l["name"] == name), None)
    if not raw or not raw.get("active"):
        print(f"  skip {name}: not active"); continue
    lane = {**defaults, **raw}
    key = subprocess.run(["pass", "show", lane["key_entry"]], capture_output=True,
                         text=True, check=True).stdout.splitlines()[0]
    body = {"model": lane["model"], "max_tokens": 60,
            "messages": [{"role": "user", "content": PROMPT}]}
    body.update(lane.get("extra_body") or {})
    req = urllib.request.Request(lane["base_url"].rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.load(r)
    except Exception as e:
        print(f"  FAIL {name}: {str(e)[:90]}"); continue
    if "error" in data:
        print(f"  FAIL {name}: error body {str(data['error'])[:70]}"); continue
    slug = lane["model"].replace("/", "_").replace(":", "-")
    p = OUT / f"{slug}.json"
    p.write_text(json.dumps(redact(data), indent=2, sort_keys=True) + "\n")
    ch = data["choices"][0]
    print(f"  OK   {name:<14} -> {p.name}  provider={data.get('provider')} "
          f"content={(ch['message'].get('content') or '')[:20]!r}")
