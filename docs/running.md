# Running Infinigrow

Three things: the executor channel, the schedule, and the gardener.
Nothing here needs credentials unless *your* executor does.

> **Language note.** The engine's runtime text — `--help`, the `status` output, reconciliation
> reports, `ALERT.md`, ledger field values — is **Chinese**, because that is the mechanism's
> language (see the glossary in [`mechanism.md`](mechanism.md)). The English documentation you are
> reading is its manual. An English CLI/report mode is not implemented yet; if you need one it can
> be added for the CLI layer only, without touching the mechanism vocabulary or the ledger fields.

## 1. The executor channel

### 1. The contract

```
    python -m infinigrow tick --executor "your command  args..."
                    │
                    ├─ stdin  ← the prompt (the mechanism prompt + this tick's question + the B-guess)
                    └─ stdout → your answer (stored verbatim under state/traces/, plus an optional usage line)
```

- **No executor means a mechanical tick**: zero tokens, zero credentials, no network, no
  subprocess. That is the default posture, and the one CI and an empty repository run in.
- One call is one chance to act. The same channel serves two purposes, told apart by the
  environment variable `IG_PASS_KIND`:
  - `tick`: the difference this tick has to resolve (the question);
  - `org-session`: the semantic pass (find differences, write the planned predictions, register sprouts).
- **Spawning does not go through a shell**: the command string is split into argv (honouring
  quotes) and executed directly — `shell=True` would hand the freedom of string concatenation back
  to the caller, and on Windows it would also expand `%VAR%`. Quote paths with a drive letter, or
  write them with forward slashes.

Credentials are **not** the engine's business: put them in your own environment or in the executor
script — the engine never stores, moves or echoes them.

### 2. Wiring it up

| Way | Command |
|---|---|
| one-off (CLI) | `infinigrow tick --executor "your-command"` |
| config file | `executor = "your-command"` (in `infinigrow.toml`) |
| environment | `IG_EXECUTOR="your-command"` (handiest inside a scheduled task or guard script) |
| force a mechanical tick | `--no-executor` (ignores whatever the config set) |
| timeout | `--executor-timeout 300` or `IG_EXECUTOR_TIMEOUT_S` (default 120 seconds) |

```bash
infinigrow tick --executor "your-command --flags"     # or set IG_EXECUTOR
```

No executor means a **mechanical tick**: zero tokens, zero credentials, no network, no
subprocess. That is what CI runs and what you use to see the mechanism turn without paying for it.

**Timeout × the scheduler's time limit (K12/A17 — do not burn the whole window)**: the per-call
executor timeout (`IG_EXECUTOR_TIMEOUT_S`, 600 seconds on this machine) and the scheduled task's
total limit (30 minutes) are **not the same thing**. One tick may fire a `tick` call and an
`org-session` call, each with its own timeout. If both run to the end (600 + 600 = 1200 seconds
≈ 20 minutes) you are still inside the 30-minute limit, but only 10 minutes are left — and the
same tick still has reconciliation, bookkeeping and the gardener to run, after which Windows Task
Scheduler **kills the process** at the limit. So: executor timeout × calls per tick must be
**clearly smaller** than the scheduling limit (rule of thumb: leave at least 1/3 of the window as
headroom). A hung call occupying the window, a task killed by the scheduler and a ledger left
mid-tick are all far more expensive than one failed call — prefer a shorter per-call timeout
(lower `IG_EXECUTOR_TIMEOUT_S`) to dragging the whole tick until it is killed. (Nothing here
changes your environment variables; it only states the relation and the advice.)

### 3. Environment variables the engine gives the executor

| The engine sets | Value |
|---|---|
| `IG_TICK` | this tick number |
| `IG_PASS_KIND` | `tick` or `org-session` |
| `IG_SUBJECT_ROOT` | where the work happens |
| `IG_STATE_ROOT` | where the ledgers are |
| `IG_MODEL` | the model label from config (`IG_LLM_MODEL`), if set |
| `PYTHONIOENCODING` | `utf-8` (so the prompt survives non-UTF-8 consoles) |

### 4. Failures must be visible (all four cases are recorded)

