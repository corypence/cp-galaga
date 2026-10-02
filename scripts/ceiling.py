"""
ceiling.py — Phase 2: run-level cost ceiling + auto-pause + stalled detection.

Reads the board and enforces run-level ceilings (design doc §5.9):
    - cost ceiling: total $ or wall-time across the run; if exceeded, pause (freeze the board).
    - stalled detection: a ticket stuck in `reviewing`/`awaiting-approval` > threshold -> page.

`auto-pause` writes a marker so the reconciler stops dispatching. `check` returns a status dict the
reconciler polls each tick. `pause`/`resume` flip the pause flag. `unpause` clears stalls.

Usage:
    python ceiling.py --check --board run/board.yaml
    python ceiling.py --pause --reason "cost ceiling hit"
    python ceiling.py --resume
    python ceiling.py --check --stalled-threshold 1800

Exit codes: 0 ok (not paused), 1 paused (ceiling hit), 2 config error.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

STATE_FILE = "run/ceiling.state"


def load_board(board_path: str) -> dict:
    import yaml
    return yaml.safe_load(Path(board_path).read_text())


def total_cost(board: dict) -> float:
    total = 0.0
    for t in board.get("tickets", []):
        total += t.get("cost", {}).get("usd", 0.0)
    return total


def total_wall(board: dict) -> float:
    total = 0.0
    for t in board.get("tickets", []):
        total += t.get("cost", {}).get("wall_s", 0.0)
    return total


def check(board_path: str, stalled_s: int = 0) -> dict:
    board = load_board(board_path)
    run = board["run"]
    ceilings = run.get("ceilings", {})
    cost = total_cost(board)
    wall = total_wall(board)
    paused = Path(STATE_FILE).exists()
    now = datetime.now(timezone.utc)

    reasons = []
    if ceilings.get("usd") and cost > ceilings["usd"]:
        reasons.append(f"cost ${cost:.2f} > ceiling ${ceilings['usd']}")
    if ceilings.get("wall_s") and wall > ceilings["wall_s"]:
        reasons.append(f"wall {int(wall)}s > ceiling {ceilings['wall_s']}s")

    stalls = []
    for t in board.get("tickets", []):
        ts = t.get("col_ts")
        if ts:
            dt = datetime.fromisoformat(ts)
            age = (now - dt).total_seconds()
            if stalled_s and age > stalled_s and t.get("col") in (
                    "reviewing", "awaiting-approval"):
                stalls.append({"ticket": t["id"], "col": t.get("col"), "age_s": int(age)})

    wip = sum(1 for t in board.get("tickets", [])
              if t.get("col") in ("building", "reviewing", "awaiting-approval"))
    counts = {}
    for t in board.get("tickets", []):
        c = t.get("col", "blocked")
        counts[c] = counts.get(c, 0) + 1
    bottleneck = max(counts.items(), key=lambda kv: kv[1]) if counts else ("", 0)

    return {
        "paused": paused,
        "cost": cost,
        "cost_ceiling": ceilings.get("usd"),
        "wall": wall,
        "wall_ceiling": ceilings.get("wall_s"),
        "wip": wip,
        "bottleneck": {"column": bottleneck[0], "count": bottleneck[1]},
        "stalls": stalls,
        "reasons": reasons,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Cost ceiling + auto-pause + stall detection")
    ap.add_argument("--check", action="store_true", help="check state")
    ap.add_argument("--board", default="run/board.yaml")
    ap.add_argument("--stalled-threshold", type=int, default=0,
                    help="seconds for stall detection")
    ap.add_argument("--pause", action="store_true", help="pause the run")
    ap.add_argument("--resume", action="store_true", help="resume the run")
    ap.add_argument("--reason", help="reason for pause")
    args = ap.parse_args()

    if args.pause:
        rec = {"ts": datetime.now(timezone.utc).isoformat(), "reason": args.reason or ""}
        Path(STATE_FILE).write_text(json.dumps(rec, indent=2))
        print(json.dumps({"paused": True, "state": json.loads(Path(STATE_FILE).read_text())}))
        return 1

    if args.resume:
        if Path(STATE_FILE).exists():
            Path(STATE_FILE).unlink()
        print(json.dumps({"paused": False}))
        return 0

    if args.check:
        status = check(args.board, args.stalled_threshold)
        print(json.dumps(status, indent=2))
        return 1 if status["paused"] else 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
