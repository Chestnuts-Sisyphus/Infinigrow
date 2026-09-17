<!-- Pull request template: not "what did you do", but "what is the evidence". -->
## What changed

(one sentence)

## Why

(the constraint or the incident; if the mechanism changed, point at the section of
`docs/mechanism.md`)

## Evidence

- [ ] `python -m pytest -q` passes
- [ ] `python -m infinigrow scan` all PASS
- [ ] `python -m infinigrow selftest` green
- [ ] `python tools/check_prompt_code_sync.py` in sync
- [ ] `python tools/privacy_scan.py --root .` zero hits
- [ ] if the mechanism changed: `docs/mechanism.md` + code + `prompts/` changed **together**
- [ ] if a mechanism was retired: a row was added to `docs/superseded.md`

## Known limitations / not covered

(state them honestly; write "none" if there are none)
