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

Requires Python 3.11 or newer with the `cryptography` package, and
[`pass`](https://www.passwordstore.org/), which holds the store's DB key.

```console
$ git clone https://github.com/CryptoJones/FlatlineRoundtable
$ cd FlatlineRoundtable
$ python3 -m pip install --user cryptography
$ ./roundtable db init                                # the store, and its key in pass
$ ./roundtable db import examples/roster.example.json # or lanes add, or import-yaml
$ ./roundtable --list        # shows the roster; makes no network calls
```

Optionally `./install.sh` to expose it as a Claude Code skill.

## Secrets

**No key ever appears in plaintext on disk, in this repo, or in a process list.**

- A lane names a secret (`key_entry: openrouter/agent/skeptic`), never a key.
- Secrets live in the store, AES-256-GCM-encrypted. The DB key that unlocks them
  lives in the `pass` entry `flatline-roundtable/db-key`, so the store file alone
  gives up nothing.
- Keys are decrypted once, before fan-out, and held in memory only. Never in
  `argv`, which is world-readable via `ps`.
- Keys never reach the transcript or `--json` output.
- A missing secret fails the run loudly and names the fix. It never silently
  falls back to an unauthenticated call.

**The store ([#105](https://github.com/CryptoJones/FlatlineRoundtable/issues/105)) is the only configuration.**
`roundtable db init` creates `~/.local/share/flatline-roundtable/roundtable.db`
(`0600`, `XDG_DATA_HOME` honoured) and a 32-byte DB key in `pass`. Runs read
their lanes and secrets from it; `--config` names another store. One `pass show`
per process, for the DB key, replaces one per lane secret.
`roundtable secrets set NAME --stdin` stores a value encrypted under the key. A
value typed on the command line is refused. `secrets check` prints only
presence, length and key id.

YAML is retired (#109): a `.yaml` `--config` is refused with the command that
moves it in. Move an old YAML config in once, with PyYAML installed for that
one command only:

```sh
roundtable import-yaml ~/.config/flatline-roundtable/FlatlineRoundtable.yaml --dry-run
roundtable import-yaml ~/.config/flatline-roundtable/FlatlineRoundtable.yaml --pull-secrets
```

`--dry-run` writes nothing and prints each lane with the notes taken from its
YAML comments, because the store has no comments of its own. `--pull-secrets`
copies each `key_entry` value from `pass` into the store, encrypted. Re-running
the import changes nothing that has not changed.

After that, lanes are edited with commands, and every write is checked by the
same rules `load_config()` applies:

```sh
roundtable lanes list [--all]
roundtable lanes add Skeptic --harness http --set model=vendor/model \
    --set base_url=https://openrouter.ai/api/v1 --key-entry openrouter/skeptic
roundtable lanes edit Skeptic --set timeout=120 --reason "slow on long briefs"
roundtable lanes history Skeptic
roundtable globals set budget_usd=0.50
roundtable db export --out roster.json      # no secret values, ever
roundtable db import roster.json --replace  # on another host
```

A change to a lane's config or `key_entry` is a new version in `lane_versions`.
Renaming, enabling, disabling and editing notes are not, so a lane's record
follows the lane rather than its name. `rename` keeps the old name as an alias,
`retire` frees the name and keeps the history, and `clone` makes an inactive
copy. `--set` values are JSON when they parse and strings otherwise.
[`examples/roster.example.json`](examples/roster.example.json) is the example
YAML config after `import-yaml` and `db export`.

**Backups (#110).** `roundtable db backup` writes an integrity-checked `0600`
copy to `backups/` beside the store, with SQLite's online backup API, so it is
consistent while a run has the store open. It keeps the newest 14 (`--keep N`).
`roundtable db restore FILE` refuses a corrupt file, and a file from a newer
schema unless `--force`; the store it replaces is kept as
`roundtable.db.pre-restore-<stamp>`.

[`scripts/backup-telesto.sh`](scripts/backup-telesto.sh) is a one-shot job: it
takes a `db backup`, then pushes the backups and the gpg-encrypted DB key entry
to a restic repository on telesto (`sftp:telesto:/NAS/backups/flatline-roundtable/<host>`,
password in the `pass` entry `flatline-roundtable/restic-telesto`), prunes to
14 daily, 8 weekly and 6 monthly snapshots, and runs `restic check` on Sundays.
A store without its DB key cannot decrypt its secrets, which is why the key goes
too; the key is in turn useless without your gpg private key.
[`examples/net.thenetwerk.roundtable-backup.plist`](examples/net.thenetwerk.roundtable-backup.plist)
runs it daily at 03:45 under launchd.

The restore drill, run against a scratch path so the live store is untouched:

```sh
export RESTIC_REPOSITORY=sftp:telesto:/NAS/backups/flatline-roundtable/$(hostname -s)
export RESTIC_PASSWORD_COMMAND="pass show flatline-roundtable/restic-telesto"
restic restore latest --target /tmp/drill
roundtable db restore /tmp/drill/.../backups/roundtable-<host>-<stamp>.db --config /tmp/drill/roundtable.db
roundtable db doctor --config /tmp/drill/roundtable.db
roundtable secrets check --config /tmp/drill/roundtable.db
roundtable --config /tmp/drill/roundtable.db --list
```

## Fleet

Each host has its own store and its own DB key. makemake is the system of
record: its roster is exported and imported elsewhere, and each host sets its
own secrets under the same names (epic #105, decisions 2 and 6). Nothing is
shared live, so a host that is down or behind never blocks another.

On makemake, after any roster change worth sharing:

```sh
roundtable db export --out ~/roster.json            # 0600, never holds a secret value
scp ~/roster.json pluto:roster.json
```

On the other host (pluto shown; its default `python3` is 3.9, with 3.11 beside it):

```sh
git -C ~/source/repos/FlatlineRoundtable pull --ff-only
python3.11 -m pip install --user cryptography
cd ~/source/repos/FlatlineRoundtable && PYTHON=python3.11 ./install.sh
roundtable db init                                   # this host's own DB key, in its pass
roundtable db import ~/roster.json --replace
# Secrets: same names as makemake, this host's values. pluto has one shared
# OpenRouter key, so every openrouter/agent/* name gets that one value.
for n in $(roundtable lanes list | cut -f7 | sed -n 's/^key=//p' | grep '^openrouter/agent/' | sort -u); do
    pass show openrouter/api-key | roundtable secrets set "$n" --stdin
done
pass show nvidia/api-key | roundtable secrets set nvidia/api-key --stdin
roundtable secrets check                             # every name: present
roundtable --list
```

`PYTHON=python3.11 ./install.sh` installs `roundtable` as a two-line wrapper
that execs that interpreter, so the host's default `python3` is left alone.

A host can keep its own value for a host-specific setting, such as a CLI path
or a wrapper. Set it with `lanes edit` after the import, with a `--reason`.
The next `db import --replace` from makemake puts makemake's value back, so
re-apply it after each import. On pluto that is GLaDOS, which reads its brief
through `~/.local/bin/grok-stdin`, because Linux caps one argument at 128 KB:

```sh
roundtable lanes edit GLaDOS --set command=/home/akclark/.local/bin/grok-stdin --set stdin=true \
    --set 'args=[...pluto args...]' --reason "pluto: Linux argv limit"
```

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
rather than reported. Under a budget, an `http` lane whose price cannot be
resolved is refused outright rather than estimated at $0 — a guard that
cannot see a lane cannot bind on it. `cli`/`acp` lanes, `:free` models and an
explicit `price_per_mtok: 0` are free, not unknown.

## Usage

```console
roundtable --each "the brief"           # each lane its own process (do this)
roundtable --lanes Skeptic "..."        # one lane
roundtable --panel "the brief"          # all lanes, one shared deadline
cat brief.md | roundtable -             # long briefs on stdin
roundtable --lanes Skeptic,Chair "..."  # a subset
roundtable --list                       # roster + route; no network calls
roundtable --json                       # structured output
roundtable --list --json                # roster as JSON, for tools; no secret refs
roundtable --each --run-id ID "..."     # tag every transcript of this run with ID
roundtable --synthesize latest:12        # --diff readers over a finished run; no lane re-asked
roundtable --each --revise latest-run    # round 2 over the newest run, found by run_id
roundtable --config DB             # another store (default ~/.local/share/flatline-roundtable/roundtable.db)
roundtable --max-spend 0.50        # refuses BEFORE dispatch if the estimate exceeds it
roundtable --panel --diff          # report only where the lanes disagree (not with --each)
roundtable --no-transcript
roundtable --each --revise latest:12    # optional second round — see below
```

Every transcript carries a `run_id`. `--each` hands its children one id, so
the N per-lane transcripts of a fan-out can be grouped as one run; without
`--run-id` a fresh one is generated per invocation.

`--diff` asks lanes to report AGREED / SPLIT / LONE CLAIMS across the others,
because reading N full answers does not scale and disagreement is the product.
It needs every answer in one process, so it pairs with `--panel`; `--each
--diff` is refused up front rather than silently dropping the flag. To get the
independent-process run *and* a comparison, run `--each`, then
`--synthesize latest:N` (or the run's transcript paths). It sends the locked
answers to the readers only — no lane is asked again — clears the budget gate
first, and writes the synthesis as a transcript on the same `run_id`.

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

Two rosters ship with the repo, as `db import` files.
`examples/roster.example.json` is a starting roster with one lane of each kind.
`examples/full-roster.json` is a real thirteen-lane roster, kept because a tuned
config is mostly *numbers you had to measure*, and those are worth reading
before you pick your own. The old annotated YAML template, with the reasoning
for every option, is kept as
[`tests/fixtures/legacy-example.yaml`](tests/fixtures/legacy-example.yaml); each
option it documents is a `--set` key now.

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

### `--discuss` — the shared-context discussion

(`--converse` is an alias; the two are the same flag.)

`--revise` shows every lane the others' answers once. `--discuss` lets them
talk. The panel shares **one** context — the brief, the anonymised opening
positions, and every turn said so far, in order — and takes turns in it, one
lane speaking at a time. Each turn is one ordinary request with that shared
context as the prompt, so the process holds a single request in flight, a
`cli` lane's agent runtime exists only for its turn, and nothing outlives the
run. That is the whole point: a standing fleet with a resident runtime per
lane and a message bus between them can do this too, and is far too heavy to
keep around for it.

```console
roundtable --each "the brief"               # round 1, blind
roundtable --discuss latest:12              # the same 12 lanes discuss it
roundtable --discuss latest:12 --discuss-rounds 3 "focus on the cost claims"
cat brief.md | roundtable --discuss new -   # start cold, no blind round
roundtable --lanes HAL9000,SHODAN,Cortana --discuss latest:12   # a subset
```

Seed it from a blind round and round 1 keeps its epistemic claim; `new`
starts cold and its transcript *is* round 1 — a dependent one. Each pass
gives every lane one turn (the opener rotates each pass, so no lane always
anchors or always gets the last word), and after the last pass each lane
writes a closing that opens with `HOLD` or `REVISE`. The report tallies the
closings under the same banner `--revise` uses, because the same caveat
applies: agreement after a discussion is persuasion, not independent
convergence.

The thread is O(N²) in prompt tokens — turn *k* re-sends the *k−1* turns before
it — so a turn is capped at ~300 words and `--discuss-rounds` defaults to 2.
The budget gate prices the longest packet times the requests per lane
(`rounds + 1`), and `deadline_seconds` bounds one turn rather than the run.
Every turn is appended to the transcript as soon as it returns, so a run that
dies at turn 17 leaves 16 turns on disk. The closings are saved as `results`,
which makes a discussion transcript a valid parent for `--revise`, for `--diff`
synthesis, or for another `--discuss`.

`--discuss` refuses `--each`, `--panel` and `--revise` alongside it (there is
nothing to fan out — each turn is built from the ones before it), and refuses
fewer than two lanes.

Use it when lanes split on a **judgment** — severity, reachability, which fix
is right — and the split is what you need settled. When the only dissent
rests on a **checkable fact**, check the fact; a discussion costs
`rounds × lanes` requests and can manufacture evidence, a fact check costs one
command.

**What a turn can see.** `--discuss` drives the lanes itself, through the same
`http` / `cli` / `acp` harnesses as round 1. An `http` or `acp` turn sees the
shared packet and nothing else — no tools, no repo — so anything the panel
needs to check must already be in the openings or in the focus text (quote
contiguous excerpts, mark elisions). A `cli` turn has whatever its vendor CLI
normally has. If round 1 was a tool round driven by `skill/toolpanel.py`, its
per-lane answer files are not transcripts; fold them into one with
`skill/toolpanel-seed.py` and seed from that:

```console
skill/toolpanel-seed.py brief.md seed.json answers/*.md
roundtable --lanes HAL9000,SHODAN,Cortana --discuss seed.json "the split to settle"
```

**What the transcript holds.** `brief` (the round-1 brief), `results` (the
closings), `discussion` (every turn: `turn`, `pass`, `alias`, `lane`, `answer`,
`seconds`, `cost`), `aliases` (letter → lane, so the anonymity is auditable),
`parent` (the seed transcripts, `[]` for `new`), `round`, `mode: discuss`.

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
  one turn). An `acp` lane's `config_options` (thought level, mode, model —
  whatever the agent lists under `configOptions`) are applied with
  `session/set_config_option` after `session/new` and before the prompt, because
  the agent's own CLI flags do not reach them; a rejected or unhonoured value
  fails the lane rather than answering at the wrong setting.
- Tool access is a property of the harness, not the panel. `http` and `acp`
  lanes see the brief and nothing else — put the material in it. `cli` lanes run
  the vendor's CLI with its normal tools and may read, run, and write in the
  directory they are launched from; commit first, and expect them to
  investigate. A lane keeps its tools until it cheats (reads another lane's
  answer, edits the code under review, games the question); then it loses them.
- Lanes never see each other's answers. That is the point; it is also why they
  cannot build on one another.
- A weak lane is worse than an absent one — it still gets counted. Prune the
  roster on quality, and record known defects in each lane's `notes`.
