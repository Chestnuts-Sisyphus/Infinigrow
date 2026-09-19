# Mechanism

> The design of record. Code and prompts must agree with this document; drift is caught by
> `infinigrow scan` rule **R2** (bidirectional prompt↔code sync) and by
> `tests/test_mechanism_docs.py`.
>
> **Language note.** The engine's mechanism vocabulary is Chinese — that is the language its
> prompts, ledgers and code comments use, and the terms are treated as identifiers, not prose
> (see the glossary at the end of this file). The full Chinese design document lives in
> [`zh/mechanism.md`](zh/mechanism.md); this file is the English rendering of the same rules.

---

## 1. Premises

There are exactly two stores:

- **B = belief** (what the engine thinks)
- **W = world** (what is actually there)

Every structure is an **edge** between them:

| Edge | Direction | In one line | Grows when |
|---|---|---|---|
| `read` | W→B | understand the world | a prediction about that object is confirmed at the next reconciliation |
| `act` | B→W | be able to do | the action produces an observable change on the W side |
| `principle` | B→B | figure something out | the derived claim holds in a domain never tested before |
| `solidify` | W→W | automatic | the same class of input no longer costs cognition |

**Reality is the only judge.** A judgement is not taken from the engine's own say-so; it is
reconciled against reality, and the judgement itself goes into a ledger where it can be
contradicted later.

**Maturity chain**: an experience goes read → act → principle → solidify. Step 4 is the cap;
the cap is not a dead end, it is a new entry point (see sprout source ②). There is no fifth step.

---

## 2. One tick

```
org session (optional, needs an executor) → fix B-guess → pick a sprout → act (executor, optional)
→ W-read (**after** acting) → reconcile → differences → domain gate → sprout → account → heartbeat
```

- **B-guess**: the falsifiable commitments written down *before* acting (object, dimension,
  expected state, pointer).
- **W-read**: the world's answer read *after* acting. The order is part of the mechanism: a
  reading taken before the action cannot prove anything about that action.
- Reconciliation is mechanical: align by `(object, dimension)`, and `expected == actual` means
  "confirmed". Semantic judgements (intent, hard conflicts) belong to the org session, and they
  are recorded so they can be contradicted.

### 2.1 What the engine grows (the growth subject)

The engine acts inside a **growth subject**: a directory, by default a *sibling* of the repo
(`IG_SUBJECT_ROOT` points anywhere). Objects are named `<subject>/<relative path>`.

The mechanical observation surface is **read-only, bounded, no subprocesses, no network**:

| Observed | Dimension | Evidence pointer |
|---|---|---|
| the subject root | existence, file count | `subject root` |
| each sub-directory (up to 10) | file count | `subject dir:<path>` |
| each file (up to 20) | existence + byte size | `subject:<path>` |

- Files are taken by **most recent mtime first** and directories by **name order** — the surface
  is bounded on purpose (a tick must not be unbounded work). File count and total bytes are
  **real totals**, not truncated counts.
- A directory is itself an object: `<subject>/<path>/` (trailing `/` is the marker, so a
  directory never collides with a file of the same name), and its accountable quantity is the
  number of files inside. This exists so that "grow this directory by one entry" can be
  proposed **without naming the file** — a future file's name contains its *creation* tick,
  which the proposer cannot know (K7). See [`growth-subject.md`](growth-subject.md).
- **Keyed supplemental reading**: if a key that appears in the predictions falls outside the
  bounded window (a newly created file pushes the boundary out), the observation side reads
  that key anyway — it only reads keys that were predicted, so the surface stays bounded.
- Symmetry is the rule: predict and observe the **same object and dimension**, or the engine
  manufactures differences out of thin air (observed 6 files but predicted 3 → three phantom
  "unpredicted findings" per tick).
- The engine's own state files are **never** reconciled: they change because the engine writes
  them, and treating that as a difference is the engine assigning work to itself. Engine health
  is the gardener's job (liveness, locks, failure counts, rotation).

### 2.2 The executor channel

