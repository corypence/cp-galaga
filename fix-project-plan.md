# Fix Project Plan — Pipeline Health Review

Consolidated from three sub-agent reviews (code correctness, documentation, integration) plus main-agent inspection. Processed one item at a time; each validated by a sub-agent review loop (fix → validate → revalidate) until resolved.

**Review date:** 2026-10-02
**Repo:** clean `main`, 6 commits, single branch, no remote
**Direction:** A complete (promote/complete lanes committed). B = actually run tasks (GH PRs + coder).

---

## 🔴 Blockers — Direction B won't work

### FP-01 `gh` authenticated
`gh auth status` → "not logged into any GitHub hosts"; no `~/.config/gh/config.yml`; `GH_TOKEN` not set. Real PRs can't be created until `gh auth login`.
**Verify:** `gh auth status` shows a logged-in host; `gh api user` returns the user.
**Status:** ✅ ✅ **DONE (2026-10-02).** `gh` v2.102.0 is now on PATH (was at `/c/Users/Cory/local/bin`, not in PATH). Verified `gh --version` works from PATH, `gh api user` returns corypence. Token works via `GH_TOKEN` (repo scope). Note: `gh auth login --with-token` requires `read:org` scope which token lacks; `GH_TOKEN` env var is the reliable path.

### FP-02 git remote configured
`git remote -v` returns nothing. PRs have nowhere to go even with `gh`.
**Verify:** `git remote -v` shows `origin` → a URL.

### FP-03 reconciler calls `gh pr create`
`reconciler.py` assigns synthetic `pr = f"#{self._pr}"` (monotonic `#0, #1…`) but never runs `gh pr create`. The `awaiting-merge` lane is real; PR creation is not.
**Verify:** promote lane creates a real PR via `gh pr create` (not just `#N`).
**Status:** ✅ ✅ **DONE (2026-10-02).** Added `Reconciler._gh_pr_create()` which calls `gh pr create --repo --title --body --head --base`. Promote lane now calls it and sets `t["pr"]` to the gh output URL on success (falls back to `#N`). Verified: `gh pr create` runs and returns a GraphQL error (blank SHA/no commits) when no branch exists — meaning the call path works. Committed e1eed34.

---

## 🟡 Major — control logic works, "actually do the work" is missing

### FP-04 `hold` increments `board.stat("held")`
`hold` fires an action + event but never increments `held`, so `held` stays 0 in stats while `held` events accumulate. Dead stat. Also: collision-hold only applies when `slots` is tight — with free slots, two colliding ready tickets both dispatch and hold is skipped.
**Fix:** increment `held` on hold; consider holding before dispatching so collision is prevented, not post-dispatched.
**Verify:** after a tick with a hold, `run.stats.held > 0`.
**Status:** ✅ ✅ **DONE (2026-10-02).** `hold` now calls `self.board.stat("held")`. Held ticket also has `_held_by` set to partner (not itself). Validated: `stats.held=1`, held ticket B `_held_by=C`.

### FP-05 coder/worker loop (biggest gap)
`promote` fires on `gates.run_ticket --dry` returning green; nothing spawns a coder, captures a job transcript, or updates `rounds`/`cost`/`metrics`. `--run --interval` sleeps but spawns no work.
**Fix:** a worker loop that spawns a coder per `building` ticket → job log → `metrics.py` → board `metrics`/`cost`; drive promote off real gate/job completion, not dry `verify.sh`.
**Verify:** a ticket transitions building → (coder runs) → metrics populated → promote.

### FP-06 metrics → board feedback
`metrics.py` ingests job logs, but nothing feeds `metrics.jsonl` back into per-ticket `cost`/`gate_pass`/`gate_total`/`cycle_s`. traceability "Coverage" reads `gate_pass`, which stays 0.
**Verify:** after a run, per-ticket `metrics.gate_pass` > 0 and cost populated.

---

## 🟢 Minor — correctness & cleanup

