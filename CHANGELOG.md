# Changelog

Only externally visible changes are recorded here: mechanism, interface, tests. Internal
implementation detail stays out. Versioning rules: [`docs/versioning.md`](docs/versioning.md).
The long-form reasoning behind each entry (incident, measurement, decision) lives in the design
documents — [`docs/mechanism.md`](docs/mechanism.md) and the Chinese originals in
[`docs/zh/`](docs/zh/).

## v2.2.28 — attribution reads the executor's exit code, and two published verdicts are corrected (2026-09-19)

- **The read side of the CLI entered CI, and so did Python 3.13** (`.github/workflows/ci.yml` ＋
  `tests/test_cli_surface.py` ＋ both READMEs ＋ `CONTRIBUTING.md`). Until now CI exercised only the
  write path (`dry-run`/`tick`/`gardener`/`org-status`); `status`, `redemption --json`, `rotate`,
  `rotate --search` and `version --check` had never run on any CI, even though the docs publish them
  as the reading surface — and `rotate --search`, the documented answer to "moved but still
  findable", had **zero** cases. The new step reuses the cold-start temp state root (`${{ runner.temp }}`)
  so it runs against ledgers that have content, on both ubuntu and windows; `tests/test_cli_surface.py`
  pins the hit and miss directions of `--search` (hit must report `file:line`, miss must report 0 and
  not crash), the exit-code contract of `version --check` offline (behind → 3, equal → 0), clean
  stderr on the success path, and that the Python versions the docs list are exactly the CI matrix.
  **3.13 joins the matrix on measurement, not hope**: this machine's interpreter is 3.13.7 and the
  whole gate battery (pytest / ruff / scan R1–R10 / selftest / prompt-sync / privacy / abs-path) is
  green on it. End-to-end on a copy of the live state root (the live one untouched): `rotate
  --max-bytes 4000` moved 1,290 + 3,462 + 1,233 lines into `archive/`, then `rotate --search`
  reported 20 hits in the archived files (rc=0) and 0 hits for an absent needle (rc=0); the config
  source line printed `defaults、caller` with `IG_EXECUTOR`/`IG_EXECUTOR_TIMEOUT_S` cleared.
- **The project privacy layer is now provable on CI instead of permanently skipped**
  (`tests/data/privacy-deny-sample.txt` ＋ `tests/data/privacy-sentinel/leaky-example.md` ＋
  `tests/test_privacy_deny_layer.py` ＋ `.github/workflows/ci.yml` ＋ both `privacy.md` files).
  The real deny list is machine-specific and stays out of the repository — that is by design and was
  not changed — but as a consequence `test_repo_is_free_of_project_deny_hits` skipped on every CI
  run, so nothing anywhere proved that `--deny` still bites; a broken loader would have read as
  green. The fix is **not** to delete the skip (it is genuine environment adaptation): a committed
  deny sample made of invented terms, plus a sentinel carrying the payload it must catch, now prove
  both directions on ubuntu and windows — deny given → the three rules report hits and exit 1;
  payload removed → zero hits and exit 0 — and the sentinel is itself checked to contribute no
  generic-layer hits, so shipping it cannot dirty the repo-wide gate.
- **Configuration defaults now have one source, and three numeric gates became readable**
  (`src/infinigrow/core/config.py` ＋ `tests/test_config_single_source.py` ＋ both `mechanism.md`
  ＋ `prompts/org-session.md` ＋ both READMEs). `Settings` used to spell its 24 defaults out twice —
  once in `_FIELDS`, once in the class body — so editing one silently separated the runtime default
  from the table humans read (and the table is the published wording). The class body now derives
  from the table, and the test proves the derivation rather than restating it: it fails if a literal
  default reappears. The other half of the gap was invisible thresholds: `DEFAULT_ZERO_GAP` (10
  rows), `TRACE_GATE_FILES` (the "used this tick" gate read "the last few traces" — a number that
  existed only in code) and `review_frozen(max_relight=…)` (never mentioned anywhere outside the
  source, including `prompts/`, although it is the queue the session competes for). Each now carries
  its own number in both originals, in `prompts/org-session.md`, and in a case that interpolates the
  constant — change the constant without the docs and it goes red, in either language. Behaviour
  cases cover four knobs rather than their parsing: cooldown minutes flip the same ledger from
  "cooling" to "gap backfill", `tick_minutes` reaches the scheduler as seconds and rejects
  non-positive values loudly, `executor_timeout_s` really kills a slow executor, and
  `rotate_keep_files` decides how many traces stay while the excess moves (never deletes).
  **No threshold value changed** (`docs/versioning.md`: this is provenance, not mechanism).
- **`tools/split_monolith.py` is registered as parked rather than newly tested** (`CONTRIBUTING.md`).
  It is analysis-only and its `--src` input — the v1 monolith — is not in this repository, so a
  behavioural case would mean committing a fabricated monolith and testing the fixture; CI keeps
  covering its `--help` syntax, and the note records what to add (`--table`) if a real input appears.

- **Failure attribution gained a second executor-side test** (`engine/reconcile.py`
  `executor_tick_failures` ＋ `cli.py` `redemption` ＋ both `mechanism.md` files ＋
  `tests/test_redemption_report.py`). The "dropped on the executor side" bucket used to recognise
  only the literal "output was not parsed" marker in the trace, which the adapter writes when
  *parsing* fails. When the executor exits non-zero it writes no such marker, so that failure was
  filed against the subject: at tick 723 `state/executor.jsonl` has `rc=1`/`usage=unknown` while
  the outcome row for the same tick is `verifiable=true`, `redeemed=false` — the age rule called
  it "genuinely not done". The bucket now also fires when **every** tick-class call of that tick
  exited non-zero or timed out, with the disqualifiers kept strict (one `rc=0` attempt in the same
  tick, or only org-session calls, is not an excuse). Measured on the live ledgers at tick 730:
  723 moves buckets, 499/521 stay put, 676/679 keep the marker route, and the **numerator and
  denominator are untouched** (318 sampled / 311 redeemed / 7 failed / 363 unverifiable).
- **"Proposal went stale" is now stated as what it is** — a mechanical *proxy, pending proof*: age
  ≥ 30 ticks proves the premise was old, never that the proposal's content expired, and the bucket
  is only reached once both executor-side tests fail to hold. The wording was already hedged in the
  Chinese original; the English table now carries the same grade instead of a bare "proxy".

- **Two published verdicts in the evidence section were re-run and are publicly corrected**
  (both `mechanism.md` files ＋ `tests/test_evidence_snapshot.py` ＋
  `tests/data/redemption-tick-00731.json`). v2.2.27 quoted a tick-624 snapshot as if it were a
  conclusion; the ledgers only grow, so by tick 731 the readings are 682 led rows / **319 checkable
  samples** / 312 redeemed / 363 unverifiable (53% of leads) and the two claims failed a live
  re-run: (1) the `lib*` origin was reported as *no samples*, yet the bucket holds
  **8 checkable samples since tick 654** (654, 656–662) — and n=8 buys a sample count and its ticks,
  **not** a 1.00 verdict; (2) the misses were reported as 4 rows with **0 "genuinely not done"**,
  yet there are **7**, splitting 3 / 2 / 2 under the attribution above. The "no case to extrapolate"
  discipline is kept and extended: it binds the n=8 bucket exactly as it bound the 0-case one.
  Every figure in the section is now checked against one `redemption --json` snapshot by a test, so
  corrupting a number in the docs turns CI red; the README's test-size figure moved to ≈6,600
  because the new cases are 236 lines.