"Acting" is done by an **executor**: prompt on **stdin**, answer on **stdout**
(`IG_EXECUTOR` / `--executor`). No executor means a **mechanical tick**: zero tokens, zero
credentials, no network. Four failure modes (non-zero exit / timeout / empty output / cannot
start) are all recorded, and counted separately from tick failures. See [`running.md`](running.md).

### 2.3 The org session (the semantic pass) and when it runs

The **org session** is the one place where a semantic judgement is allowed (intent, hard
conflicts, "what should come next"). It needs the executor channel; without one it never runs.

It runs when **any** of four criteria holds (the cooldown gate has the final say):

| # | Criterion | Reading |
|---|---|---|
| ① | never ran | org ledger has 0 rows |
| ② | longest gap | `tick − last_org_tick ≥ org_gap_ticks` (5) |
| ③ | pending-pointer differences | count > 0 |
| ④ | "quiet streak" | consecutive predicted-OK **rows** at the tail of the difference ledger ≥ `zero_gap` (10) |

**Unit honesty (N56, [proven])**: ④ counts **ledger rows, not ticks**. A quiet tick writes
~40–43 rows; a growth tick writes at least one non-OK row, which resets the counter to 0.
Measured over the last 40 ticks (400–439): the reading is either ~40–43 or 0, and it reached
≥ 10 on **14 of those 40 ticks**. So `zero_gap = 10` **means ≈ "the previous tick was quiet"**
(about 0.23 tick) — not "ten consecutive quiet ticks". The label was fixed in v2.2.9 to say
rows. **The semantics are now settled: the row reading stands** (N58-① closed, proven
2026-09-19). Reading it literally as "ten consecutive quiet ticks" is not a slower cadence but
a **nearly unreachable** one: a growth tick always writes a non-OK row and resets the streak.
Measured here over ticks 556–628 (the 73 ticks still in the difference ledger): only
**14 of 73 ticks were quiet (19%)**, the **longest run of consecutive quiet ticks was 1**, and
runs of ≥ 10 occurred **0 times**. Re-opening this means changing what resets the streak —
code, tests and both originals move together — not editing the `zero_gap` number.

**Measured cadence ([proven])**: the cooldown gate allows one run per 30 minutes, and the
measured interval is **median 40.0 min / mean 42.3 min** (`state/org-llm.jsonl`, 100 intervals,
manual runs under 10 minutes excluded). The reason is structural: ④ can only fire after a
*quiet* tick, and the ticks that actually move the subject always write a non-OK row — ④ and
growth are negatively correlated (N58). The effective cadence is the cooldown plus one quiet tick.

**"Last time" counts org-segment attempts, not successful LLM calls ([proven], measured here
2026-09-19)**: ①, ② and the cooldown all read the **org-attempt ledger**, and a row is written on
only three paths, each of them *after* the org segment actually started — the prompt file is
missing (that one never touches the executor), the executor call fails (rc≠0 / timeout), or the
segment completes. The first two are why "attempted" is not the same as "the LLM answered".
**With no executor configured the org segment does not run at all and writes nothing**: measured
on a fresh state root with `IG_EXECUTOR=""`, three ticks left no `org-llm.jsonl` file and
`org-check` still reported "never attempted" — a purely mechanical deployment does not throttle
itself. (**The previous version of this paragraph said the opposite** — that a state root running
only mechanical ticks had a row at tick 1 — because a debugging run that had inherited
`IG_EXECUTOR` from the environment was read as an executor-less one.) The consequence keeps a
sharper edge: a tick **with an executor wired** — including one manual tick typed for debugging —
occupies the cooldown window and delays the next real LLM segment by up to `org_cooldown_min`
minutes. **Settled 2026-09-19: the unit stays "attempt"; it is not being narrowed to "the LLM call
succeeded".** The reason: if a failed call did not count, the cooldown would stop protecting
anything, and ①②③④ would release a retry against the same broken executor every tick — spending
tokens on a call already known to fail, which is exactly what that gate was installed to prevent.

---

