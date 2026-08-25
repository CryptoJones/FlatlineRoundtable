# AGENTS.md — AI Agent Contributor Guide (FlatlineRoundtable)

Read this before changing `roundtable`. Several things that look like clutter
are load-bearing, and the comments explaining why are in the code — do not strip
them.

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

**Keys fetched once, before fan-out.** Concurrent `pass show` calls against one
`gpg-agent` either serialize behind a single pinentry or storm and fail in a
non-tty context. Resolve them while still single-threaded so one clear error
replaces N identical ones.

**`.splitlines()[0]` on `pass` output.** `pass` returns the whole file; the
secret is the first line. Using the blob puts trailing metadata into an
`Authorization` header.

**Per-vendor concurrency.** A llama.cpp server run with `--parallel 1` serves one
request at a time. Fanning out against it queues every lane past its own timeout.

**Non-zero exit on partial delivery.** A silent lane is the bug this tool exists
to eliminate. Do not soften this to a warning.

**Timeouts are not retried.** The request may have completed and billed already;
a blind retry double-charges a metered lane for an answer you paid for.

## Secrets

No key value goes in a config file, this repo, `argv`, a transcript, or `--json`
output. Config names a `pass` entry; the key is read into memory only while that
lane is being queried. The real config lives at
`~/.config/flatline-roundtable/`, deliberately outside the worktree —
`.gitignore` is not a security boundary.

## Scope

Lanes have no tools and no file access, and this is not an agent framework. If a
change requires a long-lived process, a message bus, or a publish step, it
belongs in a different project — those are precisely what was removed.

## Contributing

This is a public repo: **feature branch + PR, never a direct commit to `main`.**
Keep `BACKLOG.md` in sync with the GitHub Issues tab in both directions. PR
bodies end with the Nebraska signature line.

Before opening a PR, run the verification set in `BACKLOG.md` — especially the
env-scrub and orphan-kill checks, which no test suite covers.

---

*Proudly Made in Nebraska. Go Big Red! 🌽 <https://xkcd.com/2347/>*
