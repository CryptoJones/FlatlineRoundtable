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
import shutil
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
        if model == "reasoned_away_once":
            self.server.hits[model] = self.server.hits.get(model, 0) + 1
            if self.server.hits[model] == 1:
                self._send(200, {
                    "choices": [{"message": {"content": "", "reasoning": "thinking..."},
                                 "finish_reason": "length"}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 60},
                })
                return
            self._send(200, {"choices": [{"message": {"content": "recovered"},
                                          "finish_reason": "stop"}]})
            return
        if model == "reasoned_away":
            # Captured live from two vendors: the whole budget went to
            # `reasoning` and no content was ever emitted.
            self.server.hits[model] = self.server.hits.get(model, 0) + 1
            self._send(200, {
                "choices": [{"message": {"content": "", "reasoning": "thinking..."},
                             "finish_reason": "length"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 60,
                          "completion_tokens_details": {"reasoning_tokens": 60}},
            })
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


PRINTF_ANSI = "printf '\\033[32mgreen\\033[0m answer\\n'\n"
PRINTF_EMOJI = "printf '\\xf0\\x9f\\x95\\x90 the answer\\n'\n"
PRINTF_BANNER = "printf '>> updating\\nreal answer\\n'\n"


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

    def _loads(self, lanes):
        return rt.load_config(self._cfg(lanes))

    def test_rejects_unknown_harness(self):
        self._dies([{"name": "A", "harness": "carrier-pigeon"}], "harness must be")

    def test_rejects_http_lane_without_base_url(self):
        self._dies([{"name": "A", "harness": "http", "model": "m"}], "needs base_url")

    def test_a_yaml_boolean_name_is_explained_not_just_rejected(self):
        """#29: `name: Off` arrives as False and reported "has no name" -- an
        error naming neither the cause nor the fix."""
        f = Path(tempfile.mkdtemp()) / "c.yaml"
        f.write_text("lanes:\n  - name: Off\n    harness: cli\n"
                     "    command: x\n    args: ['-p']\n    stdin: true\n")
        with self.assertRaises(SystemExit) as e:
            rt.load_config(f)
        msg = str(e.exception)
        self.assertIn("name must be a string", msg)
        self.assertIn("quote the name", msg)

    def test_yes_and_on_are_caught_too(self):
        for word in ("Yes", "On", "No"):
            with self.subTest(word=word):
                f = Path(tempfile.mkdtemp()) / "c.yaml"
                f.write_text(f"lanes:\n  - name: {word}\n    harness: cli\n"
                             "    command: x\n    args: ['-p']\n    stdin: true\n")
                with self.assertRaises(SystemExit) as e:
                    rt.load_config(f)
                self.assertIn("name must be a string", str(e.exception))

    def test_a_quoted_boolean_word_is_a_valid_name(self):
        f = Path(tempfile.mkdtemp()) / "c.yaml"
        f.write_text('lanes:\n  - name: "Off"\n    harness: cli\n'
                     "    command: x\n    args: ['-p']\n    stdin: true\n")
        self.assertEqual(rt.load_config(f)["lanes"][0]["name"], "Off")

    def test_rejects_duplicate_lane_names(self):
        self._dies(
            [{"name": "A", "harness": "cli", "command": "x", "args": ["-p"], "stdin": True},
             {"name": "A", "harness": "cli", "command": "x", "args": ["-p"], "stdin": True}],
            "duplicate lane name",
        )

    def test_extra_body_cannot_override_the_request(self):
        # A config typo here would silently send a call you did not intend.
        self._dies(
            [{"name": "A", "harness": "http", "model": "m", "base_url": "http://x/v1",
              "extra_body": {"model": "something-else"}}],
            "extra_body may not set",
        )

    def test_cli_lane_must_actually_deliver_the_prompt(self):
        """#20: args non-empty was the only check, so a lane could send nothing.

        The dangerous outcome is not the CLI erroring -- that fails loudly. It is
        a CLI answering an empty prompt with something plausible, giving a lane
        that counts as a vote without having seen the question.
        """
        self._dies([{"name": "A", "harness": "cli", "command": "x", "args": ["-p"]}],
                   "would send no prompt")

    def test_prompt_placeholder_satisfies_the_check(self):
        cfg = self._loads([{"name": "A", "harness": "cli", "command": "x",
                            "args": ["-p", "{prompt}"]}])
        self.assertEqual(cfg["lanes"][0]["name"], "A")

    def test_stdin_satisfies_the_check(self):
        cfg = self._loads([{"name": "A", "harness": "cli", "command": "x",
                            "args": ["-p"], "stdin": True}])
        self.assertEqual(cfg["lanes"][0]["name"], "A")

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

    def test_a_reasoning_overshoot_is_retried(self):
        """#53, correcting #46.

        #46 assumed this shape was deterministic and skipped its retry. It is
        not: reasoning usage is a distribution. The same lane, same brief, same
        max_tokens came back empty 5 times in 10, so a retry is another draw and
        wins about half the time at the margin."""
        self._no_sleep()
        with StubServer() as s:
            with self.assertRaises(RuntimeError):
                rt.http_lane({"model": "reasoned_away", "base_url": s.url,
                              "timeout": 10}, "hi", None, 3)
            self.assertEqual(s.srv.hits["reasoned_away"], 4,
                             "an overshoot must get its retries like any empty answer")

    def test_a_reasoning_overshoot_recovers_when_a_later_draw_fits(self):
        """The whole point: the next draw often does fit."""
        self._no_sleep()
        with StubServer() as s:
            out = rt.http_lane({"model": "reasoned_away_once", "base_url": s.url,
                                "timeout": 10}, "hi", None, 2)
            self.assertEqual(out["answer"], "recovered")
            self.assertEqual(s.srv.hits["reasoned_away_once"], 2)

    def test_an_exhausted_overshoot_names_max_tokens(self):
        """What #46 got right and this keeps: "empty answer" points at the
        vendor; max_tokens is the number the operator can actually change."""
        self._no_sleep()
        with StubServer() as s:
            with self.assertRaises(RuntimeError) as e:
                rt.http_lane({"model": "reasoned_away", "base_url": s.url,
                              "timeout": 10}, "hi", None, 1)
            self.assertIn("raise max_tokens", str(e.exception))

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

    def test_retry_after_parses_the_forms_vendors_actually_send(self):
        """#30: `.isdigit()` accepted neither legal form reliably."""
        self.assertEqual(rt.parse_retry_after("60"), 60.0)
        self.assertEqual(rt.parse_retry_after("1.5"), 1.5)     # was silently ignored
        self.assertEqual(rt.parse_retry_after("  30  "), 30.0)
        self.assertIsNone(rt.parse_retry_after(None))
        self.assertIsNone(rt.parse_retry_after(""))
        self.assertIsNone(rt.parse_retry_after("soon"))

    def test_retry_after_accepts_the_http_date_form(self):
        import datetime as dt, email.utils
        when = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=45)
        got = rt.parse_retry_after(email.utils.format_datetime(when))
        self.assertIsNotNone(got)
        self.assertGreater(got, 30)
        self.assertLess(got, 60)

    def test_a_retry_after_date_in_the_past_is_not_negative(self):
        import datetime as dt, email.utils
        when = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=120)
        self.assertEqual(rt.parse_retry_after(email.utils.format_datetime(when)), 0.0)

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
            out = rt.cli_lane({"command": str(exe), "args": ["-p"], "stdin": True, "timeout": 10}, "hi")
        finally:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        self.assertIn("KEY=[unset]", out["answer"])
        self.assertNotIn("leaked-would-bill", out["answer"])

    def test_bedrock_and_vertex_routes_are_scrubbed(self):
        """#22: these bill via ambient cloud credentials, with no API key.

        A key-only denylist does nothing about them, so the "free lane silently
        becomes a paid one" failure had a second door.
        """
        for var in ("CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX",
                    "ANTHROPIC_BASE_URL", "GOOGLE_GENAI_USE_VERTEXAI"):
            with self.subTest(var=var):
                os.environ[var] = "1"
                self.addCleanup(os.environ.pop, var, None)
                self.assertNotIn(var, rt.child_env({}))

    def test_unknown_vendor_key_shapes_are_scrubbed_by_pattern(self):
        # The roster spans vendors whose variables are not named in SCRUB_ENV.
        for var in ("MISTRAL_API_KEY", "COHERE_API_KEY", "SOMEVENDOR_AUTH_TOKEN",
                    "SOMEVENDOR_BASE_URL"):
            with self.subTest(var=var):
                os.environ[var] = "x"
                self.addCleanup(os.environ.pop, var, None)
                self.assertNotIn(var, rt.child_env({}))

    def test_a_lane_can_scrub_extra_variables(self):
        os.environ["WEIRD_VENDOR_TOKEN"] = "x"
        self.addCleanup(os.environ.pop, "WEIRD_VENDOR_TOKEN", None)
        self.assertIn("WEIRD_VENDOR_TOKEN", rt.child_env({}))
        self.assertNotIn("WEIRD_VENDOR_TOKEN",
                         rt.child_env({"scrub_env": ["WEIRD_VENDOR_TOKEN"]}))

    def test_ordinary_environment_survives_the_scrub(self):
        # Over-scrubbing fails a lane loudly, but PATH still has to get through.
        env = rt.child_env({})
        self.assertIn("PATH", env)
        self.assertEqual(env["NO_COLOR"], "1")

    def test_hung_lane_is_killed_and_leaves_no_orphan(self):
        """A thread timeout does not kill a process tree. This proves the group dies."""
        marker = self.tmp / "orphan-marker"
        exe = write_exe(self.tmp / "hang", f'sleep 45 && touch "{marker}"')
        t0 = time.time()
        with self.assertRaises(RuntimeError) as e:
            rt.cli_lane({"command": str(exe), "args": ["-p"], "stdin": True, "timeout": 2}, "hi")
        self.assertIn("timed out", str(e.exception))
        self.assertLess(time.time() - t0, 15, "did not return promptly on timeout")
        time.sleep(3)
        self.assertFalse(marker.exists(), "child survived the kill and kept running")

    def test_ansi_escapes_are_stripped_not_whole_lines(self):
        """#28: the old filter dropped any line starting with an escape byte --
        and with one machine's clock emoji. Deleting an answer line to dodge a
        banner is the wrong trade in a tool that flags clipped answers."""
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        exe = write_exe(d / "cli", PRINTF_ANSI)
        out = rt.cli_lane({"command": str(exe), "args": ["-p"], "stdin": True,
                           "timeout": 10}, "hi")
        self.assertEqual(out["answer"], "green answer")

    def test_an_answer_starting_with_an_emoji_survives(self):
        # The hardcoded clock emoji deleted any line beginning with it, so a
        # lane answering with an emoji, bullet or flag lost that line.
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        exe = write_exe(d / "cli", PRINTF_EMOJI)
        out = rt.cli_lane({"command": str(exe), "args": ["-p"], "stdin": True,
                           "timeout": 10}, "hi")
        self.assertIn("the answer", out["answer"])

    def test_a_lane_may_declare_its_own_banner_prefixes(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        exe = write_exe(d / "cli", PRINTF_BANNER)
        out = rt.cli_lane({"command": str(exe), "args": ["-p"], "stdin": True,
                           "timeout": 10, "strip_prefixes": [">>"]}, "hi")
        self.assertEqual(out["answer"], "real answer")

    def test_nonzero_exit_is_an_error(self):
        exe = write_exe(self.tmp / "fail", 'echo "boom" >&2; exit 3')
        with self.assertRaises(RuntimeError) as e:
            rt.cli_lane({"command": str(exe), "args": ["-p"], "stdin": True, "timeout": 10}, "hi")
        self.assertIn("exit 3", str(e.exception))

    def test_empty_output_is_an_error_not_a_pass(self):
        exe = write_exe(self.tmp / "quiet", 'true')
        with self.assertRaises(RuntimeError):
            rt.cli_lane({"command": str(exe), "args": ["-p"], "stdin": True, "timeout": 10}, "hi")


class TestSynthesis(unittest.TestCase):
    """--diff runs two readers, and compares them mechanically.

    One reader cannot show its own bias: with a single reading you cannot tell a
    real split from that model's taste in splits. Comparing the two with a THIRD
    model would just move the problem, so the comparison is structural.
    """

    LANES = [
        {"name": "Cli",   "harness": "cli",  "vendor": "anthropic", "model": "sonnet"},
        {"name": "Free",  "harness": "http", "vendor": "openrouter", "model": "x/y:free"},
        {"name": "Paid",  "harness": "http", "vendor": "mistral",    "model": "big"},
        {"name": "Free2", "harness": "http", "vendor": "openrouter", "model": "z/w:free"},
    ]

    def test_prefers_free_lanes_and_spreads_across_vendors(self):
        got = rt.pick_synthesizers(self.LANES, None, 2)
        self.assertEqual([l["name"] for l in got], ["Cli", "Free"])
        self.assertEqual(len({l["vendor"] for l in got}), 2)

    def test_an_explicit_synthesizer_is_kept_and_joined_by_another_vendor(self):
        got = rt.pick_synthesizers(self.LANES, "Paid", 2)
        self.assertEqual(got[0]["name"], "Paid")
        self.assertNotEqual(got[1]["vendor"], "mistral")

    def test_repeats_a_vendor_only_when_spread_cannot_fill_the_quota(self):
        two_lanes = [l for l in self.LANES if l["vendor"] == "openrouter"]
        got = rt.pick_synthesizers(two_lanes, None, 2)
        self.assertEqual(len(got), 2)      # correlated beats having only one

    def test_never_returns_more_than_asked(self):
        self.assertEqual(len(rt.pick_synthesizers(self.LANES, None, 1)), 1)

    def test_acp_ranks_as_free_like_cli(self):
        # lane_prices treats acp as free; rank used to put it alongside metered
        # http, making reader choice depend on roster order.
        lanes = [{"name": "Paid", "harness": "http", "vendor": "m", "model": "big"},
                 {"name": "Acp",  "harness": "acp",  "vendor": "p", "model": "x"}]
        self.assertEqual(rt.pick_synthesizers(lanes, None, 1)[0]["name"], "Acp")
        self.assertEqual(rt.pick_synthesizers(list(reversed(lanes)), None, 1)[0]["name"], "Acp")

    def test_synthesis_cost_is_estimated_before_dispatch(self):
        lanes = [{"name": f"L{i}", "harness": "http", "vendor": f"v{i}",
                  "model": "paid", "max_tokens": 2000} for i in range(3)]
        table = {"paid": (1.0, 1.0)}
        est = rt.estimate_synthesis(lanes, "brief", table, {}, {}, None, 2)
        self.assertGreater(est, 0)

    def test_synthesis_estimate_scales_with_reader_count(self):
        lanes = [{"name": f"L{i}", "harness": "http", "vendor": f"v{i}",
                  "model": "paid", "max_tokens": 2000} for i in range(3)]
        table = {"paid": (1.0, 1.0)}
        one = rt.estimate_synthesis(lanes, "brief", table, {}, {}, None, 1)
        two = rt.estimate_synthesis(lanes, "brief", table, {}, {}, None, 2)
        self.assertGreater(two, one)

    def test_free_readers_estimate_to_nothing(self):
        lanes = [{"name": "Cli", "harness": "cli", "vendor": "a", "model": "sonnet"},
                 {"name": "Acp", "harness": "acp", "vendor": "b", "model": "x"}]
        self.assertEqual(
            rt.estimate_synthesis(lanes, "brief", {"sonnet": (1.0, 1.0)}, {}, {}, None, 2),
            0.0)

    def test_synthesis_spend_lands_in_the_run_total(self):
        """The hole in #19: synthesis tokens never reached `spent`."""
        with StubServer() as s:
            lanes = [{"name": f"L{i}", "harness": "http", "vendor": f"v{i}",
                      "model": "m", "base_url": s.url, "timeout": 10}
                     for i in range(2)]
            results = [{"lane": "L0", "model": "m", "answer": "a", "usage": {}},
                       {"lane": "L1", "model": "m", "answer": "b", "usage": {}}]
            spent = [0.0]
            synth, err = rt.synthesize(
                results, "brief", {}, lanes, {}, {"m": (1.0, 1.0)}, count=2,
                sems={}, lock=threading.Lock(), spent=spent, retries=0)
            self.assertIsNone(err)
            self.assertEqual(len(synth["readings"]), 2)
        self.assertGreater(spent[0], 0.0)

    def test_a_reader_failing_reports_rather_than_raising(self):
        with StubServer() as s:
            lanes = [{"name": "Good", "harness": "http", "vendor": "a",
                      "model": "m", "base_url": s.url, "timeout": 10},
                     {"name": "Bad", "harness": "http", "vendor": "b",
                      "model": "always_error_body", "base_url": s.url, "timeout": 10}]
            results = [{"lane": "X", "model": "m", "answer": "a"},
                       {"lane": "Y", "model": "m", "answer": "b"}]
            synth, err = rt.synthesize(
                results, "brief", {}, lanes, {}, {}, count=2,
                sems={}, lock=threading.Lock(), spent=[0.0], retries=0)
        self.assertIsNone(err)
        self.assertEqual(len(synth["readings"]), 1)
        self.assertEqual(len(synth["errors"]), 1)

    def test_classify_mentions_buckets_lanes_by_section(self):
        text = ("AGREED\nAlpha and Beta both say yes.\n"
                "SPLIT\nGamma disagrees.\n"
                "LONE CLAIMS\nDelta invented a number.")
        got = rt.classify_mentions(text, ["Alpha", "Beta", "Gamma", "Delta"])
        self.assertEqual(got["Alpha"], ["AGREED"])
        self.assertEqual(got["Gamma"], ["SPLIT"])
        self.assertEqual(got["Delta"], ["LONE CLAIMS"])

    def test_a_preamble_restating_the_headings_does_not_relocate_lanes(self):
        """The regression from #18.

        Anchoring on the first occurrence of each marker anywhere in the text
        meant a reader that opened by restating its instructions put all three
        markers in its preamble, and every lane fell into whichever section came
        last. Models restating instructions is the common case.
        """
        body = ("AGREED\nAlpha and Beta agree.\n"
                "SPLIT\nGamma dissents.\n"
                "LONE CLAIMS\nDelta invented a number.")
        pre = "I will report AGREED, SPLIT and LONE CLAIMS below.\n\n" + body
        self.assertEqual(rt.classify_mentions(pre, ["Alpha", "Beta", "Gamma", "Delta"]),
                         rt.classify_mentions(body, ["Alpha", "Beta", "Gamma", "Delta"]))

    def test_a_preamble_does_not_manufacture_conflicts(self):
        # The output this protects is THE READERS DISAGREE, which is trusted
        # precisely because it is mechanical.
        body = "AGREED\nAlpha\nSPLIT\nBeta\nLONE CLAIMS\nGamma"
        pre = "Reporting AGREED, SPLIT and LONE CLAIMS.\n\n" + body
        conflicts = rt.compare_readings(
            [{"by": "R1", "text": pre}, {"by": "R2", "text": body}],
            ["Alpha", "Beta", "Gamma"])
        self.assertEqual(conflicts, [])

    def test_lane_names_match_on_word_boundaries(self):
        # `Chair` must not be claimed by the word "Chairman".
        got = rt.classify_mentions(
            "AGREED\nThe Chairman objected.\nSPLIT\nChair dissents.", ["Chair"])
        self.assertEqual(got, {"Chair": ["SPLIT"]})

    def test_headers_are_recognised_in_the_shapes_models_emit(self):
        got = rt.classify_mentions(
            "## 1. AGREED\nAlpha\n\n**SPLIT**\nBeta\n\n### 3) LONE CLAIMS\nGamma",
            ["Alpha", "Beta", "Gamma"])
        self.assertEqual(got, {"Alpha": ["AGREED"], "Beta": ["SPLIT"],
                               "Gamma": ["LONE CLAIMS"]})

    def test_a_heading_word_used_mid_sentence_is_not_a_header(self):
        # "they agreed" / "the split" in prose must not open a section.
        got = rt.classify_mentions(
            "AGREED\nAlpha and Beta agreed, and the split was minor. Beta held.",
            ["Alpha", "Beta"])
        self.assertEqual(got, {"Alpha": ["AGREED"], "Beta": ["AGREED"]})

    def test_classify_mentions_survives_an_unstructured_reading(self):
        # A model that ignores the format must not crash the comparison.
        self.assertEqual(rt.classify_mentions("they all basically agree", ["Alpha"]), {})
        self.assertEqual(rt.classify_mentions("", ["Alpha"]), {})

    def test_conflicts_are_reported_when_readers_disagree(self):
        readings = [
            {"by": "R1", "text": "AGREED\nAlpha\nSPLIT\nBeta"},
            {"by": "R2", "text": "AGREED\nBeta\nSPLIT\nAlpha"},
        ]
        got = rt.compare_readings(readings, ["Alpha", "Beta"])
        self.assertEqual({c["lane"] for c in got}, {"Alpha", "Beta"})

    def test_overlapping_placements_are_not_a_conflict(self):
        """#51: readers differ in how liberally they name lanes.

        One writes "all four land on the same core" and names every lane in every
        section; another names lanes only under LONE CLAIMS. Observed live on a
        panel whose own reader said "no genuine disagreement" -- and every lane
        was flagged."""
        readings = [
            {"by": "Wordy", "text": "AGREED\nAlpha\nSPLIT\nAlpha\nLONE CLAIMS\nAlpha"},
            {"by": "Terse", "text": "AGREED\nnobody named\nLONE CLAIMS\nAlpha"},
        ]
        self.assertEqual(rt.compare_readings(readings, ["Alpha"]), [])

    def test_disjoint_placements_are_still_a_conflict(self):
        readings = [
            {"by": "R1", "text": "AGREED\nAlpha"},
            {"by": "R2", "text": "SPLIT\nAlpha"},
        ]
        got = rt.compare_readings(readings, ["Alpha"])
        self.assertEqual([c["lane"] for c in got], ["Alpha"])

    def test_one_reader_silent_on_a_lane_is_not_a_conflict(self):
        readings = [
            {"by": "R1", "text": "AGREED\nAlpha"},
            {"by": "R2", "text": "AGREED\nsomething else entirely"},
        ]
        self.assertEqual(rt.compare_readings(readings, ["Alpha"]), [])

    def test_no_conflict_when_readers_agree(self):
        readings = [
            {"by": "R1", "text": "AGREED\nAlpha\nSPLIT\nBeta"},
            {"by": "R2", "text": "AGREED\nAlpha\nSPLIT\nBeta"},
        ]
        self.assertEqual(rt.compare_readings(readings, ["Alpha", "Beta"]), [])

    def test_a_single_reading_yields_no_conflicts(self):
        readings = [{"by": "R1", "text": "AGREED\nAlpha"}]
        self.assertEqual(rt.compare_readings(readings, ["Alpha"]), [])


class TestTokenCalibration(unittest.TestCase):
    """The pre-flight estimate measures itself instead of assuming 4 chars/token.

    The budget check refuses runs that would overspend, so the one thing this
    must never do is come in *under* the truth.
    """

    def setUp(self):
        self.cache = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.cache, True)
        self._orig = rt.TOKENIZER_CACHE
        rt.TOKENIZER_CACHE = self.cache / "tokens.json"
        self.addCleanup(lambda: setattr(rt, "TOKENIZER_CACHE", self._orig))

    def test_unmeasured_model_uses_the_pessimistic_constant(self):
        self.assertEqual(rt.chars_per_token("never-seen", {}), rt.CHARS_PER_TOKEN)

    def test_too_few_samples_still_uses_the_constant(self):
        calib = {"m": {"chars": 400, "tokens": 100, "samples": 1}}
        self.assertEqual(rt.chars_per_token("m", calib), rt.CHARS_PER_TOKEN)

    def test_measured_ratio_is_used_once_there_are_enough_samples(self):
        # 300 chars for 100 tokens = 3.0, shrunk by the safety factor.
        calib = {"m": {"chars": 300, "tokens": 100, "samples": 5}}
        self.assertAlmostEqual(rt.chars_per_token("m", calib),
                               3.0 * rt.CALIBRATION_SAFETY)

    def test_the_safety_factor_errs_high_never_low(self):
        # A measured ratio must translate into an estimate at or above the one
        # the raw measurement implies -- fewer chars per token means more
        # tokens, means a bigger number.
        calib = {"m": {"chars": 300, "tokens": 100, "samples": 5}}
        self.assertLess(rt.chars_per_token("m", calib), 3.0)

    def test_a_corrupt_cache_is_ignored_not_fatal(self):
        rt.TOKENIZER_CACHE.parent.mkdir(parents=True, exist_ok=True)
        rt.TOKENIZER_CACHE.write_text("{ this is not json")
        self.assertEqual(rt.load_calibration(), {})

    def test_recording_accumulates_across_runs(self):
        lanes = [{"name": "A", "model": "m", "personality": "x" * 100}]
        results = [{"lane": "A", "model": "m", "usage": {"prompt_tokens": 50}}]
        rt.record_calibration(results, "y" * 100, lanes)
        rt.record_calibration(results, "y" * 100, lanes)
        calib = rt.load_calibration()
        self.assertEqual(calib["m"]["samples"], 2)
        self.assertEqual(calib["m"]["chars"], 400)     # (100 + 100) * 2
        self.assertEqual(calib["m"]["tokens"], 100)    # 50 * 2

    def test_lanes_without_usage_are_not_recorded(self):
        # cli/acp lanes report no usage; recording a zero would skew the ratio.
        lanes = [{"name": "A", "model": "m"}]
        rt.record_calibration([{"lane": "A", "model": "m", "usage": None}], "hi", lanes)
        self.assertEqual(rt.load_calibration(), {})

    def test_estimate_shrinks_once_a_model_is_measured(self):
        lanes = [{"name": "A", "harness": "http", "model": "m", "max_tokens": 0}]
        table = {"m": (1.0, 0.0)}          # price the prompt side only
        prompt = "z" * 4000
        naive = rt.estimate_run(lanes, prompt, table, {}, {})
        measured = rt.estimate_run(
            lanes, prompt, table, {}, {"m": {"chars": 8000, "tokens": 1000, "samples": 9}})
        # 8 chars/token measured vs the constant 4: half the tokens, half the cost.
        self.assertLess(measured, naive)


