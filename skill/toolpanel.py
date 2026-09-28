#!/usr/bin/env python3
"""One roundtable lane, WITH read-only repo tools. Scratch driver, not a roundtable change.

Reuses roundtable's config, pass-key fetch and env scrubbing. HTTP lanes get an
OpenAI-style tool loop (read_file / grep / list_dir / git) sandboxed to REPO;
CLI lanes run with cwd=REPO and their own harness's read-only tools.

usage: ROUNDTABLE_REPO=/path/to/repo toolpanel.py LANE BRIEF_FILE OUT_FILE
"""

import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(os.environ.get("ROUNDTABLE_REPO", ".")).resolve()
MAX_ROUNDS = 30
MAX_TOOL_OUT = 15000

_loader = importlib.machinery.SourceFileLoader("roundtable", str(Path.home() / ".local/bin/roundtable"))
_spec = importlib.util.spec_from_loader("roundtable", _loader)
rt = importlib.util.module_from_spec(_spec)
_loader.exec_module(rt)


def _safe(path: str) -> Path:
    p = (REPO / path).resolve()
    if p != REPO and REPO not in p.parents:
        raise ValueError("path escapes the repository")
    if ".git" in p.relative_to(REPO).parts or p.name.startswith(".env"):
        raise ValueError("path not readable")
    return p


def _clip(text: str) -> str:
    return text if len(text) <= MAX_TOOL_OUT else text[:MAX_TOOL_OUT] + f"\n...[clipped, {len(text)} chars total; narrow the request]"


def t_read_file(path, start_line=1, end_line=400):
    lines = _safe(path).read_text(errors="replace").splitlines()
    s, e = max(1, int(start_line)), min(len(lines), int(end_line))
    return "\n".join(f"{i}\t{lines[i-1]}" for i in range(s, e + 1)) + f"\n[{len(lines)} lines total]"


def t_list_dir(path="."):
    p = _safe(path)
    return "\n".join(sorted((c.name + ("/" if c.is_dir() else "")) for c in p.iterdir() if c.name not in (".git", "node_modules", "__pycache__", "venv")))


def t_grep(pattern, path=".", glob=None):
    cmd = ["git", "-C", str(REPO), "grep", "-n", "-I", "-E", "--", pattern]
    target = str(_safe(path).relative_to(REPO)) or "."
    cmd.append(target if not glob else f"{target}/**/{glob}" if target != "." else glob)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return r.stdout or r.stderr or "(no matches)"


GIT_OK = {"diff", "show", "log", "ls-files", "blame"}


def t_git(args):
    argv = args if isinstance(args, list) else args.split()
    if not argv or argv[0] not in GIT_OK or any(a.startswith(("--output", "--ext-diff", "-c")) for a in argv):
        return f"refused: only read-only subcommands {sorted(GIT_OK)}"
    r = subprocess.run(["git", "-C", str(REPO), "--no-pager", *argv], capture_output=True, text=True, timeout=60)
    return r.stdout or r.stderr or "(empty)"


