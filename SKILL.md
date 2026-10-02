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
- PyYAML for board YAML scripts (`pip install pyyaml`); default python is 3.14, yaml lives in the
  Hermes venv at `C:/Users/Cory/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe`.

---

## Phase 0 — Quick wins (observability + gates)

### 0.1 Dependency DAG
```bash
python scripts/dag.py --tasks spec/tasks.md --mermaid graph/dag.mmd --text graph/dag.txt
```
Parses task headers (`### T-01`) + inline `Depends` fields → dependency graph + critical path
(Mermaid + text). Expect 23 tasks, critical path of 5 nodes.

### 0.2 Cost + latency metrics
```bash
python scripts/metrics.py --logs orchestrator/job-logs --out run/metrics.jsonl
```
Ingests job logs into `run/metrics.jsonl` (verdict, wall_s, rounds). Expects 31 records.

### 0.3 Secrets + dependency audit gate
```bash
python scripts/audit.py --source . --json
```
Scans for secrets and audits deps. Exits 0/1/2 (2 = config error).

### 0.4 Retry with backoff + quarantine
```bash
python scripts/retry.py --call "python scripts/audit.py --source ." --max-retries 3
python scripts/retry.py --quarantine add --tier unit --test alpha-suite
```
Exponential backoff + jitter; flaky tests can be quarantined so they don't block the run.

---

## Phase 1 — Core pipeline

### 1.1 Generate the board
```bash
python scripts/gen_board.py --spec spec/tasks.md --out run/board.yaml
```
Parses `spec/tasks.md` → `run/board.yaml` with the extended schema (§5.3 of the design doc).
Handles backtick-delimited `Covers` lists (`#22`, `N1`, `N2`) and inline `Depends` fields.

### 1.2 The reconciler (dispatch engine)
```bash
python reconciler.py --tick                 # one decision pass
python reconciler.py --run --interval 300    # keep running on interval
python reconciler.py --simulate              # dry-run the whole run
```
Reads `run/board.yaml` + `spec/tasks.md`; every tick decides: dispatch (critical-path first), fold
(deps merged), collision hold, escalate, complete. State-driven, idempotent, append-only events.

### 1.3 Gates ladder
```bash
python scripts/gates.py --list-ladder
python scripts/gates.py --run --ticket T-01 --module core:ui --dry
python scripts/gates.py --quarantine add --tier perf --test slow-suite
```
unit → integration → contract → security → coverage → perf → global. Fail fast at the cheapest
tier; flaky tiers retry with backoff.

### 1.4 Auto rebase + merge driver
```bash
python scripts/rebase.py --configure '*.xml' --driver union --out gates/rebase.conf
python scripts/rebase.py --ticket T-01 --base main --branch T-01 --dry
```
Kills manual base-resolution churn. Merge-driver policy per file glob.

---

## Phase 2 — First-class

### 2.1 Notifications + escalation
```bash
python scripts/notify.py --emit --ticket T-01 --sev page --msg "stuck in reviewing"
python scripts/notify.py --config --channel slack --webhook URL
python scripts/notify.py --stalled --threshold 1800
```
Severity-scoped: info / warn / error / page. Appends to `run/notifications.log`.

### 2.2 Human Go/NO-GO gates
```bash
python scripts/humangate.py --list
python scripts/humangate.py --gate pre-merge --dec go --owner cory
python scripts/humangate.py --status --gate spec
```
Three gates: spec, pre-merge, release. Decisions recorded to `run/humangate.ndjson`.

### 2.3 Cost ceiling + auto-pause
```bash
python scripts/ceiling.py --check --board run/board.yaml
python scripts/ceiling.py --pause --reason "cost ceiling hit"
python scripts/ceiling.py --resume
```
Enforces run-level $ / wall-time ceilings; pages on stalls > threshold.

### 2.4 Traceability matrix
```bash
python scripts/traceability.py --board run/board.yaml --out run/traceability.md
python scripts/traceability.py --board run/board.yaml --json
python scripts/traceability.py --board run/board.yaml --csv
```
Requirement → task → ticket → PR → coverage matrix.

### 2.5 Metrics dashboard
```bash
python scripts/dashboard.py --board run/board.yaml --metrics run/metrics.jsonl
```
Self-contained HTML dashboard: burn-down, cost, WIP/column, bottleneck, flake rate. Output at
`dashboard/index.html`.

---

## Phase 3 — Polish

```bash
python scripts/phase3.py --spec-version --spec spec/          # snapshot spec/
python scripts/phase3.py --determinism                        # pins + cache key
python scripts/phase3.py --promote --canary 4 --dry           # controlled promotion
python scripts/phase3.py --incidents --seed                   # incident taxonomy
```

---

## Directory layout
```
project-pipeline/
├── spec/          R0 contract (requirements.md, design.md, tasks.md)
├── run/           board.yaml, events.ndjson, metrics.jsonl, tickets/, incidents.ndjson
├── scripts/       dag, metrics, audit, retry, gen_board, reconciler, gates, rebase,
│                  notify, humangate, ceiling, traceability, dashboard, phase3
├── references/    board-schema.yaml
├── templates/     ticket.yaml, plan.md, board.yaml
├── graph/         dag.mmd, dag.txt
├── gates/         rebase.conf
├── dashboard/     index.html
└── worktrees/     parallel git worktrees
```

## Quick reference
| Script | Purpose | Phase |
|---|---|---|
| `dag.py` | tasks.md → DAG + critical path | 0 |
| `metrics.py` | job logs → metrics.jsonl | 0 |
| `audit.py` | secrets + dependency gate | 0 |
| `retry.py` | retry with backoff + quarantine | 0 |
| `gen_board.py` | tasks.md → board.yaml | 1 |
| `reconciler.py` | dispatch engine | 1 |
| `gates.py` | gates ladder | 1 |
| `rebase.py` | auto rebase + merge driver | 1 |
| `notify.py` | notifications + escalation | 2 |
| `humangate.py` | human Go/NO-GO gates | 2 |
| `ceiling.py` | cost ceiling + auto-pause | 2 |
| `traceability.py` | requirement → PR matrix | 2 |
| `dashboard.py` | metrics HTML dashboard | 2 |
| `phase3.py` | versioning, determinism, promotion | 3 |

## Procedure
1. `dag.py` — confirm topo order is OK, note critical path.
2. `gen_board.py` — build board.yaml from spec.
3. `reconciler.py --tick` — see what dispatches.
4. `gates.py` — run the ladder; quarantine flaky tiers.
5. `notify.py` — page on stalls/ceiling hits.
6. `humangate.py` — record decisions at spec/pre-merge/release gates.
7. `traceability.py` — generate the audit matrix.
8. `dashboard.py` — render the live view.
9. `phase3.py` — snapshot, lock determinism, promote, log incidents.

## Pitfalls
- `dag.py` parses `### T-01` headers with inline `Depends` fields.
- `gen_board.py` handles backtick-delimited `Covers` lists and `—` (em dash) for no-deps.
- `metrics.py` uses wall-clock from timestamps; logs without timestamps get wall_s=0.
- `audit.py` skips node_modules/.git/build — widen SKIP_DIRS if your layout differs.
- `retry.py` uses full jitter; first retry can be faster than the base delay.
- `board.yaml` lacks `stats`/`events` if hand-edited — `gen_board.py` adds them.

## Verification
Each script exits 0 and prints expected output; run `--dry` where applicable. The `--demo` flag on
retry.py proves backoff.