## 3. Differences (the one primary sprout source)

Four kinds, no fifth:

| Kind | Test | Spawns? |
|---|---|---|
| predicted-wrong | expected state change ≠ actual state change | yes |
| predicted-right | expected == actual | no (counts as confirmed) |
| unpredicted finding | reality has it, the prediction did not mention it | yes |
| not-executed | the prediction was written, nothing was done | yes |

**A pointer is mandatory**: every difference must carry a provenance pointer. A difference
without one goes to a "pending pointer" area and, after a grace period, produces a
**pointer-missing** difference — which *does* spawn a sprout (rejected ≠ dropped).

Granularity is `object × state dimension`: one object and one dimension wrong is one
difference; two objects are two.

---

## 4. Sprouts (three sources, no more)

> **No difference, no sprout.** No difference, no cap, no unused entry → no sprout this tick.
> **The acting session cannot create sprouts** — structurally: `engine/tick.py` has no entry
> point for "register a new candidate".

| Source | Mechanical test | The question it asks |
|---|---|---|
| ① difference | a difference with a pointer | resolve this difference |
| ② maturity cap | the object reached step 4 **this tick** | what else can this be used for? |
| ③ unused capability | entry idle ≥ threshold and absent from the executor's trace | why is this not used — does it hold elsewhere? |

Sources ② and ③ were added deliberately: with ① alone, once the differences were resolved the
queue filled with the acting session's own re-statements of what it had just done (a previous
generation of this engine had 186 of 221 queued sprouts near-identical and ground to a halt).

**The inputs of ③ must be real readings.** `last_used_tick` is updated when an entry is
**mentioned in the executor's trace output**, and the "used this tick" gate reads those traces
(not a free-text note stored elsewhere — that mistake made the gate a no-op).