TOOLS = {"read_file": t_read_file, "list_dir": t_list_dir, "grep": t_grep, "git": t_git}
SCHEMAS = [
    {"type": "function", "function": {"name": "read_file", "description": "Read a file in the vigil repo (numbered lines). Paths are repo-relative.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "list_dir", "description": "List a directory in the vigil repo.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "grep", "description": "git grep -n -E a regex in the repo, optionally under a path and a filename glob like '*.py'.",
     "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}, "glob": {"type": "string"}}, "required": ["pattern"]}}},
    {"type": "function", "function": {"name": "git", "description": "Run a read-only git command in the repo: diff, show, log, ls-files, blame. Example args: ['diff','origin/main..HEAD','--','core/integrations/wazuh/client.py'].",
     "parameters": {"type": "object", "properties": {"args": {"type": "array", "items": {"type": "string"}}}, "required": ["args"]}}},
]


def post(lane, key, body):
    url = lane["base_url"].rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    attempts = 6
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
            with urllib.request.urlopen(req, timeout=lane.get("timeout", 300)) as r:
                data = json.load(r)
            if "error" in data:
                raise RuntimeError(str(data["error"])[:300])
            return data
        # ConnectionError covers http.client.RemoteDisconnected: NVIDIA dropped a
        # long GLaDOS tool loop mid-response (2026-09-27); that is worth a retry.
        except (urllib.error.HTTPError, RuntimeError, TimeoutError, urllib.error.URLError, ConnectionError) as e:
            code = getattr(e, "code", 500)
            detail = e.read().decode(errors="replace")[:300] if hasattr(e, "read") else str(e)
            limited = code == 429 or "429" in detail or "rate-limited" in detail
            if attempt == attempts - 1 or (isinstance(code, int) and 400 <= code < 500 and not limited):
                raise RuntimeError(f"HTTP {code}: {detail}")
            # Shared upstream quotas (Mistral via OpenRouter, 2026-09-27) refill per
            # minute; a tool loop exhausts them mid-review, so wait the window out.
            retry_after = getattr(e, "headers", None) and e.headers.get("Retry-After")
            if limited:
                wait = float(retry_after) if (retry_after or "").isdigit() else 20 * (attempt + 1)
                print(f"  [{lane['name']}] rate-limited, waiting {wait:.0f}s", file=sys.stderr)
            else:
                wait = 5 * (attempt + 1)
            time.sleep(min(wait, 90))


def http_with_tools(lane, key, brief):
    msgs = ([{"role": "system", "content": lane["personality"]}] if lane.get("personality") else []) + [{"role": "user", "content": brief}]
    calls = 0
    text_calls = 0
    # Per-lane cap: NVIDIA drops GLaDOS requests once a long tool loop has grown the
    # context (2026-09-27), so that lane must answer earlier.
    max_rounds = int(lane.get("toolpanel_max_rounds") or MAX_ROUNDS)
    for rnd in range(max_rounds):
        last = rnd == max_rounds - 1
        if last:
            # Without this a model still exploring ends the loop with no answer.
            msgs.append({"role": "user", "content": "Tool budget exhausted. Write your final review now from what you have read. No more tool calls."})
        body = {"model": lane["model"], "max_tokens": max(lane.get("max_tokens", 2000), 8000), "messages": msgs}
        if not last:
            body["tools"] = SCHEMAS
        if lane.get("temperature") is not None:
            body["temperature"] = lane["temperature"]
        body.update(lane.get("extra_body") or {})
        for _attempt in range(3):
            data = post(lane, key, body)
            msg = data["choices"][0]["message"]
            tcs = msg.get("tool_calls") or []
            # Reasoning models intermittently return neither text nor tool calls
            # (Kimi K3, 2026-09-27); one retry of the same round usually recovers.
            # finish_reason "error" means the provider's stream died mid-answer
            # (MasterControl on Mistral, 2026-09-27); the partial text is not an answer.
            if data["choices"][0].get("finish_reason") == "error":
                continue
            if tcs or (msg.get("content") or "").strip():
                break
        text = (msg.get("content") or "").strip()
        if not tcs and not last and "<tool_call>" in text and text_calls < 3:
            # Nemotron with reasoning off sometimes writes the call as text instead
            # of using function calling (SELMA, 2026-09-27); that is not an answer.
            text_calls += 1
            msgs.append({"role": "assistant", "content": text})
            msgs.append({"role": "user", "content": "That tool call was written as text, so it did not run. Call tools through the function-calling interface, or give your final review now."})
            continue
        if not tcs or last:
            return text, calls, data["choices"][0].get("finish_reason")
        turn = {"role": "assistant", "content": msg.get("content") or "", "tool_calls": tcs}
        if msg.get("reasoning_content"):
            # Thinking models expect their reasoning echoed back across tool turns.
            turn["reasoning_content"] = msg["reasoning_content"]
        msgs.append(turn)
        for tc in tcs:
            calls += 1
            fn = tc["function"]["name"]
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
                out = _clip(str(TOOLS[fn](**args)))
            except Exception as e:
                out = f"tool error: {e}"
            print(f"  [{lane['name']}] tool {fn} {tc['function'].get('arguments','')[:120]}", file=sys.stderr)
            msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": out})
    return "", calls, "max_rounds"


def cli_with_tools(lane, brief):
    text = (lane.get("personality", "") + "\n\n---\n\n" + brief) if lane.get("personality") else brief
    cmd = [lane["command"]]
    args = list(lane["args"])
    if lane["command"] == "claude":
        # Read-only tools, no user hooks: the lane must see the repo, not this operator's memory.
        args += ["--allowedTools", "Read,Grep,Glob,Bash(git diff:*),Bash(git show:*),Bash(git log:*),Bash(git grep:*)",
                 # bypassPermissions in the user's settings would otherwise hand the
                 # lane Write/Edit/any Bash inside the reviewed checkout.
                 "--permission-mode", "default",
                 "--disallowedTools", "Write,Edit,NotebookEdit",
                 "--settings", json.dumps({"disableAllHooks": True})]
    elif lane["command"] == "agy":
        args = ["--sandbox", *args]
    stdin = text if lane.get("stdin") else None
    cmd += [text if a == "{prompt}" else a for a in args]
    r = subprocess.run(cmd, input=stdin, capture_output=True, text=True, cwd=REPO, env=rt.child_env(lane),
                       timeout=lane.get("timeout", 900) * 2, start_new_session=True)
    if r.returncode != 0:
        raise RuntimeError(f"exit {r.returncode}: {r.stderr.strip()[:300]}")
    return rt.ANSI_RE.sub("", r.stdout).strip(), None, "stop"


def main():
    name, brief_file, out_file = sys.argv[1:4]
    cfg = rt.load_config(rt.DEFAULT_CONFIG)
    lane = next(l for l in cfg["lanes"] if l["name"] == name)
    # One-off request overrides without editing the shared config, e.g.
    # TOOLPANEL_EXTRA_BODY='{"reasoning": {"enabled": false}}' to turn thinking off.
    if os.environ.get("TOOLPANEL_EXTRA_BODY"):
        lane = {**lane, "extra_body": {**(lane.get("extra_body") or {}), **json.loads(os.environ["TOOLPANEL_EXTRA_BODY"])}}
    brief = Path(brief_file).read_text()
    if lane.get("toolpanel") is False:
        # Lanes marked tool-less in the shared config (no tool endpoint, or
        # ungrounded with tools) run through plain `roundtable` on a full-diff brief.
        msg = f"# {name} SKIPPED: toolpanel: false in the lane config; run it tool-less with `roundtable --lanes {name}`\n"
        Path(out_file).write_text(msg)
        print(msg.strip())
        return 3
    t0 = time.time()
    try:
        if lane.get("harness") == "http":
            key = rt.fetch_keys([lane]).get(lane.get("key_entry"))
            answer, calls, finish = http_with_tools(lane, key, brief)
        else:
            answer, calls, finish = cli_with_tools(lane, brief)
        status = "ok" if answer else "EMPTY"
    except Exception as e:
        answer, calls, finish, status = f"LANE FAILED: {e}", None, None, "FAILED"
    hdr = f"# {name} ({lane.get('model')}, {lane.get('harness')}) status={status} tool_calls={calls} finish={finish} secs={int(time.time()-t0)}\n\n"
    Path(out_file).write_text(hdr + answer + "\n")
    print(hdr.strip())
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
