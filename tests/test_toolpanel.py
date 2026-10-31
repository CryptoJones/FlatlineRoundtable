# SPDX-License-Identifier: Apache-2.0
"""skill/toolpanel.py: how a cli lane is run on a tool round (#134, #135).

The driver is a skill script, so it is loaded by path. Nothing here runs a
vendor CLI: the argv builder is pure, and the one subprocess test uses a fake
executable, as the roundtable tests do.
"""

import importlib.machinery
import importlib.util
import os
import shutil
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_toolpanel():
    loader = importlib.machinery.SourceFileLoader("toolpanel", str(ROOT / "skill" / "toolpanel.py"))
    spec = importlib.util.spec_from_loader("toolpanel", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


tp = _load_toolpanel()

GLADOS_ARGS = ["--no-auto-update", "--disable-web-search", "--no-subagents", "--no-plan",
               "--tools", "", "--max-turns", "1", "--output-format", "plain", "-m", "grok-4.6",
               "-p", "{prompt}"]


class TestGrokBranch(unittest.TestCase):
    def test_grok_gets_read_only_tools_denied_integrations_and_review_length_turns(self):
        lane = {"name": "GLaDOS", "command": "/Users/x/.grok/bin/grok", "args": GLADOS_ARGS, "harness": "cli"}
        args = tp.build_cli_args(lane)
        # The stored tool-less pair is gone, not merely followed: grok takes the LAST value.
        self.assertEqual(args.count("--tools"), 1)
        self.assertEqual(args.count("--max-turns"), 1)
        self.assertEqual(args[args.index("--tools") + 1], tp.GROK_READ_ONLY_TOOLS)
        self.assertEqual(args[args.index("--max-turns") + 1], str(tp.MAX_ROUNDS))
        self.assertEqual(args[args.index("--deny") + 1], "*__*")
        self.assertEqual(args[args.index("--permission-mode") + 1], "default")
        # Everything else the lane stored survives, prompt placeholder included.
        for kept in ("--no-auto-update", "--disable-web-search", "--no-subagents", "--no-plan",
                     "--output-format", "plain", "-m", "grok-4.6", "-p", "{prompt}"):
            self.assertIn(kept, args)

    def test_the_read_only_set_names_real_grok_tools(self):
        # `read` and `view` are not file tools; a `--tools` entry that names no tool
        # makes grok keep EVERY tool available (verified on 1.0.70). Pin the names.
        self.assertEqual(tp.GROK_READ_ONLY_TOOLS, "read_file,glob")

    def test_the_grok_stdin_shim_takes_the_same_branch(self):
        lane = {"name": "GLaDOS", "command": "/home/x/.local/bin/grok-stdin", "args": GLADOS_ARGS, "stdin": True}
        self.assertIn("--deny", tp.build_cli_args(lane))

    def test_equals_forms_are_dropped_too(self):
        lane = {"name": "G", "command": "grok", "args": ["--tools=", "--max-turns=3", "-p", "{prompt}"]}
        args = tp.build_cli_args(lane)
        self.assertNotIn("--tools=", args)
        self.assertNotIn("--max-turns=3", args)
        self.assertEqual(args[args.index("--tools") + 1], "read_file,glob")

    def test_claude_and_agy_branches_are_unchanged(self):
        claude = tp.build_cli_args({"name": "HAL", "command": "claude", "args": ["-p", "{prompt}"]})
        self.assertIn("--allowedTools", claude)
        self.assertEqual(claude[claude.index("--permission-mode") + 1], "default")
        self.assertIn("--disallowedTools", claude)
        agy = tp.build_cli_args({"name": "Dix", "command": "agy", "args": ["--model", "m", "-p", "{prompt}"]})
        self.assertEqual(agy[0], "--sandbox")

    def test_an_unknown_cli_keeps_its_args_verbatim(self):
        args = ["--flag", "-p", "{prompt}"]
        self.assertEqual(tp.build_cli_args({"name": "X", "command": "other-cli", "args": args}), args)


class TestInvokedModel(unittest.TestCase):
    def test_the_args_win_over_the_record(self):
        # TheDixieFlatline: record said gemini-3.1-pro-high, args invoked 3.8-flash-high.
        lane = {"model": "gemini-3.1-pro-high", "args": ["--model", "gemini-3.8-flash-high", "-p", "{prompt}"]}
        self.assertEqual(tp.invoked_model(lane), "gemini-3.8-flash-high")

    def test_short_and_equals_forms(self):
        self.assertEqual(tp.invoked_model({"model": "x", "args": ["-m", "grok-4.6"]}), "grok-4.6")
        self.assertEqual(tp.invoked_model({"model": "x", "args": ["--model=foo"]}), "foo")
        self.assertEqual(tp.invoked_model({"model": "x", "args": ["-m=bar"]}), "bar")

    def test_falls_back_to_the_record(self):
        self.assertEqual(tp.invoked_model({"model": "recorded", "args": ["-p", "{prompt}"]}), "recorded")
        self.assertIsNone(tp.invoked_model({"args": []}))


class TestStderrOnEmptyStdout(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _exe(self, name, body):
        path = self.tmp / name
        path.write_text("#!/usr/bin/env bash\n" + textwrap.dedent(body))
        path.chmod(0o755)
        return str(path)

    def test_exit_zero_with_empty_stdout_keeps_the_stderr_tail(self):
        # #135: agy exited 0 with nothing on stdout and the driver reported EMPTY,
        # dropping the only place the reason lived.
        exe = self._exe("quiet", 'echo "sandbox: refused to read the brief" >&2\nexit 0\n')
        answer, calls, finish, tail = tp.cli_with_tools({"name": "L", "command": exe, "args": ["{prompt}"]}, "brief")
        self.assertEqual(answer, "")
        self.assertIsNone(calls)
        self.assertEqual(finish, "stop")
        self.assertEqual(tail, "sandbox: refused to read the brief")

    def test_a_normal_answer_still_comes_back_first(self):
        exe = self._exe("talker", 'echo "the answer"\necho "a warning" >&2\n')
        answer, _, _, tail = tp.cli_with_tools({"name": "L", "command": exe, "args": ["{prompt}"]}, "brief")
        self.assertEqual(answer, "the answer")
        self.assertEqual(tail, "a warning")

    def test_the_tail_is_bounded(self):
        exe = self._exe("noisy", 'head -c 10000 /dev/zero | tr "\\0" x >&2\nexit 0\n')
        _, _, _, tail = tp.cli_with_tools({"name": "L", "command": exe, "args": ["{prompt}"]}, "brief")
        self.assertEqual(len(tail), tp.STDERR_TAIL)

    def test_a_non_zero_exit_still_raises_with_stderr(self):
        exe = self._exe("dies", 'echo "Max turns reached" >&2\nexit 1\n')
        with self.assertRaises(RuntimeError) as ctx:
            tp.cli_with_tools({"name": "L", "command": exe, "args": ["{prompt}"]}, "brief")
        self.assertIn("exit 1: Max turns reached", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