Four failure modes are all recorded in `state/executor.jsonl` and counted separately from tick
failures (non-zero exit / timeout / empty output / cannot start), because "the tick ran but
nothing acted" and "the tick did not run" are different illnesses. An executor may report usage
by printing a line `IG_USAGE {"input_tokens": 1234, "cost_usd": 0.01}`; without it the ledger
stores `null` — the engine does not guess token counts from output length.

### 5. Traces

Every call leaves a trace in `state/traces/<kind>-<tick>.md` containing the prompt and the
output verbatim. Traces are how the org session reads what actually happened (and how you debug
a channel), so they are written even when the executor fails.

### 6. Dry run first (burn nothing)

```bash
infinigrow dry-run                 # resolved config, subject root, executor — writes nothing
infinigrow tick --probe            # one mechanical tick
python tools/demo_executor.py      # a deterministic local "executor" (used in the docs)
infinigrow tick --executor "python tools/demo_executor.py"
infinigrow org-session --tick <n>  # run just the semantic pass
infinigrow org-status              # how the org session's findings turned out
```

## 2. Scheduling and watching

### 1. One-click files

| File | What it does |
|---|---|
| `tools/run_tick.bat` | one full run: **version gate → one tick → gardener** (locks, liveness, failure escalation, rotation) |
| `tools/manage_scheduled_task.bat` | `install` / `status` / `uninstall` the scheduled task |
| `tools/scheduled_task.ps1` | the actual registration logic (current user, no elevation) |
| `tools/run_tick_hidden.vbs` | **the hidden launcher**: the task runs this, not the `.bat` |

Double-clicking `tools/run_tick.bat` runs one tick; the scheduled task runs the same file.

### 2. Hooking up a scheduled task (one tick every 10 minutes)

```bat
tools\manage_scheduled_task.bat install
tools\manage_scheduled_task.bat status
```

- the interval comes from `IG_TICK_MINUTES` (default **10 minutes**, same as the `tick_minutes`
  config key);
- the task name is `Infinigrow_tick` by default (`IG_TASK_NAME` changes it);
- **every run passes the version gate**: upgrade to the latest by default; if it cannot
  (dirty tree / tick in flight / diverged / offline / self-test failed and rolled back) it
  **runs the current version anyway** and prints why this run is not the latest — it never stops
  the engine for being behind;
- uninstall: `tools\manage_scheduled_task.bat uninstall` (**removes the task only** — state and
  ledgers are untouched).

### 2.5 Why not schedule the `.bat` directly (**do not remove this layer**)

Letting the task run the `.bat` (or `cmd`, or a bare `python`) **flashes a console window on every
run** — it steals focus and covers whatever the person at the machine is looking at.
`run_tick_hidden.vbs` hides it with WSH window style 0, so the task action is
`wscript.exe //nologo …run_tick_hidden.vbs`. Note that `New-ScheduledTaskSettingsSet -Hidden`
hides the *task entry* in the list, **not the window** — do not mix the two up.

(Same family of lessons: keep `.bat`/`.vbs` **pure ASCII** — cmd and wscript read scripts in the
system code page and non-ASCII comments break parsing; use `pythonw.exe` for windowless Python.)

### 3. Watching (the gardener does it in passing)

| Check | Criterion | Consequence |
|---|---|---|
| dead lock | lock file mtime older than 15 minutes | the stale lock is cleared |
| stalled | last tick's **mechanical timestamp** older than 12 hours | fatal flag (`state/ALERT.md`) |
| tick failures | 3 consecutive | fatal flag |
| executor failures | 3 consecutive | fatal flag (with the last rc) |
| bad ledger lines | unparseable lines > 0 | fatal flag |
| ledger rotation | ledger bytes ≥ `rotate_max_bytes` | rotation (move-only) |

A human only needs one file: **`state/ALERT.md`** — with a fatal flag it says "someone should
look" plus the reasons; without one it says the engine is fine plus the last tick's time.

The gardener runs at the end of every scheduled tick (and standalone):

```bash
infinigrow gardener     # stale locks, liveness, failure escalation, ledger/frozen-zone rotation
```

### 4. Logs

`run_tick.bat` appends every step to `state/logs/tick.log` (inside the state root, so it moves
with the state).

### 5. Troubleshooting order (outside in)