## v2.2.27 — the five open judgements are closed, and one correction from last round was wrong (2026-09-19)

- **`org-check` got its own exit code** (`core/exit_codes.py` ＋ `cli.py` ＋ both `running.md`
  files ＋ `tests/test_cli.py` ＋ `.github/workflows/ci.yml`). "Not this tick" used to answer `1`,
  which is the usage-error slot — a caller branching on rc read the answer backwards, and a
  genuinely mistyped command hid behind a legitimate "no" (`|| true` in CI swallowed both).
  It is now `NOT_THIS_TICK = 5`, `1` means usage errors again, and the CI cold-start step calls
  the command on an empty state root where the answer is `should_run=true`/0, so the workaround
  is gone rather than widened. **This is an interface change**; anything that keyed on rc=1 for
  "not now" should key on 5, or better, on the JSON field. Behaviour of the decision itself is
  unchanged.
- **The reserved `long_task` exemption is retired** (S9 in `docs/superseded.md`, both languages
  ＋ `engine/model.py`·`sprout_queue.py`·`tick.py`·`org_session.py` ＋
  `tests/test_sprout_queue.py`). Last round guarded it as "reserved, unwired, not deleted";
  measuring it here showed what that was worth: at tick 647 the ledgers hold 4,370 sprout rows,
  every one carrying the key, **none set to true** — the branch had never been used, yet a row
  that did carry it would still have released a sprout past the lead limit. The limit came out of
  the v1 "186 of 221 queued sprouts were one family" incident, so a bypass that no writer ever
  needed was not worth its reach. Old rows still parse (`from_record` ignores unknown keys) but
  the flag buys nothing; the new case fails if the name returns to `src/` or `prompts/`, if the
  S9 row disappears from either table, or if a marked legacy row is treated as exempt.
- **Two capacity questions were answered by measuring, not by adjusting** (`docs/growth-subject.md`
  and its Chinese original ＋ `tests/test_mechanism_docs.py`). `app/` holds the solidify edge's
  evidence files and has no rotation rule while `journal/` rotates at `journal_keep_files`: that
  asymmetry is now written down as a decision, with the reason (moving an evidence file out makes
  a named object read as *missing* and drops `app/`'s directory-object count — differences the
  engine made for itself, not growth) and with the measurement that bounds it (145 files,
  261,713 bytes, 102 added on the busiest day). The observation limits stay at **10 directories /
  20 files**: nothing presses either boundary, and `subject_files`' per-file window is deliberately
  narrower than the counts, which use real totals. The verdict sentence is asserted against the
  constants themselves, so raising a limit without changing the criterion goes red. The stale
  directory enumeration that round five fixed in the documents was still sitting in
  `engine/subject.py`'s own comment; it is gone and the ban now scans `src/` and `prompts/` too.
- **Last round's correction of the org-segment unit was itself wrong, and is corrected here**
  (`engine/org_trigger.py` ＋ `core/config.py` ＋ both `mechanism.md` originals ＋
  `tests/test_org_trigger.py`). v2.2.26 stated that a state root running only mechanical ticks
  already writes an `org-llm.jsonl` row at tick 1. It does not: `run_tick` enters the org segment
  only when a runner exists, and measured with `IG_EXECUTOR=""` over three ticks the file is never
  created and `org-check` still reports "never attempted". The run that produced the claim had
  inherited `IG_EXECUTOR` from the environment — it was an executor-backed debug tick, which *does*
  consume the cooldown window, so the operational warning stands with a narrower condition. Rows
  come from three paths after the segment starts: missing prompt (never touches the executor),
  failed executor call, completed run. **Settled: the unit stays "attempt".** Narrowing it to
  "the LLM call succeeded" would leave a broken executor being retried every tick, since ①②③④ all
  pass again when nothing was recorded. The regression is now pinned by behaviour, not prose: a
  case runs two executor-less ticks and asserts the ledger does not exist.
- **Journal rotation now moves content out of the growth surface** (`engine/subject.py` ＋
  `ledger/rotation.py` ＋ `docs/growth-subject.md` and its Chinese original ＋
  `prompts/tick.md`·`prompts/org-session.md` ＋ `tests/test_subject.py`·`tests/test_rotation.py`).
  `rotate_journal` moved `journal/` overflow into `<subject>/archive/journal/`, and the observation
  surface went on looking at it: `move_file` writes the destination before unlinking the source, so
  an archived entry carries the mtime of *the move* — newer than whatever is still growing. Measured
  on a copy of the live subject at `journal_keep_files=200`, adding one entry per round and running
  the gardener: past the limit every rotation took one more slot of the 20-file window (rounds
  12/13/14 = 1/2/3), the first slot was always `archive/journal/…md.<stamp>`, `archive/` and
  `archive/journal/` became directory objects that could be proposed, and the subject's file count
  never dropped (363→377). Rotation had moved nothing out of sight, while `rotate_journal`'s own
  docstring claimed the opposite ("does not affect the visibility of new content").
  `SUBJECT_ARCHIVE_DIR` excludes the subject root's `archive/` from all three readings and from the
  object-name gate, proposals included; the rule is scoped to the root, so `journal/archive/` stays
  ordinary content. Re-running the same curve: archived slots 0 of 20 across 14 rounds, window head
  back to the newest journal entry. **The observation and capacity limits themselves are unchanged**
  (10 directories / 20 files / 200 entries).
- **A missing evidence file is now attributed, and last round's naming theory is refuted**
  (`engine/reconcile.py`·`engine/sprout_sources.py` ＋ `cli.py`·`engine/tick.py` ＋
  `docs/mechanism.md` and its Chinese original ＋ `tests/test_app_edge.py`·`tests/test_mechanism_docs.py`).
  The theory on the table was "the predicted name and the written name disagree, so false failures
  enter the denominator" (predicted `app/0676-…`, present `0677-app_0637-…`). Reading it row by row
  here says it does not hold: all 174 files in the subject's `app/` are reproducible from some cap
  row's (object, tick) through the engine's own path function — **0 orphans** — and the two flagged
  rows (ticks 676, 679) declared in their traces *exactly* the path the engine had written verbatim
  into the prompt, returned rc=0, and still produced no file anywhere on disk. `0677-app_0637-…` is
  another tick's own evidence file, mis-paired with this one. What was actually missing was a
  reading that separates the causes, so `status` and the reconciliation report now carry one:
  自述已写未落地 (declared the agreed path, file absent) / 命名漂移 (declared a different name —
  a tick off by one is caught here, not hidden) / 未自述写入 (no trace, or no `app/` write claimed).
  It reads only the trace's output section: the prompt already quotes the path, and scanning the
  whole file would have the engine testify for itself. Measured over the last 30 / 40 / 60 cap
  leads: 2 / 0 / 0 across the three buckets. **The redemption algorithm, its numerator and its
  denominator are untouched** — this only says which point was lost and why.
