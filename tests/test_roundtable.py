#!/usr/bin/env python3
"""Tests for roundtable.

These target the behaviours that silently cost money or leave processes running
— the ones no amount of reading the code will catch:

    * an ambient API key must not reach a subscription-backed CLI lane
    * a hung lane must not survive its timeout
    * a missing secret must fail loudly, never fall back to an unauthenticated call
    * a silent lane must fail the run

Everything runs against a stub HTTP server and fake CLI binaries. No test in
this file contacts a real vendor, spends money, or needs a credential.

    python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_loader(
    "roundtable", importlib.machinery.SourceFileLoader("roundtable", str(ROOT / "roundtable"))
)
rt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rt)


# --------------------------------------------------------------------------- #
# stub vendor
# --------------------------------------------------------------------------- #
class StubHandler(BaseHTTPRequestHandler):
    """Minimal OpenAI-compatible endpoint. Behaviour switches on the model name."""

    def log_message(self, *a):  # silence
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.last_request = body
        self.server.last_auth = self.headers.get("Authorization")
        model = body.get("model", "")

        if model == "boom":
            self._send(500, {"error": {"message": "upstream exploded"}})
            return
        if model == "truncate":
            self._send(200, {
                "choices": [{"message": {"content": "cut off mid-"}, "finish_reason": "length"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            })
            return
        if model == "empty":
            self._send(200, {"choices": [{"message": {"content": ""}, "finish_reason": "stop"}]})
            return
        # Behaviours below count attempts so a retry can be observed directly.
        self.server.hits[model] = self.server.hits.get(model, 0) + 1
        if model == "always_error_body":
            # HTTP 200 carrying an error payload -- an upstream failure behind a
            # gateway that itself succeeded.
            self._send(200, {"error": {"message": "Upstream error from StubCo"}})
            return
        if model == "error_body_once":
            if self.server.hits[model] == 1:
                self._send(200, {"error": {"message": "Upstream error from StubCo"}})
                return
            self._send(200, {"choices": [{"message": {"content": "recovered"},
                                          "finish_reason": "stop"}]})
            return
        if model == "empty_once":
            if self.server.hits[model] == 1:
                self._send(200, {"choices": [{"message": {"content": ""},
                                              "finish_reason": "stop"}]})
                return
            self._send(200, {"choices": [{"message": {"content": "recovered"},
                                          "finish_reason": "stop"}]})
            return
        if model == "ratelimited":
            self._send(429, {"error": {"message": "rate-limited upstream"}},
                       extra={"Retry-After": "60"})
            return
        if model == "ratelimited_forever":
            self._send(429, {"error": {"message": "rate-limited upstream"}},
                       extra={"Retry-After": "3600"})
            return
        self._send(200, {
            "choices": [{"message": {"content": "stub answer"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 200},
            "provider": "StubCo",
        })

    def _send(self, code, payload, extra=None):
        raw = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)


class StubServer:
    def __enter__(self):
        self.srv = HTTPServer(("127.0.0.1", 0), StubHandler)
        self.srv.last_request = self.srv.last_auth = None
        self.srv.hits = {}
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_port}/v1"
        return self

    def __exit__(self, *a):
        self.srv.shutdown()
        self.srv.server_close()   # else the socket leaks a ResourceWarning per test


def write_exe(path: Path, body: str) -> Path:
    path.write_text("#!/usr/bin/env bash\n" + textwrap.dedent(body))
    path.chmod(0o755)
    return path


# --------------------------------------------------------------------------- #
class TestConfigValidation(unittest.TestCase):
    """Bad config must be rejected up front, not discovered mid-run."""

    def _cfg(self, lanes):
        f = Path(tempfile.mkdtemp()) / "c.yaml"
        f.write_text(json.dumps({"lanes": lanes}))  # JSON is valid YAML
        return f

    def _dies(self, lanes, needle):
        with self.assertRaises(SystemExit) as e:
            rt.load_config(self._cfg(lanes))
        self.assertIn(needle, str(e.exception))

    def test_rejects_unknown_harness(self):
        self._dies([{"name": "A", "harness": "carrier-pigeon"}], "harness must be")

    def test_rejects_http_lane_without_base_url(self):
        self._dies([{"name": "A", "harness": "http", "model": "m"}], "needs base_url")

    def test_rejects_duplicate_lane_names(self):
        self._dies(
            [{"name": "A", "harness": "cli", "command": "x", "args": ["-p"]},
             {"name": "A", "harness": "cli", "command": "x", "args": ["-p"]}],
            "duplicate lane name",
        )

    def test_extra_body_cannot_override_the_request(self):
        # A config typo here would silently send a call you did not intend.
        self._dies(
            [{"name": "A", "harness": "http", "model": "m", "base_url": "http://x/v1",
              "extra_body": {"model": "something-else"}}],
            "extra_body may not set",
        )

    def test_acp_lane_needs_only_a_command(self):
        cfg = rt.load_config(self._cfg([{"name": "A", "harness": "acp", "command": "x"}]))
        self.assertEqual(cfg["lanes"][0]["harness"], "acp")


class TestHttpLane(unittest.TestCase):
    def test_sends_bearer_and_returns_answer(self):
        with StubServer() as s:
            out = rt.http_lane(
                {"model": "m", "base_url": s.url, "timeout": 10}, "hi", "SECRET-VALUE", 0)
            self.assertEqual(out["answer"], "stub answer")
            self.assertEqual(s.srv.last_auth, "Bearer SECRET-VALUE")

    def test_personality_becomes_a_system_message(self):
        with StubServer() as s:
            rt.http_lane({"model": "m", "base_url": s.url, "timeout": 10,
                          "personality": "you are terse"}, "hi", None, 0)
            msgs = s.srv.last_request["messages"]
            self.assertEqual(msgs[0], {"role": "system", "content": "you are terse"})

    def test_truncation_is_reported_not_hidden(self):
        # A clipped answer reads as complete. That is the failure mode.
        with StubServer() as s:
            out = rt.http_lane({"model": "truncate", "base_url": s.url, "timeout": 10}, "hi", None, 0)
            self.assertEqual(out["finish_reason"], "length")

    def test_server_error_raises_after_retries(self):
        with StubServer() as s:
            with self.assertRaises(RuntimeError):
                rt.http_lane({"model": "boom", "base_url": s.url, "timeout": 10}, "hi", None, 0)


class TestFreeLaneResilience(unittest.TestCase):
    """The failure modes free endpoints actually produce under load.

    Each of these used to end the lane on the first attempt, which fails the
    whole run -- a lane that delivered nothing is the bug this tool exists to
    eliminate, so it is worth one more call to avoid it.
    """

    def _no_sleep(self):
        """Patch out the backoff and record what it was asked to wait."""
        slept = []
        orig = rt.time.sleep
        rt.time.sleep = lambda n: slept.append(n)
        self.addCleanup(lambda: setattr(rt.time, "sleep", orig))
        return slept

    def test_error_body_in_a_200_is_retried(self):
        self._no_sleep()
        with StubServer() as s:
            out = rt.http_lane(
                {"model": "error_body_once", "base_url": s.url, "timeout": 10}, "hi", None, 2)
            self.assertEqual(out["answer"], "recovered")
            self.assertEqual(s.srv.hits["error_body_once"], 2)

    def test_error_body_still_raises_once_retries_are_spent(self):
        self._no_sleep()
        with StubServer() as s:
            with self.assertRaises(RuntimeError):
                rt.http_lane(
                    {"model": "always_error_body", "base_url": s.url, "timeout": 10}, "hi", None, 1)
            self.assertEqual(s.srv.hits["always_error_body"], 2)

    def test_empty_answer_is_retried(self):
        self._no_sleep()
        with StubServer() as s:
            out = rt.http_lane(
                {"model": "empty_once", "base_url": s.url, "timeout": 10}, "hi", None, 2)
            self.assertEqual(out["answer"], "recovered")
            self.assertEqual(s.srv.hits["empty_once"], 2)

    def test_exhausted_empty_answer_is_still_reported_empty(self):
        # It must not start raising -- ask() turns this into "empty answer",
        # and a silent lane still has to fail the run.
        self._no_sleep()
        with StubServer() as s:
            out = rt.http_lane(
                {"model": "empty", "base_url": s.url, "timeout": 10}, "hi", None, 0)
            self.assertEqual(out["answer"], "")

    def test_retry_after_is_honoured_past_the_old_30s_cap(self):
        # Vendors advertise 60s free-tier windows. Sleeping 30 and retrying into
        # a window that has not reopened burns the retry for nothing.
        slept = self._no_sleep()
        with StubServer() as s:
            with self.assertRaises(RuntimeError):
                rt.http_lane(
                    {"model": "ratelimited", "base_url": s.url, "timeout": 10}, "hi", None, 1)
        self.assertEqual(slept, [60.0])

    def test_retry_after_is_still_capped(self):
        # Honour the vendor, but never park a lane for an hour.
        slept = self._no_sleep()
        with StubServer() as s:
            with self.assertRaises(RuntimeError):
                rt.http_lane(
                    {"model": "ratelimited_forever", "base_url": s.url, "timeout": 10}, "hi", None, 1)
        self.assertEqual(slept, [rt.RETRY_AFTER_CAP])


class TestCliLane(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_prompt_is_passed_through(self):
        exe = write_exe(self.tmp / "fake", 'echo "GOT:$2"')
        out = rt.cli_lane({"command": str(exe), "args": ["-p", "{prompt}"], "timeout": 10}, "hello")
        self.assertIn("GOT:hello", out["answer"])

    def test_stdin_mode(self):
        exe = write_exe(self.tmp / "fake", 'cat')
        out = rt.cli_lane(
            {"command": str(exe), "args": ["-p"], "stdin": True, "timeout": 10}, "from-stdin")
        self.assertIn("from-stdin", out["answer"])

    def test_ambient_api_key_never_reaches_the_child(self):
        """THE cost test.

        A subscription CLI costs nothing via OAuth -- unless an API key is in the
        environment, in which case it bills metered credits instead, silently.
        """
        exe = write_exe(self.tmp / "fake", 'echo "KEY=[${ANTHROPIC_API_KEY:-unset}]"')
        os.environ["ANTHROPIC_API_KEY"] = "leaked-would-bill"
        try:
            out = rt.cli_lane({"command": str(exe), "args": ["-p"], "timeout": 10}, "hi")
        finally:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        self.assertIn("KEY=[unset]", out["answer"])
        self.assertNotIn("leaked-would-bill", out["answer"])

    def test_hung_lane_is_killed_and_leaves_no_orphan(self):
        """A thread timeout does not kill a process tree. This proves the group dies."""
        marker = self.tmp / "orphan-marker"
        exe = write_exe(self.tmp / "hang", f'sleep 45 && touch "{marker}"')
        t0 = time.time()
        with self.assertRaises(RuntimeError) as e:
            rt.cli_lane({"command": str(exe), "args": ["-p"], "timeout": 2}, "hi")
        self.assertIn("timed out", str(e.exception))
        self.assertLess(time.time() - t0, 15, "did not return promptly on timeout")
        time.sleep(3)
        self.assertFalse(marker.exists(), "child survived the kill and kept running")

    def test_nonzero_exit_is_an_error(self):
        exe = write_exe(self.tmp / "fail", 'echo "boom" >&2; exit 3')
        with self.assertRaises(RuntimeError) as e:
            rt.cli_lane({"command": str(exe), "args": ["-p"], "timeout": 10}, "hi")
        self.assertIn("exit 3", str(e.exception))

    def test_empty_output_is_an_error_not_a_pass(self):
        exe = write_exe(self.tmp / "quiet", 'true')
        with self.assertRaises(RuntimeError):
            rt.cli_lane({"command": str(exe), "args": ["-p"], "timeout": 10}, "hi")


class TestSecrets(unittest.TestCase):
    def test_missing_pass_entry_aborts_the_run(self):
        """It must never proceed unauthenticated."""
        lanes = [{"name": "A", "harness": "http", "model": "m",
                  "base_url": "http://127.0.0.1:1/v1",
                  "key_entry": "definitely/not/a/real/entry/xyzzy"}]
        with self.assertRaises(SystemExit) as e:
            rt.fetch_keys(lanes)
        self.assertIn("xyzzy", str(e.exception))

    def test_lanes_without_keys_need_no_pass(self):
        self.assertEqual(rt.fetch_keys([{"name": "A", "harness": "cli"}]), {})


class TestPricing(unittest.TestCase):
    def test_cli_and_acp_lanes_are_free(self):
        for h in ("cli", "acp"):
            self.assertEqual(rt.lane_prices({"harness": h, "model": "x"}, {}), (0.0, 0.0))

    def test_config_price_overrides_the_table(self):
        pin, pout = rt.lane_prices(
            {"harness": "http", "model": "x", "price_per_mtok": 2.0}, {"x": (9.9, 9.9)})
        self.assertAlmostEqual(pin, 2.0 / 1_000_000)

    def test_estimate_assumes_full_max_tokens(self):
        # Worst case, so the budget binds before the spend rather than after.
        lanes = [{"name": "A", "harness": "http", "model": "x", "max_tokens": 1000}]
        est = rt.estimate_run(lanes, "a" * 400, {"x": (0.0, 1e-6)}, {})
        self.assertAlmostEqual(est, 1000 * 1e-6, places=9)

    def test_free_lanes_contribute_nothing(self):
        lanes = [{"name": "A", "harness": "cli", "model": "x", "max_tokens": 99999}]
        self.assertEqual(rt.estimate_run(lanes, "hello", {}, {}), 0.0)


class TestEndToEnd(unittest.TestCase):
    """Exit codes, via the real CLI entry point."""

    def _run(self, lanes, *args, extra_cfg=None):
        d = Path(tempfile.mkdtemp())
        cfg = {"lanes": lanes}
        cfg.update(extra_cfg or {})
        (d / "c.yaml").write_text(json.dumps(cfg))
        return subprocess.run(
            [sys.executable, str(ROOT / "roundtable"), "--config", str(d / "c.yaml"),
             "--no-transcript", *args, "brief"],
            capture_output=True, text=True, timeout=90,
        )

    def test_all_answered_exits_zero(self):
        with StubServer() as s:
            r = self._run([{"name": "A", "harness": "http", "model": "m", "base_url": s.url}])
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_a_silent_lane_fails_the_run(self):
        """Partial delivery is the bug this tool exists to eliminate."""
        with StubServer() as s:
            r = self._run([
                {"name": "Good", "harness": "http", "model": "m", "base_url": s.url},
                {"name": "Mute", "harness": "http", "model": "empty", "base_url": s.url},
            ])
            self.assertEqual(r.returncode, 1)
            self.assertIn("FAILED  Mute", r.stdout)

    def test_budget_refuses_before_dispatch(self):
        with StubServer() as s:
            r = self._run(
                [{"name": "A", "harness": "http", "model": "m", "base_url": s.url,
                  "price_per_mtok": 1000.0, "max_tokens": 2000}],
                "--max-spend", "0.001")
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("refusing to dispatch", r.stderr)
            self.assertIsNone(s.srv.last_request, "dispatched despite being over budget")

    def test_list_makes_no_network_calls(self):
        with StubServer() as s:
            r = self._run([{"name": "A", "harness": "http", "model": "m", "base_url": s.url}],
                          "--list")
            self.assertEqual(r.returncode, 0)
            self.assertIsNone(s.srv.last_request)


if __name__ == "__main__":
    unittest.main(verbosity=2)