```bash
python -m infinigrow dry-run        # are config/subject/executor what you think they are?
python -m infinigrow tick --json    # run one tick: rc, differences, report name
python -m infinigrow gardener       # one health pass (writes ALERT.md) and prints its JSON
cat state/ALERT.md                  # the human-facing surface
cat state/tick_status.json          # heartbeat: tick / timestamp / failures / engine identity
tail state/executor.jsonl           # executor call ledger (rc / duration / output size / usage)
python -m infinigrow org-status     # how the org session's findings turned out
```

**`org-check`: the answer is in the JSON; the exit code only says whether the command ran.**
It returns `should_run=true → 0` and `should_run=false → 5`. That 5 is `exit_codes.NOT_THIS_TICK`
— "ran fine, and the answer is: not this tick" — which since 2026-09-19 replaces the borrowed
`1` this command used to return (1 is usage errors again, so a mistyped flag can no longer hide
behind a legitimate "no"). The CI cold-start step now calls it on an empty state root, where the
answer is `should_run=true`/0, so the `|| true` that used to swallow real usage errors is gone.
Branch on `should_run`, not on rc.

---

## 3. Cost and usage (only meaningful once an executor is attached)

| Fact | Where to see it |
|---|---|
| the engine itself | **zero tokens**: mechanical ticks, the gardener, rule scans, reconciliation and bookkeeping burn no cognition |
| the executor | usage is self-reported (one `IG_USAGE` line); the engine records, it does not guess |
| redemption rate | the "redemption" section of `state/reconcile/reconcile-*.md`: with no executor acting it says **"no samples"** — not 0, not "bad" |

The denominator counts only ticks where an **executor acted** (`sample=true`): a mechanical
tick's "failure to redeem" does not mean the capability is bad — it means no hand was moving.

## 4. One-screen status and pause/resume

```bash
python -m infinigrow status      # tick / subject files / queue / capacity+re-ask gates / compliance / executor-side loss / usage split / ALERT line / today's tokens
python -m infinigrow pause       # disable the scheduled task (**does not delete** it; resume works)
python -m infinigrow resume      # re-enable it
```

`pause`/`resume` only toggle the task's Enabled state
(`Disable-ScheduledTask`/`Enable-ScheduledTask`) — they **never delete the task or touch the
ledgers**. On non-Windows they report "environment not satisfied" (rc=4) instead of pretending to
succeed. The token count in `status` only sums what executors **self-reported** (`IG_USAGE`) —
without it, it says "not estimable"; the engine never passes output length off as tokens.

## 5. Local deployment reference (private part; **never put credentials in the repo**)

The engine runs with zero configuration; making it actually act, on schedule, takes four things:

1. **an executor adapter** (a private script, outside the repo): reads *your* credential source
   (read-only, through environment variables, never written to disk or echoed), feeds the engine's
   prompt (stdin) to your model, returns stdout verbatim, and prints one `IG_USAGE {…}` line on
   success. The contract is section 1 of this document. The engine **hard-codes no vendor**:
   which model you use is decided by `IG_EXECUTOR`.
2. **user-level environment variables**: `IG_EXECUTOR` (the adapter command),
   `IG_EXECUTOR_TIMEOUT_S` (timeout), plus whatever model-tier variables your adapter needs
   (for example `IG_MUSE_EFFORT=low`).
3. **a scheduled task**: `tools\manage_scheduled_task.bat install` or
   `tools\scheduled_task.ps1 -Action install` (one tick every 10 minutes; the action is the
   **hidden launcher**, see §2.5 — do not schedule the `.bat` directly). To change the frequency:
   `IG_TICK_MINUTES`.
4. **a growth subject**: by default a sibling of the repo (`<repo name>-subject`); switching it
   means changing `IG_SUBJECT_ROOT` **together with `IG_STATE_ROOT`** (old ledgers describe the
   old subject — see [`growth-subject.md`](growth-subject.md)).

Self-check: `python <your adapter> --selftest` (if it has one) should print an "online" kind of
answer; `python -m infinigrow status` should show the tick number advancing over time and
`ALERT.md`'s first line saying the engine is fine. For the troubleshooting order, see §2.5.

Chinese original: [`zh/running.md`](zh/running.md).
