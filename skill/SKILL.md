---
name: flatline-roundtable
description: Put a question to a panel of independent AI models in parallel and report where they agree and disagree — for reviewing a design, a diff, a plan, a transcript, or a decision. Each lane is a different model from a different training lineage, so convergence is evidence rather than an echo. Use when the user says "ask the roundtable", "ask the hive", "ask the board", "get a second opinion", "have the panel review this", or wants cross-model review.
---

# FlatlineRoundtable

## ONE RUN PER LANE. This is not optional.

**Never invoke the whole panel in one command.** Loop, one lane per invocation:

```bash
for lane in $(roundtable --list | awk '{print $2}'); do
  cat brief.md | roundtable --lanes "$lane" - > "answers/$lane.txt" 2>&1
done
```

CJ has given this instruction repeatedly, and it keeps getting violated because
`roundtable -` looks like the obvious call. It is the wrong call.

A single invocation finishes when its **slowest** lane finishes. That couples every
lane's fate to the worst one: one slow lane sets the wall-clock for all of them,
raising its timeout pushes the whole run past the 10-minute foreground Bash cap into
the background where the task supervisor reaps it, and a lane that dies cannot be
retried without rerunning everything. Lanes are supposed to be independent; sharing a
deadline makes their failures dependent.

**Lane order: CmdrData (poolside Laguna) runs LAST, and in the FOREGROUND — CJ SOP, 2026-08-30.** Run every other lane first (backgrounded loop is fine), then CmdrData as its own FOREGROUND Bash call with `timeout: 600000` (the 10-minute harness maximum). Never background this lane: the Claude Code task supervisor reaps backgrounded roundtable runs intermittently, and on 2026-08-30 it reaped two CmdrData attempts mid-flight. CJ's preferred cap is 10000s ("poolside is free to me and is genuinely novel perspective") but foreground's 600s ceiling is the binding limit; if the lane times out silent, re-attempt once, then report the round as N−1 with the lane named — never quietly summarize. Underlying defect was FlatlineRoundtable#56 — the acp harness ignored agent-initiated requests (stalling the turn) and discarded answer text already streamed when the deadline hit. Both fixed 2026-08-30: a turn that times out now returns whatever answer streamed, marked TRUNCATED — so on a huge brief the lane delivers a partial instead of nothing.

Measured 2026-08-30: the poolside/ACP lane needs ~400s alone on a 110KB brief and
exceeded 780s under 12-lane contention. Four consecutive rounds lost it. Every loss
was avoidable.

```bash
roundtable --lanes Skeptic "..."          # ONE lane -- the normal call
cat brief.md | roundtable --lanes X -     # long briefs on stdin
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

Lanes have no tools and no file access. Whatever they need to see must be in the
brief.

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

**Watch for confident fabrication.** Lanes have not seen your codebase. One
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