**A reminder must be able to end** (the difference/cap sources can be resolved; "is this
capability used?" cannot be, because no mechanical reading exists for it):

| Exit | Test | Action |
|---|---|---|
| consumed | the entry's name appears in the executor's trace output | `last_used_tick` updated; its queued sprouts are moved to the frozen zone and not asked again |
| closed | asked up to the lead limit (3) with no consumption | the library ledger gets `closed_tick` plus a **closure pointer** to the trace that was asked; the entry leaves the candidate pool permanently |

**Queue discipline**

- One sprout per object × dimension (a new one replaces the old). **Deduplication includes the
  frozen zone**: "suspended" is not "dead" — a frozen sprout is still the sprout for that
  question. (Scanning only the active queue let every evicted object be re-created on the next
  tick; measured: 39 new sprouts per tick against a queue cap of 50, which starved the
  difference source for 137 ticks.)
- **A re-proposal does not change the question's age** (Q1/A1): the new sprout inherits the older
  **birth tick** and the previous record's *last touched* tick, so a long-waiting question is not
  reset to newborn by being re-proposed, and the merge never moves it ahead of the sprout it
  replaced. The **lead budget is not inherited** — it belongs to the record row; inheriting it
  would permanently kill a difference that reappears after being asked three times. The new row
  keeps its own budget, exactly as before.
- Active queue cap 50; beyond that the oldest move to the **frozen zone** (the queue is mutable,
  the ledgers are not).
- One sprout may be led at most 3 times. A frozen sprout can be **re-lit** when its difference
  reappears. **The lead limit has no back door**: the `long_task` exemption that used to be
  registered as reserved (K16) was **retired on 2026-09-19** (see `docs/superseded.md` S9). It
  never had a writer — measured at tick 647: 48 active plus 4,322 frozen rows, every one carrying
  the key, **none set to true** — and a branch that grants a pass merely by reading an old row is
  how a limit bought with an incident quietly turns back into a suggestion. The leftover
  `long_task` key in old ledger rows does not raise (`Sprout.from_record` ignores unknown keys)
  but has **no effect**; `tests/test_sprout_queue.py` holds both halves — the name may not appear
  in the source, and a marked old row may not buy an exemption. Restoring it goes through the
  retirement procedure in `docs/superseded.md`, starting with a mechanical test for "what counts
  as a long task".
- **Re-asking frozen sprouts**: after `frozen_requestion_ticks` (default 300) without being
  re-lit, an object is no longer blocked by its frozen sprout — it may be asked again. The test
  uses the *newest* freeze of that object, so a backlog of old frozen sprouts cannot release a
  whole batch at once.
- **Frozen-zone review cadence** (T4/A5): every `frozen_review_every` ticks (default 20) the
  frozen zone is swept and a frozen sprout gets a chance to be **re-lit** into the active queue.
  Different job from the rule above: re-lighting pulls a sprout back (criterion: ticks, blind to
  the object), while re-asking permits a *new* sprout for the same object (criterion: the age of
  that object's newest freeze). The cadence ran in code before anyone wrote it down, which left
  `IG_FROZEN_REVIEW_EVERY` undiscoverable.
- The frozen zone has a **capacity rule** of its own: past `frozen_cap` (default 5000) the
  oldest lines are *moved* to `state/archive/` (move-only, same discipline as ledger rotation).
- **Capacity rotation cannot outrun the re-ask window** (measured 2026-09-19 at tick 713, on a
  copy of the state root): 4,373 lines, 627 short of `frozen_cap`, arriving at 0.66 lines/tick
  over the last 50 ticks and 1.50 over the last 100 (this machine runs ~10 minutes per tick) →
  the cap is 418–950 ticks away. A rotation still keeps `frozen_keep_tail` = 4,000 lines, i.e.
  **≥2,600 ticks** of history, while the 300-tick window needs only ~200–450 lines. So no line
  can be moved out before it becomes re-askable — whatever gets archived has long since passed
  the window (92.8% of the zone already has).

**Domain saturation**: one unfinished sprout per "object domain × accountable quantity".

- The object domain is everything before the last `/` in the object name; an object without `/`
  is its own domain, which reduces this rule to the merge rule above.
- A saturated duplicate does not spawn: it is recorded as an `absorbed` count on the existing
  sprout, and the difference itself is still written to the ledger.
- Release conditions (any one): ① a new quantity appeared; ② the sprout was resolved or is no
  longer queued; ③ the holder sprout is exhausted; ④ it is a *different* problem in the same
  domain (a new quantity by definition).

---

## 5. Ledgers (append-only)

| Ledger | One line is | Key fields |
|---|---|---|
| `diffs.jsonl` | one difference (confirmed ones included) | kind / object / dimension / expected / actual / pointer / tick / source |
| `outcomes.jsonl` | one sprout that was led | sprout id / predicted edge / actual edge / redeemed / pointer / tick / **sampled** / verifiable |
| `maturity.jsonl` | an object's step | object / step / tick / capped-this-tick |
| `library.jsonl` | a reusable capability | name / created / last used / **closure (`closed_tick` + pointer)** |
| `executor.jsonl` | one executor call | kind / rc / duration / prompt & output size / usage / tick |
| `org-findings.jsonl` | one semantic finding (can be contradicted) | kind / object / dimension / pointer / tick |
| `org-llm.jsonl` | one org attempt | tick / wall-clock stamp / note |
| `tick_status.json` | the last tick's mechanical state | failures / **executor failures** / rc / timestamp / tick / engine identity |

**The redemption rate is computed on read**, and it is honest about samples:

- the denominator counts only rows with `sample=true` (that tick really had an executor acting);
- with no samples at all, the report says **"no samples"** — the rate is *not computable*, it is
  not 0 and not "bad";
- rows whose dimension is mechanically unreadable (the "application surface" of a capped
  object, unless the evidence edge below is attached) are marked `verifiable=false`, excluded
  from the denominator, and listed separately — unreadable ≠ failure.

**A "failed to redeem" row is attributed in three ways, never in one** (M10/B2/B3/Q6): the
buckets keep the executor's own failures off the proposal's account.

| Bucket | Test | Proof level |
|---|---|---|
| **dropped on the executor side** | the tick's executor trace carries the literal "output was not parsed" marker (the adapter's own honest line: the whole reply was kept as a trace and no action ran) | proven (literal marker) |
| **proposal went stale** | age at lead time ≥ 30 ticks (birth tick read from the sprout id) | a mechanical *proxy*, pending proof |
| **genuinely not done** | age < 30 ticks and no "not parsed" marker in the trace | proven (same tests) |

Live case (proven, tick 449 on 2026-09-17): the model replied with a JSON object containing
`actions`, but the **opening `{"` was missing** → the adapter's parse failed → the whole reply
(including the write action) was dropped → the engine honestly recorded a failure to redeem. That
row's age was 59 (≥ 30), so the age rule would have filed it as "proposal went stale" — **the
wrong account**. When a `traces_dir` is given, the executor-side bucket takes precedence over the
age split. The engine's bookkeeping along this chain is honest (the file really was absent, so the
failure stands); what was lost is the executor-side action.

