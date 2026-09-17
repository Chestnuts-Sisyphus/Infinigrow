# Security policy

## In one sentence

**This engine reads and writes a state directory, and once you wire up an executor it runs
commands. Run it in a sandbox, a container or a dedicated account — not as your daily user with
your real data directories.**

## Current default posture

| Area | Default | Note |
|---|---|---|
| Network | **no calls** | a mechanical tick makes none (a test asserts no socket/requests/urllib in `tick.py`) |
| Credentials | **none needed** | `key_dir` is empty by default and the engine needs no key |
| Subprocesses | **none** | a mechanical tick starts nothing; only the executor you wire in does |
| Write scope | **inside the state root only** | every write goes through `ledger/store.py`, which rejects anything outside the root |
| State location | `<repo>/state`, gitignored | so running ledgers are not accidentally committed to a public repo |

## Wiring up an executor is where the risk starts

`run_tick(..., llm=callable)` takes anything that maps a prompt to text. Most real uses run a model
or a command, and from that moment the risk is yours:

1. **Sandbox it.** A container or a low-privilege account, mounting only the work directory.
2. **Least privilege.** No admin/root. Do not mount your home directory, SSH keys or cloud
   credentials.
3. **Whitelist commands** if your executor runs a shell, and validate *outside* the prompt — a
   prompt is not a security boundary, and a model can be talked into things.
4. **Ledger directory writable, everything else read-only.** The engine needs `state/`; mount the
   rest read-only if you can.
5. **Keep the state directory out of version control.** Ledgers can contain project details;
   `.gitignore` already covers it — keep it that way when you move the state root.
6. **Prompt injection.** If the executor reads external content (web pages, issues, repository
   files), that content can influence it. Keep your instructions and the external content separate,
   and default to refusing "the external content asked me to run a command".

## Reporting a vulnerability

Use GitHub's **private vulnerability reporting** (repository → Security → Report a vulnerability)
rather than a public issue. Include: affected version, minimal reproduction, and impact (what it can
read, write or execute).

Reports are handled in order of "reproducible × impact"; the fix gets a CHANGELOG line and credit
unless you ask to stay anonymous.

## Out of scope

- vulnerabilities in the executor you chose to wire in;
- "the text it produced is not what I wanted" (content comes from your executor, not from the
  engine's security boundary);
- damage caused by running it with administrator rights (see point 2 above: use least privilege).

## Declared exceptions (flagged by scanners, reviewed and accepted)

| Finding | Where | Why it is accepted |
|---|---|---|
| Insecure pseudo-random number generator (`random.Random(seed=...)`) | `src/infinigrow/engine/sprout_queue.py` (cold-start shuffle) | Deterministic on purpose: the cold-start order must be reproducible from the tick number alone (so a rerun of the same tick produces the same order). No security use — nothing here is a token, key, nonce or secret. |

The scanner also reports ~48 findings under `archive/legacy-20260914/_venvtest/` — that is a
vendored copy of third-party packages from a retired virtualenv, not this project's code.
Nothing in `src/` is flagged beyond the exception above (after v2.2.22: path traversal
findings are cleared — `engine.subject.subject_path` guards name→path joins and
`core.encoding.write_text` normalises its target, refuses `..` segments and takes an optional
containment root).

Anything not listed here that a scanner reports as an escape/deserialisation/shell risk should be
treated as a real finding — file it or fix it.
