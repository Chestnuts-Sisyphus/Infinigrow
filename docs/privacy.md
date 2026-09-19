# Privacy and release hygiene

> The public version of the pre-publish checklist: the rules, not this machine's specific
> deny-list. Machine-specific paths and identity terms live outside the repository, are passed
> in with `--deny`, and are **never committed**.

## Three hard lines

1. **No absolute paths** — not in source, prompts, docs or scripts: no drive letters, no home
   directories. The state root, prompt directory and credential directory are all configuration
   (`IG_*` env vars or the config file). Machine checks: rule **R1** and the `abs-*-path`
   patterns in `tools/privacy_scan.py`.
2. **No credentials** — keys, tokens and private keys never appear as literals. Credentials are
   read from the environment or an external directory, and the engine **needs none by default**
   (an empty repo runs). Machine checks: rule **R5** and the scanner's key-shape patterns.
3. **No personal or project identifiers** — usernames, real names, other projects' names, private
   infrastructure (proxy ports, VPN directories, key directories) stay out. Machine check: the
   scanner's **project layer** (`--deny <file>`, and that file is gitignored).

## Two scan layers

| Layer | Content | In the repo? | When it runs |
|---|---|---|---|
| generic | absolute paths, credential shapes, emails | **yes** (the rules are generic) | every CI run |
| project | this machine's roots, identity terms, other project names, private infra | **no** (`--deny` file, gitignored) | before publishing, locally |

The scanner's rules are **shape expressions, not a banned-word list** — putting the banned words
themselves into a public repository is exactly what the rule exists to prevent.

**The scan scope is the publish boundary**: top-level names listed in `.gitignore` never reach the
public repository, so they are not scanned (the same semantics as static rule **R1**); everything
else is, including untracked files that a commit would carry in. This alignment closes a
recurring fault: local-only directories (handover notes, machine config) used to depend on a
hard-coded skip list inside the tool, so every new one needed a code edit — and forgetting one
pitted the local scan against the publish gate. The ignore list is not a free pass: the rule has
both a positive and a negative case in `tests/test_privacy.py`.

## Before publishing

```bash
python tools/privacy_scan.py --root .                            # generic layer: zero hits
python tools/privacy_scan.py --root . --deny privacy-deny.txt     # project layer: zero hits
python -m infinigrow scan                                         # all ten rules PASS
python -m pytest -q                                               # includes cold-start and privacy tests
git status --porcelain --ignored                                  # state/, archive/, secrets ignored
```

The project layer cannot be exercised by CI on its own — the file it reads is deliberately not in
the repository, so the repo-wide test for it used to **skip on every CI run**, which left the whole
layer unproven (a broken deny loader would have looked green). A committed synthetic deny list
(`tests/data/privacy-deny-sample.txt`, made of invented terms only) plus a sentinel that carries the
payload it must catch (`tests/data/privacy-sentinel/leaky-example.md`) let
`tests/test_privacy_deny_layer.py` prove **both** directions on CI: with a deny list the sentinel
must be reported (exit code 1), and once the payload is removed it must not (exit code 0). The
sentinel is also checked against the generic layer, so adding it cannot dirty the repository scan.
None of this publishes anyone's real list.

**A cold-start check that fails blocks publishing**: run one tick in a temporary directory with an
empty state root (zero tokens, zero credentials) and confirm no absolute path appears in any
artifact. `tests/test_coldstart.py` guards that, and CI runs it on every push.

Chinese original: [`zh/privacy.md`](zh/privacy.md).
