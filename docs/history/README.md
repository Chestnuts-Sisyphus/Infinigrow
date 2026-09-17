# History (not part of the public design)

v2 is a clean-break rewrite and deliberately ships **without** v1's historical sediment:

- v1's per-change commentary, embedded fixtures, per-sprout archaeology and discussion logs do
  not enter the v2 repository. The reason is in [`versioning.md`](versioning.md): stacking new
  rules on old ones is exactly what made v1 spin in place.
- When you need to know *why* a design is the way it is, the answer is in the "why" sections of
  [`mechanism.md`](mechanism.md) — the distilled reason, not the conversation that produced it.
- Retired mechanisms are not recovered by archaeology; they are in the
  [superseded table](superseded.md): old mechanism → replacement → residue, one row each.

## When to write something here

Exactly one case: **a decision that would be mis-changed by someone who did not know why the
alternative was rejected.** Then write a short file in this shape:

```
# <decision> (<date>)
- The options at the time:
- Which was chosen, and why:
- What would make it worth reconsidering:
```

Anything else belongs in version control (`git log`). Ledgers record facts, not feelings.

Chinese original: [`zh/history/README.md`](zh/history/README.md).
