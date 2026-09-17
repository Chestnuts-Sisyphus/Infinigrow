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
rows; the *semantics* are deliberately unchanged — changing them changes the org cadence and
its token cost, which is an open decision (N58-①).

**Measured cadence ([proven])**: the cooldown gate allows one run per 30 minutes, and the
measured interval is **median 40.0 min / mean 42.3 min** (`state/org-llm.jsonl`, 100 intervals,
manual runs under 10 minutes excluded). The reason is structural: ④ can only fire after a
*quiet* tick, and the ticks that actually move the subject always write a non-OK row — ④ and
growth are negatively correlated (N58). The effective cadence is the cooldown plus one quiet tick.

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
  reappears. (A `long_task` exemption branch exists in the field set, **kept as reserved** and
  deliberately not wired: there is no writer and no mechanical test for "what counts as a long
  task", and the lead limit already prevents one sprout from hogging the slot. The field stays so
  that old ledger rows still parse.)
- **Re-asking frozen sprouts**: after `frozen_requestion_ticks` (default 300) without being
  re-lit, an object is no longer blocked by its frozen sprout — it may be asked again. The test
  uses the *newest* freeze of that object, so a backlog of old frozen sprouts cannot release a
  whole batch at once.
- The frozen zone has a **capacity rule** of its own: past `frozen_cap` (default 5000) the
  oldest lines are *moved* to `state/archive/` (move-only, same discipline as ledger rotation).

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

**Rotation** moves history into `state/archive/` (move-only). History-shaped ledgers keep the
tail N lines; state-shaped ledgers (maturity, library) keep the **latest line per key**, so an
object that has not been touched in a while cannot silently regress. Archives are searchable
with `infinigrow rotate --search <term>`.

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