class TestVendorSemaphores(unittest.TestCase):
    """#21: the cap must be the smallest in the group, not the first listed."""

    def _slots(self, sem):
        n = 0
        while sem.acquire(blocking=False):
            n += 1
        return n

    def test_the_strictest_lane_wins_regardless_of_order(self):
        loose = {"name": "A", "vendor": "local"}                    # default 8
        strict = {"name": "B", "vendor": "local", "concurrency": 1}
        for roster in ([loose, strict], [strict, loose]):
            sems = rt.build_semaphores(roster, 8)
            self.assertEqual(self._slots(sems["local"]), 1,
                             "a concurrency:1 lane must cap its whole vendor group")

    def test_vendors_are_capped_independently(self):
        sems = rt.build_semaphores(
            [{"name": "A", "vendor": "local", "concurrency": 1},
             {"name": "B", "vendor": "openrouter"}], 8)
        self.assertEqual(self._slots(sems["local"]), 1)
        self.assertEqual(self._slots(sems["openrouter"]), 8)

    def test_a_lane_without_a_vendor_is_its_own_group(self):
        sems = rt.build_semaphores([{"name": "Solo", "concurrency": 2}], 8)
        self.assertEqual(self._slots(sems["Solo"]), 2)

    def test_the_default_applies_when_no_lane_sets_one(self):
        sems = rt.build_semaphores([{"name": "A", "vendor": "v"}], 3)
        self.assertEqual(self._slots(sems["v"]), 3)
