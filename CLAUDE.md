# AGENTS.md — AI Agent Contributor Guide (FlatlineRoundtable)

Read this before changing `roundtable`. Several things that look like clutter
are load-bearing, and the comments explaining why are in the code — do not strip
them.

## ONE RUN PER LANE — the rule agents keep breaking

**Never run the whole panel in one invocation.** `roundtable --each` runs each
lane as its own process; `--lanes NAME` runs one. A bare multi-lane call is
refused by the tool, deliberately.

The reason is not style. A single invocation finishes when its **slowest** lane
finishes, so every lane inherits the worst lane's fate: one slow lane sets the
wall-clock for all of them, raising its timeout pushes the whole run past the
caller's timeout, and a lane that dies cannot be retried without rerunning
everything — including paid `http` lanes that already billed. Lanes are supposed
to be independent. A shared deadline makes their failures dependent.

Measured 2026-08-30: the poolside/ACP lane needs ~400s alone on a 110KB brief and
exceeded 780s under 12-lane contention. Four consecutive rounds lost its answer,
and each loss was avoidable. Raising its ceiling only made every *other* lane
wait longer.

`--panel` restores the old shared-deadline behaviour for anyone who genuinely
wants it. If you find yourself reaching for it to "keep things simple", you are
about to reintroduce the bug this guard exists to prevent.

## Things that must not be "simplified"

**The env scrub (`SCRUB_ENV`).** `cli` lanes ride a subscription via OAuth and
cost nothing — *unless* an API key is present in the environment, in which case
the vendor CLI prefers it and bills metered credits instead. Removing the scrub
turns free lanes into paid ones with no error and no visible difference in
output. This is the single easiest way to make this tool quietly cost money.

**`start_new_session=True` + `killpg`.** A plain subprocess timeout does not kill
a child process tree. A hung CLI — or one sitting at a login prompt — survives
as an orphan. Orphaned lanes billing forever are the exact failure this project
was built to eliminate.

**Keys fetched once, before fan-out.** The DB key comes from `pass`, and
concurrent `pass show` calls against one `gpg-agent` either serialize behind a
single pinentry or storm and fail in a non-tty context. Resolve every secret
while still single-threaded so one clear error replaces N identical ones.

**`.splitlines()[0]` on a stored value.** `pass` returns the whole file; the
secret is the first line. `secrets set` and `import-yaml --pull-secrets` keep
only that line. Storing the blob puts trailing metadata into an `Authorization`
header.

**Per-vendor concurrency.** A llama.cpp server run with `--parallel 1` serves one
request at a time. Fanning out against it queues every lane past its own timeout.

**Non-zero exit on partial delivery.** A silent lane is the bug this tool exists
to eliminate. Do not soften this to a warning.

**Timeouts are not retried.** The request may have completed and billed already;
a blind retry double-charges a metered lane for an answer you paid for.

**`--discuss` is sequential, in one process.** Each turn's packet is built
from the turns before it, so there is nothing to fan out, and one-lane-in-flight
is the memory property the mode exists for (it replaces a fleet with a resident
runtime per lane). Do not "speed it up" with a pool, do not forward it to
`--each` children, and do not make it a long-lived process with a bus — that is
the thing it was built to avoid. The thread is written to the transcript after
every turn precisely so a sequential run that dies keeps what was said.

## Secrets

No key value goes in this repo, `argv`, a transcript, or `--json` output, and
the store never holds one in plaintext. A lane names a secret; its value is
AES-256-GCM-encrypted in the store and decrypted into memory only for the run.
The DB key lives in `pass` (`flatline-roundtable/db-key`), never beside the
store. The store lives at `~/.local/share/flatline-roundtable/roundtable.db`,
deliberately outside the worktree — `.gitignore` is not a security boundary.

**A store failure must never fail a paid run.** Reading the roster and secrets
happens before any lane is dispatched, so a broken store stops the run before
it spends. Anything the run path WRITES to the store later (metrics, grades)
must be best-effort: an answer already paid for is delivered even if the write
fails.

**YAML is retired.** The store is the only configuration. PyYAML is imported
only inside `import-yaml`, the one-time move off YAML; do not bring it back to
the run path.

## Scope

The roundtable gives lanes no tools of its own — an `http` or `acp` lane has
nothing but the brief, a `cli` lane has whatever the vendor CLI has — and this is
not an agent framework. If a change requires a long-lived process, a message
bus, or a publish step, it belongs in a different project — those are precisely
what was removed.

## Contributing

This is a public repo: **feature branch + PR, never a direct commit to `main`.**
Keep `BACKLOG.md` in sync with the GitHub Issues tab in both directions. PR
bodies end with the Nebraska signature line.

Before opening a PR, run the verification set in `BACKLOG.md` — especially the
env-scrub and orphan-kill checks, which no test suite covers.

---

*Proudly Made in Nebraska. Go Big Red! 🌽 <https://xkcd.com/2347/>*