- **The journal naming rule now has an enforcement point** (`engine/subject.py` ＋
  `prompts/org-session.md` ＋ `docs/growth-subject.md` and its Chinese original ＋
  `tests/test_subject.py`·`tests/test_mechanism_docs.py`). `JOURNAL_NAME_RX`/`valid_journal_name`
  had **no call site at all** while the comment and the docs called it a mechanical judgement —
  either the claim was decorative or the enforcement was missing; the fix was to wire it in, not to
  soften the wording. `subject.valid_journal_name` is now called from the object-name gate's
  proposal branch (`valid_subject_object`), so an org session that names a not-yet-existing
  `journal/` file with a malformed name is refused on the spot instead of at reconciliation.
  Scope is deliberately narrow and pinned by tests: direct children of `journal/` only, directory
  objects untouched, already-observable objects unaffected. The **writing** side stays a prompt
  convention plus a test guard — the engine does not rename what the executor produced, because
  rewriting reality to fit the expectation is the failure mode this whole mechanism exists to avoid.
- **The version policy now says *incompatible* where it used to say "ledger format"**
  (`docs/versioning.md` ＋ Chinese original ＋ `tests/test_mechanism_docs.py`). The rule listed any
  ledger-format change as Major, while S9 deleted a serialized key and shipped it as a Patch
  (`2.2.27`) — policy and fact disagreed, and the tag had to settle which one wins. Settled: Major
  is for a change where the same ledger reads a different verdict under old vs new code, or old
  code fails on a new row; dropping a key nobody wrote, or adding a nullable one, stays a Patch.
  No version is reclassified here (`2.2.27` keeps its number), and the criterion is pinned against
  the read side rather than the prose: `Sprout.from_record` tolerating a retired key and
  `as_record()` no longer writing it are asserted in the same test, so if the reader ever turns
  strict, the "compatible ＝ Patch" sentence loses its support and that test goes red.
- **A mutation audit of the criteria, and the one that turned out decorative**
  (`engine/subject.py` ＋ `tests/test_mechanism_docs.py` ＋ both `mechanism.md` originals ＋
  README size figures). 23 pinned constants and sentences were each flipped to a wrong value in a
  clean clone of HEAD (PYTHONPATH pointing inside the clone, so the working tree and the live tick
  were never at risk) and the suite re-run. 22 went red. The survivor was the org-session prompt's
  journal-naming clause: the guard compared a string literal *copying* the rule instead of the
  rule itself, so marring that half-sentence kept the suite green — a decorative criterion. It was
  rewritten to point at its real landing place: `subject.JOURNAL_NAME_SPEC` is now the single
  constant the gate quotes in its refusal message, and the test asserts the refusal carries it and
  that `org-session.md` names the enforcement ("对象名机械闸" / "当场拒收"). Re-audited on the fixed
  HEAD: dropping "当场拒收" from the prompt fails 1 test, stopping the gate from quoting the
  constant fails 3, breaking the constant itself fails 3. One mutation still passes by design —
  swapping the sentence's connective words for synonyms — because what is pinned is the spec string,
  the gate's citation of it, and the named enforcer, not that sentence's phrasing.
  Two findings recorded as measurement, not as fixes: the three quota defaults
  (`journal_keep_files`, `frozen_cap`, `frozen_keep_tail`) did **not** survive a full-suite run —
  they are caught by `test_every_numeric_knob_is_listed`; a narrow selector in round one had
  reported them as decorative, which is the mistake of testing one view and calling it coverage.
  Separately, the frozen-zone capacity was checked against the 300-tick re-ask window on a copy of
  the state root (tick 713: 4,373 rows, 627 short of the cap, arriving 0.66–1.50 rows/tick →
  418–950 ticks away, while a rotation keeps 4,000 rows ≥ 2,600 ticks of history): rotation cannot
  outrun the window, written into both `mechanism.md` originals and pinned by arithmetic against
  the constants, not against the prose.
- **The `lib*` no-samples gap got a dated ETA** (both `mechanism.md` originals). At tick 713 the
  state root reports 28 pending questions, all blocked (28 re-ask cooldown, 17 also short of the
  idle threshold), earliest re-askable tick **892** — ~10 minutes per tick measured here, so due
  the evening of 2026-09-20. What will be measured then is whether the whole
  pending → sprout → pickup → closed/consumed chain flows, with the two named readings to re-run;
  until then that origin stays reported as **no samples**, not as 0 or 1.00.

## v2.2.26 — the documents say what the code, the tree and the Release page actually do (2026-09-18)

- **The published size claim was stale** (README, both languages): "~4,400 lines of Python plus
  ~2,600 lines of tests" measured 7,083 / 5,617 on this machine — the engine grew ~60% past its own
  description. Corrected to the measured figures, rounded the same way the sentence rounds.
  `tests/test_mechanism_docs.py` now counts the tree itself and fails if either README drifts more
  than the rounding band — the figure was only able to rot because nothing was checking it.
- **The mechanism document now says how far a long run carries a redemption-rate study**
  (both languages, §5). Written from a live reading rather than an expectation: the on-read buckets
  are object domain × predicted edge × actual edge, so **maturity step is not one of them** — joined
  against the maturity ledger it degenerates here (every checkable sample sits at the capped step,
  steps 1–3 have **no samples**, which is *not computable*, not 0). The capability-library sprout
  origin is likewise still no-samples. And of the misses, none is a mis-chosen edge, so this data
  answers "did the announced action happen", not "was the wrong edge picked" — 0 cases cannot be
  read as 1.00.
- **The privacy scanner's scope is now the publish boundary** (`tools/privacy_scan.py`): it skipped
  a hard-coded directory list, so every local-only folder (handover notes, machine config) needed a
  code edit and forgetting one pitted the local scan against the release gate. It now honours the
  top-level names in `.gitignore`, the same semantics as static rule R1. Not a free pass — pinned
  with both a positive and a negative case in `tests/test_privacy.py`, and documented in
  `docs/privacy.md` / `docs/zh/privacy.md`.
- **The reserved `long_task` branch is now guarded** (K16, both languages). It stays unwired —
  wiring it needs a mechanical test for "what counts as a long task", a design decision — but
  "reserved" was costing more than a comment: the flag is the only bypass of the lead limit, so a
  quiet assignment somewhere would turn that incident-borne constraint into a suggestion.
  `tests/test_sprout_queue.py` now fails if any engine module assigns it, and passes when the
  flag (read from an old ledger row) does grant the exemption.
- **The bucket axes in the README and the org prompt now match the code** (README both languages
  ＋ `prompts/org-session.md`). All three claimed "object domain × edge type × maturity step",
  while `reconcile._bucket` computes (object domain, predicted edge, actual edge) — so the org
  session was told to cite a bucket that cannot be computed, and the public README promised an axis
  the ledgers do not carry. `tests/test_mechanism_docs.py` pins the correct phrase and fails if the
  old wording returns.
