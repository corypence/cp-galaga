#!/usr/bin/env python3
"""
worker.py — FP-05: the coder/worker loop.

For every ticket in the `building` column of run/board.yaml, run a coder step and append a
job-log line to run/joblogs/<id>.jsonl. The reconciler's promote lane can then drive promotion
off the real job transcript (verdict == green) instead of a dry gate ladder.

The coder is a stub: it reads the ticket's module + round budget and synthesises a plausible
job — round counts, a verdict (green when every code+test round finished), a cost derived from
the ticket size, and a wall-clock cycle. Swap coder_step() for a real coder (subprocess / agent
call) and it keeps the same job-log contract:

    {
      "ticket_id": "T-01", "module": "core:ui",
      "start_ts": "2026-...Z", "end_ts": "2026-...Z",
      "verdict": "green", "gate_pass": true,
      "cost_usd": 1.5, "cycle_s": 540,
      "rounds": {"code": {"done": 3, "budget": 3},
                 "test": {"done": 3, "budget": 3},
                 "response": {"done": 5, "budget": 5}}
    }

Usage:
    python worker.py --list                 # list building tickets, run none
    python worker.py                        # run the coder for every building ticket
    python worker.py --max-build 2          # cap how many building tickets one pass serves
    python worker.py --dry                  # print what it would do; write nothing
"""
from __future__ import annotations
import argparse
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

try:
    import yaml
except ImportError:
    yaml = None


# Size -> plausible USD cost (the stub's cost model). Swap for real token accounting.
SIZE_COST = {"X": 10.0, "L": 4.0, "M": 1.5, "S": 0.5}
# Plausible seconds per finished round (code+test+response all count).
_SECONDS_PER_ROUND = 90


def load_board(path: Path) -> dict:
    if yaml is None:
        raise RuntimeError("PyYAML not installed (pip install pyyaml)")
    if not path.exists():
        raise FileNotFoundError(f"board not found: {path}")
    return yaml.safe_load(path.read_text()) or {"tickets": []}


def building_tickets(board: dict) -> list[dict]:
    return [t for t in board.get("tickets", []) if t.get("col") == "building"]


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _size_cost(size: str) -> float:
    return float(SIZE_COST.get(str(size or "").strip().upper(), 1.0))


def coder_step(ticket: dict) -> dict:
    """Run the (stub) coder for one building ticket and return a job-log dict.

    Reads the ticket's module + round budget, completes every round, and synthesises a plausible
    cost + cycle. Green verdict + gate_pass True when code + test rounds both finish.
    """
    rounds = dict(ticket.get("rounds") or {})
    for kind in ("code", "test", "response"):
        r = rounds.get(kind) or {}
        budget = int(r.get("budget", 3) or 3)
        # Coder completes every round in this pass.
        rounds[kind] = {"done": budget, "budget": budget}

    done = sum((r.get("done", 0) or 0) for r in rounds.values())
    cost = _size_cost(ticket.get("size"))
    cycle_s = int(done * _SECONDS_PER_ROUND)

    start = datetime.now(timezone.utc)
    end = start + timedelta(seconds=max(1, cycle_s))

    verdict = "green"
    gate_pass = bool(done and rounds.get("code", {}).get("done") and rounds.get("test", {}).get("done"))
    return {
        "ticket_id": ticket["id"],
        "module": ticket.get("module") or "core:ui",
        "start_ts": _iso(start),
        "end_ts": _iso(end),
        "verdict": verdict,
        "gate_pass": gate_pass,
        "cost_usd": round(cost, 3),
        "cycle_s": cycle_s,
        "rounds": rounds,
    }


def write_joblog(job: dict, logdir: Path) -> Path:
    logdir.mkdir(parents=True, exist_ok=True)
    out = logdir / f"{job['ticket_id']}.jsonl"
    # Append a line (a jsonl file); idempotent enough for a single-run-per-ticket stub.
    with out.open("a") as f:
        f.write(__import__("json").dumps(job) + "\n")
    return out


def run(board: dict, max_build: int = 0, dry: bool = False,
        logdir: Path | None = None) -> list[dict]:
    """Run the coder for building tickets (up to max_build). Return the job logs written."""
    logdir = logdir or Path("run/joblogs")
    tickets = building_tickets(board)
    if max_build:
        tickets = tickets[:max_build]

    jobs: list[dict] = []
    for t in tickets:
        job = coder_step(t)
        jobs.append(job)
        if dry:
            print(f"would run coder for {job['ticket_id']} "
                  f"({job['module']}) -> {job['verdict']}, "
                  f"cost ${job['cost_usd']}, cycle {job['cycle_s']}s "
                  f"rounds { {k: v['done'] for k, v in job['rounds'].items()} }")
        else:
            path = write_joblog(job, logdir)
            print(f"wrote {path}: {job['ticket_id']} -> {job['verdict']} "
                  f"gate_pass={job['gate_pass']}")
    return jobs


def main() -> int:
    ap = argparse.ArgumentParser(description="FP-05 worker loop: coder for building tickets")
    ap.add_argument("--board", default="run/board.yaml")
    ap.add_argument("--logdir", default="run/joblogs")
    ap.add_argument("--max-build", type=int, default=0,
                    help="cap building tickets served in one pass (0 = all)")
    ap.add_argument("--dry", action="store_true", help="print what it would do; write nothing")
    ap.add_argument("--list", action="store_true", help="list building tickets, run none")
    args = ap.parse_args()

    board = load_board(Path(args.board))
    logdir = Path(args.logdir)

    if args.list:
        for t in building_tickets(board):
            print(f"{t['id']:8s} module={t.get('module')} size={t.get('size')} "
                  f"rounds={t.get('rounds')}")
        return 0

    print(f"building tickets: {len(building_tickets(board))} "
          f"(max_build={args.max_build or 'all'}), logdir={logdir}")
    run(board, max_build=args.max_build, dry=args.dry, logdir=logdir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