**The solidify edge is now accountable, through an evidence file** (Q2/A3). The "application
surface" of a capped sprout used to be unreadable forever (measured: 160 leads, 0 verifiable
rows, and 24 of the last 31 topic slots). Now the engine fixes the path, writes it verbatim into
that tick's prompt, and reconciles the file's **existence**:

- path convention: `app/<lead tick, 4 digits>-<object name>.md`, with `/` in the object name
  turned into `_` — e.g. the sprout `cap0380-001-主体_journal_0376-20260916` led at tick 438 →
  `app/0438-journal_0376-20260916.md`;
- the engine adds a prediction for that path (`existence = present`) and reads it through the
  keyed supplemental reading, so **the file existing means the application really happened**:
  the outcome row is `verifiable=true`, redeemed/failed is judged from it, and it enters the
  denominator;
- the evidence key is a **record, not a domain object**: it spawns no sprout, never advances the
  maturity chain and never enters the capability library;
- a tick that leaves no evidence file is judged "readable but absent" — **not done**, not
  "unreadable".

**A missing evidence file gets attributed, not lumped together (settled 2026-09-19).** The
compliance line in `infinigrow status` and in the reconciliation report carries a **missing-file
attribution** with three buckets — 自述已写未落地 (*declared but never landed*: that tick's trace
output says the executor wrote *exactly* the agreed path, and the file is not there), 命名漂移
(*naming drift*: it declared a *different* name — a tick off by one counts, and must be caught),
and 未自述写入 (*never declared*: no trace, or no `app/` write claimed at all). The judgement reads
only the trace's **output section** (`reconcile.trace_write_paths`): the agreed path is already
written verbatim into the prompt by the engine, so scanning the whole file would let the engine
testify for itself. **This measurement refuted a suspicion**: that a naming mismatch was feeding
false failures into the denominator (predicted `app/0676-…`, present `0677-app_0637-…`). It does
not hold — every one of the 174 files in the subject's `app/` is reproducible from some cap row's
(object, tick) through the same path function (**0 orphans**), and over the last 30 / 40 / 60 cap
leads the attribution reads "declared-but-absent 2 / **naming drift 0** / never declared 0". The
two rows (ticks 676, 679) declared the *same* path as their prompt, returned rc=0, and still
produced no file: an action that did not land (executor-side loss, a different line of work).
Attribution **changes neither numerator nor denominator** — the redemption algorithm is untouched;
it only makes "which point was lost, and why" a mechanically readable fact.

**The read edge and the availability edge are now accountable too, through a "trace mention"**
(R1/A1, A2):

- the same shape of problem: a difference-source **read (READ) edge** (reality produced
  something unpredicted → understand it first) points at a journal file that appeared
  unexpectedly — by the tick it is led, it has already rolled out of the "most recent N by
  mtime" observation window (`SUBJECT_FILE_LIMIT`), so its `(object, dimension)` key is absent
  from `observable_keys` → honestly marked `verifiable=false` and **never resolvable**
  (measured: 8 of 9 in the last 30 ticks, while still holding topic slots); the capability
  library "availability" edge (`lib*`) suffers the same way (all 179 historical rows
  unverifiable);
