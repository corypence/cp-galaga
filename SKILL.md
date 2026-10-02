# Project Development Pipeline (Skill)

## Overview
A reusable multi-agent development pipeline, adapted from the stake-map orchestrator run, made
first-class. It drives a Hermes kanban board through four phases: Phase 0 (observability gates),
Phase 1 (board + reconciler + gates), Phase 2 (notifications + human gates + traceability), and
Phase 3 (polish + determinism).

## When to Use
- A user wants to run a multi-agent dev run (spec → decompose → plan → code → review → PR → merge).
- A user wants per-ticket cost/latency, dependency DAGs, flaky-test retries, and audit gates.

## Prerequisites
- `gh` CLI on PATH, authenticated (token in `~/.config/gh/hosts.yml`).
- A git repo with `spec/tasks.md` (topologically sorted work breakdown).

## How to Run — Phase 0 quick wins
```bash
python scripts/dag.py --tasks spec/tasks.md --mermaid graph/dag.mmd --text graph/dag.txt
python scripts/metrics.py --logs orchestrator/job-logs --out run/metrics.jsonl
python scripts/audit.py --source . --json
python scripts/retry.py --call "python scripts/audit.py --source ." --max-retries 3
```

## Quick Reference
- `dag.py` — parse tasks.md → dependency graph + critical path. Outputs Mermaid + text.
- `metrics.py` — ingest job logs → run/metrics.jsonl (verdict, wall_s, rounds).
- `audit.py` — secrets scan + dependency audit. Exits 0/1.
- `retry.py` — retry any gate command with exponential backoff + jitter.

## Procedure
1. `dag.py` — confirm topological order is OK and note the critical path.
2. `metrics.py` — write metrics.jsonl; check verdict counts.
3. `audit.py` — run from repo root; fix any secrets before dispatch.
4. `retry.py` — wrap gate runs; quarantine known-flaky tiers in run/quarantine.json.

## Pitfalls
- `dag.py` parses `deps:`/`depends:` clauses; if tasks list deps inline (not on a `deps:` line),
  adjust the regex or add a frontmatter `deps:` block to tasks.md.
- `metrics.py` uses wall-clock from timestamps in logs; logs without timestamps get wall_s=0.
- `audit.py` skips node_modules/.git/build — widen SKIP_DIRS if your layout differs.
- `retry.py` uses full jitter; the first retry can be faster than the base delay.

## Verification
- Each script exits 0 and prints expected output; run `--demo` on retry.py to prove backoff.