class TestLineageCollisions(unittest.TestCase):
    """#23: convergence between two lanes that are the same model is an echo.

    Every other guard protects the plumbing of the independence claim. This one
    protects the claim.
    """

    LANES = [{"name": "A"}, {"name": "B"}, {"name": "C"}]

    def test_same_provider_and_model_collide(self):
        results = [
            {"lane": "A", "answer": "x", "served_by": "DeepInfra", "model": "m"},
            {"lane": "B", "answer": "y", "served_by": "DeepInfra", "model": "m"},
            {"lane": "C", "answer": "z", "served_by": "Novita", "model": "other"},
        ]
        got = rt.lineage_collisions(results, self.LANES)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["lanes"], ["A", "B"])
        self.assertIn("DeepInfra", got[0]["detail"])

    def test_same_provider_different_model_does_not_collide(self):
        results = [
            {"lane": "A", "answer": "x", "served_by": "DeepInfra", "model": "m1"},
            {"lane": "B", "answer": "y", "served_by": "DeepInfra", "model": "m2"},
        ]
        self.assertEqual(rt.lineage_collisions(results, self.LANES), [])

    def test_declared_lineage_collides_across_providers(self):
        # The point of the field: two Qwen derivatives served by different
        # gateways still share priors.
        lanes = [{"name": "A", "lineage": "qwen"}, {"name": "B", "lineage": "qwen"},
                 {"name": "C", "lineage": "mistral"}]
        results = [
            {"lane": "A", "answer": "x", "served_by": "Alibaba", "model": "q1"},
            {"lane": "B", "answer": "y", "served_by": "DeepInfra", "model": "q2"},
            {"lane": "C", "answer": "z", "served_by": "Mistral", "model": "m"},
        ]
        got = rt.lineage_collisions(results, lanes)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["lanes"], ["A", "B"])
        self.assertEqual(got[0]["kind"], "lineage")

    def test_a_failed_lane_cannot_collide(self):
        results = [
            {"lane": "A", "answer": "x", "served_by": "DeepInfra", "model": "m"},
            {"lane": "B", "answer": None, "served_by": "DeepInfra", "model": "m"},
        ]
        self.assertEqual(rt.lineage_collisions(results, self.LANES), [])

    def test_unknown_provider_is_not_a_collision(self):
        # cli/acp lanes and any endpoint that does not name a provider.
        results = [
            {"lane": "A", "answer": "x", "served_by": None, "model": "m"},
            {"lane": "B", "answer": "y", "served_by": None, "model": "m"},
        ]
        self.assertEqual(rt.lineage_collisions(results, self.LANES), [])

    def test_lineage_must_be_a_string(self):
        f = Path(tempfile.mkdtemp()) / "c.yaml"
        f.write_text(json.dumps({"lanes": [
            {"name": "A", "harness": "http", "model": "m",
             "base_url": "http://x/v1", "lineage": 3}]}))
        with self.assertRaises(SystemExit) as e:
            rt.load_config(f)
        self.assertIn("lineage must be a string", str(e.exception))