- the fix (no new files): the redemption verdict now reads the **literal mention of the
  source object** in that tick's executor output (full name `主体/<relative path>` or the
  subject-relative form `<relative path>`; directory objects require the full name) — the
  **same output text and the same matching predicate** as M3 "a trace hit means it was used"
  (`entry_mentioned`);
- **a miss is mechanically decidable**: `verifiable` is always `true` for these edges, and a
  missing mention is recorded as a failure (readable yet no written trace = "not done", not
  "unreadable" — isomorphic to the solidify-edge evidence file). It judges the **mechanical
  fact** "was read and written down", not the **semantic fact** "was understood" (semantics
  belong to the org session); the verdict input contains **only the output section** (never
  the prompt — the prompt names the object, counting it would be self-certification);
- every tick's prompt states this verdict (symmetric with the cap-sprout clause, so the
  executor never has to guess).

**How far this long run carries a redemption-rate study** (proven, live at tick 624 on
2026-09-18):

- Global reading: 575 led rows, **212 checkable sample rows**, 208 redeemed → rate **0.98**
  (Wilson 95% interval 0.95–0.99). The number has to be quoted with its denominator share:
  **363 rows (63%) are `verifiable=false`** and sit outside the denominator.
- The bucket axes are object domain × predicted edge × actual edge; **maturity step is not one of
  them** — an outcome row carries no step, it takes a join against the maturity ledger on
  (object, tick ≤ lead tick). Joined that way all 212 samples land on step 4 (the cap) and steps
  1–3 have **no samples**, so "which step predicts better" is *not computable* here (not 0).
  Another 42 sample rows name an object the maturity ledger does not carry (the two ledgers spell
  objects differently) and must be normalised before the join.
- Coverage is uneven across sprout origins: the solidify / read / act / principle edges all have
  samples, while every historical `lib*` row (179 of them) predates the trace-mention fix — that
  origin is still **no samples**.
  - **Re-measurement ETA for that gap** (G7, snapshot at tick 713, 2026-09-19): 28 pending
    questions, **all** of them blocked (28 by the re-ask cooldown, 17 also short of the idle
    threshold); earliest re-askable tick is **892** (the blocking entry froze at tick 592, 179
    ticks away) and this machine runs ~10 minutes per tick → due around the evening of
    **2026-09-20**. What gets measured then is not "did one sprout appear" but whether the whole
    chain **pending → sprout → pickup → closed/consumed** actually flows; re-run the two readings
    `infinigrow status` (library channel verdict / re-ask gate) plus the `lib*` bucket of
    `infinigrow redemption --json`. Until that tick passes this origin stays **no samples** —
    neither 0 nor 1.00 may be reported for it.
- The shape of the misses: 4 failures = 3 dropped on the executor side + 1 proposal went stale +
  **0 genuinely not done**, and **no row** has a predicted edge different from the actual edge.
  So this data answers "did the announced action really happen", not "was the wrong edge chosen" —
  the second question needs rows where an edge *was* mis-chosen, and 0 cases cannot be read as
  1.00.
- **Verdict**: the format and the analysis surface are already there (computed on read, bucketed,
  three-way failure attribution, reproducible with `infinigrow redemption --json`); what a further
  study of "are the judgements accurate" lacks is not more ticks but **samples that can be wrong**.

**Rotation** moves history into `state/archive/` (move-only). History-shaped ledgers keep the
tail N lines; state-shaped ledgers (maturity, library) keep the **latest line per key**, so an
object that has not been touched in a while cannot silently regress. Archives are searchable
with `infinigrow rotate --search <term>`.
**Log rotation lives in the launcher**: the scheduler (`tools/run_tick.bat`) holds
`logs/tick.log` with an append handle for the whole tick process (the handle shares neither
delete nor write on Windows, so an in-process clear is impossible). `tools/rotate_journal.py`
runs it in the **handle gap between runs** (before any handle opens): over the threshold it
writes the full original into the archive — **redacted** of local paths, since archived logs
are portable artifacts — then clears the main file for this run's appends. Move-only, data
lands on the safe side before the main file is touched.

