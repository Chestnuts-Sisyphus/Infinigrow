# Upgrading: the engine runs the latest version it can get

## One sentence

Infinigrow is the **engine**; this rule is about the engine's version (not the subject it
grows). Default behaviour: **upgrade to the latest if that is possible, then run; if it is not
possible, run the current version anyway and say why.**

## The entry point

```bash
python tools/run_latest.py                     # default: conditional upgrade, then one tick
python tools/run_latest.py -- --probe          # everything after "--" goes to `infinigrow tick`
python tools/run_latest.py --check             # report the version state, do not run
python tools/run_latest.py --no-update         # do not try to upgrade
python tools/run_latest.py --require-latest    # strict: refuse to run when not on the latest
```

## Three cases

| Case | Behaviour | Why |
|---|---|---|
| Upgrade is possible (behind + clean tree + no tick in flight + no divergence + post-upgrade self-test green) | **upgrade, then run the new version** | the default is "newest" for the user |
| Upgrade is not possible (dirty tree / tick in flight / diverged history / offline / pull failed / self-test failed and rolled back) | **run the current version**, and print why this run is not the latest | never stop the engine just because it is not the latest — a version that runs is more useful than a rule that does not |
| Strict mode (`--require-latest`) | refuse to run (rc=4) | opt-in strictness for CI and release verification |

Details worth knowing:

- **A dirty working tree blocks the upgrade** (the upgrade is `git pull --ff-only`, which would
  not overwrite your changes anyway — but it also would not include them).
- **A tick in flight blocks the upgrade** (`state/locks/tick.lock` exists): the engine never
  replaces its own code while running. Concurrency inside the engine is handled by that same
  lock — a session that cannot take it skips the tick idempotently.
- **A failed self-test rolls back** (`selftest` plus `scan`), and the rolled-back version runs:
  better an older version than one that fails its own tests.
- **Only engine code is touched**: `state/` is gitignored, so `pull`/`reset` never touches the
  ledgers, the queue or the reports.

## Every tick records which engine ran

The heartbeat carries the engine version and commit, so historical readings can be attributed to
a version. "The engine must be the latest to run" is only meaningful if each tick says which
version it was.

```bash
infinigrow version            # local version
infinigrow version --check    # local vs. latest release (exit code 3 when behind)
```

Chinese original: [`zh/upgrading.md`](zh/upgrading.md).