class TestPacer(unittest.TestCase):
    """Proactive per-vendor pacing.

    The semaphore bounds how many requests are in flight; this bounds how fast
    they start. A vendor's per-minute cap is tripped by the second quantity, and
    can be tripped before any 429 arrives to warn us.
    """

    def test_first_call_does_not_wait(self):
        self.assertEqual(rt.Pacer(5.0).wait(), 0.0)

    def test_subsequent_calls_are_spaced(self):
        p = rt.Pacer(0.25)
        p.wait()
        t0 = time.monotonic()
        p.wait()
        self.assertGreaterEqual(time.monotonic() - t0, 0.2)

    def test_zero_interval_never_waits(self):
        p = rt.Pacer(0)
        self.assertEqual(p.wait(), 0.0)
        self.assertEqual(p.wait(), 0.0)

    def test_slots_are_handed_out_without_overlap(self):
        # Under concurrency the reservations must still be distinct, or the
        # burst this exists to prevent happens anyway.
        p = rt.Pacer(0.05)
        waits = []
        lk = threading.Lock()

        def go():
            w = p.wait()
            with lk:
                waits.append(w)

        threads = [threading.Thread(target=go) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(waits), 6)
        # Six slots 0.05s apart: the last one waits at least 4 intervals.
        self.assertGreaterEqual(max(waits), 0.2)

    def test_pacers_are_per_vendor_and_take_the_smallest_rpm(self):
        pacers = rt.build_pacers([
            {"name": "A", "vendor": "openrouter", "rpm": 60},
            {"name": "B", "vendor": "openrouter", "rpm": 20},   # stricter wins
            {"name": "C", "vendor": "local"},                   # no rpm, no pacer
        ])
        self.assertEqual(set(pacers), {"openrouter"})
        self.assertAlmostEqual(pacers["openrouter"].interval, 3.0)

    def test_a_lane_without_a_vendor_paces_under_its_own_name(self):
        pacers = rt.build_pacers([{"name": "Solo", "rpm": 30}])
        self.assertAlmostEqual(pacers["Solo"].interval, 2.0)

    def test_rpm_must_be_positive(self):
        for bad in (0, -5):
            with self.assertRaises(SystemExit):
                _write_cfg_and_load(self, rpm=bad)

    def test_rpm_must_be_a_number(self):
        with self.assertRaises(SystemExit):
            _write_cfg_and_load(self, rpm="soon")


