# Backlog

Mirrors the [GitHub Issues tab](https://github.com/CryptoJones/FlatlineRoundtable/issues).
Every item here has an issue and vice versa; when one ships, check it off here so
neither side drifts.

## Open

- [ ] Wrap protocol-over-stdio agents so they can serve as `cli` lanes. Some
      assistants expose no one-shot print mode, only a JSON-RPC stdio protocol,
      which is why such lanes ship `active: false`. ([#2](https://github.com/CryptoJones/FlatlineRoundtable/issues/2))
- [ ] Cost estimation only covers lanes with `price_per_mtok` set by hand. Pull
      real pricing from the gateway so `budget_usd` is accurate rather than
      advisory. ([#3](https://github.com/CryptoJones/FlatlineRoundtable/issues/3))
- [ ] `--max-spend` is enforced *after* the run, since token counts are not known
      until responses return. A pre-flight estimate from brief length would let it
      refuse to dispatch. ([#4](https://github.com/CryptoJones/FlatlineRoundtable/issues/4))
- [ ] No test suite. The verification set below is manual. ([#5](https://github.com/CryptoJones/FlatlineRoundtable/issues/5))
- [ ] Consider a `--diff` mode that reports only where lanes disagree, since that
      is the actual product and reading nine full answers does not scale. ([#6](https://github.com/CryptoJones/FlatlineRoundtable/issues/6))

## Verification set

Run before any PR. Most of these are behavioural and no test suite covers them.

- [ ] `./roundtable --list` — correct route per lane, **zero network calls**.
- [ ] Full run — **every active lane answers**, exit code `0`. Partial delivery
      must exit non-zero; a silent lane is the bug this tool exists to eliminate.
- [ ] **Env scrub:** run with an invalid `ANTHROPIC_API_KEY` exported and confirm
      a `cli` lane still succeeds via OAuth. If it fails on the bad key, the
      scrub is broken and that lane has silently moved onto metered billing.
- [ ] **Orphan kill:** point a `cli` lane at a hanging command with a short
      timeout; confirm it fails cleanly and `pgrep` finds no survivor.
- [ ] **Missing key:** point a lane at a nonexistent `pass` entry; confirm it
      fails loudly naming the entry, and never calls unauthenticated.
- [ ] **No key in argv:** during a run, `ps auxww` shows no key.
- [ ] **No key in output:** transcript and `--json` contain no `Authorization`
      value.
- [ ] `git check-ignore -v FlatlineRoundtable.yaml` confirms the real config
      cannot be committed; `git status --porcelain` is clean after a run.
- [ ] `./install.sh` then `./install.sh --uninstall` round-trips, and refuses to
      delete anything that is not a symlink.

## Done

- [x] Direct-call architecture replacing long-lived agent processes — no
      identity, no message bus, no publish step, nothing left running to bill.
- [x] Secrets via `pass` entry names only; keys resolved once, held in memory,
      never in `argv`, transcripts, or `--json`.
- [x] Env scrub so subscription-backed CLI lanes cannot be silently converted to
      metered billing by an ambient API key.
- [x] Process-group kill on CLI timeout.
- [x] Per-vendor concurrency caps for single-slot local servers.
- [x] Transcript written per run.
- [x] Truncation surfaced via `finish_reason` rather than passing a clipped
      answer off as complete.
- [x] `extra_body` denylist so a config typo cannot rewrite the request.

---

*Proudly Made in Nebraska. Go Big Red! 🌽 <https://xkcd.com/2347/>*
