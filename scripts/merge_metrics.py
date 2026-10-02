#!/usr/bin/env python3
"""
merge_metrics.py — FP-06: feed `run/metrics.jsonl` back into `run/board.yaml`.

metrics.py ingests per-ticket cost/latency signals from job logs and writes `run/metrics.jsonl`
(one JSON line per ticket: ticket_id, verdict, wall_s, start_ts, end_ts, rounds). Nothing fed those
values back into the board, so traceability's "Coverage" column — which reads `ticket.metrics.gate_pass`
— always stayed 0, and per-ticket cost/cycle were never recorded.

This module reads the metrics records and, for each one, finds the matching board ticket and sets:

  * ticket.metrics.gate_pass   — 1 when the ticket passed, else 0 (derived from record.gate_pass,
                                 or fall back to the record verdict: 'pass' -> 1, 'fail' -> 0)
  * ticket.metrics.gate_total  — 1 if a gate verdict is known (pass/fail), else 0
  * ticket.metrics.cycle_s     — from wall_s if present & > 0, else end_ts - start_ts (seconds)
  * ticket.cost.<fields>       — merge any cost fields present in the record (tokens/usd/wall_s)

Matching is intentionally loose: a record's `ticket_id` is compared against the ticket's `id`, any
`Id` manifest field, `branch`, `worktree`, and `ticket_id`. A record is applied once per unique
`ticket_id` so re-running is idempotent (values are set, not accumulated — nothing double-counts).
The board's existing structure (columns, events, stats, rounds, ...) is preserved; only the cost and
metrics sub-dicts are touched.

Usage:
    python merge_metrics.py --board run/board.yaml --metrics run/metrics.jsonl
    python merge_metrics.py --board run/board.yaml   # reads run/metrics.jsonl by default

Exit codes: 0 ok, 2 config error (missing files / no PyYAML).
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path


def load_board(path: Path) -> dict:
    try:
        import yaml  # type: ignore
    except ImportError:
        print("PyYAML required for merge; install with `pip install pyyaml`")
        raise SystemExit(2)
    if not path.exists():
        print(f"board not found: {path}")
        raise SystemExit(2)
    return yaml.safe_load(path.read_text()) or {}


def load_metrics(path: Path) -> list[dict]:
    if not path.exists():
        print(f"metrics file not found: {path}")
        raise SystemExit(2)
    records = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as e:
            print(f"skipping malformed metrics line: {e}")
    return records


def _match_keys(ticket: dict) -> set[str]:
    """All identifiers a metrics record's `ticket_id` might equal for this ticket."""
    keys = set()

    def add(v):
        if v:
            keys.add(str(v))

    add(ticket.get("id"))
    add(ticket.get("Id"))          # manifest id field when present
    add(ticket.get("branch"))
    add(ticket.get("worktree"))
    # tickets[].ticket_id if the board ever stores that form
    add(ticket.get("ticket_id"))
    return keys


def _verdict_to_gate(rec: dict) -> int:
    """Map a record to a pass (1) / fail (0) gate signal. 0 when unknown."""
    if "gate_pass" in rec and isinstance(rec.get("gate_pass"), (int, float)):
        return 1 if rec["gate_pass"] else 0
    verdict = str(rec.get("verdict", "")).lower()
    if verdict == "pass":
        return 1
    if verdict == "fail":
        return 0
    return 0


def _cycle_s(rec: dict) -> int:
    wall = rec.get("wall_s")
    if isinstance(wall, (int, float)) and wall > 0:
        return int(wall)
    start, end = rec.get("start_ts"), rec.get("end_ts")
    if start and end:
        try:
            from datetime import datetime
            fmt = "%Y-%m-%dT%H:%M:%SZ"
            d0 = datetime.strptime(start, fmt)
            d1 = datetime.strptime(end, fmt)
            return max(0, int((d1 - d0).total_seconds()))
        except (ValueError, TypeError):
            pass
    return 0


def merge(board: dict, records: list[dict]) -> dict:
    tickets = board.get("tickets", [])
    applied: dict[str, int] = {}     # ticket_id -> gate_pass, dedupes re-runs
    updated = 0
    for rec in records:
        tid = str(rec.get("ticket_id", ""))
        if not tid:
            continue
        if tid in applied:
            continue  # first application wins → idempotent
        for t in tickets:
            keys = _match_keys(t)
            # exact match on any id, or bare prefix match (e.g. MMA-6048 vs MMA-6048-a)
            if tid in keys or tid == t.get("id") or tid.startswith(t.get("id", "")) or \
               t.get("id", "").startswith(tid):
                metrics = t.setdefault("metrics", {})
                gate = _verdict_to_gate(rec)
                metrics["gate_pass"] = gate
                metrics["gate_total"] = 1 if gate else 0
                metrics["cycle_s"] = _cycle_s(rec)
                # cost fields — merge only those present in the record, preserve existing
                if isinstance(rec.get("cost"), dict):
                    cost = t.setdefault("cost", {})
                    for k, v in rec["cost"].items():
                        cost[k] = v
                applied[tid] = gate
                updated += 1
                break
    return {"updated": updated, "applied": applied}


def main() -> int:
    ap = argparse.ArgumentParser(description="Feed metrics.jsonl into board.yaml per-ticket")
    ap.add_argument("--board", default="run/board.yaml")
    ap.add_argument("--metrics", default="run/metrics.jsonl")
    args = ap.parse_args()

    board = load_board(Path(args.board))
    records = load_metrics(Path(args.metrics))
    result = merge(board, records)

    Path(args.board).write_text(yaml.safe_dump(board, sort_keys=False))
    print(f"merged {result['updated']} ticket(s) from {args.metrics} -> {args.board}")
    for tid, gate in result["applied"].items():
        print(f"  {tid}: gate_pass={gate}")
    return 0


if __name__ == "__main__":
    import yaml  # used by main() once validated available
    raise SystemExit(main())
