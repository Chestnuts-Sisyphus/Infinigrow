# Infinigrow

**An engine that grows by predicting, reconciling, and turning differences into sprouts.**

[中文说明](README.zh-CN.md) · [Mechanism](docs/mechanism.md) · [Architecture](docs/architecture.md) · [Security](SECURITY.md)

---

## What it is

Most "autonomous agent" loops grow by *accumulating*: more notes, more memory,
more summaries. That kind of growth has no gradient — it can run forever without
getting better, and eventually it just plows the same furrow.

Infinigrow grows by *being contradicted*. Every tick:

1. **Predict (B)** — before acting, the session writes down what it expects reality to become.
2. **Act (W)** — it does the work.
3. **Reconcile** — reality answers (`W回`). The engine mechanically diffs prediction vs. observation.
4. **Sprout** — each difference becomes a sprout: the next thing to resolve. **No difference, no sprout.**

The engine itself is about 2,000 lines of Python (plus 600 lines of tests) and makes no network
calls by default. It runs one tick with zero tokens and zero credentials, which is exactly what
CI does on every push.

## Why "predict and reconcile"

A prediction is the only thing that makes growth **falsifiable**. Without it,
"progress" is whatever the system says it is. With it, the ledger can compute a
redemption rate (how often predictions were confirmed) without asking anyone's opinion.

Design decisions follow from that:

| Decision | Reason |
|---|---|
| Sprouts come **only** from ledgers (differences / maturity cap / unused library entries) | The executor session must not be able to manufacture its own work; when it could, a previous generation of this engine filled its queue with 186 near-identical "sprouts" and ground to a halt |
| **N differences → N sprouts; zero differences → zero sprouts** | Otherwise sprouts become a vanity metric |
| Ledgers are **append-only**; only the queue is mutable | Statistics you can edit are not statistics |
| Maturity chain advances **at most +1 per tick** | Two concurrent sessions once double-incremented it |
| Reconcile reports are named `reconcile-<tick>.md`, sessions take a lock | Same-second overwrites silently destroyed reports |
| A failed heartbeat **raises** | The gardener's liveness check reads that file; a silent stall makes two guards report "healthy" |

## Quick start

```bash
pip install -e ".[dev]"

infinigrow version              # Infinigrow 2.0.0
infinigrow dry-run              # show resolved config and paths (writes nothing)
infinigrow tick --probe         # run one tick, zero tokens
infinigrow tick --json          # machine-readable result
infinigrow gardener             # mechanical immune system
infinigrow scan                 # static rules (paths / sync / secrets / BOM …)
infinigrow selftest             # rule positive & negative cases
infinigrow org-check --tick 9   # should the LLM reconciliation pass run now?
```

State lives in `./state/` by default and is **gitignored**. Point it anywhere:

```bash
infinigrow --state-root /tmp/ig tick
IG_STATE_ROOT=/tmp/ig infinigrow tick
```

Fresh clone, empty state, no credentials:

```bash
git clone https://github.com/Chestnuts-Sisyphus/Infinigrow && cd Infinigrow
pip install -e .
infinigrow tick --probe
```

## Architecture

```
CLI ─▶ scheduler ─┐
                   ├─▶ engine ──▶ ledger ──▶ core
     rules ────────┤   tick        store      paths/config/encoding
     garden ───────┘   reconcile   (only write path)   (only machine-specific layer)
                       sprout_*
```

Six layers, dependencies pointing one way, and exactly one module allowed to touch the disk.
Full diagram and the reasoning behind each boundary: [`docs/architecture.md`](docs/architecture.md).

## Mechanism, in one table

| Edge | Direction | Grows when |
|---|---|---|
| 判读 read | W→B | a prediction about that object is later confirmed |
| 行动 act | B→W | the action produces an observable change in reality |
| 原理 principle | B→B | the derived claim holds in a domain never tested before |
| 固化 solidify | W→W | the same input no longer costs cognition (it is automatic) |

Maturity chain: read → act → principle → solidify (4 steps; the 4th is the cap).
Three sprout sources: differences, maturity cap ("what else can this be used for?"),
unused library entries ("why is this not used — does it hold elsewhere?").
Everything else is in [`docs/mechanism.md`](docs/mechanism.md).

## Plugging in an executor

The tick takes an optional executor; without one it runs in purely mechanical mode.

```python
from infinigrow import load_settings, run_tick

def my_executor(prompt: str) -> str:
    # your model / script / human here; see SECURITY.md before wiring anything that runs commands
    return "..."

result = run_tick(settings=load_settings(), llm=my_executor)
print(result.diff_summary, result.new_sprouts)
```

## Guarantees enforced by machines, not by memory

```bash
infinigrow scan      # R1 no absolute paths · R2 prompt↔code sync · R3 no self-sprout clause
                     # R4 state root ignored · R5 no credential literals · R6 no BOM
infinigrow selftest  # every rule has a positive and a negative case
python tools/check_prompt_code_sync.py   # bidirectional prompt↔code check
python tools/privacy_scan.py --root .    # paths / secrets / emails before publishing
```

## Status & limitations

v2.0.0 is the first release of the rewritten line. Known limitations are listed in
[CHANGELOG.md](CHANGELOG.md#known-limitations-v200) — notably: the mechanical tick does no
cognition of its own, the executor interface is a plain callable, and deployment
integration (schedulers, proxying, multi-provider rotation) is deliberately out of scope.

## License

MIT — see [LICENSE](LICENSE).
