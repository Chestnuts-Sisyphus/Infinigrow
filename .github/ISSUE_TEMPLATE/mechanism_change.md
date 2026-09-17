<!-- For a mechanism change, read the four steps under "Changing the mechanism" in CONTRIBUTING.md first. -->
---
name: Mechanism change proposal
about: Change a test (edge / maturity chain / difference kind / sprout source / ledger)
labels: ["mechanism"]
---

**Which test changes**
(section number in `docs/mechanism.md`)

**Why the current test is not enough**
(describe the **specific state** that triggers it. Frequency-style descriptions such as "this
keeps happening lately" cannot be checked mechanically and are not accepted here as a reason.)

**What it becomes**
(what checkable state replaces it? how does a ledger show it holds or fails?)

**Impact**
- [ ] prompts must change with it
- [ ] ledger format changes (what happens to existing ledgers?)
- [ ] existing tests must change
- [ ] a retirement entry is needed (a row in `docs/superseded.md`)
