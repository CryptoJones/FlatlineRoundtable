# Backlog

Mirrors the [GitHub Issues tab](https://github.com/CryptoJones/FlatlineRoundtable/issues).
Every item here has an issue and vice versa; when one ships, check it off here so
neither side drifts.

## Open

- [ ] Per-vendor rate-limit awareness. `Retry-After` is honoured on 429, but a
      wide fan-out can still trip a vendor's per-minute cap before any 429
      arrives. ([#7](https://github.com/CryptoJones/FlatlineRoundtable/issues/7))
- [ ] `--diff` synthesis is one lane's reading, not a neutral one. Consider
      running it on two lanes and reporting where the *syntheses* differ. ([#8](https://github.com/CryptoJones/FlatlineRoundtable/issues/8))
- [ ] The pre-flight estimate uses ~4 chars/token rather than a real tokenizer,
      so it overestimates. Safe direction, but a wide margin on long briefs. ([#9](https://github.com/CryptoJones/FlatlineRoundtable/issues/9))

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

- [x] Wrap protocol-over-stdio agents so they can serve as lanes — new `acp`
      harness: initialize → session/new → session/prompt → process-group kill,
      one turn only. ([#2](https://github.com/CryptoJones/FlatlineRoundtable/issues/2))
- [x] Real pricing pulled from the gateway and cached for a day; prompt and
      completion charged at their separate rates. ([#3](https://github.com/CryptoJones/FlatlineRoundtable/issues/3))
- [x] `--max-spend` / `budget_usd` enforced **before dispatch** against a
      worst-case estimate, so an overrun is prevented, not reported. ([#4](https://github.com/CryptoJones/FlatlineRoundtable/issues/4))
- [x] Test suite — 25 tests, stub HTTP server and fake CLI binaries, no vendor
      contacted and nothing spent. ([#5](https://github.com/CryptoJones/FlatlineRoundtable/issues/5))
- [x] `--diff` mode reporting AGREED / SPLIT / LONE CLAIMS. ([#6](https://github.com/CryptoJones/FlatlineRoundtable/issues/6))
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
