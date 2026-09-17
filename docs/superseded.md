# Superseded mechanisms

> A retired mechanism may neither **disappear quietly** nor **stay alive quietly**.
> Every retirement is registered here: old mechanism → replacement → residue → status.
> Machine check: `infinigrow scan` (rule **R3** watches for the old clause returning to the
> prompts).

"Residue" means traces still present in the code or prompts of the *current* generation; v1's
own leftovers are out of scope (v1 is sealed — see [`versioning.md`](versioning.md)).

| # | Retired | Why | Replaced by | Residue | Status |
|---|---|---|---|---|---|
| S1 | "Branch on completion": every tick must register at least one new sprout candidate | Forcing a sprout per tick makes the laziest possible output a re-statement of what was just done; measured: 186 of 221 queued sprouts were one family with verbatim-identical titles, and the engine span | A sprout is the product of a predicted difference ([`mechanism.md`](mechanism.md) §4); the acting session cannot create sprouts | none (R3 fails the build if the clause appears) | **cleared** |
| S2 | Apex trimming (cut the growth direction at the "top") | Not mechanically testable; orthogonal to "differences create sprouts" | Queue discipline: lead limit + frozen zone + cap-as-new-entry | none | **cleared** |
| S3 | Three-tier scoring / blind grading of output | Self-assessed dashboard: no external judge, and the score is unrelated to growth | Outcomes ledger (reality decides redeem/contradict, fully mechanical) | none | **cleared** |
| S4 | Early "four mechanisms / four sets / node tests" design | Overlapped the current edge + maturity chain and introduced conflicting vocabulary | [`mechanism.md`](mechanism.md) as the single design document | none | **cleared** |
| S5 | Dual time sources (model-written timestamps as test input) | A model can write any timestamp; tests must be mechanical | Mechanical timestamps in the heartbeat file | none (gardener and liveness read `tick_status.json`) | **cleared** |
| S6 | Self-assessed "capability cards / principle cards" ledger | Duplicated edges; more cards does not mean more growth | Maturity chain ledger (which step an object reached) | none | **cleared** |
| S7 | State root coupled to a host project | Code and state in different projects: moving the code leaves the state behind, and publishing leaks the directory layout | Parameterised state root in `core/paths.py`, defaulting to `<repo>/state` | none (R1: no absolute paths in source) | **cleared** |
| S8 | One 900 KB source file with embedded fixtures | Reading the whole file to change one line; tests and code interleaved so breakage went unnoticed | Six-layer package + `tests/` | none | **cleared** |

## Retiring something new

1. **Add a row** here (do not delete old rows — the retirement history is a ledger too).
2. Remove the mechanism from code and prompts (or mark it as history, never in a mechanism slot).
3. Run `infinigrow scan` and `pytest`; green means the retirement is complete.
4. If the retirement changes a premise, update [`mechanism.md`](mechanism.md) and the prompts in
   the same change.

Chinese original: [`zh/superseded.md`](zh/superseded.md).
