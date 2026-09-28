# Backlog

Mirrors the [GitHub Issues tab](https://github.com/CryptoJones/FlatlineRoundtable/issues).
Every item here has an issue and vice versa; when one ships, check it off here so
neither side drifts.

## Open

- [x] Optional second round: `--revise latest:N` replays a finished run so each
      lane sees the locked answers (own marked YOURS, peers anonymised) and
      opens with HOLD or REVISE; report marks the round non-independent
      ([#64](https://github.com/CryptoJones/FlatlineRoundtable/issues/64)) — shipped in PR #65
- [ ] `acp` harness: pool-acp lane times out waiting for session/prompt while
      poolside streams a full answer — generated, billed, never delivered
      ([#56](https://github.com/CryptoJones/FlatlineRoundtable/issues/56))
- [ ] TODO: assign mathematical weighting to lanes based on model ability —
      per-lane weights from each lane's verified track record (CORRECT / PARTLY /
      WRONG), Beta-smoothed, optionally seeded from benchmark scores. Weights rank
      findings for verification and annotate the synthesis; they never decide a
      finding. Motivated by the 2026-09-27 rounds: six lanes agreed on the same
      wrong "bug" while each real defect came from one lane.
      ([#89](https://github.com/CryptoJones/FlatlineRoundtable/issues/89))
- [ ] `--each` silently defeats `--max-spend`: no budget gate before fan-out
      ([#71](https://github.com/CryptoJones/FlatlineRoundtable/issues/71))
- [ ] Unknown model id estimates to $0, so `--max-spend` cannot bind
      ([#72](https://github.com/CryptoJones/FlatlineRoundtable/issues/72))
- [ ] Transcripts are world-readable (0755 dir / 0644 file)
      ([#73](https://github.com/CryptoJones/FlatlineRoundtable/issues/73))
- [ ] `--diff` is silently dropped under `--each`
      ([#74](https://github.com/CryptoJones/FlatlineRoundtable/issues/74))
- [ ] `--revise latest:N` counts files, not lanes; wrong for `--panel` rounds
      ([#75](https://github.com/CryptoJones/FlatlineRoundtable/issues/75))
- [ ] `--revise latest:<non-int>` throws a raw `ValueError` traceback
      ([#76](https://github.com/CryptoJones/FlatlineRoundtable/issues/76))
- [ ] Env scrub has no test on the `acp` harness (shared `child_env`)
      ([#77](https://github.com/CryptoJones/FlatlineRoundtable/issues/77))
- [ ] No per-lane CA bundle: self-hosted endpoints force global TLS bypass
      ([#78](https://github.com/CryptoJones/FlatlineRoundtable/issues/78))
- [ ] Report per-lane cost and run-level spend in `--json` (and under `--diff`)
      ([#79](https://github.com/CryptoJones/FlatlineRoundtable/issues/79))
- [ ] Give a round an identity (`run_id`) so `--revise latest-run` is robust
      ([#80](https://github.com/CryptoJones/FlatlineRoundtable/issues/80))
- [ ] Add `--dry-run` / `--estimate`: priced pre-flight without dispatching
      ([#81](https://github.com/CryptoJones/FlatlineRoundtable/issues/81))
- [ ] Transcripts accumulate forever; add bounded retention
      ([#82](https://github.com/CryptoJones/FlatlineRoundtable/issues/82))
- [ ] `synthesize()` collects readers serially instead of via `as_completed`
      ([#83](https://github.com/CryptoJones/FlatlineRoundtable/issues/83))
- [ ] `load_pricing` caches the whole catalog and re-parses it every run
      ([#84](https://github.com/CryptoJones/FlatlineRoundtable/issues/84))
- [ ] No integration tests for `--each` budget gate, transcript integrity,
      unknown price, `--diff`+`--each`
      ([#85](https://github.com/CryptoJones/FlatlineRoundtable/issues/85))
- [ ] Add Python 3.14 to the CI matrix (suite already passes on it)
      ([#86](https://github.com/CryptoJones/FlatlineRoundtable/issues/86))

## Verification set

Run before any PR. Most of these are behavioural and no test suite covers them.
The first two items and the config-parse check now run in CI on every PR; the
rest still need a human, and the env-scrub and orphan-kill checks especially.

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

- [x] Corrected #46: an empty answer with `finish_reason: length` is variance,
      not determinism — reasoning usage ranged 20–21,606 tokens across runs of
      one identical brief. The retry is restored; the message naming
      `max_tokens` is kept for when retries are exhausted.
      ([#53](https://github.com/CryptoJones/FlatlineRoundtable/issues/53))
- [x] `THE READERS DISAGREE` fired when readers merely differed in how liberally
      they named lanes, not in judgement — a conflict now requires disjoint
      placements rather than unequal ones. Found on a live run whose own reader
      reported "no genuine disagreement" while every lane was flagged.
      ([#51](https://github.com/CryptoJones/FlatlineRoundtable/issues/51))
- [x] An empty answer with `finish_reason: length` is a doomed retry, not a
      transient one — the model spent its whole budget on reasoning and will
      do it again. Fails once with an actionable message instead of billing
      `retries` more certain failures.
      ([#46](https://github.com/CryptoJones/FlatlineRoundtable/issues/46))
- [x] `classify_mentions` anchors sections on the first occurrence anywhere in the
      text, so a reader restating its instructions collapses every lane into one
      bucket and manufactures phantom `THE READERS DISAGREE` rows. Lane matching
      is unbounded substring. Regression from #16. ([#18](https://github.com/CryptoJones/FlatlineRoundtable/issues/18))
- [x] `--diff` synthesis runs outside the budget, semaphores, pacer and deadline.
      It is the largest request of the run and, since #16, is sent twice. ([#19](https://github.com/CryptoJones/FlatlineRoundtable/issues/19))
- [x] A `cli` lane with neither `{prompt}` nor `stdin: true` sends no prompt at
      all, and validation accepts it while its error text promises otherwise. A
      lane can vote without seeing the question. ([#20](https://github.com/CryptoJones/FlatlineRoundtable/issues/20))
- [x] The per-vendor semaphore takes the first lane's `concurrency` rather than the
      smallest; `build_pacers` gets the same problem right. ([#21](https://github.com/CryptoJones/FlatlineRoundtable/issues/21))
- [x] `SCRUB_ENV` covers API keys but not `CLAUDE_CODE_USE_BEDROCK` / `_VERTEX` or
      `ANTHROPIC_BASE_URL`, which bill a subscription lane with no key involved. ([#22](https://github.com/CryptoJones/FlatlineRoundtable/issues/22))
- [x] Nothing detects that two lanes resolved to the same underlying model.
      `served_by` is captured and never used, so an echo can be reported as
      convergence — the one claim the tool exists to make. ([#23](https://github.com/CryptoJones/FlatlineRoundtable/issues/23))
- [x] `acp_lane` passes the real `cwd` to a coding agent, never drains its stderr,
      and never reaps the killed process. ([#24](https://github.com/CryptoJones/FlatlineRoundtable/issues/24))
- [x] `deadline_seconds` bounds nothing: both checks run before the semaphore
      acquire, so they pass at t=0 and never apply again. ([#25](https://github.com/CryptoJones/FlatlineRoundtable/issues/25))
- [x] A config whose lanes are all `active: false` reports `0/0 answered` and exits
      0, claiming success having asked nobody anything. ([#26](https://github.com/CryptoJones/FlatlineRoundtable/issues/26))
- [x] The pre-flight estimate assumes one call per lane, but retries can bill the
      prompt up to `(1 + retries)` times. ([#27](https://github.com/CryptoJones/FlatlineRoundtable/issues/27))
- [x] `cli_lane` filters a hardcoded clock emoji — one machine's shell-hook banner
      baked into a public tool, silently deleting answer lines. ([#28](https://github.com/CryptoJones/FlatlineRoundtable/issues/28))
- [x] A lane named `Off`, `No`, `Yes` or `On` is coerced to a YAML 1.1 boolean and
      fails with a misleading "has no name". ([#29](https://github.com/CryptoJones/FlatlineRoundtable/issues/29))
- [x] `Retry-After: 1.5` fails `.isdigit()` and is ignored in favour of the default
      backoff. ([#30](https://github.com/CryptoJones/FlatlineRoundtable/issues/30))
- [x] The stub server in the test suite is hand-written, so its response *shape*
      can drift from what vendors actually return without CI noticing. Add
      golden fixtures captured from real responses, and optionally a
      `workflow_dispatch`-only live smoke job. A heavier emulator (LocalAI,
      Ollama) was considered and rejected: they serve *correct* responses, while
      the value here is in the malformed ones. ([#13](https://github.com/CryptoJones/FlatlineRoundtable/issues/13))
- [x] `--diff` uses two independent readers from different vendors and reports
      where the *readings* disagree about a lane's classification, so the
      synthesizer's own bias is visible rather than invisible. The comparison is
      mechanical — a third model judging the first two would only move the
      problem. ([#8](https://github.com/CryptoJones/FlatlineRoundtable/issues/8))
- [x] Pre-flight estimate calibrates itself from observed `usage.prompt_tokens`
      instead of assuming 4 chars/token, falling back to the constant until a
      model has enough samples. Note the original premise was wrong: 4
      chars/token **under**-estimates a markdown-heavy personality
      (`gpt-oss-120b` measures 3.30), which is the unsafe direction for a budget
      check, not a wide-but-safe margin.
      ([#9](https://github.com/CryptoJones/FlatlineRoundtable/issues/9))
- [x] Per-vendor rate-limit awareness — optional `rpm` per lane, shared across a
      vendor group and taking the smallest value, spacing request *starts* so a
      per-minute cap is not tripped before any 429 arrives. `concurrency` bounds
      how many run at once, which is a different quantity.
      ([#7](https://github.com/CryptoJones/FlatlineRoundtable/issues/7))
- [x] Free-lane retry resilience — a 200 carrying an error body and an empty
      answer are both retried instead of ending the lane, and `Retry-After` is
      honoured to 90s rather than capped at 30s below the 60s window vendors
      actually advertise. ([#11](https://github.com/CryptoJones/FlatlineRoundtable/issues/11))
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
