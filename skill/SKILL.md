---
name: flatline-roundtable
description: Put a question to a panel of independent AI models in parallel and report where they agree and disagree — for reviewing a design, a diff, a plan, a transcript, or a decision. Each lane is a different model from a different training lineage, so convergence is evidence rather than an echo. Use when the user says "ask the roundtable", "ask the hive", "ask the board", "get a second opinion", "have the panel review this", or wants cross-model review.
---

# FlatlineRoundtable

## ONE RUN PER LANE. This is not optional.

**Never invoke the whole panel in one command.** Use `--each`, which re-invokes
the tool once per lane:

```bash
cat brief.md | roundtable --each -              # one lane at a time
cat brief.md | roundtable --each -j 8 -         # up to 8 at a time
```

CJ has given this instruction repeatedly, and it keeps getting violated because
`roundtable -` looks like the obvious call. It is the wrong call, and the tool
now refuses it.

A single invocation (`--panel`) finishes when its **slowest** lane finishes. That
couples every lane's fate to the worst one: one slow lane sets the wall-clock for all
of them, raising its timeout pushes the whole run past the 10-minute foreground Bash
cap into the background where the task supervisor reaps it, and a lane that dies
cannot be retried without rerunning everything. Lanes are supposed to be independent;
sharing a deadline makes their failures dependent.

`--each` is what keeps them independent — every lane gets its own process, its own
deadline and its own transcript. **`-j N` does not change that**; it only lets N of
those processes be in flight at once. Parallel and independent are not in tension
here, and before `-j` existed the only way to get parallelism was `--panel`, which
gave up the independence.

**Choose N by the box, not by the roster.** Measured 2026-08-30, on a 16 GB machine
shared with other work: the poolside/ACP lane needed ~400s alone on a 110KB brief and
exceeded 780s under 12-lane contention, losing its answer four rounds running. A
2026-09-05 fan-out of 11 lanes alongside a Whisper job was killed outright for low
memory. Measured 2026-09-07: an HTTP lane peaks at ~42 MB, but a CLI lane (claude,
codex, agy) peaks at 400-750 MB because each spawns a whole agent runtime. Count the
CLI lanes, not the total. Default `-j1` on a small box; a 128 GB host runs 15 lanes
flat out without noticing.

Per-lane and per-vendor caps still apply on top of `-j`: a lane with
`concurrency: 1` holds its whole vendor group to one at a time, which is what stops
two local-model lanes hitting the same GPU together.

```bash
roundtable --lanes Skeptic "..."          # ONE lane -- the normal call
cat brief.md | roundtable --lanes X -     # long briefs on stdin
cat brief.md | roundtable --each -j 8 -   # whole panel, 8 concurrent
roundtable --json > answers.json          # structured
roundtable --list                         # roster + route; no network calls
```

**You then read the answers and summarize.** The panel produces raw opinion; the
synthesis is your job and is the actual deliverable.

## Writing the brief

**Never assemble a brief by grepping for matching lines.** That preserves content
and destroys control flow. A panel once reported a "PROVEN Critical" bug that did
not exist, because two mutually exclusive branches separated by a `continue` had
been glued together into what looked like sequential code. The lane reasoned
correctly from a corrupted excerpt.

Excerpt contiguous blocks — whole functions, or line ranges — and mark every
elision. **A mangled excerpt is a false fact.**

**Tool access is a property of the harness, not the panel.** `http` and `acp`
lanes see the brief and nothing else: whatever they need must be in it. `cli`
lanes run the vendor's own CLI (`claude`, `agy`) with its normal tools, and they
will use them. On 2026-09-05 HAL9000 decided the brief was stale, read the
checkout instead, wrote `zz_review_probe_test.go` into the reviewed repo, ran
`go test`, deleted the file, and produced the best review of the round. That is
by design: a lane keeps its tools until it cheats (reads another lane's answer,
edits the code under review, games the question), and then that lane loses them
(launch `claude` with `--safe-mode --disallowedTools ...`, or run from an empty
directory with `CLAUDE_CODE_*` scrubbed). So, before a round on a checked-out
repo: commit or stash everything, or snapshot the tree (`git diff > snap.patch;
git status --short --untracked-files=all > snap.status`) and compare after the
lane exits. Never commit while a `cli` lane is running. And write the brief for
the `http` lanes regardless — a `cli` lane's review of the tree is not a review
of the brief the others saw, so its findings are not evidence of convergence.

Ask for something falsifiable. "What is missing, what is wrong, what should be
cut" beats "what do you think", which returns nine summaries.

## Reading the answers

**Report by lane, not just by argument.** Say which lane said what. Lane quality
is only measurable if attribution survives into the summary.

**Convergence is evidence, not proof.** Independently-trained models agreeing
means something. But every major model is RLHF-tuned toward a similar helpful,
balanced posture, so some agreement is shared training rather than shared
insight. Weight a dissent that gives a *reason* over a majority that gives a
vibe.

**A weak lane still gets counted.** Treat a lone dissent from a lane with known
defects as suspect before treating it as insight. Record defects in that lane's
`notes` in the config so the next reader inherits the warning.

**Watch for confident fabrication.** `http` and `acp` lanes have not seen your
codebase (a `cli` lane may have — check its answer for what it says it did). One
answered a general architecture question by citing a specific file and line
number that does not exist. Verify any concrete claim before repeating it.

## The optional second round — `--revise`

`roundtable --each --revise latest:N` (N = the prior run's lane count) reruns
the panel with every lane shown the locked round-1 answers, its own marked
`YOURS`, peers anonymised as PANELIST letters. Lanes open with `HOLD` or
`REVISE`; the report tallies who moved.

Use it AFTER reading round 1, when the split itself is the question — you want
to know which positions survive the others' arguments, not just where lanes
land. Never skip straight to it: round-1 blindness is the tool's entire
epistemic claim, and a round-2 consensus is persuasion, not convergence. Report
round-2 agreement to the user as "the panel converged after debate", never as
"N independent models agree".

## Cost

`harness` decides cost, not `model`. `cli` lanes ride an existing subscription
and cost nothing; `http` lanes bill per token. **Never "simplify" a `cli` lane
into an `http` lane pointed at the same vendor's API** — that silently moves it
onto metered credits.

Use `--lanes` to ask a subset when the question does not need the whole panel.

## When it fails

- **Non-zero exit means a lane was silent** — that is a real failure, not a
  rounding error. Say so in the summary rather than quietly reporting N-1
  answers.
- `!! TRUNCATED` means an answer hit `max_tokens` and stopped mid-thought. Raise
  it for that lane and re-run; do not summarize a clipped answer as if complete.
- A missing `pass` entry names itself and the fix. It never falls back to an
  unauthenticated call.

Every run writes a transcript to
`~/.local/share/flatline-roundtable/transcripts/`, so a summary can always be
checked against what was actually said.

---

*Proudly Made in Nebraska. Go Big Red! 🌽 <https://xkcd.com/2347/>*