---

## 6. Goals are separated (incentive compatibility)

| Role | Its score (computed from ledgers) | Not part of its score |
|---|---|---|
| acting session | predicted edge vs. actual edge (redemption) | how much text it produced |
| org session | whether its findings survive later reconciliation | how many findings it filed |
| engine | mechanical liveness, ledger health | how good the growth looks |

The point is that no role can improve its own score by producing more words.

---

## 7. Static rules

`infinigrow scan` (R1–R10) — zero tokens, runs on an empty repo: no absolute paths, prompt↔code
sync, no self-sprout clause in prompts, state root gitignored, no credential literals, no BOM,
single source for exit codes, a single write path, the sync table cannot be shrunk, and the
scheduled task must use the hidden launcher. `infinigrow selftest` runs a positive and a
negative case for every rule.

---

## 8. Same source as the prompts

The mechanism vocabulary (read / act / principle / solidify / maturity chain / difference /
outcomes ledger / maturity cap / unused capability / no difference no sprout / **growth subject /
executor / org session / domain saturation / rotation**) must exist on **both** sides: the code
and the prompts. The table lives in `src/infinigrow/rules/static_scan.py` (`SYNC_TERMS`, the
single source of truth) and `tools/check_prompt_code_sync.py` checks it in both directions; rule
**R9** guards the table's **lower bound** (silently deleting a term brings the drift back). This
is the structural prevention for v1's root disease: the same rule written twice, each side
evolving until they contradicted each other.

---

## Glossary

The mechanism vocabulary, Chinese and English. These terms are identifiers in code, prompts and
ledgers; the Chinese form is the canonical one.

| 中文 | English | Meaning |
|---|---|---|
| 判读 | read | W→B edge: understanding reality |
| 行动 | act | B→W edge: making reality change |
| 原理 | principle | B→B edge: deriving new belief |
| 固化 | solidify | W→W edge: no longer costs cognition |
| 成熟链 | maturity chain | read → act → principle → solidify, 4 steps |
| 差异 | difference | the reconciled gap between prediction and reality |
| 预测内错 | predicted-wrong | expected change ≠ actual change |
| 预测内对 | predicted-right | expected == actual (confirmed) |
| 预测外发现 | unpredicted finding | reality has something the prediction did not mention |
| 预测未执行 | not executed | predicted, but nothing was done |
| 兑现账 | outcomes ledger | one line per sprout that was led |
| 兑现率 | redemption rate | share of sampled, verifiable rows that redeemed |
| 芽 | sprout | one resolvable difference, the unit of work |
| 芽源 | sprout source | differences / maturity cap / unused capability |
| 差异对账 | difference reconciliation | sprout source ① |
| 成熟链封顶 | maturity cap | sprout source ② (step 4 reached) |
| 能力库未用 | unused capability | sprout source ③ (library entry idle) |
| 零差异零芽 | no difference, no sprout | the hard rule of the sprout economy |
| 冻结区 | frozen zone | where evicted sprouts are suspended (not deleted) |
| 重问 | re-ask | asking a frozen question again after its cooling period |
| 结案 | closure | the exit that ends a reminder permanently |
| 生长主体 | growth subject | the directory the engine grows |
| 目录对象 | directory object | `<subject>/<path>/`, quantity = file count |
| 执行者 | executor | whatever acts (prompt on stdin, answer on stdout) |
| 组织会话 | org session | the semantic pass: reconcile, propose, file findings |
| 域饱和 | domain saturation | one unfinished sprout per domain × quantity |
| 轮转 | rotation | moving old ledger lines into `state/archive/` |
| 定键补观测 | keyed supplemental reading | reading predicted keys that fell outside the window |
| 观察面 | observation surface | the bounded set of mechanically readable facts |

Chinese design document: [`zh/mechanism.md`](zh/mechanism.md).