def _write_cfg_and_load(case, rpm):
    d = Path(tempfile.mkdtemp())
    case.addCleanup(shutil.rmtree, d, True)
    p = d / "cfg.yaml"
    p.write_text(textwrap.dedent(f"""
        lanes:
          - name: A
            vendor: openrouter
            harness: http
            model: m
            base_url: http://127.0.0.1:1/v1
            rpm: {rpm!r}
    """).lstrip())
    return rt.load_config(p)


class TestGoldenResponses(unittest.TestCase):
    """Replay real vendor responses through the real parsing path (#13).

    The stub elsewhere in this file is hand-written, so it proves roundtable
    handles the shape we *think* vendors return. These are captured from live
    endpoints, so they prove it handles the shape they actually returned -- and
    they fail if a vendor moves a field, which the stub never would.

    Recapture with scripts/capture-fixtures.py when a vendor changes.
    """

    FIXTURES = sorted((ROOT / "tests" / "fixtures" / "responses").glob("*.json"))

    def _serve(self, payload):
        """A server that returns exactly these bytes, so http_lane does the
        parsing rather than the test."""
        raw = payload.encode()

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        return f"http://127.0.0.1:{srv.server_port}/v1"

    def test_fixtures_exist(self):
        self.assertGreaterEqual(len(self.FIXTURES), 5,
                                "golden fixtures missing -- run scripts/capture-fixtures.py")

    @staticmethod
    def _spent_its_budget(data):
        ch = data["choices"][0]
        return (ch["finish_reason"] == "length"
                and not (ch["message"].get("content") or "").strip())

    def test_every_fixture_parses_into_a_lane_result(self):
        for f in self.FIXTURES:
            payload = f.read_text()
            data = json.loads(payload)
            if self._spent_its_budget(data):
                continue          # covered by the budget-exhausted test below
            with self.subTest(fixture=f.name):
                url = self._serve(payload)
                out = rt.http_lane(
                    {"model": data["model"], "base_url": url, "timeout": 10}, "hi", None, 0)

                expected = (data["choices"][0]["message"].get("content") or "").strip()
                self.assertEqual(out["answer"], expected)
                self.assertEqual(out["finish_reason"], data["choices"][0]["finish_reason"])
                self.assertEqual(out["served_by"], data["provider"])
                self.assertEqual(out["usage"]["prompt_tokens"],
                                 data["usage"]["prompt_tokens"])

    def test_fixtures_carry_the_fields_the_tool_depends_on(self):
        """A shape contract. If a vendor drops one of these, this fails loudly
        instead of the parser failing quietly in production."""
        for f in self.FIXTURES:
            with self.subTest(fixture=f.name):
                d = json.loads(f.read_text())
                self.assertIn("provider", d)            # served_by / lineage detection
                self.assertIn("usage", d)               # spend + calibration
                self.assertIn("prompt_tokens", d["usage"])
                self.assertIn("completion_tokens", d["usage"])
                ch = d["choices"][0]
                self.assertIn("finish_reason", ch)      # truncation detection
                self.assertIn("content", ch["message"])  # may be null; must exist

    def test_fixtures_carry_no_credentials(self):
        for f in self.FIXTURES:
            with self.subTest(fixture=f.name):
                body = f.read_text().lower()
                for needle in ("authorization", "bearer ", "sk-", "api_key", "api-key"):
                    self.assertNotIn(needle, body)

    def test_a_reasoning_model_that_spent_its_budget_is_not_a_pass(self):
        """Two captured fixtures came back finish_reason=length with empty
        content -- the whole token budget went to `reasoning`. That must read as
        a failed lane, not a silent empty answer."""
        spent = [f for f in self.FIXTURES
                 if self._spent_its_budget(json.loads(f.read_text()))]
        self.assertTrue(spent, "expected at least one budget-exhausted fixture")
        for f in spent:
            with self.subTest(fixture=f.name):
                payload = f.read_text()
                url = self._serve(payload)
                # Not an empty answer to be retried -- a deterministic budget
                # failure that names its own fix. Retrying it is `retries` more
                # billed calls, every one certain to fail the same way.
                with self.assertRaises(RuntimeError) as e:
                    rt.http_lane({"model": json.loads(payload)["model"],
                                  "base_url": url, "timeout": 10}, "hi", None, 3)
                self.assertIn("raise max_tokens", str(e.exception))


