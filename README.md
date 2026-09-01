<p align="center"><em>Proudly Made in Nebraska. Go Big Red! 🌽 <a href="https://xkcd.com/2347/">https://xkcd.com/2347/</a></em></p>

# FlatlineRoundtable

Ephemeral Board of AI Advisors that only convene when you need them.

Put one question to a panel of independent models, in parallel, and read where
they disagree.

```console
$ roundtable "Is replacing our message queue with direct calls a mistake?"

==========================================================================
Skeptic  (some-vendor/some-model)  2.1s
==========================================================================
...

9/9 lanes answered in 51.2s
transcript: ~/.local/share/flatline-roundtable/transcripts/20260825-163840.json
```

## Why a panel

One model asked one question gives you one prior. Ask eight models from eight
different training lineages and the *disagreement* is the product: where
independently-trained models land in the same place, that convergence is
evidence; where they split, that is where your thinking is underdetermined.

A panel of one model wearing eight hats gives you neither — shared priors
produce convergence that looks like corroboration and is not.

## Why it is not an agent framework

This replaced a design where each advisor was a long-lived agent process with
its own identity, message-bus membership, and a tool it had to call to publish
its answer. Everything that went wrong with that was transport, not models:

- An abandoned run kept billing for **54 hours** — a backgrounded agent has no
  reason to stop.
- A nine-advisor review delivered **four answers**. The other five produced
  correct responses that died in log files, because those models never called
  the publish tool. The harness logged the text and discarded it.
- Advisor names that resolved ambiguously notified **nobody**, silently.

None of that is possible here:

- **No long-lived processes.** A lane is one HTTP request or one short-lived
  subprocess. There is nothing left running to bill.
- **No delivery step.** The answer arrives in the response or the lane failed
  loudly. Nothing can "succeed" into a place nobody reads.
- **Partial delivery is a failure.** If any active lane is silent, the exit code
  is non-zero. A quiet advisor is the bug, not a rounding error.

## Install