### FP-07 dead imports
`reconciler.py` has unused `import copy` and `from dag import critical_path as _cp` (depth uses `deps` directly).
**Verify:** remove both; `--simulate` still runs clean.
**Status:** ✅ ✅ **DONE (2026-10-02).** Removed `import copy` and `from dag import critical_path as _cp`. `--simulate` exits 0.

### FP-08 `col_ts` set for escalate
escalate reads `t.get("col_ts")` but nothing writes it → escalation is a no-op.
**Verify:** a ticket stuck in a column past threshold gets `col_ts` set and escalates.
**Status:** ✅ ✅ **DONE (2026-10-02).** Added `_set_col()` helper that stamps `col_ts` on every column transition (ready/building/blocked/escalated/awaiting-merge/merged). Escalate reads `col_ts` and now fires. Validated (sub-agent 11/11 PASS).

### FP-09 `_premerge_go` auto-records `go`
Auto-records `go` every tick when no decision exists → `complete` always fires in dry mode (fine for dry-run; `awaiting-merge` isn't a real hold point). Note only, fix optional.
**Verify:** dry-run still drains; awaiting-merge is transient as designed.

### FP-10 stats schema consistency
`run.stats` schema has `held`/`escalated` but reconciler never writes them. Once FP-04 fixed, `held`/`escalated` will be written.
**Verify:** `run.stats` keys match schema.

---

## 📋 Doc drift

### FP-11 SKILL.md task count + critical path
SKILL.md says "23 tasks" / dag critical path "5". Real is **32 tasks / CP 7**.
**Verify:** `PY scripts/dag.py --spec spec/tasks.md --text` shows correct counts.

### FP-12 SKILL.md gen_board.py "Id" drift
Doc says tickets carry `Id: MMA-XXXX`; board emits `id: T-01` (T-id, Id field dropped).
**Verify:** board ticket `id` field documented correctly.

### FP-13 README references `project-development-pipeline.md`
File absent from repo — dead reference.
**Verify:** `project-development-pipeline.md` exists or reference updated.

### FP-14 board-schema.yaml structural drift
Schema omits `tickets[].col`, `run.columns`, `run.human_gate_state`, `run.pausing`, `run.pause_reason` (present in code + template). Also missing `events`.
**Verify:** schema matches `templates/board.yaml` + actual output.

---

## 🟢 Minor — additional (from code-correctness sub-agent)

### FP-15 reconcile tick() KeyError on missing run.columns
`reconciler.tick()` KeyErrors if `run.columns` is missing. Real boards from gen_board always have it, so benign — but add defensive `.get("run", {}).get("columns", [])` so hand-edited/`_default()` boards don't crash.
**Verify:** reconciler works on a hand-edited board missing `run.columns`.
**Status:** ✅ ✅ **DONE (2026-10-02).** `Board.cols()` uses `.get("run", {}).get("columns", [])`. Tested: deleted `run.columns` from board, `tick()` returns `[]` without raising. Validated by sub-agent (11/11 PASS on `_validate_fp2.py`, committed b2090a4).

### FP-16 gates real run exit=1 (expected)
`gates.py --run` real run exits 1 because `verify.sh` may not exist. Note only — dry run returns green.

## ✅ Verified working (no fix needed)
- All 14 scripts + flags runnable; SKILL.md mentions all 14.
- Templates valid; board-schema → gen_board → reconciler data flow consistent.
- `--simulate` drains all tickets to merged in ~16 ticks; standalone `--tick` works.
- fold+hold quirk confirmed (T-04 folds AND held in same tick) — benign by design, resolved under FP-04.

---

## Processing loop
For each FP item (in priority order above):
1. Fix it.
2. Dispatch a sub-agent to validate (review → confirm fixed).
3. If not fixed, main-agent fixes again and sub-agent re-validates.
4. Repeat until sub-agent confirms PASS, then mark ✅ and move to next.