class TestAcpLane(unittest.TestCase):
    """#24. The acp harness had no test at all, which is how three defects lived
    in one function: it handed the agent the caller's cwd, held stderr in a pipe
    nothing drained, and never reaped the process it killed."""

    AGENT = """            __EXTRA__
            while IFS= read -r line; do
              case "$line" in
                *initialize*)
                    echo '{"jsonrpc":"2.0","id":0,"result":{}}' ;;
                *session/new*)
                    echo '{"jsonrpc":"2.0","id":1,"result":{"sessionId":"s1"}}'
                    pwd > "$RT_CWD_FILE" ;;
                *session/prompt*)
                    echo '{"jsonrpc":"2.0","method":"session/update","params":{"update":{"sessionUpdate":"agent_message_chunk","content":{"text":"hello from acp"}}}}'
                    echo '{"jsonrpc":"2.0","id":2,"result":{"stopReason":"end_turn"}}' ;;
              esac
            done"""

    def _agent(self, extra=""):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        self.cwd_file = d / "cwd.txt"
        os.environ["RT_CWD_FILE"] = str(self.cwd_file)
        self.addCleanup(os.environ.pop, "RT_CWD_FILE", None)
        return write_exe(d / "agent", self.AGENT.replace("__EXTRA__", extra))

    def test_answers_one_turn(self):
        out = rt.acp_lane({"command": str(self._agent()), "args": [], "timeout": 20}, "hi")
        self.assertEqual(out["answer"], "hello from acp")
        self.assertEqual(out["finish_reason"], "stop")

    def test_the_agent_does_not_get_the_callers_cwd(self):
        """A lane must not see context the others cannot -- that is the
        independence claim breaking quietly."""
        exe = self._agent()
        rt.acp_lane({"command": str(exe), "args": [], "timeout": 20}, "hi")
        got = Path(self.cwd_file).read_text().strip()
        self.assertNotEqual(Path(got).resolve(), Path(os.getcwd()).resolve())
        self.assertIn("roundtable-acp-", got)

    def test_a_noisy_agent_does_not_deadlock_on_stderr(self):
        """stderr in an undrained PIPE fills, blocks the writer, and the lane
        'times out' for a reason nothing reports."""
        noisy = 'for i in $(seq 1 5000); do echo "chatter $i chatter $i chatter" >&2; done'
        out = rt.acp_lane(
            {"command": str(self._agent(extra=noisy)), "args": [], "timeout": 30}, "hi")
        self.assertEqual(out["answer"], "hello from acp")

    def test_the_process_is_reaped_not_left_a_zombie(self):
        exe = self._agent()
        rt.acp_lane({"command": str(exe), "args": [], "timeout": 20}, "hi")
        stat = subprocess.run(["ps", "-eo", "stat,command"],
                              capture_output=True, text=True).stdout
        leftover = [l for l in stat.splitlines()
                    if str(exe) in l and l.split()[0].startswith("Z")]
        self.assertEqual(leftover, [], f"zombie left behind: {leftover}")

    def test_the_temp_workdir_is_cleaned_up(self):
        exe = self._agent()
        rt.acp_lane({"command": str(exe), "args": [], "timeout": 20}, "hi")
        used = Path(Path(self.cwd_file).read_text().strip())
        self.assertFalse(used.exists(), "acp workdir outlived the lane")


