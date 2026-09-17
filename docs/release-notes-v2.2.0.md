# Infinigrow v2.2.0 — calibration from a live run

**The premises are unchanged** (four edges, four-step maturity chain, four difference kinds, three
sprout sources). This release closes the calibration gaps that only a real run exposes: each item
below corresponds to one observed tick where the accounting disagreed with reality, or where a
class of sprout could never be resolved.

## Fixed, each from a live observation

- **The engine no longer reconciles its own state files.** It observed six of its own ledgers while
  predicting three of them, producing three phantom "byte size" sprouts per tick that no executor
  could ever act on. Engine health is the gardener's job.
- **Observation and prediction are symmetric per object and dimension.** Predicting a file's
  existence without observing it produced a "not executed" difference on the very first tick.
- **Changes the action itself caused are recorded but never spawned.** Creating a file changed the
  file count, which came back as a sprout telling the executor to deal with the result of its own
  action (four consecutive ticks of refusals). Such rows are tagged `act_caused`.
- **A sprout carries the expectation it came from.** Otherwise the most frustrating case appears:
  the executor did exactly what was asked, and the outcome was recorded as contradicted because the
  acting tick's prediction list did not mention it.
- **Unreadable dimensions are marked, not counted as failures.** The "application surface" of a
  capped object cannot be read mechanically, so those outcome rows carry `verifiable=false`, are
  excluded from the redemption denominator, and are listed separately.
- **The maturity chain advances at most +1 per object per tick** (one object with several confirmed
  dimensions used to jump two steps).
- **The org session gained a proposer role and a machine-checked object-name gate.** It used to
  only reconcile; the subject sat still for eight ticks while its own declaration said what it
  should grow. Its input now includes subject content (a bounded excerpt) and the accountable
  object list, and object names are validated.
- **Three-state reporting for the executor**: not wired / wired but nothing to do / actually ran.
  Collapsing these into "mechanical tick, zero tokens" was dishonest.
- **A heartbeat that cannot be read no longer silently resets the tick number to 1** (which
  overwrote reports); the number is recovered from the ledgers, with a visible note.

## Engineering

- Public docs rewritten for a cold reader, with the incident behind each rule.
- Defect registry (`docs/superseded.md`) so retired mechanisms are neither quietly gone nor quietly
  alive.

**Full changes**: [`CHANGELOG.md`](../CHANGELOG.md).
