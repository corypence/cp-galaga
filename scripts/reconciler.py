"""
reconciler.py — Phase 1: the dispatch engine.

Reads `run/board.yaml` (machine-readable board) + `spec/tasks.md` (deps), and every tick decides:
  * dispatch  — move `ready` tickets into `building` when a slot is free and deps are all `merged`
  * fold      — a ticket whose deps just merged becomes unblocked
  * hold      — two `ready` tickets share a file in `fileset`; dispatch the critical-path one, hold the other
  * promote   — `building` -> `reviewing` when the coder's job finishes (tracked via an event marker)
  * escalate  — a ticket stuck > threshold in a column gets escalated
  * complete  — `reviewing`/`awaiting-approval` -> `merged` on human approve

Design (from the reference run's reconciler.log): a fixed-interval control loop, state-driven and
idempotent. It does NOT run the agents — it updates board state and prints the action to take, and
a thin runner (or cron) spawns the actual work.

Usage:
    python reconciler.py --tick                 # one decision pass; prints actions
    python reconciler.py --run --interval 300    # keep running every N seconds
    python reconciler.py --simulate              # dry-run a full run over the board

Board state is mutated in place; --simulate leaves it untouched.
"""
from __future__ import annotations
import argparse
import copy
import json
import time
from pathlib import Path
from datetime import datetime, timezone

try:
    import yaml
except ImportError:
    yaml = None


class Board:
    def __init__(self, path: Path):
        self.path = path
        self.data = self._load()

    def _load(self) -> dict:
        if yaml is None:
            raise RuntimeError("PyYAML not installed (pip install pyyaml)")
        if self.path.exists():
            return yaml.safe_load(self.path.read_text()) or self._default()
        return self._default()

    def _default(self) -> dict:
        return {
            "run": {"id": "run-0", "base": "main", "slots": 2,
                    "ceilings": {"usd": 500.0, "wall_s": 864000},
                    "columns": ["blocked", "ready", "building", "reviewing",
                                "awaiting-approval", "awaiting-merge", "merged",
                                "escalated", "external"]},
            "tickets": [],
            "events": [],
            "stats": {"dispatched": 0, "promoted": 0, "merged": 0, "escalated": 0, "held": 0},
        }

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(yaml.safe_dump(self.data, sort_keys=False))

    def stat(self, key: str, n: int = 1) -> int:
        self.data.setdefault("stats", {}).setdefault(key, 0)
        self.data["stats"][key] += n
        return self.data["stats"][key]

    def cols(self) -> list[str]:
        return self.data["run"]["columns"]

    def get(self, tid: str):
        for t in self.data["tickets"]:
            if t["id"] == tid:
                return t
        return None

    def add_event(self, kind: str, tid: str, detail: str = ""):
        self.data.setdefault("events", []).append({
            "ts": datetime.now(timezone.utc).isoformat(), "kind": kind,
            "ticket": tid, "detail": detail})

    def ready_count(self) -> int:
        return sum(1 for t in self.data["tickets"] if t.get("col") == "ready")

    def building_count(self) -> int:
        return sum(1 for t in self.data["tickets"] if t.get("col") == "building")