- **N58-① is closed: trigger ④ keeps its row reading** (settled, no behaviour change). It was the
  repository's only explicit open decision, and measuring it here settled the question rather than
  deferring it: over ticks 556–628 only 14 of 73 ticks were quiet, the longest run of consecutive
  quiet ticks was **1**, and a run of ≥ 10 never occurred — so the literal "ten consecutive quiet
  ticks" reading is not a slower org cadence but an unreachable one. The verdict is recorded in
  both originals and in `engine/org_trigger.py`, and `tests/test_mechanism_docs.py` now refuses
  the old "open decision" wording on its way back.
- **A subject-state sentence in the Chinese original is now a dated snapshot**
  (`docs/zh/growth-subject.md`). It enumerated the subject's current top-level directories as
  "journal / archive"; measured here (tick 633) they are `journal` and `app`, and `archive/` only
  appears at the first journal rotation. The rule next to it (directory limit 10, and raising it is
  a judgement change) was never wrong — the observation masquerading as a fact was. It now carries
  its measurement date and points at `infinigrow status` for the live reading, and
  `tests/test_mechanism_docs.py` rejects the old enumeration on its way back.
- **A live knob that no document mentioned is now documented** (`frozen_review_every`, default 20;
  config table ＋ both mechanism originals ＋ `tests/test_mechanism_docs.py`). The engine sweeps the
  frozen zone every N ticks so a frozen sprout can be re-lit into the active queue — it has been
  doing that since T4/A5, but the setting appeared in neither the config table nor the mechanism
  document, which made `IG_FROZEN_REVIEW_EVERY` undiscoverable. The new case fails if any integer
  setting is missing from that table, or if a stated default or env-var name disagrees with code:
  a missing row raises no error, it just becomes a switch nobody knows about.
- **`org-check`'s exit code is now written down, and now has a test** (both `running.md` files ＋
  `core/exit_codes.py` ＋ `tests/test_cli.py`). It answers "not this tick" with rc=1 — the
  *usage-error* slot, borrowed — so a caller that treats rc as pass/fail reads it exactly
  backwards (the `|| true` in the CI cold-start step is that workaround). The command had no test
  at all before; it now has both directions pinned (empty ledger → `should_run=true`/0, just-ran →
  `should_run=false`/1, rc and JSON forced to agree). Behaviour is unchanged: a dedicated code is
  an interface change, undecided.
- **Release titles have one source on each side of a measured boundary** (`tools/sync_release_notes.py`
  ＋ `CONTRIBUTING.md` ＋ `tests/test_release_tooling.py`). The tool kept a hand-copied title for every
  version and `--apply` writes whatever that table says — but the table was copied from an older
  reading of the CHANGELOG. Comparing all 28 live Releases (`gh release view --json name`, 2026-09-18):
  through v2.2.15 the published title is the recorded string, from v2.2.16 it is the `CHANGELOG.md`
  heading **verbatim, date included** (that is what the workflow feeds `gh release create`). So the
  copies were a second source, and applying them would have stripped the date off ten published
  titles and reworded eleven more. `title_for()` now reads the boundary (`TITLES_UNTIL = 2.2.15`):
  recorded before it, derived from the CHANGELOG after. Tests pin both halves, the exact set of 11
  pre-boundary wordings that legitimately differ from the CHANGELOG (so nobody "aligns" a published
  Release away), and a negative case proving a hand-copied title can never win after the boundary.
- **The observation-surface limits are now pinned where they are actually written**
  (`tests/test_mechanism_docs.py`; the limits themselves are unchanged). The existing check asked only
  whether `"10"` and `"20"` appear anywhere in the mechanism document — and both do, for unrelated
  reasons (stall alert 12 ticks, org cooldown 30 minutes, queue cap 50), so raising
  `SUBJECT_DIR_LIMIT` or `SUBJECT_FILE_LIMIT` could never redden it. The check now reads the sentences
  that state the boundary (`docs/zh/growth-subject.md` table and rule line, `docs/growth-subject.md`
  "Directory limit 10, file limit 20") against the constants, and carries its own negative case:
  the same phrase with the digits swapped must not be found. Measured: simulate `SUBJECT_DIR_LIMIT=12`
  and only 1 of the 4 phrases still matches (2 of 4 with `SUBJECT_FILE_LIMIT=25`) — the check fails,
  which is the point: `docs/growth-subject.md` promises that changing a limit means changing document,
  code **and test** together, and until now the third leg was decorative.
- **The org segment's cooldown window measures attempts, not LLM calls — the text now says so**
  (`engine/org_trigger.py` ＋ `core/config.py` ＋ both `mechanism.md` originals ＋
  `tests/test_mechanism_docs.py`). The reason string read "since the last LLM segment" and the config
  table called the knob "LLM-segment gap", but the ledger behind both is written by **any** org
  segment: measured here, a state root that only ever ran mechanical ticks already had an
  `org-llm.jsonl` row at tick 1. The wording was not harmless — it implies a manual debugging tick
  costs nothing, while in fact it consumes the window and delays the real LLM segment by up to
  `org_cooldown_min` minutes. Behaviour is unchanged (only a mechanism change would alter it: gate the
  write on an actual LLM call — undecided); the four places that state the unit now agree, and the
  new case rejects the old wording on its way back.
- **`SECURITY.md`'s scanner-scope sentence was describing a run that no longer happens**
  (`SECURITY.md` ＋ `tests/test_mechanism_docs.py`). It said the scanner "also reports ~48 findings
  under `archive/legacy-20260914/_venvtest/`". After this version moved the skip list to
  `.gitignore`, the default pass does not enter `archive/` at all (measured: 126 files, no hits),
  and the number was never the whole story: pointing the scanner at that tree explicitly
  (`--root archive`) reports 667 files with 2,017 / 90 / 16 hits by rule. Both cases are now stated
  separately and a case forbids the conflated wording from returning. Part of a full read of the
  remaining public docs against code: `upgrading.md`'s exit codes do match
  `core/exit_codes.py` (`BEHIND=3`, `REFUSE=4`), and the `versioning.md` / `privacy.md` /
  `SECURITY.md` claims that were checked held.

## v2.2.25 — log rotation moves to the launcher's handle gap, where it can actually work (2026-09-18)

- **`logs/tick.log` rotation now runs in the launcher, before any handle opens** (v2.2.25):
  the v2.2.24 in-process approach turned out to be impossible — the scheduler's append
  handle shares *neither* delete *nor* write (Windows), so both `unlink` and an in-place
  truncate failed with `PermissionError` on the live machine, keeping `rc=1` and a
  path-carrying traceback in the log. `tools/run_tick.bat` now calls
  `tools/rotate_journal.py` at the very start, in the handle gap between runs: over the
  threshold it archives the full original — **redacted** of local paths, since archived
  logs are portable artifacts — and clears the main file for this run's appends.
  Move-only, data lands in the archive first. The gardener no longer rotates the journal
  (`rotate_files` drops the log section; `ledger.store.truncate_file` is removed as an
  unusable primitive). Test-pinned end to end.
- **The mechanism document states where rotation happens and why** (both languages).

## v2.2.24 — the log rotation fails gracefully on a busy journal, and the README names every status reading (2026-09-18)

> **Superseded by v2.2.25**: the in-place truncate below is *not* achievable while the
> scheduler holds the journal (Windows shares neither delete nor write); rotation lives in
> the launcher from v2.2.25 on. The README/status-line work in this release stands.