Requires Python 3 with PyYAML, and [`pass`](https://www.passwordstore.org/) if
any lane needs an API key.

```console
$ git clone https://github.com/CryptoJones/FlatlineRoundtable
$ cd FlatlineRoundtable
$ mkdir -p ~/.config/flatline-roundtable
$ cp FlatlineRoundtable.yaml.example ~/.config/flatline-roundtable/FlatlineRoundtable.yaml
$ $EDITOR ~/.config/flatline-roundtable/FlatlineRoundtable.yaml
$ ./roundtable --list        # shows the roster; makes no network calls
```

Optionally `./install.sh` to expose it as a Claude Code skill.

## Secrets

**No key ever appears in a config file, in this repo, or in a process list.**

- A lane names a `pass` entry (`key_entry: openrouter/agent/skeptic`), never a
  key.
- Keys are read once, before fan-out, and held in memory only. Never in `argv`,
  which is world-readable via `ps`.
- Keys never reach the transcript or `--json` output.
- A missing entry fails that lane loudly and names the fix. It never silently
  falls back to an unauthenticated call.
- Your real config lives at `~/.config/flatline-roundtable/`, outside the repo,
  because `.gitignore` is not a security boundary — `git add -f`, stashes, and
  editor backups all defeat it.

## Cost

**`harness` decides cost, not `model`.**

An `http` lane bills per token. `cli` and `acp` lanes drive a vendor's own binary
against an existing subscription and cost nothing extra.

Rewriting a `cli` lane as an `http` lane pointed at the same vendor's API
silently moves it onto metered credits. So does leaving an API key in your
shell: these CLIs prefer an env key over the OAuth session. FlatlineRoundtable
scrubs `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` and friends from every CLI lane's
environment for that reason.

Prices come from the gateway's own table (cached for a day), so they do not go
stale the way a hand-maintained number does; `price_per_mtok` overrides it for
vendors with no price endpoint. `--max-spend` and `budget_usd` are checked
**before dispatch** against a worst-case estimate, so an overrun is prevented
rather than reported.

## Usage

```console
roundtable --each "the brief"           # each lane its own process (do this)
roundtable --lanes Skeptic "..."        # one lane
roundtable --panel "the brief"          # all lanes, one shared deadline
cat brief.md | roundtable -             # long briefs on stdin
roundtable --lanes Skeptic,Chair "..."  # a subset
roundtable --list                       # roster + route; no network calls
roundtable --json                       # structured output
roundtable --config PATH
roundtable --max-spend 0.50        # refuses BEFORE dispatch if the estimate exceeds it
roundtable --diff                  # report only where the lanes disagree
roundtable --no-transcript
roundtable --each --revise latest:12    # optional second round — see below
```

`--diff` asks lanes to report AGREED / SPLIT / LONE CLAIMS across the others,
because reading N full answers does not scale and disagreement is the product.

It is opt-in and it is not neutral — a synthesizer is one model with its own
priors deciding what counts as a disagreement, so the raw answers still go to
the transcript. That is also why it uses **two** readers by default, picked from
different vendors: with a single reading you cannot tell a real split from that
model's taste in splits. Where the two place the same lane differently,
roundtable says so under `THE READERS DISAGREE` — that is the reading doing the
work rather than the evidence, and a signal to go read that lane's raw answer.

The comparison is mechanical on purpose. Handing it to a third model would just
move the problem one level up. Set `synthesizers: 1` to go back to a single
reader, or name a specific one with `synthesizer: <lane>`. It prefers free
lanes, so the convenience does not quietly cost money.

After a run, any lanes that turn out **not** to be independent are named:

```
  LANES THAT ARE NOT INDEPENDENT
    Twin1, Twin2 — answered from claude / haiku
    Agreement between these is an echo, not convergence.
```

Two lanes collide when a gateway served them the same model, or when they
declare the same `lineage:`. It is never fatal — a deliberate duplicate is a
legitimate thing to want — but it must not be silent, because it is invisible in
the answers themselves and it falsifies the one claim the tool makes.

Two config files ship with the repo. `FlatlineRoundtable.yaml.example` is the
annotated template — every option, with the reasoning for each. `examples/full-roster.yaml`
is a real thirteen-lane roster, kept because a tuned config is mostly *numbers
you had to measure*, and those are worth reading before you pick your own.

Every run writes a transcript to
`~/.local/share/flatline-roundtable/transcripts/`, because answers that exist
only in a terminal scrollback are answers waiting to be lost.

### `--revise` — the optional second round

Round 1 is blind by construction: a lane cannot see the others because their
answers do not exist yet in its process. `--revise` is the one deliberate
exception. It replays a **finished** run's transcript(s), handing every lane
the locked round-1 answers — its own marked `YOURS`, the rest anonymised as
`PANELIST A/B/C` — and instructions to open with `HOLD` or `REVISE` and to move
only for a reason it can state. Anonymised, because "the Anthropic lane said
so" is exactly the deference the instructions forbid.

```console
roundtable --each "the brief"             # round 1, blind, 12 lanes
roundtable --each --revise latest:12      # round 2: the whole prior run
roundtable --each --revise latest:12 "focus on the cost claims"   # extra focus
roundtable --lanes Chair --revise ~/.local/share/.../20260901-*.json
```

`--each` writes one transcript per lane, which is why `--revise` takes
`latest:N` and comma-separated paths and merges them; it refuses to mix
transcripts whose briefs differ, because that is only ever an accident. The
report ends with who held and who moved, under a banner that says the thing
that matters:

```
ROUND 2 — lanes saw the round-1 answers. Agreement here is persuasion,
not independent convergence.
```

Treat round-2 convergence accordingly. Round 1 tells you where independent
models land; round 2 tells you which positions survive contact with the
others' arguments. Both are useful; only the first is evidence of
independence. A round-2 transcript records `round`, its parent transcripts,
and the alias map, so the anonymity is auditable after the fact. `--revise
latest:12` on a round-2 run produces round 3; nothing caps it, but each round
is another full panel spend, and the returns fall fast.

## Tests

```console
$ python3 -m unittest discover -s tests
```

132 tests against a stub HTTP server and fake CLI binaries — no vendor is
contacted, nothing is spent, no credential is needed. They cover the behaviours
that silently cost money or leak processes: the env scrub, the process-group
kill, the missing-secret abort, and partial delivery failing the run.

## Limits

- Three harnesses: `http` (any OpenAI-compatible endpoint), `cli` (one-shot
  subscription CLIs), and `acp` (JSON-RPC-over-stdio agents, driven for exactly
  one turn).
- Lanes have **no tools and no file access**. This is "read this and tell me what
  you think," not "go investigate the repo." Put the material in the brief.
- Lanes never see each other's answers. That is the point; it is also why they
  cannot build on one another.
- A weak lane is worse than an absent one — it still gets counted. Prune the
  roster on quality, and record known defects in each lane's `notes`.
