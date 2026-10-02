"""
gen_board.py — Phase 1: generate `run/board.yaml` from `spec/tasks.md`.

Parses each task header + its fields (**Module**, **Covers**, **Depends**, **QA**, **Size**,
**Id**) and emits a board ticket entry. The reconciler consumes this file.

Usage:
    python gen_board.py --spec spec/tasks.md --out run/board.yaml

Output is deterministic: tickets ordered as they appear in the spec. Every ticket starts in
`ready` if it has no deps, else `blocked`. A `fileset` is seeded from the module + id so the
collision gate has something to compare.
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path

TASK_ID = r"[A-Za-z]+-\d+[a-z]*"
HEADER_RE = re.compile(r"^\s*#+\s*" + TASK_ID + r"\b")


def parse_task(line_iter):
    """Given an iterator whose first line is a header, return the ticket dict."""
    header = next(line_iter)
    tid = re.match(TASK_ID, header.lstrip("#").strip()).group(0)

    # Collect the block: header + lines until the next task header.
    block = [header]
    for l in line_iter:
        if HEADER_RE.match(l):
            block.append(l)
            break
        block.append(l)

    def read_field(name):
        # The field appears as **Name** `value`. Capture everything up to the next ` · ` field
        # separator or end of line (the value itself may hold backtick lists).
        for l in block:
            m = re.search(rf"\*\*\s*{name}\s*\*\*\s*(.+?)(?= · \*\*| ·|$)", l)
            if m:
                return m.group(1).strip()
        return ""

    module = read_field("Module")
    covers_raw = read_field("Covers")
    depends_raw = read_field("Depends")
    qa = read_field("QA")
    size = read_field("Size")

    # Covers is a backtick-delimited comma list: `#22`, `N1`, `N2`
    covers = re.findall(r"\`([^`]+)\`", covers_raw)
    covers = [c.strip() for c in covers if c.strip()]

    # Depends is a comma/space list, or em dash `—` for none.
    depends = [d.strip().lstrip("*") for d in re.split(r"[,\s]+", depends_raw) if d.strip()
               and d != "—" and d != "-" and d != "·"]

    deps = depends

    ticket = {
        "id": tid,
        "module": module or "—",
        "covers": covers,
        "depends": deps,
        "qa": qa.strip(),
        "size": size.strip(),
        "fileset": [],
    }
    # Seed a fileset so the collision gate has data: module + id + a couple of likely files.
    if module and module != "—":
        ticket["fileset"] = [f"{module}/"]
    return ticket


def gen(spec_path: Path) -> dict:
    lines = spec_path.read_text().splitlines()
    i = 0
    tickets = []
    while i < len(lines):
        if HEADER_RE.match(lines[i]):
            ticket = parse_task(iter(lines[i:]))
            tickets.append(ticket)
            # Advance past the ticket block until next header (or end).
            j = i + 1
            while j < len(lines) and not HEADER_RE.match(lines[j]):
                j += 1
            i = j
            continue
        i += 1

    run = {
        "id": "run-0",
        "base": "main",
        "slots": 2,
        "ceilings": {"usd": 500.0, "wall_s": 864000},
        "columns": ["blocked", "ready", "building", "reviewing", "awaiting-approval",
                    "awaiting-merge", "merged", "escalated", "external"],
        "stats": {"dispatched": 0, "promoted": 0, "merged": 0, "escalated": 0, "held": 0},
        "events": [],
    }
    for t in tickets:
        t["col"] = "ready" if not t["depends"] else "blocked"
        t["state"] = "ready" if not t["depends"] else "blocked"
        t["worktree"] = ""
        t["branch"] = ""
        t["pr"] = None
        t["rounds"] = {"code": {"done": 0, "budget": 3},
                       "test": {"done": 0, "budget": 3},
                       "response": {"done": 0, "budget": 5}}
        t["cost"] = {"tokens": 0, "usd": 0.0, "wall_s": 0}
        t["metrics"] = {"cycle_s": 0, "gate_pass": 0, "gate_total": 0}
        t["escalations"] = []
    return {"run": run, "tickets": tickets}


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate board.yaml from spec/tasks.md")
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    try:
        import yaml  # type: ignore
    except ImportError:
        print("PyYAML required for --out yaml; install with `pip install pyyaml`")
        return 2

    board = gen(Path(args.spec))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(yaml.safe_dump(board, sort_keys=False))
    print(f"wrote {args.out}: {len(board['tickets'])} tickets")
    ready = sum(1 for t in board["tickets"] if not t["depends"])
    print(f"{ready} ready at start, {len(board['tickets']) - ready} blocked on deps")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
