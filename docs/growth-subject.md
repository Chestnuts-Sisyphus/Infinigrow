# The growth subject

> The question this file answers: **what is the engine growing?**
>
> Without a subject there is no target: a mechanical tick would keep moving while watching only
> its own state files — a dashboard watching a dashboard.

## 1. Two things that must stay separate

| | Engine (Infinigrow) | Subject |
|---|---|---|
| What | code: tick loop, ledgers, rules, prompts | **the thing being grown**: the reality that accumulates changes |
| Change rate | changed as little as possible (open-sourceable, upgradable, movable) | changes constantly (a tick's output *is* its change) |
| Owner | the project (public repo) | **the user** (may contain private material) |
| Default location | the repository | a **sibling** directory `<repo name>-subject` |

Keeping them apart is the default, not a suggestion: co-locating them eventually produces two
kinds of accident — upgrading the engine touches the growth traces, or sharing the repo ships the
subject with it.

## 2. Where the subject is

| Setting | Env var | Default |
|---|---|---|
| `subject_root` | `IG_SUBJECT_ROOT` | `<parent of repo>/<repo name>-subject` |

Any directory works, including one that does not exist yet — a missing subject is observed as
"missing", not treated as an error, and the engine does not invent work for itself because of it.

Objects inside the subject are named `<subject>/<relative path>` (POSIX separators). The prefix
keeps subject objects from ever colliding with the engine's own state objects in the same
reconciliation space, and it lets domain saturation treat one directory as one domain.

## 3. How it is read (mechanically)

One tick does a **read-only, bounded, no-subprocess, no-network** observation:

| Observed | Dimension | Pointer |
|---|---|---|
| subject root | existence (`present` / `missing`) | `subject root` |
| subject root | file count | `subject root` |
| each sub-directory (up to 10, by name) | file count | `subject dir:<path>` |
| each file (up to 20, newest mtime first) | existence **and** byte size | `subject:<path>` |

- File count and total bytes are **real totals**, not truncated counts: the per-file window is
  bounded, the aggregate is not. The aggregate counts the **growth surface** only — the
  subject's own `archive/` subtree is not part of it (next bullet).
- **Rotated content really leaves the growth surface (settled 2026-09-19).** The gardener moves
  `journal/` overflow into `<subject>/archive/journal/`; moving means *write a new file, then
  unlink the source*, so an archived entry carries the mtime of **the moment it was moved** —
  newer than the content still growing. Measured on a copy of the live subject
  (`journal_keep_files=200`, adding one entry per round and running the gardener): past the
  limit every rotation added one archived slot to the 20-file window (rounds 12/13/14 = 1/2/3),
  the first slot was always `archive/journal/…md.<stamp>`, and the subject's file count never
  dropped (363→377) — the rotation had moved nothing out of sight. So `archive/` is excluded in
  all three readings (per-file window, directory objects, file count / total bytes) and the
  object-name gate rejects it even as a proposal (`for_proposal`): one cannot propose "grow
  inside the blind spot". The rule is scoped to the subject **root**: `journal/archive/` is
  ordinary content and stays observable. Code: `subject.SUBJECT_ARCHIVE_DIR`.
- **A sub-directory is an object**: `<subject>/<path>/` (the trailing `/` is the marker). Its
  accountable quantity is the number of files inside, which makes "grow this directory by one
  entry" a **name-free** prediction.
- **Keyed supplemental reading**: keys that appear in the predictions but fall outside the window
  (because a new file pushed the boundary out) are read anyway — only predicted keys, so the
  surface stays bounded. Without it, boundary files were recorded as "not executed" while
  actually present.
- Directory limit 10, file limit 20. Beyond that a directory does not enter the observation
  surface, so proposals about it are rejected by the object-name gate. With a large subject,
  keep the number of top-level directories small (or raise the limit deliberately — a judgement
  change, so change the constant *and* this document *and* its test together).
  **Settled 2026-09-19: both stay at 10 / 20.** Nothing is pressing against the boundary — the
  subject has far fewer than 10 top-level directories, the per-file window takes the 20 newest by
  mtime while file count and total bytes use real totals outside that window — so raising a limit
  would widen the observation surface without adding one accountable quantity.
- **Only one of the two subtrees has a capacity rule.** The gardener rotates `journal/` at
  `journal_keep_files` (default 200 entries), moving the overflow — never deleting — into
  `<subject>/archive/journal/`. `app/` is **deliberately not rotated**: those files are the
  objects the solidify edge is reconciled against — the outcome test literally reads "is the
  evidence file there" (`evaluate_outcome`'s `evidence_key`: present means the application
  happened). Moving one out does two things at once: a named object disappears from the subject
  and the next tick reports it, truthfully, as *missing*, and the **directory object** `app/`
  loses a unit of its file count. Both are differences the engine manufactured for itself (the
  same fault as S1's "branch on completion"), not growth. Before any move is safe there has to
  be a test for
  "this evidence file is closed and no maturity chain refers to it"; without that test a general
  rotation just moves the redemption evidence out of sight. **The size is a dated snapshot**
  (measured 2026-09-19, tick 647): `app/` 145 files / 261,713 bytes (median 1,752), busiest day
  102 new files (2026-09-18) ≈ 0.18 MB/day; `journal/` 179 entries / 544,710 bytes; 325 files in
  the subject root. Re-read it from `infinigrow status`. The trigger to revisit: once the
  evidence files start crowding the observation surface or the disk budget, design the
  "movable" criterion first — do not just move a number.
  **That trigger has now fired (measured 2026-09-19, tick 745):** `observation_composition`
  reads the 20-slot file window as `app` 18 / `journal` 2 (`app/` now 201 files, `journal/`
  194 entries). A copy of the subject under a temp dir confirms the mechanism: pruning `app/`
  to its 4 newest files flips that same window to `journal` 16 / `app` 4, so the crowding
  comes from app's ever-newest mtimes — not from 20 being too small. **Conclusion: needs a
  decision.** The remedy is the still-missing "this evidence file is closed and no maturity
  chain refers to it" test; the observation caps (10 / 20) stay untouched this round, because
  widening them would only let more evidence files crowd out `journal/` without adding one
  accountable quantity.
- `.git` and cache directories are skipped.
- Content-level judgement is not here: byte sizes changed *is* a fact, and no one has to
  interpret it.

## 4. How "it changed" is judged

Reconciliation is mechanical: the B-guess written **before** the act (expectations) is aligned
with the W-answer read **after** it (actuals) on `(object, dimension)` pairs — equal is "right",
unequal is "wrong". Nothing is compared that was not predicted, and nothing is predicted that is
not observed (the symmetry rule) — asymmetry manufactures phantom differences in both directions.
Subject objects are always named:

```
subject/<relative path>      (e.g. subject/notes.md, subject/sub/a.md)
```

The prefix is not decoration. It keeps subject objects and the engine's own state objects
(`tick_status.json` and friends) from ever colliding in one reconciliation space, and it lets the
domain-saturation test read same-directory objects as one domain (`subject/` is one domain,
`subject/sub/` is another). So "did the subject change" becomes a checkable fact:

- predicted `subject/notes.md bytes = 100`, read 120 → a difference (wrong-prediction) → sprout;
- predicted "the number of files at the subject root is unchanged", one more appeared → a
  difference → sprout;
- everything matches → zero differences, zero sprouts (nothing in this tick was corrected by
  reality).

**Note**: the default B-guess is "stays the same" (`predict_subject_unchanged`) — that is the
honest expectation when nothing is known, not conservatism. To predict what the subject will look
like after the work, the **semantic session** writes planned values, which override the defaults
(`subject.merge_predictions`), and the outcome ledger judges the planned values. Without that
layer, any tick where something really happened would be booked as "wrong-prediction": that would
say "nothing was predicted", not "the work was done badly".

## 5. Naming: the one rule that is fixed

New files under `journal/` are named `<created tick, 4 digits>-<created date YYYYMMDD>.md`:
the tick segment is the tick that **created** the file, the date segment is that day's
mechanical date. The same sentence appears in the acting prompt, the org-session prompt and this
document, and `subject.valid_journal_name` is the mechanical test — a proposer cannot know a
future file's creation tick, so proposals name the *directory*, never the file. The test is
**enforced on the proposal side** (the object-name gate rejects a malformed file name outright,
§3); on the writing side it is a prompt convention plus a test guard — the engine never renames
what the executor produced.

## 6. What the subject has to do with the three sprout sources

| Source | Relation to the subject |
|---|---|
| ① difference reconciliation | the most common source (the subject changed unpredicted, or was predicted wrong) |
| ② maturity cap | a subject object reached step 4 (solidified) → "what else can this be used for?" |
| ③ unused capability | unrelated to the subject (it reads the capability-library ledger) |

"One unfinished sprout per domain × quantity" (domain saturation) bites most often on the
subject: when two files under `主体/` are both wrong at once, only one sprout is filed and the
rest are recorded as **absorbed** (the differences still enter the ledger, they just do not each
get a sprout).

## 7. Reproducible checks

```bash
# the resolved config, where the subject is, and that it exists — writes nothing
infinigrow dry-run
# one tick, printed: observations carry the 主体/ prefix and the subject dimensions
infinigrow tick --probe
# the snapshot on disk: directory names and relative names only, never an absolute path
cat state/subject.json
# tests: the subject path defaults outside the repo, is never the state root, and a mechanical
# tick really reads it
python -m pytest tests/test_subject.py
```

## 8. Changing the subject

```bash
export IG_SUBJECT_ROOT=/path/to/another/subject   # per instance, or in the config file
infinigrow dry-run                                # print the resolved subject root (writes nothing)
```

State and subject are independent: pointing at a new subject does not move the ledgers, and
moving the state root does not touch the subject. The honest way to switch subjects is to switch
the **state root with it** (`IG_STATE_ROOT`) — the old ledgers (differences, outcomes, maturity
chain) all describe the old subject's history, and letting them carry over would make the new
subject inherit a past that is not its own.

Chinese original: [`zh/growth-subject.md`](zh/growth-subject.md).
