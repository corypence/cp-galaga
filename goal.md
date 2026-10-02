# GOAL — Fix Project Pipeline Review Items

Process every item in `fix-project-plan.md` until all are resolved. For each item: main agent fixes it, dispatches a sub-agent to validate (review + confirm fixed), if not fixed the main agent fixes again and the sub-agent re-validates, repeating until PASS. Then mark ✅ and move to the next item.

**Source of truth:** `fix-project-plan.md` (FP-01 → FP-16).

**Validation loop contract for sub-agents:**
- Read the item's fix, run the `Verify` check(s) against real scripts/CLI.
- Python w/ yaml: `/c/Users/Cory/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe` (call `PY`).
- Run from `/c/Users/Cory/project-pipeline`.
- Report PASS/FAIL with evidence. Do NOT fix — only validate.
- If FAIL, give the main agent enough detail to re-fix.

**Order:** FP-01 → FP-16 (blockers first, then major, then minor/doc).

**Done:** each item gets ✅ + a one-line validation note in `fix-project-plan.md` as it clears.