class TestSecrets(unittest.TestCase):
    def _fake_pass(self, body):
        """Put a stub `pass` first on PATH.

        This test used to depend on the host having a real `pass` installed --
        it passed on a developer machine and failed the moment it ran anywhere
        else, because roundtable dies on "pass is not installed" before it can
        reach the missing-entry branch. Supplying the binary keeps the test
        hermetic and lets each branch be exercised on purpose.
        """
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        write_exe(d / "pass", body)
        orig = os.environ["PATH"]
        os.environ["PATH"] = f"{d}{os.pathsep}{orig}"
        self.addCleanup(lambda: os.environ.__setitem__("PATH", orig))

    def test_missing_pass_entry_aborts_the_run(self):
        """It must never proceed unauthenticated."""
        self._fake_pass('echo "pass: xyzzy is not in the password store" >&2\nexit 1\n')
        lanes = [{"name": "A", "harness": "http", "model": "m",
                  "base_url": "http://127.0.0.1:1/v1",
                  "key_entry": "definitely/not/a/real/entry/xyzzy"}]
        with self.assertRaises(SystemExit) as e:
            rt.fetch_keys(lanes)
        self.assertIn("xyzzy", str(e.exception))

    def test_absent_pass_binary_aborts_the_run(self):
        """The other way to have no secret: no `pass` at all."""
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        orig = os.environ["PATH"]
        os.environ["PATH"] = str(d)          # an empty dir -- no `pass` anywhere
        self.addCleanup(lambda: os.environ.__setitem__("PATH", orig))
        lanes = [{"name": "A", "harness": "http", "model": "m",
                  "base_url": "http://127.0.0.1:1/v1", "key_entry": "some/entry"}]
        with self.assertRaises(SystemExit) as e:
            rt.fetch_keys(lanes)
        self.assertIn("not installed", str(e.exception))

    def test_only_the_first_line_of_a_pass_entry_is_used(self):
        """`pass` returns the whole file; a blob would land in an auth header."""
        self._fake_pass('printf "THE-SECRET\nurl: https://example.invalid\n"\n')
        keys = rt.fetch_keys([{"name": "A", "harness": "http", "model": "m",
                               "base_url": "http://127.0.0.1:1/v1",
                               "key_entry": "some/entry"}])
        self.assertEqual(keys["some/entry"], "THE-SECRET")

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

    def test_retries_multiply_the_prompt_charge(self):
        """#27: http_lane re-issues on an error-body 200 and on an empty answer,
        and both bill the prompt. The estimate assumed one call per lane."""
        lanes = [{"name": "A", "harness": "http", "model": "m", "max_tokens": 0}]
        table = {"m": (1.0, 0.0)}                    # price the prompt side only
        once = rt.estimate_run(lanes, "z" * 4000, table, {}, {}, retries=0)
        thrice = rt.estimate_run(lanes, "z" * 4000, table, {}, {}, retries=3)
        self.assertAlmostEqual(thrice, once * 4)

    def test_retries_do_not_multiply_the_completion_charge(self):
        # A retry happens precisely because no usable completion came back, so
        # the completion ceiling is still a single max_tokens.
        lanes = [{"name": "A", "harness": "http", "model": "m", "max_tokens": 1000}]
        table = {"m": (0.0, 1.0)}                    # price the completion side only
        once = rt.estimate_run(lanes, "z" * 4000, table, {}, {}, retries=0)
        thrice = rt.estimate_run(lanes, "z" * 4000, table, {}, {}, retries=3)
        self.assertAlmostEqual(once, thrice)

    def test_free_lanes_contribute_nothing(self):
        lanes = [{"name": "A", "harness": "cli", "model": "x", "max_tokens": 99999}]
        self.assertEqual(rt.estimate_run(lanes, "hello", {}, {}), 0.0)


