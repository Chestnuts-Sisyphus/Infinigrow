# Marker registry

> A marker is the mechanical anchor attached to **one proposition**. Until now there was no
> registry: a document could write "(M7/N45)" and a reader could not look up what that
> proposition says, where it is enforced, or whether it is still in force. This table closes
> that gap — **if it is referenced, it is registered**.
>
> The checks (`tests/test_docs_bilingual.py`):
> (1) every marker appearing in `docs/` or `docs/zh/` must have a row here (in both languages);
> (2) none of the four cells (id | proposition | where it is enforced | status) may be empty;
> (3) a marker nothing in the repository references any more must say so honestly — its status
> must read "orphan", it may **not** pretend to be in force.
>
> "Where" is the file that carries the enforcement (file level on purpose: line numbers rot).
> Status vocabulary: `in force` | `retired (see superseded Sx)` | `undecided` |
> `ambiguous, annotated` | `orphan, no reference in repo`.

---

## 1. The registry (sorted by id)

| id | proposition | where it is enforced | status |
|---|---|---|---|
| A1 | Re-proposing a question does not change its age: the merged sprout inherits the older birth tick | `src/infinigrow/engine/sprout_queue.py` (the `replaced` branch of `add`) + `tests/test_sprout_queue.py` | in force |
| A2 | The read edge and the availability edge became accountable through a trace mention | `src/infinigrow/engine/tick.py` + `tests/test_read_edge.py` | in force |
| A3 | The solidify edge is accountable once "application" is backed by an evidence file | `src/infinigrow/engine/tick.py` + `tests/test_redemption_report.py` | in force |
| A5 | The frozen zone is re-reviewed every `frozen_review_every` ticks | `src/infinigrow/engine/sprout_queue.py` (`review_frozen`) + `tests/test_tick.py` | in force |
| A7 | "Application surface" is a semantic dimension: unreadable is not "failed", so it is listed separately | `src/infinigrow/engine/reconcile.py` (`redemption_report`) + `tests/test_rotation.py` | in force |
| A8 | The `journal/` file-name rule is fixed: `<created tick, 4 digits>-<YYYYMMDD>.md` | `src/infinigrow/engine/tick.py` + `tests/test_subject.py` | in force |
| A10 | Runtime text is Chinese; an English CLI mode is not implemented (a language boundary) | `docs/running.md` + `src/infinigrow/engine/executor.py` (usage-line contract) | in force (a decision; implementing it is still open) |
| A15 | One-glance overview and pause/resume: `status` / `pause` / `resume` | `src/infinigrow/cli.py` + `tests/test_cli.py` | in force |
| A17 | Executor timeout x calls per tick must be clearly smaller than the scheduler's time limit | `tools/scheduled_task.ps1` (`-ExecutionTimeLimit`) + `tests/test_config_single_source.py` (the timeout really kills) | in force (the relation is written down; the arithmetic gate is K12's) |
| B2 | A "failed to redeem" row is attributed by cause, in three buckets — never one number | `src/infinigrow/engine/reconcile.py` (`redemption_attribution`) + `tests/test_redemption_report.py` | in force |
| B3 | Buckets are cut by the sprout's age at lead time, read mechanically from the id's tick segment | same file (`sprout_created_tick`) + `tests/test_rules.py` | in force (the age bucket is a mechanical proxy, unproven) |
| G1 | Rotated content really leaves the growth surface (the archive is not observed) | `src/infinigrow/ledger/rotation.py` (`rotate_journal`) + `tests/test_subject.py` | in force |
| G2 | Missing evidence items are attributed in three classes, never one bucket | `src/infinigrow/engine/sprout_sources.py` + `tests/test_tick.py` | in force |
| G3 | A semantic session needs a runner; the naming gate lives in the proposer branch of `valid_subject_object` | `src/infinigrow/engine/subject.py` + `tests/test_subject.py` | in force |
| G5 | Capacity rotation cannot outrun the re-ask window (archived lines passed the window long ago) | `src/infinigrow/engine/subject.py` observation readings + `tests/test_mechanism_docs.py` | in force (measured on a copy) |
| G6 | The redemption rate is computed on the spot and presented honestly (no sample is not 0) | `src/infinigrow/engine/tick.py` + `tests/test_redemption_report.py` | in force |
| G7 | **One id, two meanings**: (1) what the capability-library ETA still owes; (2) rotation (ledgers only grow, history moves to the archive) | (1) `docs/mechanism.md` section 5 readings; (2) `src/infinigrow/ledger/rotation.py` | ambiguous, annotated (cite it with the context; do not merge the two) |
| G9 | Frozen is not sealed forever: after `frozen_requestion_ticks` an object may be asked again | `src/infinigrow/engine/sprout_queue.py` (`known_objects`) + `tests/test_sprout_queue.py` | in force |
| K1 | The domain-saturation release conditions gained ③④ so an enumerable dimension cannot deadlock a domain | `src/infinigrow/engine/tick.py` + `tests/test_domain_saturation.py` | in force |
| K2 | The observation quota takes the newest N=20 files by mtime, and self-reported counts stay truthful | `src/infinigrow/engine/subject.py` + `tests/test_subject.py` | in force |
| K7 | A proposer cannot know a future creation tick, so prompts must not name future files | `src/infinigrow/engine/tick.py` + `tests/test_tick.py` | in force |
| K12 | Do not burn the whole scheduling window: leave at least 1/3 of it | `tools/scheduled_task.ps1` (the limit) + `docs/running.md` wiring section | in force (the rule of thumb; the arithmetic gate lands in M10) |
| K14 | The comparison window when scanning reality is "since the last semantic session" | `src/infinigrow/engine/tick.py` + `tests/test_org_session.py` | in force |
| K15 | Whether the ordering key should change (ties after the lead limit) is **not decided** | `src/infinigrow/engine/sprout_queue.py` (the `order_key` comment) + `tests/test_sprout_queue.py` | undecided (open question; this round does not move the key) |
| K16 | The `long_task` exemption once registered as reserved | `docs/superseded.md` S9 + `tests/test_sprout_queue.py` | retired (closed with S9; not reopened) |
| M3 | "A trace hit means it was used" and the read edge share the same output text and predicate | `src/infinigrow/engine/tick.py` + `tests/test_tick.py` | in force |
| M4 | The re-ask test anchors on `frozen_tick` (the tick that evicted it), falling back to `created_tick` | `src/infinigrow/ledger/rotation.py` + `tests/test_sprout_queue.py` | in force |
| M5 | The frozen zone has its own capacity rule: past `frozen_cap` the oldest lines move out | `src/infinigrow/ledger/rotation.py` (`rotate_frozen_sprouts`) + `tests/test_rotation.py` | in force |
| M6 | Directories are observed objects too: 10 slots by ascending name (`SUBJECT_DIR_LIMIT`) | `src/infinigrow/engine/subject.py` + `tests/test_subject.py` | in force |
| M7 | Key-pinned supplemental observation: re-read predicted keys pushed off the boundary | `src/infinigrow/engine/tick.py` (`augment_observations`) + `tests/test_subject.py` | in force |
| M10 | Lead-and-redemption attribution is a re-runnable command form | `src/infinigrow/engine/reconcile.py` + `tests/test_redemption_report.py` | in force |
| N41 | The deadlock case: a domain holding one unfinished sprout was blocked by an enumerable dimension | `src/infinigrow/engine/tick.py` + `tests/test_domain_saturation.py` | in force (fixed by K1) |
| N42 | The "file count" dimension is always the real total, unaffected by the quota | `src/infinigrow/engine/subject.py` + `tests/test_subject.py` | in force |
| N43 | A subdirectory is an object (the trailing `/` is the test); a forward gap is written `+N` | `src/infinigrow/engine/tick.py` + `tests/test_tick.py` | in force |
| N45 | Supplemental observation covers only keys that appeared in a prediction; the surface does not grow | `src/infinigrow/engine/tick.py` + `tests/test_subject.py` | in force |
| N48 | The inputs of the three sprout sources must be real readings (de-duplication includes the frozen zone) | `src/infinigrow/rules/static_scan.py` + `tests/test_tick.py` | in force |
| N48-1 | `last_used_tick` must have a real writer, not a creation-time constant | `src/infinigrow/engine/tick.py` + `tests/test_read_edge.py` | in force |
| N48-2 | The "used this tick" gate reads trace output (the old gate read a `note`: 19 characters, never fired) | `src/infinigrow/engine/tick.py` (`recent_trace_output`) + `tests/test_config_single_source.py` | in force |
| N48-3 | A reminder must be able to end; fixing only de-duplication would cut this channel's power | `src/infinigrow/engine/sprout_sources.py` + `tests/test_tick.py` | in force |
| N48-4 | The frozen-zone capacity rule follows rotation discipline: move, never delete | `src/infinigrow/ledger/rotation.py` + `tests/test_rotation.py` | in force |
| N48-5 | Directory slots are the first 10 by ascending name; the test is hard-coded | `src/infinigrow/engine/subject.py` + `tests/test_subject.py` | in force |
| N55 | "Previous tick snapshot vs this tick's list" has nothing in between, so it was always empty | `src/infinigrow/engine/tick.py` + `tests/test_org_session.py` | in force (fixed by K14) |
| N56 | Unit honesty: criterion ④ counts ledger **rows**, not ticks | `src/infinigrow/engine/org_trigger.py` + `tests/test_org_trigger.py` | in force |
| N58 | What triggers the semantic session versus the measured cadence (④ only accepts "the previous tick was quiet") | `src/infinigrow/engine/tick.py` + `tests/test_org_session.py` | in force (there is **no definition table** for it in-repo; semantics in mechanism section 2.3) |
| Q1 | Queue discipline: a repeatedly re-proposed question must not be refreshed into a new sprout | `docs/zh/mechanism.md` queue section + `tests/test_mechanism_docs.py` | in force |
| Q2 | A solidify sprout taking a slot is deliberate: it must be judgeable as applied or not | `src/infinigrow/engine/tick.py` + `tests/test_redemption_report.py` | in force |
| Q6 | Redemption bucketing ships as a re-runnable function | `src/infinigrow/engine/reconcile.py` + `tests/test_redemption_report.py` | in force |
| Q13 | Language boundary of the public face: release notes are English only | `docs/release-notes-*.md` + `tests/test_docs_bilingual.py` (`ENGLISH_ONLY`) | in force |
| R1 | No absolute paths in source | `src/infinigrow/rules/static_scan.py` + `tests/test_status_gates.py` | in force |
| R2 | Prompts and code stay in sync, both directions | `src/infinigrow/rules/static_scan.py` + `tests/test_status_gates.py` | in force |
| R3 | No self-sprout clause may appear in the prompts | `src/infinigrow/rules/static_scan.py` + `tests/test_rules.py` | in force |
| R5 | No credential literals | `src/infinigrow/rules/static_scan.py` + `tests/test_status_gates.py` | in force |
| R7 | Exit codes have a single source (no bare integers in the CLI) | `src/infinigrow/rules/static_scan.py` + `src/infinigrow/core/exit_codes.py` | in force |
| R8 | One write window (only `ledger/store` touches disk) | `src/infinigrow/rules/static_scan.py` + `tests/test_status_gates.py` | in force |
| R9 | The sync table cannot shrink (coverage floor) | `src/infinigrow/rules/static_scan.py` + `tools/check_prompt_code_sync.py` | in force |
| R10 | Scheduled tasks launch through the hidden launcher (vbs window style 0) | `src/infinigrow/rules/static_scan.py` + `tests/test_scheduler_artifacts.py` | in force |
| S1 | "Branch on completion": every tick must register at least one new sprout candidate | `docs/superseded.md` S1 + `src/infinigrow/engine/tick.py` (zero diffs, zero sprouts) | retired |
| S2 | Apex trimming (cut the growth direction at the "top") | `docs/superseded.md` S2 | retired |
| S3 | Three-tier / blind grading of output | `docs/superseded.md` S3 | retired |
| S4 | The early "four mechanisms / four sets / node tests" design | `docs/superseded.md` S4 | retired |
| S5 | Dual time sources (a model-written timestamp used as a test) | `docs/superseded.md` S5 + the heartbeat `tick_status.json` | retired |
| S6 | Self-assessed "capability cards / principle cards" ledger | `docs/superseded.md` S6 | retired |
| S7 | A state root coupled to a host project | `docs/superseded.md` S7 + `src/infinigrow/core/paths.py` | retired |
| S8 | One monolith with embedded fixtures | `docs/superseded.md` S8 + the six-layer package layout | retired |
| S9 | `long_task` exempting a sprout from the lead limit | `src/infinigrow/engine/sprout_queue.py` (`eligible`) + `tests/test_sprout_queue.py` | retired |
| T3 | A criterion and a prompt that nobody calls do not exist | `src/infinigrow/engine/tick.py` + `tests/test_tick.py` | in force |
| T4 | The frozen-zone review cadence (a different job from re-asking) | `src/infinigrow/engine/sprout_queue.py` + `tests/test_tick.py` | in force |
| T6 | Rotation and capacity: ledgers only grow; history moves to the archive | `src/infinigrow/ledger/rotation.py` + `tests/test_rotation.py` | in force |
| T7 | Domain saturation: one unfinished sprout per "object domain x accountable quantity" | `src/infinigrow/engine/domain_saturation.py` + `tests/test_rules.py` | in force |
| T8 | The outward entry for scheduling and care (overview / pause / resume) | `src/infinigrow/cli.py` + `tests/test_cli.py` | in force |
| T11 | The honest presentation of the redemption rate (no sample is neither 0 nor "bad") | `src/infinigrow/engine/tick.py` + `tests/test_tick.py` | in force |
| H8 | An early id for the same decision Q13/A10 records: release notes stay English | `tests/test_docs_bilingual.py` (the `ENGLISH_ONLY` comment) — the proposition now lives under **Q13/A10** | orphan, no definition site (the citation is the only trace) |
| O5 | Proposition **not recoverable**: a repo-wide search (including `.qoder/handoff/`) returns zero hits | the inventory printed by `tools/check_markers.py` (the same script's own output is the evidence) | orphan, no reference in repo (must not be cited as evidence) |

---

## 2. What the series prefixes mean is **not written down**

One honest measurement: the prefixes actually in use across `docs`, `src` and `tests` are
**K, A, N, Q, T, M, G, B, S, R, H, O, C, U** (measured 2026-09-19, see the command below). They
came from the numbering habits of earlier sessions, and **this repository has never defined what
a prefix stands for** — so this table registers **concrete ids** (propositions quoted from where
they first appear, not rewritten or back-filled) and does not pretend to know the naming scheme.
Pinning the series semantics down is an open item, not something to invent here.

---

## 3. Re-running the inventory behind this table

```bash
python tools/check_markers.py           # ids referenced in docs minus ids registered here
python -m pytest tests/test_docs_bilingual.py -q   # referenced means registered (missing row = red)
```

`tools/check_markers.py` uses the same regex and the same tests do; whoever changes a marker sees
the difference by running the first command.
