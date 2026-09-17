# Infinigrow v2.1.0 — the runtime line

**The test layer is unchanged**: four edges, a four-step maturity chain, four difference kinds,
three sprout sources. This release adds what it takes to actually run: the engine now knows
**what it is growing**, **who acts**, **who does the semantic pass**, plus the discipline around
them.

```bash
pip install -e ".[dev]"
infinigrow dry-run         # resolved state root, growth subject, executor
infinigrow tick --probe    # one tick (mechanical by default: zero tokens, no network)
```

## Added

- **Growth subject**: the thing being grown is an explicit directory (a sibling of the repo by
  default; `IG_SUBJECT_ROOT` points anywhere). Mechanical observation reads *the subject* —
  existence, file count, per-file byte size, bounded and stably ordered — and objects are named
  `<subject>/<relative path>`. A missing subject is not an error and does not invent work:
  "missing" is an honest observation. See [`growth-subject.md`](growth-subject.md).
- **Executor channel**: `infinigrow tick --executor "<command>"` (or `IG_EXECUTOR`). Prompt on
  **stdin**, answer on **stdout**; output is stored verbatim in `state/traces/`, each call is
  recorded in `state/executor.jsonl` (rc, duration, sizes, optional usage). **No executor means a
  mechanical tick** — that default is unchanged. Four failure modes (non-zero exit, timeout, empty
  output, cannot start) are visible and counted separately from tick failures. See
  [`running.md`](running.md).
- **Org session runtime**: the semantic pass is now code, not just prompt text. Input: B-guess,
  traces, readings. Output: the four difference kinds plus **planned predictions**. Findings land
  in `state/org-findings.jsonl`, and their fate is computed later by reconciliation
  (`infinigrow org-status`: pending / confirmed / contradicted) — the engine does not grade itself.
- **Planned predictions override the default**: the default B-guess is "unchanged"; a planned value
  overrides it. Without that layer, any tick that really acted would be recorded as
  "predicted-wrong" — which would not mean "it acted wrongly" but "nothing was predicted".
- **Domain saturation**: one unfinished sprout per "object domain × accountable quantity",
  including within one tick. A duplicate difference does not spawn; it is recorded as an
  `absorbed` count on the existing sprout, and the difference itself still enters the ledger
  (`absorbed_by_domain`) — a quota is not a cover-up.
- **Ledger rotation**: past a size threshold, history **moves** into `state/archive/` (move-only).
  History-shaped ledgers keep the tail N lines; state-shaped ledgers (maturity, library) keep the
  **latest line per key**, so an untouched object cannot silently regress. Archives are searchable.
- **An honest redemption rate**: outcome rows carry `sample`, and the denominator counts only ticks
  where an executor really acted. With no samples the report says **"no samples"** (not
  computable) — not 0, not "bad".
- **Three more static rules** (nine total, each with both cases): **R7** single source for exit
  codes, **R8** a single write path, **R9** the sync table cannot shrink.

## Engineering

- One-click launcher `tools/run_tick.bat` (**version gate → one tick → gardener**) plus a
  scheduled-task registrar (every 10 minutes by default).
- **CI on two platforms**: `windows-latest` joined the matrix, because that is where the engine
  actually runs.
- `update_local.py` merged into `run_latest.py --update`.
- Two real defects fixed: `run_latest.py --repo` had no effect on the version check, and the
  sprout-picking order was dominated by ID prefixes (`cap*` always sorted before `sp*`, starving
  the primary source).
- A family of defects caught by the first two-platform CI run: Chinese output raised
  `UnicodeEncodeError` on non-UTF-8 consoles (all entry points now go through
  `core/encoding.harden_stdio`), non-ASCII text inside `.bat`/`.ps1` was mangled by the system code
  page (those files are ASCII-only now), and the artifact checker false-positived on PNG bytes.

## Known limitations

- The org session **depends on the executor**: without one it does not run (it only leaves a "due"
  marker).
- Domain saturation records same-domain duplicates as `absorbed`: a quota, not a resolution.
- Rotation does not compress: history stays in `state/archive/` verbatim.
- Out of the box the ledgers are **mechanical** ticks: they prove the mechanism turns, but the
  redemption rate reads "no samples" until something that acts is wired up.

**Full changes**: [`CHANGELOG.md`](../CHANGELOG.md).
