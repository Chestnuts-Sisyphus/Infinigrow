# Running Infinigrow

Three things: the executor channel, the schedule, and the gardener.
Nothing here needs credentials unless *your* executor does.

> **Language note.** The engine's runtime text — `--help`, the `status` output, reconciliation
> reports, `ALERT.md`, ledger field values — is **Chinese**, because that is the mechanism's
> language (see the glossary in [`mechanism.md`](mechanism.md)). The English documentation you are
> reading is its manual. An English CLI/report mode is not implemented yet; if you need one it can
> be added for the CLI layer only, without touching the mechanism vocabulary or the ledger fields.

## 1. The executor channel

**Contract**: the prompt goes in on **stdin**, the answer comes out on **stdout**. One call is
one chance to act.

```bash
infinigrow tick --executor "your-command --flags"     # or set IG_EXECUTOR
```

No executor means a **mechanical tick**: zero tokens, zero credentials, no network, no
subprocess. That is what CI runs and what you use to see the mechanism turn without paying for it.

| The engine sets | Value |
|---|---|
| `IG_TICK` | this tick number |
| `IG_PASS_KIND` | `tick` or `org-session` |
| `IG_SUBJECT_ROOT` | where the work happens |
| `IG_STATE_ROOT` | where the ledgers are |
| `IG_MODEL` | the model label from config (`IG_LLM_MODEL`), if set |
| `PYTHONIOENCODING` | `utf-8` (so the prompt survives non-UTF-8 consoles) |

Credentials are **not** the engine's business: put them in your own environment or in the
executor script. The engine never stores, moves or echoes them.

Four failure modes are all recorded in `state/executor.jsonl` and counted separately from tick
failures (non-zero exit / timeout / empty output / cannot start), because "the tick ran but
nothing acted" and "the tick did not run" are different illnesses. An executor may report usage
by printing a line `IG_USAGE {"input_tokens": 1234, "cost_usd": 0.01}`; without it the ledger
stores `null` — the engine does not guess token counts from output length.

Every call leaves a trace in `state/traces/<kind>-<tick>.md` containing the prompt and the
output verbatim. Traces are how the org session reads what actually happened (and how you debug
a channel), so they are written even when the executor fails.

### Try it without burning anything

```bash
infinigrow dry-run                 # resolved config, subject root, executor — writes nothing
infinigrow tick --probe            # one mechanical tick
python tools/demo_executor.py      # a deterministic local "executor" (used in the docs)
infinigrow tick --executor "python tools/demo_executor.py"
infinigrow org-session --tick <n>  # run just the semantic pass
infinigrow org-status              # how the org session's findings turned out
```

## 2. Scheduling and watching

```bat
tools\run_tick.bat                        :: version gate -> one tick -> gardener
tools\manage_scheduled_task.bat install   :: register the task (every 10 minutes)
tools\manage_scheduled_task.bat status
tools\manage_scheduled_task.bat remove
```

`IG_TICK_MINUTES` sets the interval. The task action is
`wscript //nologo tools\run_tick_hidden.vbs`, which runs `run_tick.bat` with window style 0.

**Why the hidden launcher is not optional**: Windows flashes a console window for a scheduled
`.bat`, a bare `python`, or any child process that allocates a console. A window that steals
focus every ten minutes is unusable on a machine someone is working on. (`-Hidden` in the task
settings only hides the *task entry*, not the window.) Rule **R10** and
`tests/test_scheduler_artifacts.py` keep this in place.

The gardener runs at the end of every scheduled tick (and standalone):

```bash
infinigrow gardener     # stale locks, liveness, failure escalation, ledger/frozen-zone rotation
```

It writes `state/ALERT.md` — the single human-facing alert surface. No fatal flag means one line
saying the engine is fine.

## 3. Watching a long run

```bash
infinigrow status                     # tick, subject, queue composition, redemption, ALERT, today's usage
infinigrow tick --json | jq .         # machine-readable result of one tick
ls state/reconcile/ | tail            # one report file per tick (named by tick number)
```

Healthy is not "rc=0 and ALERT is normal". Look at the *composition*: what the queue is made of,
which sprout sources are producing, and whether the source you care about is being picked. The
`status` command prints the queue's origin distribution for exactly this reason.

## 4. Pausing

```bash
infinigrow pause      # disables the scheduled task (state is untouched)
infinigrow resume     # re-enables it
```

Or disable the task in the Windows Task Scheduler. Pausing never touches ledgers or the subject.

Chinese original: [`zh/running.md`](zh/running.md).
