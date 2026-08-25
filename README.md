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
roundtable "the brief"                  # every active lane, in parallel
cat brief.md | roundtable -             # long briefs on stdin
roundtable --lanes Skeptic,Chair "..."  # a subset
roundtable --list                       # roster + route; no network calls
roundtable --json                       # structured output
roundtable --config PATH
roundtable --max-spend 0.50        # refuses BEFORE dispatch if the estimate exceeds it
roundtable --diff                  # report only where the lanes disagree
roundtable --no-transcript
```

`--diff` asks one lane to report AGREED / SPLIT / LONE CLAIMS across the others,
because reading N full answers does not scale and disagreement is the product.
It is opt-in and it is not neutral — the synthesizer is one model with its own
priors deciding what counts as a disagreement, so the raw answers still go to the
transcript. It prefers a free lane, so the convenience does not quietly cost
money.

Every run writes a transcript to
`~/.local/share/flatline-roundtable/transcripts/`, because answers that exist
only in a terminal scrollback are answers waiting to be lost.

## Tests

```console
$ python3 -m unittest discover -s tests
```

25 tests against a stub HTTP server and fake CLI binaries — no vendor is
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
