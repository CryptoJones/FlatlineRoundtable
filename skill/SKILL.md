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

**And the loop is SEQUENTIAL. One lane at a time.** Do not put `&` on the loop
body and fan all the lanes out at once. "One run per lane" means one lane
running, then the next -- not eleven separate processes running together. On
2026-09-05 an instance parallelised the loop, the machine ran out of memory, the
batch was killed and two lanes had to be rerun. CJ: "you do them one at a time."
Backgrounding the *whole sequential loop* as one task is fine; parallelising the
lanes inside it is not.

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

## Tool-calling rounds — lanes inspect the repo themselves (CJ, 2026-09-27)

For a **code review of a checked-out repo**, CJ wants lanes to have read-only tool
access so they can verify claims instead of reasoning from a pasted diff. `roundtable`
itself stays tool-less by charter (its AGENTS.md: "not an agent framework"), so this
runs through a separate driver that reuses its config, `pass` keys and env scrubbing:

```bash
D=~/.claude/skills/flatline-roundtable/toolpanel.py
export ROUNDTABLE_REPO=/abs/path/to/repo      # the sandbox root
for lane in <names from `roundtable --list`, column 2>; do   # still ONE AT A TIME
  python3 $D "$lane" brief.md "answers/$lane.txt" 2>"answers/$lane.log"
done
```

What each harness gets:
- **http lanes**: an OpenAI-style tool loop (`read_file`, `list_dir`, `grep` = `git grep`,
  `git` limited to diff/show/log/ls-files/blame). Paths are confined to `ROUNDTABLE_REPO`;
  `.git/` and `.env*` are refused; outputs clipped at 15 KB; 30 rounds max. The last round has no tools and tells the
  lane to write its final answer; before that nudge existed, a lane still exploring at round 30
  ended with no answer (Colossus, 2026-09-27). `answers/<lane>.log`
  records every tool call. Tool calls re-send the growing history each round, so metered
  lanes cost several times a single-shot answer. Check `tool_calls=` in each answer header.
- **claude cli lanes**: `cwd=ROUNDTABLE_REPO`, `--allowedTools Read,Grep,Glob,Bash(git diff|show|log|grep:*)`,
  **`--permission-mode default --disallowedTools Write,Edit,NotebookEdit`**, hooks disabled.
  The permission-mode flag is LOAD-BEARING: `~/.claude/settings.json` sets
  `defaultMode: bypassPermissions`, which a lane would otherwise inherit and gain write and
  exec access in the reviewed checkout (HAL9000 once wrote probe files that way, 2026-09-05).
  Verified 2026-09-27: with the flags, a lane asked to create files could not.
- **codex (SHODAN)**: its config already carries `--sandbox read-only`; runs with cwd=repo.
- **agy (TheDixieFlatline)**: `--sandbox` is prepended.

Rules:
- **Commit or snapshot the repo before the round** and check `git status --untracked-files=all`
  after it. Never commit while a lane is running.
- The brief must say "you have read-only tools, cite only files and lines you opened". Keep it
  short: list starting points (`git diff origin/main..HEAD --stat`, the model files) instead of
  pasting the diff.
- Smoke-test one free lane first (Colossus) and confirm it actually calls tools.
- A lane with tools can still be confidently wrong. Colossus's first tool-backed answer flagged a
  "timezone bug" that OpenSearch's UTC date storage makes impossible. Verification is still your job,
  or a fresh-context subagent's.
- A model that rejects the `tools` parameter fails as `LANE FAILED: HTTP 4xx`; report it by name.
- One-off request overrides go through `TOOLPANEL_EXTRA_BODY='<json>'`, merged into the lane's
  `extra_body` without editing the shared config.
- A lane marked `toolpanel: false` in the config is skipped (exit 3, `SKIPPED` in its answer
  file). Run those with plain `roundtable --lanes <name>` on a full-diff brief, and label the
  answers tool-less.

### Lane settings (CJ, 2026-09-27)

The settings live in `~/.config/flatline-roundtable/FlatlineRoundtable.yaml`. The pre-change copy
is `FlatlineRoundtable.yaml.bak-lanes-20260927`. Each lane's config carries a comment with the
reason.