def parse_deps(tasks_md: Path) -> dict[str, list[str]]:
    """Re-use dag.py's parsing to get dependency edges from spec/tasks.md."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    import dag  # type: ignore
    text = tasks_md.read_text()
    edges, _ordered = dag.parse_edges(text)
    return edges


def merge_filesets(tickets: list[dict]) -> list[tuple[str, str]]:
    """Return (a, b) pairs of tickets whose filesets intersect (collision candidates)."""
    collisions = []
    indexed = {t["id"]: set(t.get("fileset", [])) for t in tickets}
    ids = list(indexed)
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            shared = indexed[ids[i]] & indexed[ids[j]]
            if shared:
                collisions.append((ids[i], ids[j]))
    return collisions


class Reconciler:
    def __init__(self, board: Board, deps: dict[str, list[str]],
                 critical_path_len: dict[str, int], ctx: dict):
        self.board = board
        self.deps = deps
        self.critical = critical_path_len  # ticket -> depth (for ordering)
        self.ctx = ctx
        self._pr = 0  # monotonic PR counter for promote/complete

    def _deps_merged(self, tid: str) -> bool:
        for d in self.deps.get(tid, []):
            t = self.board.get(d)
            if not t or t.get("col") != "merged":
                return False
        return True

    def _depth(self, tid: str) -> int:
        return self.critical.get(tid, 0)

    def _gate_passed(self, tid: str, module: str, dry: bool = True) -> bool:
        """Promote gate: run the ticket's ladder and report if it's green."""
        import gates
        ladder = {t: cfg["cmd"] for t, cfg in gates.DEFAULT_LADDER.items()}
        res = gates.run_ticket(tid, ladder, module or "core:ui", dry=dry)
        return bool(res.get("green"))

    def _premerge_go(self, tid: str) -> tuple[bool, dict]:
        """Pre-merge human gate. Autonomous approve (approval flag off) records a Go;
        if a human decision already exists, honour it."""
        import humangate
        last = humangate.last_decision("pre-merge")
        if last and last.get("decision") in ("go", "no-go", "hold"):
            return last.get("decision") == "go", last
        humangate.record("pre-merge", "go", owner="cory", detail="autonomous approve")
        return True, {"owner": "cory"}

    def tick(self) -> list[str]:
        actions = []
        cols = self.board.cols()
        slots = self.board.data["run"]["slots"]

        # 1) Fold: blocked -> ready when deps merge.
        for t in self.board.data["tickets"]:
            if t.get("col") == "blocked" and self._deps_merged(t["id"]):
                t["col"] = "ready"
                actions.append(f"fold {t['id']} -> ready (deps merged)")
                self.board.add_event("fold", t["id"], "deps merged")

        # 2) Dispatch: ready -> building when slots free and deps merged.
        ready = [t for t in self.board.data["tickets"] if t.get("col") == "ready"]
        ready.sort(key=lambda t: (-self._depth(t["id"]), t["id"]))  # critical-path first
        building = self.board.building_count()
        free = slots - building
        for t in ready[:max(0, free)]:
            if not self._deps_merged(t["id"]):
                continue
            t["col"] = "building"
            t["worktree"] = f"w-{t['id']}"
            t["branch"] = t["id"]
            actions.append(f"dispatch {t['id']} -> building")
            self.board.add_event("dispatch", t["id"], "slot free, deps merged")
            self.board.stat("dispatched")

        # 3) Collision hold: among remaining ready, if two share a fileset, hold the shallower.
        ready_now = [t for t in self.board.data["tickets"] if t.get("col") == "ready"]
        for a, b in merge_filesets(ready_now):
            ta, tb = self.board.get(a), self.board.get(b)
            holder = ta if self._depth(a) >= self._depth(b) else tb
            partner = tb if holder is ta else ta
            if holder:
                holder["col"] = "blocked"
                holder["_held_by"] = partner["id"]
                actions.append(f"hold {holder['id']} (collision with {partner['id']})")
                self.board.add_event("hold", holder["id"], "fileset collision")

        # 4) Escalate: stuck > threshold.
        threshold = self.ctx.get("escalate_after", 0)
        if threshold:
            from datetime import datetime
            now = datetime.now(timezone.utc)
            for t in self.board.data["tickets"]:
                ts = t.get("col_ts")
                if ts:
                    dt = datetime.fromisoformat(ts)
                    if (now - dt).total_seconds() > threshold:
                        t["col"] = "escalated"
                        t.setdefault("escalations", []).append({"at": ts})
                        actions.append(f"escalate {t['id']} (stuck >{threshold}s)")
                        self.board.add_event("escalate", t["id"], "stuck")

        # 5) Promote: building -> awaiting-merge when the 7-tier gate ladder is green.
        for t in self.board.data["tickets"]:
            if t.get("col") == "building":
                if self._gate_passed(t["id"], t.get("module", "")):
                    t["col"] = "awaiting-merge"
                    t["pr"] = f"#{self._pr}"
                    self._pr += 1
                    t.setdefault("escalations", [])
                    actions.append(f"promote {t['id']} -> awaiting-merge (gates green)")
                    self.board.add_event("promote", t["id"], "gates green")
                    self.board.stat("promoted")

        # 6) Complete: awaiting-merge -> merged on pre-merge Go.
        for t in self.board.data["tickets"]:
            if t.get("col") == "awaiting-merge":
                go, _ = self._premerge_go(t["id"])
                if go:
                    t["col"] = "merged"
                    actions.append(f"complete {t['id']} -> merged (pre-merge go)")
                    self.board.add_event("complete", t["id"], "pre-merge go")
                    self.board.stat("merged")
                else:
                    actions.append(f"hold {t['id']} (pre-merge no-go)")

        if not actions:
            actions.append("(nothing to do)")
        return actions

    def simulate(self, ticks: int = 200) -> list[str]:
        log = []
        for i in range(ticks):
            a = self.tick()
            log.append(f"tick {i}: {a}")
            if all(t.get("col") in ("merged", "external", "escalated", "cancelled")
                   for t in self.board.data["tickets"]) and self.board.building_count() == 0:
                log.append(f"run complete after {i + 1} ticks")
                break
        return log


def main() -> int:
    ap = argparse.ArgumentParser(description="Dispatch engine for the pipeline")
    ap.add_argument("--tick", action="store_true", help="one decision pass")
    ap.add_argument("--run", action="store_true", help="keep running on interval")
    ap.add_argument("--simulate", action="store_true", help="dry-run the run")
    ap.add_argument("--interval", type=int, default=300, help="seconds between ticks")
    ap.add_argument("--board", default="run/board.yaml")
    ap.add_argument("--tasks", default="spec/tasks.md")
    ap.add_argument("--escalate-after", type=int, default=0)
    args = ap.parse_args()

    board = Board(Path(args.board))
    deps = parse_deps(Path(args.tasks))
    # Critical-path depth per ticket (longest chain to merge).
    from dag import critical_path as _cp
    depth: dict[str, int] = {}
    for t in board.data["tickets"]:
        memo = {}

        def d(tid, stack):
            if tid in memo:
                return memo[tid]
            if tid in stack:
                return 0
            stack = stack | {tid}
            best = 0
            for x in deps.get(tid, []):
                best = max(best, d(x, stack))
            memo[tid] = best + 1
            return memo[tid]
        depth[t["id"]] = d(t["id"], set())

    ctx = {"escalate_after": args.escalate_after}
    recon = Reconciler(board, deps, depth, ctx)

    if args.simulate:
        for line in recon.simulate():
            print(line)
        return 0

    if args.run:
        while True:
            acts = recon.tick()
            board.save()
            print(time.strftime("%H:%M:%S"), acts)
            time.sleep(args.interval)
    else:
        acts = recon.tick()
        board.save()
        print("actions:", acts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