- **Log rotation no longer crashes the tick when the journal is busy** (new, 2026-09-18):

- **Log rotation no longer crashes the tick when the journal is busy** (new, 2026-09-18):
  the scheduler holds `logs/tick.log` with an append handle; Windows (no delete-sharing)
  made `unlink` fail with `WinError 32` on every rotation, so the tick exited `rc=1` and a
  traceback containing the machine's absolute paths was archived every run. Rotation now
  writes the full original into the archive first, then truncates the main file *in place*
  when it cannot be removed — the append side keeps writing, no error, no data loss
  (`ledger.store.truncate_file`, test-pinned with a held handle).
- **The README quick-start `status` line carries all five readings** (S3/D1): bilingual
  description now lists the capacity and re-ask gates, evidence compliance, executor-side
  loss and the usage split — matching `docs/running.md` one line for one line.
- **The mechanism document notes the busy-handle tolerance** on rotation (both languages),
  so the failure semantics are written down where the mechanism is.

## v2.2.23 — the ledger split no longer drops ticks, and the report carries the gate readings (2026-09-18)

- **The usage split now covers every call made today** (S1/A4): org-session calls
  (`kind=org-session`) used to be filtered out, so the bucket sums fell short of the
  "calls today" total — a report that silently drops a call. They now form their own
  `组织会话` bucket; the bucket sum always equals the day's call total (test-pinned).
- **The reconcile report carries the two time-gate readings** (S1/A5): the frozen-capacity
  line count / remaining rows, and the earliest re-ask tick — rendered by the *same*
  functions `status` uses (`frozen_requestion_eta`, the frozen ledger row count), so the
  archived report and the live status can never disagree about how far away the gates are.
- **The bilingual running guide's `status` line names all five new readings** (S2/D1):
  `docs/running.md` and `docs/zh/running.md` now list capacity gate, re-ask gate,
  compliance, executor-side loss and the usage split in the one-line summary.

## v2.2.22 — executor-side loss and token spend are both visible (2026-09-17)

- **`status` and the reconcile report report executor-side loss** (R2/N69): of the last 10
  ticks' executor traces, how many carry the "output was not parsed" marker — the same literal
  marker and the same trace reader as the failure-attribution bucket, just windowed and
  independent of which sprout the action was lost on. The adapter lives outside this
  repository; until its fix gets a decision, the loss has to stay visible instead of being
  remembered.
- **Token spend is split by sprout source** (R9/E5): `status` now answers "where did today's
  tokens go" per source prefix (`cap`/`sp`/`lib`), joining `executor.jsonl` calls to the
  tick's led sprout by tick number; calls with no topic and calls with unreported usage are
  listed separately instead of being apportioned. Readings only — no budget gate, no
  automatic downgrade.
- **The generic text-write primitive is hardened** (R6/E1 follow-through): `encoding.write_text`
  now normalises the target path (`resolve`), refuses any input carrying a `..` segment, and
  takes an optional `root` for a containment check — the last escape hatch the scanner kept
  flagging after the join-level guard (`subject_path`) landed.

## v2.2.21 — name-to-path joins are guarded, and the release-note tool is public (2026-09-17)

- **Object names now resolve through a single guarded path function** (R6/E1). A scanner had
  flagged a path-traversal primitive: joins like `subject_root / item.name` (names come from
  observation and ledgers) carried no containment check. `engine.subject.subject_path` is now
  the only resolver for name→path joins and rejects anything that resolves outside the subject
  root — empty names, absolute paths, drive letters, `..` segments — sharing the single
  `core.paths.within_root` predicate with the existing write guard; the org-session renderer
  reads through it. `SECURITY.md` gains a **declared exceptions** table for the two
  reviewed-and-accepted scanner findings: the deterministic cold-start shuffle (reproducible
  by design from the tick number; nothing security-bearing) and the generic `write_text`
  primitive (its real call sites are guarded).
- **The release-note tool is now in `tools/` and test-pinned** (R7/D2):
  `tools/sync_release_notes.py` batch-realigns historical Release titles and bodies with the
  repository sources (documented English notes first, the `CHANGELOG.md` section otherwise;
  an empty body is skipped with a warning — never an empty shell on the public page). It is a
  dry run by default and only touches GitHub with `--apply`. `CONTRIBUTING.md` lists it with
  the other maintenance tools, and a test asserts the title table covers the current version,
  so a release cannot silently fall off the list.

## v2.2.20 — the read and availability edges are now accountable (2026-09-17)

- **Read (`判读`) and capability-library availability edges are now mechanically accountable**
  (R1/A1, A2). A difference-source read sprout points at a journal file that appeared
  unpredicted; by the tick the sprout is led, that object has already rolled out of the
  "most recent N by mtime" observation window (`SUBJECT_FILE_LIMIT`), so its
  `(object, dimension)` key was never in `observable_keys` and the row stayed
  `verifiable=false` forever — measured 8 of the last 9 read sprouts, while still holding
  topic slots. The verdict now reads the **literal mention of the source object in that
  tick's executor output** (full name, or the subject-relative form; directory objects need
  the full name) — the same output text and the same matching predicate as "a trace hit
  means the library entry was used" (`entry_mentioned`). A miss is mechanically decidable:
  these edges report `verifiable=true`, and a missing mention is recorded as a failure
  (readable yet not written down = "not done", isomorphic to the solidify-edge evidence
  file, which was built the same way in v2.2.17). The tick prompt states this verdict, so
  the executor never has to guess.
- **`status` shows both time gates** (R5/A3, A4): the frozen-area capacity gate as rows
  left (`frozen_cap − current rows`; live: `4103 行／上限 5000（剩 897 行）`) and the
  requestion gate's earliest requestion tick computed in the engine's own caliber
  (candidate-pool entries only, latest freeze per object; live: `主体/journal/0247-20260916.md`
  frozen at tick 325 → requestion tick 625). Previously neither gate had a reading, so
  "how far away is it" was not visible anywhere.
- **`status` and the reconcile report show the evidence-file compliance rate** (R8/A9):
  of the cap leads in the last 30 ticks, the share whose evidence file really exists
  (live: `20/21 = 0.95`, the missing one listed by path). The rate is computed through the
  same path function the engine hands to the executor (`app_evidence_path`), so the ledger
  row and the file on disk are reconciled on one predicate instead of being counted by hand.

## v2.2.19 — a failed redemption is attributed to whoever actually failed (2026-09-17)

- **The "failed to redeem" attribution has a third bucket, and it takes precedence**: when the
  tick's executor trace carries the literal "output was not parsed" marker, the row is filed as
  **dropped on the executor side** instead of being blamed on the proposal's age. Live case that
  forced it (tick 449): the model replied with a JSON object containing `actions`, but the
  **opening `{"` was missing**, so the adapter's parser failed and the whole reply — including a
  valid write action — was dropped; the engine honestly recorded a failure to redeem, and the
  age rule (59 ticks ≥ 30) would have filed it as "proposal went stale", which is the wrong
  account. `infinigrow redemption` now prints all three buckets
  (`执行者侧未落地 / 提议过期 / 真没做`); pass `traces_dir` (the CLI does) to enable the split —
  without it the behaviour is exactly as before.