| Lane | Model / route | Setting | Why | Status |
|---|---|---|---|---|
| SELMA | Nemotron 3 Super (free), OpenRouter | `extra_body: {reasoning: {enabled: false}}` | With thinking on: 15-21 min per tool review, and one run died "overloaded". | Verified: 101 s, 28 tool calls, grounded review |
| GLaDOS-K3 (parked) | Kimi K3, NVIDIA API (free) | `active: false` | Kimi K3 thinking is **always on**: `thinking=false` is accepted but unsupported. At the default effort (`max`), NVIDIA's endpoint broke down (`!!!!…` reasoning, no answer), and at `high` the answers were sound. But NVIDIA's free endpoint closes any request still running at about 60 s (tool-less, at effort high and low), reset a streamed request at 179 s with no answer yet, and reset every tool session. NVIDIA pins `top_p` at 0.95; multi-turn tool use requires echoing `reasoning_content`. CJ parked it rather than pay for OpenRouter Kimi K3 (~$1/$9 per Mtok). | Parked 2026-09-27 |
| **GLaDOS** (was MUTHUR) | Kimi K2.6, OpenRouter | model, route, key and `reasoning: {effort: low}` unchanged; the GLaDOS persona moved over, its runtime line changed to Kimi K2.6 on OpenRouter | Renamed by CJ so the GLaDOS seat stays filled with a Kimi-lineage model that works | Verified: correct model self-report, 11 s, $0.0065 on a probe; clean on every tool round that day as MUTHUR |
| MasterControl | **Mistral Medium 3.1**, OpenRouter, unpinned | `model: mistralai/mistral-medium-3.1`, `provider: {allow_fallbacks: true}`, `max_tokens: 12000` | OpenRouter's shared quota for `mistral-large-2512` returned 429 on every attempt, even with backoff to 80 s. Medium 3.1 on the same key is not limited ($2.00/Mtok out vs $1.50). Only Mistral itself serves these models, and CJ will not add a second paid provider. Merge's free plan has no Mistral (403 until a card is added). | Verified: a 23.7 KB review with 14 tool calls in 91 s. It needs `max_tokens: 12000`; the driver's 8000 floor truncated it (`finish=length`). |
| Multivac | Hermes 4 405B, OpenRouter | `toolpanel: false` | Its only endpoint (Nebius) does not support tool calls. | Tool-less only |
| Proteus | **Qwen 3.7 Flash**, OpenRouter (was Nova Pro) | `model: qwen/qwen3.7-flash`, `toolpanel: false` removed | Nova Pro was 0 CORRECT / 6 WRONG across the two Vigil #1217 rounds, ungrounded with or without tools. Qwen 3.7 Flash passed a tool-round grounding test on 2026-09-28 (17 tool calls, 194 s, correct `file:line` citations, noticed live merge markers) at $0.03/$0.13 per Mtok vs $0.80/$3.20. | Swapped by CJ 2026-09-28; tool rounds on |

The other nine lanes (HAL9000, Cortana, SHODAN, TheDixieFlatline, Joshua, Neuromancer, GLaDOS
(then named MUTHUR), Cerebex, Colossus) ran tool rounds cleanly with their defaults on 2026-09-27.

### Driver failure modes `toolpanel.py` handles (each seen live on 2026-09-27)

- **The lane is still exploring at round 30:** the last round drops tools and asks for the final
  answer.
- **An empty answer with no tool calls** (Kimi): the round is retried.
- **A tool call written as text** (`<tool_call><function=…>`, Nemotron with reasoning off): the
  model is told it did not run, up to 3 times.
