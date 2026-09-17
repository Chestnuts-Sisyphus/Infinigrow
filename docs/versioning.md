# Versioning

## The two generations

| Generation | Codename | Status | What it is |
|---|---|---|---|
| v1 | `Cultivar` | **sealed** (no longer developed) | one long-lived runtime: a single monolith source file, embedded fixtures, its state root inside a host directory, layers of retired mechanism terms |
| v2 | `Infinigrow` | **current** | a rewrite that keeps only the mechanism: explicit tests, movable state, zero hard-coded paths |

**v2 is not an upgrade of v1; it is a clean break**, and that is deliberate.

v1's problem was not a handful of bugs: the *same rule was written in two places and the two
evolved apart*. The prompt still carried the old clause "each tick must branch and create a new
sprout", while the design and the code said "a sprout is the product of a predicted difference".
With both rules in force, the acting session manufactured one re-statement sprout per tick and
the queue filled with near-identical work: 186 of 221 queued sprouts were the same family, with
verbatim-identical titles, and the engine span in place. Patching a stack like that means every
patch first fights the residue.

So v2 was built by **rewriting from the mechanism**, and by turning "do not accumulate layers
again" into machine checks (`infinigrow scan`; rule R3 specifically watches for the old clause
coming back).

## Version numbers

- **Major** (`x.0.0`): the test layer changes — semantics of edges, maturity chain, difference
  kinds, sprout sources or ledger formats. That is a change of premises: `docs/mechanism.md`,
  the code and the prompts change together, and the sync check rejects a one-sided edit.
- **Minor** (`2.x.0`): new capability, unchanged tests (a new rule, a new accounting view).
- **Patch** (`2.0.x`): fixes, documentation, tests.

v2 starts at `2.0.0`; there are no `1.x` releases after v1 was sealed. The single source of the
version is `__version__` in `src/infinigrow/__init__.py` together with `version` in
`pyproject.toml`; a mismatch fails `tests/test_version.py`.

## Why the name

`Infinigrow` = infini + grow: **growth itself is the infinite thing**, not "growing in infinite
space". The older codename `Cultivar` is kept here as a historical label.

Chinese original: [`zh/versioning.md`](zh/versioning.md).
