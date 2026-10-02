# Project Development Pipeline

A reusable multi-agent development pipeline, adapted from a stake-map orchestrator run, made
**first-class**. It drives a kanban board through four phases and turns an Obsidian-only,
unobservable run into a machine-readable, cost/latency-observable, auditable pipeline.

Full design (review → best aspects → gaps → design → roadmap) lives in
`project-development-pipeline.md` (the source document).

## What it does

Spec → decompose → plan → code → review → gates → PR → human review → merge → release.
A **reconciler** dispatches tickets into parallel git worktrees (critical-path first, collision
holds), a **gates ladder** fails fast at the cheapest tier, and everything is mirrored to a
machine-readable board with cost/latency observability.

## Layout

```
spec/          R0 contract (requirements, design, tasks.md — topologically sorted)
run/           board.yaml (single source of truth), metrics.jsonl, incidents.ndjson, tickets/
scripts/       the engine (dag, metrics, audit, retry, gen_board, reconciler, gates, rebase,
               notify, humangate, ceiling, traceability, dashboard, phase3)
references/    board-schema.yaml
templates/     ticket.yaml, plan.md, board.yaml
graph/         dependency DAG (Mermaid + text)
gates/         rebase driver config
dashboard/     live metrics HTML widget
```

## Run it

```bash
# Phase 0 — observability
python scripts/dag.py --tasks spec/tasks.md --mermaid graph/dag.mmd --text graph/dag.txt
python scripts/metrics.py --logs orchestrator/job-logs --out run/metrics.jsonl
python scripts/audit.py --source .
python scripts/retry.py --demo

# Phase 1 — core
python scripts/gen_board.py --spec spec/tasks.md --out run/board.yaml
python scripts/reconciler.py --tick
python scripts/gates.py --run --ticket T-01 --module core:ui --dry
python scripts/rebase.py --configure '*.xml' --driver union --out gates/rebase.conf

# Phase 2 — first-class
python scripts/notify.py --emit --ticket T-01 --sev page --msg "stuck"
python scripts/humangate.py --gate pre-merge --dec go --owner cory
python scripts/ceiling.py --check --board run/board.yaml
python scripts/traceability.py --board run/board.yaml --out run/traceability.md
python scripts/dashboard.py --board run/board.yaml --metrics run/metrics.jsonl

# Phase 3 — polish
python scripts/phase3.py --determinism
python scripts/phase3.py --promote --canary 4 --dry
python scripts/phase3.py --incidents --seed
```

## Validation loop

Each phase was built then validated by an isolated sub-agent that ran the scripts against real
data (23-task `spec/tasks.md`, 31-record job logs). Bugs found were fixed and re-reviewed before
moving to the next phase.