- **`finish_reason: "error"`** (Mistral's stream died mid-answer): the partial text is discarded
  and the round retried.
- **A per-lane tool-round cap** (`toolpanel_max_rounds`) for providers that drop long loops.
- **HTTP 429 from shared quotas:** honors `Retry-After`, otherwise waits 20/40/60 s, up to 6
  attempts.
- **A dropped connection** (`RemoteDisconnected`, NVIDIA on long loops): retried like a 5xx.
- **Thinking models** get their `reasoning_content` echoed back on every tool turn.

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

## The discussion — `--discuss` (alias `--converse`)

`--converse` is the same flag by the name CJ uses for it — "run the converse
pass" means `--discuss`. There is no separate converse mode.

`roundtable --discuss latest:N` (N = the prior blind run's lane count) puts the
panel in ONE shared context — brief, anonymised openings, every turn said so
far — and has them take turns in it, **one lane in flight at a time**, in a
single process. Passes over the roster: `--discuss-rounds` (default 2), opener
rotating each pass. After the last pass each lane closes with `HOLD` or
`REVISE`; the report tallies those under the same "persuasion, not
convergence" banner as `--revise`. `--discuss new` starts cold from a brief on
stdin/argv with no blind round; any brief text given alongside a transcript
spec rides as extra focus.

This is the lightweight stand-in for a Buzz-style conversation: no resident
runtimes, no bus, a `cli` lane's agent exists only for its turn. Do NOT add
`--each`, `-j` or `--panel` — the tool refuses them, because a turn cannot be
built until the one before it has been said. Do not run it instead of round
1: the blind round is still the evidence; the discussion is what you run
AFTER reading it, when you want to see which positions survive being argued
with rather than merely being shown.

**When to discuss, and when not to** (the default; CJ's two-pass procedure
below overrides it). Discuss when lanes split on a
*judgment* — severity, reachability, whether a change is the right fix — and
the split is what you need settled. Do not discuss when the only dissent
rests on a *checkable fact*: verify the fact yourself and move on. A
discussion costs rounds × lanes requests and, as #98 showed, can manufacture
evidence; a fact check costs one command. Vigil #1217 round 4 (2026-09-28):
12 tool lanes said READY, Multivac alone said NOT READY on the claim that
`isinstance(x, str)` discards `str` subclasses — false, and checkable in one
line — so the right move was verification, not a discussion, and that is what
was done.

**Seeding from a tool round.** `--discuss` drives the lanes itself through
roundtable's own harnesses; it does not run tool rounds and does not read
`toolpanel.py` answer files. An `http`/`acp` turn is tool-less — it sees the
shared packet and nothing else — so the evidence has to be in the openings or
the focus text (contiguous excerpts, elisions marked). A `cli` turn keeps its
vendor CLI's tools. To discuss a tool round's findings, fold the per-lane
answer files into one seed transcript first:

```bash
S=~/.claude/skills/flatline-roundtable/toolpanel-seed.py
$S brief.md seed.json answers/*.md             # status!=ok lanes get answer=null
roundtable --lanes HAL9000,SHODAN,Cortana --discuss seed.json "focus: the split, by finding"
```

Put the disputed claims in the focus text by finding, not by lane, and say
what would settle each; that is what the panel argues about.

Reading it: the thread is streamed turn by turn as it happens and saved to the
transcript after every turn (`"discussion"`: `turn`, `pass`, `alias`, `lane`,
`answer`, `seconds`, `cost`; closings under `"results"`; `"aliases"` letter →
lane; `"parent"` the seed), so a run killed mid-thread still leaves what was
said. Report the discussion by panelist letter → lane, quote the turn that
actually moved a lane, and report closings as "converged after discussion",
never as "N independent models agree".

**Check every fact that first appears mid-thread against the code before you
repeat it.** A shared thread can do what a blind round cannot: turn one lane's
invention into everyone's premise. First live run, 2026-09-28 (#98): Colossus
asserted a "default 24 h" approval expiry that does not exist (it is
`approval_expiry_days`, default 7, pending only), and HAL9000, SHODAN and
Cerebex each cited "B's 24-hour expiry" as evidence in the next three turns.
The verdict was right; the evidence was false. The prompts now tell lanes a
fact introduced in the thread is a claim until sourced, which lowers the rate
and does not eliminate it. The `discussion` array is in turn order: find where
a fact was first said, and if that turn cites no file, command or document,
treat every later use of it as unverified. Cost is O(N²) in turns; use `--lanes`
for the three-to-five lanes that actually split, not all twelve, and
`--max-spend` still gates (longest packet × rounds+1 per lane).
`deadline_seconds` bounds one turn, not the run.

## The two-pass review (CJ, 2026-09-28)

CJ's procedure for reviewing a fix branch, in his words: *"We should do pass
two with the results of pass one without changing things and then evaluate
and report to me"* and *"Make sure to use the new `--converse` flag on the
second pass!"* When he asks for a two-pass review, this is what it means:

1. **Pass 1 is a blind tool round.** `toolpanel.py`, one lane at a time, over
   a committed or snapshotted checkout. Lanes marked `toolpanel: false` get
   the full diff through plain `roundtable` and are labelled tool-less.
2. **Pass 2 is ALWAYS `--converse`, seeded from pass 1's answers exactly as
   they are.** Fold the answer files with `toolpanel-seed.py` and run
   `roundtable --converse seed.json`. Change NOTHING between the passes: not
   the code, not the brief, not the answers. No fixing findings first, no
   dropping a lane's claim, no re-running pass 1. The converse pass discusses
   what pass 1 actually said.
3. **This overrides "when to discuss, and when not to" above.** Under this
   procedure the converse pass runs even when pass 1 is unanimous or its only
   dissent is a checkable fact. That guidance stays the default only when CJ
   has not asked for the two-pass procedure.
4. **Evaluation happens after both passes.** A fresh-context verifier checks
   every finding from both passes against the code, and against `main`'s
   behaviour where a finding claims "main did X". Lane agreement is never the
   evidence; a converse-pass consensus is persuasion (see #98).
5. **Report to CJ before acting.** No fixes, commits, PRs or merges based on
   the review until he has seen the evaluated report. Fixes go into a new
   commit, and a new review starts again from pass 1.

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