- Also recorded, not fixed (the adapter is out of this repository's scope): **62 of 397 executor
  traces (15.6%) hit that parse fallback**, 23 of them on capped-sprout topics — so roughly one in
  seven ticks an intended action never lands. The engine's bookkeeping is honest throughout; the
  loss is on the executor side, and it is the main real cause behind "failed to redeem" rows on
  the application edge.
- Docs: both mechanism documents describe the three-way split and its proof levels.
- Tests: `+1` (the unparsed-marker bucket, including the "no `traces_dir` → old behaviour" path).

## v2.2.18 — the re-proposal rule is written down where the mechanism is (2026-09-17)

- **The queue rule from v2.2.14 is now stated in all five places.** "A re-proposal does not change
  the question's age" — the new sprout inherits the older birth tick and the last-touched tick, and
  **not** the lead budget — was implemented, tested and in the changelog, but neither mechanism
  document nor the prompts said it. Both documents (`docs/mechanism.md`, `docs/zh/mechanism.md`,
  queue discipline section) and `prompts/org-session.md` (where the merge rule already lived) now
  carry it, and `tests/test_mechanism_docs.py` pins the rule in Chinese, English and the prompts
  together with the mechanical behaviour — so a one-sided edit fails the suite instead of drifting
  silently.

## v2.2.17 — the reading that shows the solidify edge got connected (2026-09-17)

- **`status` now shows the windowed reading of the solidify edge**, next to the cumulative one:
  `固化边（应用面，未接证据边的行）：N 条累计｜最近 30 拍 cap 领做 X 次，可对账 Y（不可对账 Z）`.
  The cumulative bucket lives on an **append-only ledger**, so its absolute number cannot fall —
  the reading that actually shows whether the edge got connected is *how many of the recently led
  cap rows are accountable*, and it is now visible without a separate command.
  Measured on the live root: the window's unaccountable count falls monotonically
  21 → 20 → 19 → 18 → 17 across ticks 442–446 (one per tick, as the pre-fix rows roll out),
  reaching 0 from tick 472, while every new cap row is accountable.
- **A re-proposed sprout inherits the older birth tick and the last-touched tick, but not the
  lead budget.** `leads` is the record row's allowance: inheriting it would permanently kill a
  difference that reappears after being asked three times — a semantic change nobody asked for.
  The new row keeps its own budget, exactly as before this change.
- Tests: `+1` net (the same-key replacement drill now asserts budget non-inheritance, and
  `status`'s windowed cap reading is pinned).

## v2.2.16 — the two languages can no longer drift apart (2026-09-17)

- **A mechanical check now keeps `docs/` and `docs/zh/` structurally aligned.**
  `tests/test_docs_bilingual.py` asserts that each document pair has the **same heading skeleton
  position by position**, that every document has a mirror (with a declared exception list for the
  English-only release notes), and that `README.md` / `README.zh-CN.md` agree in sections, code
  blocks **and the commands those blocks run** (comments and placeholder arguments are allowed to
  differ; the commands are not). A section added to one language alone now fails the suite.
- **The documents were aligned to make that check true** rather than the check being weakened:
  `running.md` grew the sections the Chinese side already had (one-click files, scheduled task,
  hidden launcher, gardener checks, logs, troubleshooting order, cost, status/pause, local
  deployment), `architecture.md` and `growth-subject.md` gained their missing counterparts,
  `mechanism.md` gained "Same source as the prompts" in English and a glossary in Chinese, and
  `upgrading.md` gained its three missing sections.
- **The docs also state what used to be folklore**: `long_task` is documented as a **reserved,
  deliberately unwired** field (with the reason), and the runtime-language boundary is written in
  both READMEs and both `running.md`s (runtime text is Chinese — the mechanism's language; an
  English CLI layer is not implemented and would not touch mechanism words or ledger fields).
- **New release tooling (Q11)**: `tools/extract_changelog_section.py` pulls a tag's section out of
  `CHANGELOG.md`, and `.github/workflows/release.yml` creates the GitHub Release for a pushed
  `v*` tag **from that section only**, idempotently (an existing release is never overwritten) and
  failing loudly when the section is missing or too short — no empty releases.
  `.github/CODEOWNERS` records the single owner explicitly.
- Tests: `+9` (the bilingual checker plus its own drift-detection self-test, and the release
  tooling: extraction, missing tag, too-short section, workflow wiring).

## v2.2.15 — the solidify edge becomes accountable (2026-09-17)

- **The "application surface" of a capped sprout is no longer unmeasurable.** Caps used to occupy
  the topic slot while producing outcomes the engine could never check (measured: 160 leads, 0
  verifiable rows, 24 of the last 31 topic slots). Now the topic prompt names, verbatim, a path
  the executor must leave evidence at — `app/<lead tick, 4 digits>-<object name>.md` (slashes in
  the object name become underscores) — and the engine **reconciles that file's existence**: a
  prediction for the path is added, read through the keyed supplemental observation, so the
  outcome row is `verifiable=true`, redeemed is judged from the file, and the row enters the
  denominator.
- **The evidence key is a record, not a domain object**: it spawns no sprout, never advances the
  maturity chain and never enters the capability library (the diff ledger keeps its row, marked
  `app_evidence`, the same way `act_caused` diffs are marked).
- **A tick with no evidence file is judged "readable but absent" — not done, not "unreadable".**
  Rows from before this change (and any call that does not attach the edge) keep the old
  treatment: `verifiable=false`, listed separately, out of the denominator.
- Docs: `docs/mechanism.md` and `docs/zh/mechanism.md` describe the convention and the naming
  rule; `prompts/tick.md` states the requirement to the executor.
- Tests: `+5` (`tests/test_app_edge.py`: path naming, redeemed-only-with-evidence, no spawn and
  no maturity advance for the evidence key, the bucket moving into the denominator, and the
  prompt handing the executor the exact path).

## v2.2.14 — a re-proposal no longer makes an old question look new (2026-09-17)

- **A sprout that is re-proposed keeps its age.** When a new sprout replaces an existing one for
  the same object and dimension ("new over old"), it now **inherits the older birth tick** instead
  of being reborn at the current tick, and carries the previous record's "last touched" state with
  it. Before this, a question that had been waiting a long time was reset to newborn every time the
  org session re-proposed it (measured: `sp0326-001` was created at tick 326 and only got a topic
  slot at 338, after being re-proposed every 3 ticks). The ordering key itself is unchanged
  (least-recently-touched first); a merged sprout is never moved **ahead** of the sprout it
  replaced.
- **`status` and reconciliation reports now show the capability-library candidate pool:**
  open-and-unconsumed N / closed M / consumed K, plus how many of the N are held back by the
  re-question cooldown or by the idle threshold, and how many could sprout right now. Silence on
  this channel used to be unreadable — "expected" (the pool is empty) and "the channel is dead"
  looked identical. Measured on the live state root: 25 open, 17 closed, 110 consumed, 0 able to
  sprout (all 25 held by the re-question cooldown).
- **Org-session criterion ④ is documented with its real semantics and measured cadence** (no
  semantic change): it counts difference-ledger **rows**, not ticks — a quiet tick writes ~40–43
  rows and a growth tick resets the counter, so `zero_gap = 10` means ≈ "the previous tick was
  quiet" (measured: 14 of 40 ticks reached the threshold). The cooldown gate is 30 minutes but the
  measured org cadence is **median 40.0 min / mean 42.3 min**, because ④ and growth are negatively
  correlated. See `docs/mechanism.md` §2.3.
- **New `infinigrow redemption` command and `redemption_attribution()`** — leads bucketed by sprout
  source (`sp`/`cap`/`lib`) with a verifiable/unverifiable split, and non-redeemed rows attributed
  by **age at lead time**: "proposal went stale" (age ≥ 30 ticks) vs "genuinely not done". The
  bucket is a mechanical proxy and the report says so; the age is read from the birth tick encoded
  in the sprout id.
- Tests: `+11` (age inheritance and no-earlier ordering on replacement, lead-limit history across
  replacement, candidate-pool classification, expected-silence vs dead-channel, attribution
  buckets, and the new command).

## v2.2.13 — public surface: English-first docs, no file mixes two languages (2026-09-17)

- **No public file mixes two languages in its prose.** `README.md`, `CONTRIBUTING.md`,
  `SECURITY.md`, `CODE_OF_CONDUCT.md`, all of `docs/` and the issue/PR templates are English;
  `README.zh-CN.md` and `docs/zh/` are the Chinese mirrors. The only cross-language elements are
  the link label pointing at the Chinese README and the glossary's Chinese mechanism terms (which
  are identifiers, not prose). Previously the README, the docs and the templates mixed both
  languages inside the same file.
- **The Chinese design documents moved to `docs/zh/`** (they are the design of record for the
  mechanism's Chinese vocabulary); the English `docs/mechanism.md` is the public rendering and
  carries a **bilingual glossary** (every mechanism term, Chinese ↔ English).
- **The docs were rewritten for a cold reader**, not translated word for word: what it is, what you
  can use it for, quick start, the four edges in one table, machine-enforced guarantees, honest
  limitations, and a documentation index.
- **`CHANGELOG.md` is English and much shorter** (the long-form reasoning stays in the design
  documents); the release notes for v2.0.0–v2.2.3 were rewritten in English.
- **Commit messages are English and short from here on** (see the convention in `CONTRIBUTING.md`);
  history is not rewritten.
- Tests: the documentation↔code checks now assert both languages (Chinese design of record for the
  test phrases, English public docs for the glossary and the observation-surface boundary).

## v2.2.12 — the input block's heading no longer hard-codes a window (2026-09-17)

- The "reality change" block's **heading** stopped naming a window (`K14 … ; window on the next
  line`); the window is written by code on the following line, so a heading can no longer go stale.
- The window line says "start = tick N" instead of "anchor = tick N" (on the fallback path it is
  not an anchor, and calling it one was wrong).

## v2.2.11 — the reality window now spans "since the last org session" (2026-09-17)

- **The window must cover the consumer's absence.** The org session runs every 3–5 ticks, but the
  "reality change" window was a single tick, so it structurally missed the ticks in between
  (measured: seven consecutive org sessions with an empty "newly appeared" list). On top of that,
  trigger criterion ④ requires the previous tick to be quiet, while any tick that acted writes
  non-confirmed rows — so criterion ④ sessions always look at a quiet tick.
- The window is now an **anchor comparison**: `state/subject-org-anchor.json` (the listing the org
  session saw when it last ran) against the current listing. Entries are unchanged: newly appeared /
  changed (byte size) / disappeared / directory file-count changes.
- **The trigger criteria and the cooldown are untouched** — cadence and token cost do not change.
  A missing anchor falls back to the old one-tick window and says so on the line.
- Tests: window coverage across several ticks, and the fallback being honest about itself.

## v2.2.10 — "changed" is now reported too (2026-09-17)

- The prompt promised "newly appeared / **changed** things are candidates", but the comparison only
  looked at name sets and directory counts: a **rewrite** (same name, different bytes) was never
  reported. Added the line `changed (byte size differs, name unchanged): …`.
- Still compared inside the bounded listing (newest 20 files of the two snapshots), so the
  observation surface stays bounded.
- Test: a byte change lands under "changed" and not under "newly appeared".

## v2.2.9 — two places that reported the wrong unit/window (2026-09-17)

- The org input block's heading still said "previous tick's before → after" while its content had
  moved to the anchor window (title and content disagreeing is the same disease as a rule written
  in two places).
- Trigger criterion ④ was named "N consecutive ticks with no difference" but counted **ledger
  rows** (a tick writes dozens): the reported "86 ticks" was 86 rows ≈ 2 ticks. The threshold
  semantics are unchanged (still row-based; they pair with the 30-minute cooldown), but the reading
  and the reason now give **both** rows and the ticks they cover.

## v2.2.8 — the reality window was structurally empty (2026-09-17)

- The "reality change" block compared the **previous tick's snapshot** with **this tick's
  pre-action listing** — and the previous snapshot is written *after* acting, so nothing could
  happen in between: the block **always reported "no change"** (measured on three org sessions).
- Now it compares the **same tick's before → after** pair (`subject-before.json` step 2 vs
  `subject.json` step 8), which is exactly "what the last action changed" — those changes are
  neutralised as `act_caused` in the difference ledger, so this block is the only place they show.
- When the before-snapshot is missing, the block says so instead of substituting other readings.

## v2.2.7 — a reminder gets an exit; deduplication includes the frozen zone (2026-09-16)

- **Deduplication includes the frozen zone**: "one sprout per object × dimension" was only scanning
  the active queue, so every evicted object was re-created on the next tick (~39 new sprouts per
  tick against a queue cap of 50). Measured effect: **39 → 0 new sprouts per tick**.
- **The reminder has exits.** "Capability unused" asks about a dimension no mechanical reading can
  see (its outcome rows can only be marked `verifiable=false`), so with no exit it is a
  permanently true reminder. Two exits, both moving its queued sprouts into the frozen zone:
  **consumed** (the entry's name appears in the executor's trace output → `last_used_tick` is
  updated) and **closed** (asked up to the lead limit, 3, without consumption → the library ledger
  gets `closed_tick` plus a closure pointer to the trace that was asked, and the entry leaves the
  candidate pool permanently).
- **The "used this tick" gate reads the executor's trace output** (the most recent 5 traces) rather
  than a note in the difference ledger — that note measured 19 characters, so the gate never fired.
  Only the output section is read, and only executor traces (an org session's trace is a proposal,
  not an action).
- **Re-asking frozen sprouts**: after `frozen_requestion_ticks` (default 300) without being
  re-lit, an object is no longer blocked. The test uses the newest freeze of that object so a
  backlog cannot release a whole batch at once. New `frozen_tick` field; pre-upgrade rows fall back
  to `created_tick`.
- **Frozen-zone capacity**: past `frozen_cap` (default 5000) the oldest lines are **moved** into
  `state/archive/files/frozen/` (keeping `frozen_keep_tail`, default 4000) — move-only, same
  discipline as ledger rotation.
- **Bounded observation surface, written down and tested**: 20 files by newest mtime, 10 directories
  by name; **keyed supplemental reading** for keys that appear in the predictions but fall outside
  the window (this removes the false "not executed" rows for boundary files, measured at 8 rows).
- **The launcher no longer prints the repository's absolute path** into the state log (the scheduler
  redirects its output there); the live state root now passes
  `tools/check_no_abs_paths.py` (315 historical occurrences redacted).
- Tests 279 → 306.

## v2.2.6 — proposals stop naming files; the org session watches reality; TLS truncation retried (2026-09-16)

- **Directory objects**: a subject sub-directory is an accountable object (`<subject>/<path>/`, the
  trailing slash is the marker) whose quantity is its file count — so "grow this directory by one
  entry" can be proposed without naming a file. A future file's name contains its **creation** tick,
  which the proposer cannot know.
- **Delta predictions**: `+1` is anchored to an absolute value against the reading **before** acting,
  so a target cannot expire. The reverse does not hold: when reality has already passed the
  prediction, the old value is not sent back.
- **The org session scans reality**: its input gained a mechanical "reality change" block.
- **TLS truncation**: `SSLEOFError` / `UNEXPECTED_EOF_WHILE_READING` joined the transport-layer
  retry signatures (two live failures had exactly that signature and were not caught).
- `long_task` is registered as a reserved field: present for old rows, not wired, not deleted.

## v2.2.5 — observability and cost (2026-09-15)

- **Stall alerting**: N consecutive ticks with an executor wired in but no sprout to pick (N=12,
  ≈2 hours) raises a flag — "the engine is burning time without growing" must be visible.
- **Claimable count** and **stall-cost** readings in `status`.
- **Rotation** extended to traces, reconciliation reports and the tick log (move-only).
- **Failed calls are recorded as `usage: unknown`** rather than `null`: whether a failed request
  was billed upstream is not knowable, and a cost ledger must not pretend otherwise.
- **Sample floors** for long-window judgements: a window with fewer than 20 executor calls is
  reported as "insufficient sample", never as a pass.

## v2.2.4 — growth resumed: the domain-saturation deadlock and observation truncation (2026-09-15)

- **Domain-saturation deadlock (the real stall)**: an existence dimension's "new quantity" condition
  can never hold, so an exhausted holder sprout held its domain hostage for 37 ticks with nothing
  being picked. Occupancy is now also released when the holder sprout is exhausted or no longer
  queued.
- **Observation truncation**: the file count was computed from the *truncated* list, so with 31
  files on disk the engine reported 20. File count and total bytes are real totals now, and the
  per-file window takes the newest by mtime.
- Naming rule for new `journal/` files fixed and synced across prompt, org-session prompt and
  subject document: `<created tick, 4 digits>-<created date YYYYMMDD>.md`.

## v2.2.3 — executor subprocess forced to UTF-8 stdio (2026-09-14)

- **Root cause of a family of HTTP 400s**: the executor adapter reconfigured stdout/stderr but not
  **stdin**; a scheduler-started process read the UTF-8 prompt with the system code page, corrupting
  it into stray surrogates that the upstream rejected. The adapter now also reconfigures stdin, and
  the engine injects `PYTHONIOENCODING=utf-8`.
- Verified same-context before/after (rc=1 → rc=0) and end-to-end on the real scheduled task
  (executor failure count 9 → 0).

## v2.2.2 — closing the loop on long-run reliability (2026-09-14)

- **Heartbeat sequence regression** is recovered too (readable heartbeat that is behind the ledgers'
  maximum tick used to overwrite old reports one by one).
- **Rotation** for traces / reports / logs; **frozen sprout review**; **pending-pointer timeout**
  produces a sprout; the capability-library writer exists (the third sprout source was a dead path
  before this); the org session's object names are machine-checked.
- **`status` / `pause` / `resume`** one-liners; the executor's working directory is the repository
  root while the subject location comes from `IG_SUBJECT_ROOT`.

## v2.2.1 — runtime reliability patch (2026-09-14)

- **The scheduled task no longer opens a console window**: the action became
  `wscript //nologo tools\run_tick_hidden.vbs` (window style 0). A scheduled `.bat` or bare `python`
  flashes a console every run and steals focus.
- **Tick number recovery** when the heartbeat cannot be read (it used to fall back to 1 and
  overwrite `reconcile-00001.md`); the number is rebuilt from the ledgers with a visible note.
- **Transport-layer retries** for `IncompleteRead` and friends, with the attempt number recorded.

## v2.2.0 — calibration from a live run (2026-09-14)

The premises did not change. Every item below came from a tick where the accounting disagreed with
reality, or where a class of sprout could never be resolved:

- the engine no longer reconciles its own state files (six observed, three predicted → three
  phantom sprouts per tick that nothing could act on);
- observation and prediction are symmetric per object and dimension;
- changes the action itself caused are recorded but never spawned (tagged `act_caused`);
- a sprout carries the expectation it came from (otherwise a correct action is recorded as
  contradicted because the acting tick forgot to predict it);
- unreadable dimensions are marked `verifiable=false` and excluded from the redemption denominator
  (unreadable ≠ failure);
- the maturity chain advances at most +1 per object per tick;
- the org session gained a proposer role and a machine-checked object-name gate, and its input
  includes a bounded excerpt of subject content;
- the executor's three states (not wired / wired but nothing to do / ran) are reported separately
  instead of being collapsed into "mechanical tick, zero tokens";
- a heartbeat that cannot be read no longer silently resets the tick number.

## v2.1.0 — the runtime line (2026-09-14)

- **Growth subject**: an explicit directory to grow (a sibling of the repo by default), observed
  mechanically — existence, file count, byte sizes — with objects named `<subject>/<relative path>`
  ([`docs/growth-subject.md`](docs/growth-subject.md)).
- **Executor channel**: `infinigrow tick --executor "<command>"`; prompt on stdin, answer on stdout,
  traces under `state/traces/`, every call in `state/executor.jsonl`, four failure modes visible and
  counted separately ([`docs/running.md`](docs/running.md)).
- **Org session runtime**: the semantic pass as code — findings land in `state/org-findings.jsonl`
  and their fate is computed later by reconciliation (`infinigrow org-status`).
- **Domain saturation**, **ledger rotation**, an **honest redemption rate** (`sample`, "no samples"
  instead of 0), and three more static rules (R7 single source for exit codes, R8 single write path,
  R9 the sync table cannot shrink).
- Engineering: `tools/run_tick.bat`, a scheduled-task registrar, CI on Windows as well as Linux,
  `update_local.py` merged into `run_latest.py --update`, and fixes for the two-platform CI's first
  findings (console encodings, non-ASCII launcher scripts, a binary false positive in the artifact
  checker).

## v2.0.0 — the rewrite (2026-09-14)

The first release of the rewrite line: six packages with one-way dependencies, a parameterised state
root, sprouts only from ledgers, no self-sprout path for the acting session, queue cap plus frozen
zone, maturity chain +1 per tick, locking and tick-named reports, a heartbeat that raises when it
cannot be written, six static rules with positive/negative cases, and a CI cold start (three ticks,
empty state root, zero tokens, no absolute paths in the artifacts).

Release notes with the known limitations of each line: [`docs/release-notes-v2.0.0.md`](docs/release-notes-v2.0.0.md)
and following.
