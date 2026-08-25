---
name: flatline-roundtable
description: Put a question to a panel of independent AI models in parallel and report where they agree and disagree — for reviewing a design, a diff, a plan, a transcript, or a decision. Each lane is a different model from a different training lineage, so convergence is evidence rather than an echo. Use when the user says "ask the roundtable", "ask the hive", "ask the board", "get a second opinion", "have the panel review this", or wants cross-model review.
---

# FlatlineRoundtable

```bash
roundtable "the brief"                    # every active lane, parallel
cat brief.md | roundtable -               # long briefs on stdin
roundtable --lanes Skeptic,Chair "..."    # a subset
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
