# Infinigrow

[![ci](https://github.com/Chestnuts-Sisyphus/Infinigrow/actions/workflows/ci.yml/badge.svg)](https://github.com/Chestnuts-Sisyphus/Infinigrow/actions/workflows/ci.yml)
[![release](https://img.shields.io/github/v/release/Chestnuts-Sisyphus/Infinigrow?color=8B5CF6)](https://github.com/Chestnuts-Sisyphus/Infinigrow/releases)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](pyproject.toml)
[![runtime deps](https://img.shields.io/badge/runtime%20deps-0-brightgreen.svg)](pyproject.toml)

**An engine that grows by predicting, reconciling, and turning differences into sprouts.**

[中文说明](README.zh-CN.md) · [Mechanism](docs/mechanism.md) · [Architecture](docs/architecture.md) · [Running it](docs/running.md) · [Security](SECURITY.md)

---

## The idea

Most "autonomous agent" loops grow by **accumulating**: more notes, more memory, more summaries.
That kind of growth has no gradient — it can run forever without getting better, and eventually it
ploughs the same furrow.

Infinigrow grows by **being contradicted**. Every tick:

1. **Predict** — before acting, the session writes down what it expects reality to become
   (object, dimension, expected state, evidence pointer).
2. **Act** — the work happens (an executor, or nothing at all).
3. **Reconcile** — reality is read back and mechanically compared with the prediction.
4. **Sprout** — each difference becomes the next thing to resolve. **No difference, no sprout.**

The point of step 1 is falsifiability. Without a written prediction, "progress" is whatever the
system says it is. With one, the ledgers can compute a redemption rate — how often predictions
were actually confirmed — without asking anyone's opinion.

## What you can use it for

- **A backbone for a self-improving loop.** Plug in any model or script as the *executor*
  (`run_tick(..., llm=...)`, or a command on stdin/stdout). The engine owns everything mechanical:
  the prediction list, reconciliation, sprout creation, queue discipline, ledgers, heartbeat,
  locking.
- **A lab notebook for prediction accuracy.** Differences, outcomes and the maturity chain are
  append-only JSONL; the redemption rate is computed on read and bucketed by object domain ×
  predicted edge × actual edge (maturity step is *not* one of the axes —
  [`docs/mechanism.md`](docs/mechanism.md) §5 says what a long run can and cannot answer). The
  data format for a long-run "how often is it right?" study already exists.
- **A set of constraints worth copying.** If you are writing your own agent loop, these four
  carry over directly: *the acting session may not manufacture its own tasks*, *no difference, no
  sprout*, *one sprout per object × dimension*, *the maturity chain advances at most +1 per tick*.
  Each is the shape of an incident that happened (see the [superseded table](docs/superseded.md)).
- **Three standalone tools.** The static rule scan, the privacy/identity scan, and the
  prompt↔code sync check all run without the engine.

## The mechanism in one table

Reality (W) and belief (B); every structure is an edge between them:

| Edge | Direction | Grows when |
|---|---|---|
| read | W→B | a prediction about that object is later confirmed |
| act | B→W | the action produces an observable change in reality |
| principle | B→B | the derived claim holds in a domain never tested before |
| solidify | W→W | the same input no longer costs cognition (it is automatic) |

An experience matures along read → act → principle → solidify; the fourth step is the cap, and
reaching it opens a new question rather than closing one. There are exactly three sprout sources:
**differences**, **maturity cap** ("what else can this be used for?"), and **unused library
entries** ("why is this not used — does it hold elsewhere?").

Everything else — the queue discipline, the reminder exits, the domain gate, the ledgers, the
static rules — is in [`docs/mechanism.md`](docs/mechanism.md).
The engine's internal vocabulary is Chinese (it is the language of its prompts and ledgers); that
document carries a bilingual glossary.

## Quick start

```bash
git clone https://github.com/Chestnuts-Sisyphus/Infinigrow && cd Infinigrow
pip install -e ".[dev]"

infinigrow version              # engine version
infinigrow dry-run              # resolved config, subject root, executor (writes nothing)
infinigrow tick --probe         # run one tick — zero tokens, no credentials, no network
infinigrow tick --json          # the same, machine-readable
infinigrow gardener             # the mechanical immune system (locks / liveness / rotation)
infinigrow scan                 # static rules (paths / sync / secrets / BOM …)
infinigrow selftest             # positive and negative case for every rule
infinigrow status               # tick, subject, queue composition, capacity+re-ask gates, compliance, executor-side loss, usage split, alerts
infinigrow rotate               # move old ledger lines to state/archive/ (move-only)
```

State lives in `./state/` by default and is gitignored. Point it anywhere:

```bash
infinigrow --state-root /tmp/ig tick
IG_STATE_ROOT=/tmp/ig infinigrow tick
```

### Giving it something that acts

By default the engine runs **mechanical ticks**: zero tokens, zero credentials, no network. To let
it act, hand it an *executor* — any command that reads the prompt on **stdin** and writes its
answer to **stdout**:

```bash
infinigrow tick --executor "your-command --flags"      # or set IG_EXECUTOR
```

Four failure modes (non-zero exit / timeout / empty output / cannot start) are all recorded in
`state/executor.jsonl` and counted separately from tick failures. Every call leaves a trace in
`state/traces/`. See [`docs/running.md`](docs/running.md).

```python
from infinigrow import load_settings, run_tick

def my_executor(prompt: str) -> str:
    # your model, script or human; read SECURITY.md before wiring anything that runs commands
    return "..."

result = run_tick(settings=load_settings(), llm=my_executor)
print(result.diff_summary, result.new_sprouts)
```

### What it grows

The engine needs something to grow: a directory (the *growth subject*), by default a **sibling** of
the repository. Objects inside are named `<subject>/<relative path>`; the mechanical observation
reads existence, file count, byte sizes, and directory file counts. See
[`docs/growth-subject.md`](docs/growth-subject.md).

### On a schedule (Windows)

```bat
tools\run_tick.bat                        :: version gate -> one tick -> gardener
tools\manage_scheduled_task.bat install   :: register the task (every 10 minutes)
```

The task action is a hidden launcher (`wscript //nologo tools\run_tick_hidden.vbs`) — a scheduled
`.bat` or bare `python` flashes a console window on every run. Rule R10 and its tests keep it that
way.

## Architecture

```
CLI ─▶ scheduler ─┐
                  ├─▶ engine ───────▶ ledger ──────▶ core
     rules ───────┤   tick             store           paths / config / encoding
     garden ──────┘   reconcile        rotation        exit_codes / version_check
                      sprout_* / model  (the only write path)
                      org_trigger / org_session
                      subject / executor / domain_saturation
```

Six layers, dependencies pointing one way, and exactly one module allowed to touch the disk. The
full diagram and the reasoning behind each boundary: [`docs/architecture.md`](docs/architecture.md).

## Guarantees enforced by machines, not by memory

```bash
infinigrow scan                          # R1 no absolute paths · R2 prompt↔code sync
                                         # R3 no self-sprout clause · R4 state root ignored
                                         # R5 no credential literals · R6 no BOM · R7 exit codes
                                         # R8 single write path · R9 sync table cannot shrink
                                         # R10 scheduled task uses the hidden launcher
infinigrow selftest                      # each rule has a positive and a negative case
python tools/check_prompt_code_sync.py   # bidirectional prompt↔code check
python tools/privacy_scan.py --root .    # paths / credentials / emails before publishing
```

CI runs all of that on Linux and Windows, for Python 3.11 and 3.12, plus a **cold start**: three
ticks in an empty state root, zero tokens, zero credentials, asserting no absolute path appears in
any artifact.

## Running the latest engine

```bash
python tools/run_latest.py        # upgrade if possible, then run one tick
infinigrow version --check        # local version vs. latest release (exit code 3 when behind)
```

The default is "upgrade if that is possible, then run the new version; if it is not possible, run
the current version anyway and say why". It never stops the engine just because a newer release
exists, and it never replaces code while a tick is in flight. Details:
[`docs/upgrading.md`](docs/upgrading.md).

## Status and limitations

The engine runs on a real machine: one tick every ten minutes, an executor wired in, ledgers
growing. Each change since v2.0.0 came out of a live observation — the ones worth knowing about are
in the release notes and in the [superseded table](docs/superseded.md).

Honest limitations:

- **A mechanical tick does no cognition.** It proves the mechanism turns; it does not grow anything.
- **The engine is deliberately small** (~7,200 lines of Python plus ~6,600 lines of tests) and has
  **zero runtime dependencies**. Deployment concerns — schedulers, proxying, provider rotation,
  sandboxing — are yours; [`SECURITY.md`](SECURITY.md) is the starting point.
- **The executor interface is a plain callable / command.** No vendor SDK is included.
- **The mechanism vocabulary is Chinese** in code, prompts and ledgers (the English docs carry a
  glossary). See [`docs/mechanism.md`](docs/mechanism.md).
- **The subject is the user's**; the repository ships no subject, no ledgers and no state.

## Documentation

| Document | What it answers |
|---|---|
| [`docs/mechanism.md`](docs/mechanism.md) | the design of record + glossary (Chinese original: [`docs/zh/`](docs/zh/)) |
| [`docs/architecture.md`](docs/architecture.md) | layers, write path, state layout, one tick as a data flow |
| [`docs/growth-subject.md`](docs/growth-subject.md) | what is being grown, how it is observed, naming rules |
| [`docs/running.md`](docs/running.md) | executor channel, scheduling, watching a long run |
| [`docs/upgrading.md`](docs/upgrading.md) | the "run the latest version" rule |
| [`docs/privacy.md`](docs/privacy.md) | the three hard lines and the pre-publish checklist |
| [`docs/versioning.md`](docs/versioning.md) | v1 vs. v2, and what a version number means here |
| [`docs/superseded.md`](docs/superseded.md) | retired mechanisms and what replaced them |
| [`CHANGELOG.md`](CHANGELOG.md) | release by release |

**Language.** The documentation is English. The engine's runtime text (CLI output, reports,
`ALERT.md`, ledger fields) is **Chinese** — that is the mechanism's language, and
[`docs/mechanism.md`](docs/mechanism.md) carries a bilingual glossary for it.

## License

MIT — see [LICENSE](LICENSE).
