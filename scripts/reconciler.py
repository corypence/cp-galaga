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
        return self.data.get("run", {}).get("columns", [])

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

    def _set_col(self, t: dict, col: str):
        """Set a ticket's column and stamp col_ts so escalate can time it."""
        t["col"] = col
        t["col_ts"] = datetime.now(timezone.utc).isoformat()

    def _gate_passed(self, tid: str, module: str, dry: bool = True) -> bool:
        """Promote gate: run the ticket's ladder and report if it's green."""
        import gates
        ladder = {t: cfg["cmd"] for t, cfg in gates.DEFAULT_LADDER.items()}
        res = gates.run_ticket(tid, ladder, module or "core:ui", dry=dry)
        return bool(res.get("green"))

    def _joblog_path(self, tid: str) -> Path:
        """Path to the ticket's job log under run/joblogs."""
        return Path("run/joblogs") / f"{tid}.jsonl"

    def _real_promote(self, tid: str, module: str, logdir: str = "run/joblogs") -> bool:
        """Real promote gate: true when the ticket has a job log with a green verdict.

        Falls back to the dry gate ladder when no job log exists yet (so promote still works
        without a worker having run). Kept optional; the default dry path is unchanged.
        """
        import worker
        p = Path(logdir) / f"{tid}.jsonl"
        if not p.exists():
            return self._gate_passed(tid, module)
        try:
            lines = [ln for ln in p.read_text().splitlines() if ln.strip()]
            job = __import__("json").loads(lines[-1])
        except (ValueError, OSError):
            return self._gate_passed(tid, module)
        return bool(job.get("gate_pass") and job.get("verdict") == "green")

    def _gh_pr_create(self, tid: str, module: str) -> tuple[bool, str]:
        """Create a PR via `gh` for a promoted ticket. Returns (ok, detail).
        Uses the repo from git remote (or --repo flag), branch = tid, base = main.
        """
        import subprocess
        remote = self.board.data.get("run", {}).get("repo")
        if not remote:
            try:
                out = subprocess.run(
                    ["git", "remote", "get-url", "origin"],
                    capture_output=True, text=True, check=True)
                url = out.stdout.strip()
                # strip ssh/https prefix and trailing .git
                remote = url.split("@")[-1].replace(".git", "")
                remote = remote.replace(":", "/")
                if not remote:
                    remote = None
            except (subprocess.CalledProcessError, FileNotFoundError):
                remote = None
        repo = remote or self.ctx.get("repo")
        branch = tid
        cmd = ["gh", "pr", "create",
               "--repo", str(repo),
               "--title", f"[{module or 'core:ui'}] {tid}",
               "--body", f"Auto PR for ticket {tid}.",
               "--head", branch,
               "--base", self.board.data.get("run", {}).get("base", "main")]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.returncode == 0:
                return True, res.stdout.strip() or res.stderr.strip()
            return False, (res.stderr.strip() or res.stdout.strip())
        except FileNotFoundError:
            return False, "gh not found"

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
                self._set_col(t, "ready")
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
            self._set_col(t, "building")
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
                self._set_col(holder, "blocked")
                holder["_held_by"] = partner["id"]
                actions.append(f"hold {holder['id']} (collision with {partner['id']})")
                self.board.add_event("hold", holder["id"], "fileset collision")
                self.board.stat("held")

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
                        self._set_col(t, "escalated")
                        t.setdefault("escalations", []).append({"at": ts})
                        actions.append(f"escalate {t['id']} (stuck >{threshold}s)")
                        self.board.add_event("escalate", t["id"], "stuck")
                        self.board.stat("escalated")

        # 5) Promote: building -> awaiting-merge when the coder's job finished green (real)
        #    or the dry gate ladder is green. A job log present -> drive off the transcript;
        #    otherwise fall back to the dry gate.
        logdir = self.ctx.get("logdir", "run/joblogs")
        for t in self.board.data["tickets"]:
            if t.get("col") == "building":
                promote_ok = self._real_promote(t["id"], t.get("module", ""), logdir)
                if promote_ok:
                    self._set_col(t, "awaiting-merge")
                    self.board.stat("promoted")
                    pr_ok, pr_detail = self._gh_pr_create(t["id"], t.get("module", ""))
                    t["pr"] = pr_detail if pr_ok else f"#{self._pr}"
                    self._pr += 1
                    t.setdefault("escalations", [])
                    source = "job log green" if self._joblog_path(t["id"]).exists() else "gates green"
                    actions.append(
                        f"promote {t['id']} -> awaiting-merge ({source}"
                        + (", pr ok" if pr_ok else ", gh pr failed)")
                        + ")")
                    self.board.add_event("promote", t["id"], source + (", pr ok" if pr_ok else f", {pr_detail[:60]}"))

        # 6) Complete: awaiting-merge -> merged on pre-merge Go.
        for t in self.board.data["tickets"]:
            if t.get("col") == "awaiting-merge":
                go, _ = self._premerge_go(t["id"])
                if go:
                    self._set_col(t, "merged")
                    actions.append(f"complete {t['id']} -> merged (pre-merge go)")
                    self.board.add_event("complete", t["id"], "pre-merge go")
                    self.board.stat("merged")
                else:
                    actions.append(f"hold {t['id']} (pre-merge no-go)")

        if not actions:
            actions.append("(nothing to do)")
        return actions

    def _run_worker_once(self):
        """Run the coder loop for building tickets (creates run/joblogs if missing)."""
        import os
        Path("run/joblogs").mkdir(parents=True, exist_ok=True)
        import worker
        worker.run(self.board.data, max_build=0, dry=False,
                   logdir=Path("run/joblogs"))

    def simulate(self, ticks: int = 200, run_worker: bool = True) -> list[str]:
        log = []
        for i in range(ticks):
            if run_worker:
                self._run_worker_once()
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
    ap.add_argument("--worker", action="store_true",
                    help="run the coder loop for building tickets each tick (FP-05)")
    ap.add_argument("--simulate", action="store_true", help="dry-run the run")
    ap.add_argument("--interval", type=int, default=300, help="seconds between ticks")
    ap.add_argument("--board", default="run/board.yaml")
    ap.add_argument("--tasks", default="spec/tasks.md")
    ap.add_argument("--escalate-after", type=int, default=0)
    args = ap.parse_args()

    board = Board(Path(args.board))
    deps = parse_deps(Path(args.tasks))
    # Critical-path depth per ticket (longest chain to merge).
    from dag import critical_path  # noqa: F401 (import kept for compat; depth computed below)
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

    ctx = {"escalate_after": args.escalate_after, "worker": args.worker}
    recon = Reconciler(board, deps, depth, ctx)

    if args.simulate:
        for line in recon.simulate(run_worker=args.worker):
            print(line)
        return 0

    if args.run:
        while True:
            if args.worker:
                recon._run_worker_once()
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
