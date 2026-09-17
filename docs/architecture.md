# Architecture

## Layers

```
CLI ─▶ scheduler ─┐
                  ├─▶ engine ───────▶ ledger ──────▶ core
     rules ───────┤   tick             store           paths / config / encoding
     garden ──────┘   reconcile        rotation        exit_codes / version_check
                      sprout_* / model  (the only write path)
                      org_trigger / org_session
                      subject / executor / domain_saturation
```

1. **Dependencies point down only**: `core → ledger → engine → rules/garden/scheduler → cli`.
   An upper layer may import a lower one; a lower one may not import an upper one.
2. **All disk writes go through `ledger/store.py`**: appending to a ledger, atomic replacement of
   a work file, exclusive creation (locks) and the containment guard live in that one module;
   `core/encoding.py` only handles encodings and text. Enforced by rule **R8**.
3. **`core` is the only machine-specific layer**: state root, config, encoding, exit codes,
   version lookup. Everything above receives a `Settings` and a `StateLayout` and never builds
   a path itself.
4. **`rules` does not import `engine`**: static rules read files and compare strings, so they run
   in CI against a repository with no state at all.
5. **Exit codes have a single source**: `core/exit_codes.py`. Bare integers ≥2 in the CLI are
   reported by rule **R7**.

## The four runtime pieces

| Piece | File | It owns | It does not own |
|---|---|---|---|
| **Growth subject** | `engine/subject.py` | what the engine grows; mechanical observation (existence, file count, byte size, **directory objects**; bounded, stable order; keyed supplemental reading for predicted keys) | content-level judgement (that is the executor and the org session) |
| **Executor channel** | `engine/executor.py` | prompt on stdin, answer on stdout; recording of every call (rc, duration, sizes, usage); traces; four visible failure modes | it knows no vendor — the command comes from `--executor` / `IG_EXECUTOR` |
| **Org session** | `engine/org_session.py` | semantic work: find differences in traces and readings, write planned predictions, file findings, watch reality for changes since it last ran | it does not act (the executor does), and it cannot manufacture sprouts either |
| **Domain saturation / rotation** | `engine/domain_saturation.py` · `ledger/rotation.py` | one unfinished sprout per domain × quantity; moving ledger history and oversized frozen zones into the archive (move-only) | no content judgement; no line is ever deleted |

**Why the org trigger lives in `engine/` and not in `scheduler/`**: the tick loop must consult it
itself. A previous generation built the judgement layer but wired no caller for it, so its output
expired where it was produced. `scheduler/triggers.py` is a facade for external callers; the
implementation and the single source of truth are in `engine/org_trigger.py`, and every tick
writes the decision to `state/org-due.json` so "it should run now" cannot be silently ignored.

## One tick, as a data flow

```
                     ┌────────────────────────────────────────────┐
   executor ◀────────│ 1 org session (when due; skipped without one)│
   (stdin/stdout)    │   input : B-guess + traces + readings        │
                     │   output: differences + planned predictions  │
                     └───────────────┬────────────────────────────┘
                                     ▼
   2 B-guess (default: "unchanged"; planned predictions override it)
                                     ▼
   3 pick a sprout (oldest untouched first, then birth tick, then id)
                                     ▼
   4 act (executor; no executor = mechanical tick)
                                     ▼
   5 W-read (**after** acting) + keyed supplemental readings
                                     ▼
   6 reconcile → four kinds → domain gate → sprout
                                     ▼
   7 account: diffs / outcomes / maturity / executor / domains / report / heartbeat
```

## State layout

| Path | What | Git |
|---|---|---|
| `<repo>/state/` | ledgers, queue, reports, traces, heartbeat (default; `IG_STATE_ROOT` points anywhere) | ignored |
| `<repo>/state/archive/` | rotated ledgers, reports, traces, oversized frozen zones | ignored |
| `<repo>-subject/` (sibling) | the growth subject (`IG_SUBJECT_ROOT` points anywhere) | outside the repo |

Nothing under `state/` may contain this machine's absolute paths; `tools/check_no_abs_paths.py`
enforces that (CI runs it against a fresh state root, and it passes on the live one too —
the launcher prints a directory *name*, not a path).

## Boundaries that exist because something broke

Each of these was a live incident, and each is now structural rather than commented:

- the acting session cannot create sprouts (`engine/tick.py` has no such entry point);
- report file names carry the tick number, and sessions take a lock (same-second overwrites
  silently destroyed reports);
- the maturity chain advances at most +1 per object per tick, and the step function hard-codes it;
- a failed heartbeat **raises** instead of silently resetting the tick number, and the tick
  number is recovered from the ledgers when the heartbeat is unreadable or behind them;
- the scheduler action is a hidden launcher (window style 0): a scheduled `.bat` or bare
  `python` opens a console window on every run;
- there is no self-sprout clause in the prompts (rule **R3** guards the regression).

Full design: [`mechanism.md`](mechanism.md). Chinese original: [`zh/architecture.md`](zh/architecture.md).