class TestEndToEnd(unittest.TestCase):
    """Exit codes, via the real CLI entry point."""

    def _run(self, lanes, *args, extra_cfg=None):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        cfg = {"lanes": lanes}
        cfg.update(extra_cfg or {})
        (d / "c.yaml").write_text(json.dumps(cfg))
        # Point the caches at the throwaway dir. A test must not fold its stub's
        # fake usage numbers into the developer's real token calibration.
        env = {**os.environ, "XDG_CACHE_HOME": str(d / "cache")}
        return subprocess.run(
            [sys.executable, str(ROOT / "roundtable"), "--config", str(d / "c.yaml"),
             "--no-transcript", *args, "brief"],
            capture_output=True, text=True, timeout=90, env=env,
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

    def test_rpm_paces_lanes_sharing_a_vendor(self):
        """The wiring, not just the Pacer: three lanes, one vendor, one slot/sec."""
        with StubServer() as s:
            lanes = [{"name": f"L{i}", "harness": "http", "model": "m",
                      "vendor": "stubco", "base_url": s.url, "rpm": 60}
                     for i in range(3)]
            t0 = time.monotonic()
            r = self._run(lanes)
            elapsed = time.monotonic() - t0
        self.assertEqual(r.returncode, 0, r.stderr)
        # Slots at 0s, 1s, 2s -- the third lane cannot start before 2s.
        self.assertGreaterEqual(elapsed, 2.0)

    def test_lanes_on_different_vendors_do_not_pace_each_other(self):
        with StubServer() as s:
            lanes = [{"name": f"L{i}", "harness": "http", "model": "m",
                      "vendor": f"v{i}", "base_url": s.url, "rpm": 60}
                     for i in range(3)]
            t0 = time.monotonic()
            r = self._run(lanes)
            elapsed = time.monotonic() - t0
        self.assertEqual(r.returncode, 0, r.stderr)
        # Each vendor has its own slot 0, so nothing waits on anything else.
        self.assertLess(elapsed, 2.0)

    def test_a_lane_whose_vendor_has_no_semaphore_still_runs(self):
        """Regression: two green PRs collided here.

        The missing-vendor fallback was a nullcontext, then `with sem:` became an
        explicit acquire/release -- which nullcontext does not have. Each change
        was correct alone; together they broke every synthesis reader."""
        with StubServer() as s:
            out = rt.ask({"name": "A", "harness": "http", "model": "m",
                          "base_url": s.url, "timeout": 10, "vendor": "unlisted"},
                         "hi", {}, 0, None, {}, threading.Lock(), [0.0], (0.0, 0.0))
        self.assertEqual(out["answer"], "stub answer")
        self.assertIsNone(out["error"])

    def test_deadline_bounds_the_whole_run(self):
        """#25: both checks sat before the semaphore acquire, so with one thread
        per lane every one of them passed at t=0 and the deadline never applied
        again. Five lanes behind a one-slot vendor ran serially, unbounded."""
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        slow = write_exe(d / "slow", 'sleep 5; echo late\n')
        lanes = [{"name": f"L{i}", "harness": "cli", "vendor": "single",
                  "command": str(slow), "args": ["-p"], "stdin": True,
                  "concurrency": 1, "timeout": 30}
                 for i in range(4)]
        t0 = time.monotonic()
        r = self._run(lanes, extra_cfg={"deadline_seconds": 6})
        elapsed = time.monotonic() - t0
        # Serial at 5s each would be ~20s. The deadline has to cut it well short.
        self.assertLess(elapsed, 14, "deadline did not bound the wall clock")
        # And a run that could not deliver every lane must still fail.
        self.assertEqual(r.returncode, 1)

    def test_a_roster_with_no_active_lanes_fails(self):
        """#26: `0/0 answered` exited 0 -- success for a run that asked nobody.

        `len(answered) == len(results)` is true of two empty lists. Same shape as
        partial delivery, and in cron the exit code is the only signal."""
        r = self._run([{"name": "Parked", "harness": "http", "model": "m",
                        "base_url": "http://127.0.0.1:1/v1", "active": False}])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("none are active", r.stdout + r.stderr)

    def test_list_still_shows_an_empty_roster(self):
        # "what is configured" is a fair question even when the answer is none.
        r = self._run([{"name": "Parked", "harness": "http", "model": "m",
                        "base_url": "http://127.0.0.1:1/v1", "active": False}],
                      "--list")
        self.assertEqual(r.returncode, 0)
        self.assertIn("0 active lane(s)", r.stdout)

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
