# Backlog

Mirrors the [GitHub Issues tab](https://github.com/CryptoJones/FlatlineRoundtable/issues).
Every item here has an issue and vice versa — except the foundational entries at
the foot of **Done**, which predate the tracker. When one ships, check it off here
so neither side drifts.

## Open

Bugs first — the cost-guard and answer-loss class this tool exists to prevent,
then security, then features/optimisation, then tests. Each has a GitHub issue
and vice versa.

### Epic: encrypted SQLite is the authoritative store for lanes, secrets and (next) metrics — YAML retired ([#105](https://github.com/CryptoJones/FlatlineRoundtable/issues/105)) — DONE 2026-10-06

- [x] Split config validation from YAML parsing; route scripts through
      `rt.fetch_keys` ([#106](https://github.com/CryptoJones/FlatlineRoundtable/issues/106)) — shipped in PR #113
- [x] Encrypted store: `db init|migrate|doctor` and
      `secrets set|check|list|rotate|rm|rekey` ([#107](https://github.com/CryptoJones/FlatlineRoundtable/issues/107)) — shipped in PR #114
- [x] Lane config in the store: `lanes`, `defaults`, `globals`, `lane_versions`,
      `db export|import`, `import-yaml` ([#108](https://github.com/CryptoJones/FlatlineRoundtable/issues/108)) — shipped in PR #123
- [x] Run from the store: `load_config` reads the DB, `fetch_keys` reads secrets,
      YAML retired ([#109](https://github.com/CryptoJones/FlatlineRoundtable/issues/109)) — shipped in PR #124
- [x] `db backup|restore` and the telesto restic job ([#110](https://github.com/CryptoJones/FlatlineRoundtable/issues/110)) — shipped in PR #125
- [x] Fleet rollout notes and the Python 3.11 floor ([#111](https://github.com/CryptoJones/FlatlineRoundtable/issues/111)) — shipped in PR #126

### Epic: run the roundtable from inside Orca — local web UI, no fork ([#115](https://github.com/CryptoJones/FlatlineRoundtable/issues/115)) — DONE 2026-10-03

The UI lives in its own private repo,
[FlatlineRoundtableUI](https://github.com/CryptoJones/FlatlineRoundtableUI). AGENTS.md
§ Scope keeps long-lived processes out of this one.

- [x] `--run-id` ties an `--each` run's transcripts together; `--list --json` for tools
      ([#116](https://github.com/CryptoJones/FlatlineRoundtable/issues/116)). Merged in PR #117.
- [x] UI: server skeleton and read-only run history browser
      ([UI#1](https://github.com/CryptoJones/FlatlineRoundtableUI/issues/1))
- [x] UI: start a run, with live per-lane status and cancel
      ([UI#2](https://github.com/CryptoJones/FlatlineRoundtableUI/issues/2))
- [x] UI: `--diff`, `--revise` and `--discuss` on a finished run
      ([UI#3](https://github.com/CryptoJones/FlatlineRoundtableUI/issues/3))
- [x] UI: Orca launcher (quick command and `orca tab create`)
      ([UI#4](https://github.com/CryptoJones/FlatlineRoundtableUI/issues/4))
- [x] Upstream Orca: let plugin panels reach loopback or their own worker
      ([UI#5](https://github.com/CryptoJones/FlatlineRoundtableUI/issues/5)). Filed as
      [stablyai/orca#25129](https://github.com/stablyai/orca/issues/25129).
- [x] `--synthesize`: the `--diff` readers over a finished run's transcripts
      ([#118](https://github.com/CryptoJones/FlatlineRoundtable/issues/118)). Merged in PR #120.
- [x] UI: a run cancelled before any lane answered survives a server restart
      ([UI#6](https://github.com/CryptoJones/FlatlineRoundtableUI/issues/6))

### Other open items

- [x] Transcripts clobber each other under `--each -j N`, losing paid answers —
      one-second filename stamp + shared `.json.tmp` collide; #58's failure mode
      via the filename instead of write order
      ([#70](https://github.com/CryptoJones/FlatlineRoundtable/issues/70)) — shipped in PR #88
- [x] `--each` silently defeats `--max-spend` — the pre-dispatch budget gate runs
      after the fan-out returns, so the parent never checks the whole-panel estimate
      ([#71](https://github.com/CryptoJones/FlatlineRoundtable/issues/71)) — fixed on fix/open-issues-batch
- [x] Unknown model id estimates to `$0`, so `--max-spend` cannot bind — an http
      lane with no resolvable price fails open on the guard meant to fail closed
      ([#72](https://github.com/CryptoJones/FlatlineRoundtable/issues/72)) — fixed on fix/open-issues-batch
- [x] Transcripts are world-readable (`0755` dir / `0644` file) — full briefs and
      answers exposed to any local user or tool-bearing `cli` lane
      ([#73](https://github.com/CryptoJones/FlatlineRoundtable/issues/73)) — fixed on fix/open-issues-batch
- [x] `--diff` is silently dropped under `--each` — the flag isn't forwarded to
      children, so synthesis no-ops with exit 0 on the recommended invocation
      ([#74](https://github.com/CryptoJones/FlatlineRoundtable/issues/74)) — fixed on fix/open-issues-batch
- [x] `--revise latest:N` counts files, not lanes — wrong for a `--panel` round,
      and misleading after a clobber; docs say "lane count"
      ([#75](https://github.com/CryptoJones/FlatlineRoundtable/issues/75)) — fixed on fix/revise-latest-n-counts-lanes (v1.1.0)
- [x] `--revise latest:<non-int>` throws a raw `ValueError` traceback instead of
      the clean, actionable error every other bad input gives
      ([#76](https://github.com/CryptoJones/FlatlineRoundtable/issues/76)) — fixed on fix/open-issues-batch
- [x] Lane harnesses leak file descriptors — `acp_lane` / `cli_lane` Popen pipes
      and `http_lane`'s retried `HTTPError` are never closed (28 `ResourceWarning`s,
      all inside `roundtable`, none in the stub; found doing #86)
      ([#90](https://github.com/CryptoJones/FlatlineRoundtable/issues/90)) — fixed on fix/lane-fd-leaks (v1.1.1); CI now
      fails on any `ResourceWarning`
- [x] Env scrub has no test on the `acp` harness — `child_env()` is shared by
      `cli` and `acp`, but only `cli` asserts a key stays out; drift reopens #22
      ([#77](https://github.com/CryptoJones/FlatlineRoundtable/issues/77)) — fixed on fix/open-issues-batch
- [x] No per-lane CA bundle — a self-hosted/private-CA endpoint forces a global
      TLS bypass that also weakens the OpenRouter lanes
      ([#78](https://github.com/CryptoJones/FlatlineRoundtable/issues/78)) — fixed on feat/per-lane-ca-bundle (v1.2.0):
      `ca_bundle` and a per-lane-only `insecure`
- [x] Report per-lane `cost` and run-level spend in `--json` (and under `--diff`) —
      the number cron/CI callers need is computed but not surfaced machine-readably
      ([#79](https://github.com/CryptoJones/FlatlineRoundtable/issues/79)) — fixed on feat/json-spend (v1.3.0);
      plain `--json` stays a list, see #131
- [ ] Plain `--json` emits an object with `results` + `spend` — a breaking
      shape change held for 2.0; #79 could not add a top-level key to a bare list
      ([#131](https://github.com/CryptoJones/FlatlineRoundtable/issues/131))
- [x] Discussion mode: `--discuss` lets lanes share one context and take turns,
      one lane in flight at a time — the lightweight stand-in for a Buzz-style
      conversation, no resident runtimes or bus
      ([#93](https://github.com/CryptoJones/FlatlineRoundtable/issues/93)) — shipped in PR #94
- [x] `acp` lanes: per-lane `config_options` applied via `session/set_config_option`
      (thought level, mode, model) — the agent's CLI flags never reach these; a
      rejected or unhonoured value fails the lane loudly
      ([#95](https://github.com/CryptoJones/FlatlineRoundtable/issues/95)) — shipped in PR #97
- [x] Tool rounds: `skill/toolpanel.py` gives `http` lanes read-only repo tools
      (`read_file` / `grep` / `list_dir` / `git`) for grounded reviews; lane settings
      table and operating rules in `skill/SKILL.md`
      ([#96](https://github.com/CryptoJones/FlatlineRoundtable/issues/96)) — shipped in PR #97
- [x] `--discuss`: a fact first introduced mid-thread propagates unverified — a
      fabricated "24h expiry" was cited as evidence by the next three turns; both
      prompts now call an unsourced mid-thread fact a claim, and the skill tells the
      reader to check it against the code
      ([#98](https://github.com/CryptoJones/FlatlineRoundtable/issues/98)) — shipped in PR #99
- [x] Give a round an identity (`run_id`) so `--revise latest-run` is robust —
      replaces the fragile `latest:N` file-count heuristic with a real "round"
      ([#80](https://github.com/CryptoJones/FlatlineRoundtable/issues/80)) — run_id in PR #117,
      `latest-run` in PR #122
- [x] Add `--dry-run` / `--estimate` — a priced pre-flight that shows per-lane and
      panel worst-case cost without dispatching (and surfaces unpriced lanes)
      ([#81](https://github.com/CryptoJones/FlatlineRoundtable/issues/81))
      — shipped in PR #133
- [ ] Transcripts accumulate forever — add bounded, opt-in retention that never
      deletes a `parent` of a later round
      ([#82](https://github.com/CryptoJones/FlatlineRoundtable/issues/82))
- [ ] TODO: assign mathematical weighting to lanes based on model ability —
      per-lane weights from each lane's verified track record (CORRECT / PARTLY /
      WRONG), Beta-smoothed, optionally seeded from benchmark scores. Weights rank
      findings for verification and annotate the synthesis; they never decide a
      finding. Motivated by the 2026-09-27 rounds: six lanes agreed on the same
      wrong "bug" while each real defect came from one lane
      ([#89](https://github.com/CryptoJones/FlatlineRoundtable/issues/89))
- [ ] (feat-req) `--metrics` to show lane accuracy metrics — per-lane rounds
      answered, findings made, verified CORRECT / PARTLY / WRONG counts and rates,
      lone-claim hit rate, fabrication count, tool-round grounding stats; scoped by
      `latest:N` / transcript / `--lanes`, `--json` for raw numbers, zero network.
      The read side of the outcome record #89 weights on; never decides a finding
      ([#103](https://github.com/CryptoJones/FlatlineRoundtable/issues/103))
- [x] `synthesize()` collects readers serially instead of via `as_completed` — free
      wall-clock win, and removes a serialization trap in the reader loop
      ([#83](https://github.com/CryptoJones/FlatlineRoundtable/issues/83)) — fixed on fix/open-issues-batch
- [ ] `load_pricing` caches the whole catalog and re-parses it every run — cache the
      reduced `{id: (in, out)}` map instead
      ([#84](https://github.com/CryptoJones/FlatlineRoundtable/issues/84))
- [ ] No integration tests for `--each` budget gate, transcript integrity, unknown
      price, or `--diff`+`--each` — the four high-severity behaviours CI doesn't cover
      ([#85](https://github.com/CryptoJones/FlatlineRoundtable/issues/85))
- [x] Add Python 3.14 to the CI matrix — the suite already passes on it (verified
      locally), free signal for no extra dependency
      ([#86](https://github.com/CryptoJones/FlatlineRoundtable/issues/86)) — fixed on fix/open-issues-batch

### Epic: encrypted SQLite is the authoritative store for lanes, secrets and (next) metrics — YAML retired ([#105](https://github.com/CryptoJones/FlatlineRoundtable/issues/105))

One encrypted, structured store per host replaces the YAML file: lane config with
an edit history, lane auth secrets (AES-256-GCM, DB key in `pass`), and the tables
the metrics work (#80, #79, #103, #89, #82, #75) needs a place to write to. Lanes
are edited through subcommands; backups go to telesto. Decisions, definition of
done and risks live on the epic. Children in dependency order:

- [ ] Split config validation from YAML parsing; route scripts through `rt.fetch_keys`
      ([#106](https://github.com/CryptoJones/FlatlineRoundtable/issues/106))
- [ ] Encrypted store: `db init|migrate|doctor` and `secrets set|check|list|rotate|rm|rekey`
      ([#107](https://github.com/CryptoJones/FlatlineRoundtable/issues/107)) — after #106
- [ ] Lane config in the store: `lanes`, `defaults`, `globals`, `lane_versions`,
      `db export|import`, `import-yaml`
      ([#108](https://github.com/CryptoJones/FlatlineRoundtable/issues/108)) — after #107
- [ ] Run from the store: `load_config` reads the DB, `fetch_keys` reads secrets,
      YAML retired
      ([#109](https://github.com/CryptoJones/FlatlineRoundtable/issues/109)) — after #108
- [ ] `db backup|restore` and the telesto restic job
      ([#110](https://github.com/CryptoJones/FlatlineRoundtable/issues/110)) — after #107
- [ ] Fleet rollout notes and the Python 3.11 floor
      ([#111](https://github.com/CryptoJones/FlatlineRoundtable/issues/111)) — after #109

## Verification set

Run before any PR. Several of these are behavioural and were once human-only;
the ones now covered by an automated test name the test, so a green `make`-style
suite stands in for them. The rest still need a person, because they assert on
the real environment (process table, `ps`, `git`, `install.sh`) rather than a
stub.

- [ ] `./roundtable --list` — correct route per lane, **zero network calls.**
      *Automated:* `test_list_makes_no_network_calls`, plus a dedicated CI step
      that points the process at a dead proxy.
- [ ] Full run — **every active lane answers**, exit code `0`. Partial delivery
      must exit non-zero; a silent lane is the bug this tool exists to eliminate.
      *Automated:* `test_all_answered_exits_zero`, `test_a_silent_lane_fails_the_run`.
- [ ] **Env scrub:** run with an invalid `ANTHROPIC_API_KEY` exported and confirm
      a `cli` lane still succeeds via OAuth. If it fails on the bad key, the
      scrub is broken and that lane has silently moved onto metered billing.
      *Automated:* `test_ambient_api_key_never_reaches_the_child`,
      `test_bedrock_and_vertex_routes_are_scrubbed`. Re-check by hand when a new
      vendor CLI is added — the patterns are broad, but a novel billing route is
      exactly what they would miss.
- [ ] **Orphan kill:** point a `cli` lane at a hanging command with a short
      timeout; confirm it fails cleanly and `pgrep` finds no survivor.
      *Automated:* `test_hung_lane_is_killed_and_leaves_no_orphan`.
- [ ] **Missing key:** point a lane at a secret the store does not hold; confirm
      it fails loudly naming the secret, and never calls unauthenticated.
      *Automated:* `test_missing_secret_aborts_the_run`,
      `test_no_db_key_and_no_pass_aborts_the_run`,
      `test_a_store_secret_reaches_the_authorization_header`.
- [ ] **No key in argv:** during a run, `ps auxww` shows no key. *(human — reads
      the live process table; keys are held in memory and set as headers only.)*
- [ ] **No key in output:** transcript and `--json` contain no `Authorization`
      value. *Partly automated:* `test_fixtures_carry_no_credentials` scans the
      golden fixtures; confirm by hand against a real transcript after a run.
- [ ] `git check-ignore -v roundtable.db roundtable.db-wal` confirms a store
      cannot be committed; `git status --porcelain` is clean after a run. *(human)*
- [ ] **Store secrets never in plaintext:** `secrets set X --stdin`, then the
      `.db`, `-wal` and `-shm` bytes do not contain the value; a positional value
      is refused; a different DB key dies on the key-check value.
      *Automated:* `test_plaintext_is_absent_from_db_wal_and_shm`,
      `test_a_positional_value_is_refused`,
      `test_a_different_key_fails_on_the_key_check_value`. On a real host, also
      `ps auxww` during `db init` shows no key (it goes to `pass insert` on stdin).
- [ ] `./install.sh` then `./install.sh --uninstall` round-trips, and refuses to
      delete anything that is not a symlink. *(human — touches `$HOME`, no test)*
- [ ] `./install.sh --init` with no store creates one (`db doctor` passes), and
      with a store present leaves it byte-identical. *(CI covers both in a
      throwaway HOME)*
- [ ] **Restore drill:** `restic restore latest` from telesto → `db restore` into
      a scratch `--config` → `db doctor` → `secrets check` → `--list`, and the
      scratch store's `db export` equals the live one. *(human — needs telesto and
      the real DB key; the commands are in the README.)* Last run 2026-10-06 on
      makemake: all steps ok, 9/9 secrets present, export identical.
      *Automated parts:* `TestBackup`.

## Done

- [x] `acp` harness: a pool-acp lane timed out waiting for `session/prompt` while
      poolside streamed a full answer — generated, billed, never delivered. The
      client now answers agent-initiated requests (reject option, not `cancelled`)
      and salvages whatever streamed before the deadline, marked truncated
      ([#56](https://github.com/CryptoJones/FlatlineRoundtable/issues/56)) — shipped in PR #61;
      the reject-vs-cancel refinement followed in PR #63 ([#62](https://github.com/CryptoJones/FlatlineRoundtable/issues/62))
- [x] Docs claimed lanes have no tools; `cli` lanes run the vendor CLI with its
      full toolset (HAL9000 wrote and deleted a probe test inside a reviewed
      checkout, 2026-09-05). Tool access is now documented as a property of the
      harness, not the panel, with revoke-on-cheating and pre-round hygiene
      ([#66](https://github.com/CryptoJones/FlatlineRoundtable/issues/66)) — shipped in PR #67
- [x] Optional second round: `--revise latest:N` replays a finished run so each
      lane sees the locked answers (own marked YOURS, peers anonymised) and
      opens with HOLD or REVISE; report marks the round non-independent
      ([#64](https://github.com/CryptoJones/FlatlineRoundtable/issues/64)) — shipped in PR #65
- [x] A run that dies mid-fan-out lost every answer it already collected
      ([#58](https://github.com/CryptoJones/FlatlineRoundtable/issues/58)) —
      `list(pool.map(...))` held all answers in memory and wrote the transcript
      only after the last lane returned, so any interruption discarded completed
      lanes, paid `http` ones included. Now persisted after every lane via
      `as_completed`, atomically, marked `"partial": true` until the run finishes.
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
- [x] Test suite — stub HTTP server and fake CLI binaries, no vendor contacted
      and nothing spent. Grown from 25 to 134 tests as each defect below landed.
      ([#5](https://github.com/CryptoJones/FlatlineRoundtable/issues/5))
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
