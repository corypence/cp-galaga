#!/usr/bin/env python3
"""
dag.py — Phase 0: build a dependency DAG + critical path from `spec/tasks.md`.

`spec/tasks.md` is a topologically sorted work breakdown where each task lists its
dependencies. This script parses the dependency declarations into a graph, validates the
topological sort, renders Mermaid + a plain-text longest-chain (critical path), and prints
cycle-time-friendly output for the dashboard.

Usage:
    python dag.py --tasks spec/tasks.md [--mermaid graph/dag.mmd] [--text graph/dag.txt]

The dependency format is flexible: it looks for lines that name a task key (e.g. `T-01`,
`MMA-6050-a`) and the tasks they depend on. It tolerates the reference run's prose and the
board's `deps: [...]` frontmatter.
"""
from __future__ import annotations
import argparse
import re
import sys
from collections import defaultdict, deque
from pathlib import Path

# A task identifier: T-01 / MMA-6050-a / MMA-6048 / etc.
TASK_ID = r"[A-Za-z]+-\d+[a-z]*"

# Header line: starts with markdown heading markers then a task id.
HEADER_RE = re.compile(r"^\s*#+\s*" + TASK_ID + r"\b")

# **Depends** `T-01, T-02`  OR  **Depends** `—`  OR  **Depends** T-01, T-02  (no backticks)
DEPENDS_RE = re.compile(
    r"\*\*\s*Depends\s*\*\*\s*\`?([^·]*)",
    re.IGNORECASE,
)

# Frontmatter / YAML form:  deps: [T-01, T-02]  or  depends: T-01 T-02
DEP_LINE = re.compile(
    r"(?:deps|depends)\s*[:=]\s*\[([^\]]+)\]|"
    r"(?:deps|depends)\s*[:=]\s*([\w,\s\-]+)",
    re.IGNORECASE,
)


def parse_edges(text: str) -> tuple[dict[str, list[str]], list[str]]:
    """Return (edges: task->deps, ordered_keys) preserving file order as the topo hint."""
    edges: dict[str, list[str]] = {}
    ordered: list[str] = []
    current: str | None = None
    lines = text.splitlines()
    for line in lines:
        hm = HEADER_RE.match(line)
        if hm:
            # Strip heading markers, then grab the bare task id.
            rest = line.lstrip("#").strip()
            tok = re.match(TASK_ID, rest)
            current = tok.group(0) if tok else None
            if current and current not in edges:
                edges[current] = []
                ordered.append(current)
            continue
        if current:
            dm = DEPENDS_RE.search(line)
            if dm:
                deps = [d.strip() for d in re.split(r"[,\s]+", dm.group(1).strip()) if d.strip()]
                deps = [d for d in deps if re.fullmatch(TASK_ID, d) and d != current]
                edges[current] = deps
                continue
            lm = DEP_LINE.search(line)
            if lm:
                group = lm.group(1) or lm.group(2) or ""
                for dep in re.split(r"[,\s]+", group.strip()):
                    dep = dep.strip("[]\"' ")
                    if re.fullmatch(TASK_ID, dep) and dep != current:
                        edges[current].append(dep)
    return edges, ordered


def validate_topo(edges: dict[str, list[str]], ordered: list[str]) -> list[str]:
    """Check that every task appears after its deps in `ordered`."""
    pos = {t: i for i, t in enumerate(ordered)}
    violations = []
    for t, deps in edges.items():
        for d in deps:
            if d in pos and pos[d] > pos.get(t, -1):
                violations.append(f"{d} depends-after {t} (should come first)")
    return violations


def critical_path(edges: dict[str, list[str]]) -> tuple[list[str], int]:
    """Longest path through the DAG by node count (depth = max deps chain)."""
    memo: dict[str, int] = {}
    parent: dict[str, str] = {}

    def depth(t: str, stack: set[str]) -> int:
        if t in memo:
            return memo[t]
        if t in stack:  # cycle guard
            return 0
        stack = stack | {t}
        best, bp = 0, ""
        for d in edges.get(t, []):
            if d in edges or d in {k for k in []}:
                dd = depth(d, stack)
                if dd > best:
                    best, bp = dd, d
        memo[t] = best + 1
        parent[t] = bp
        return memo[t]

    longest, root = 0, ""
    for t in edges:
        d = depth(t, set())
        if d > longest:
            longest, root = d, t
    # Walk parents back from root to rebuild the path.
    path = []
    node = root
    while node:
        path.append(node)
        node = parent.get(node)
    path.reverse()
    return path, longest


def mermaid(edges: dict[str, list[str]]) -> str:
    lines = ["mermaid", "graph LR"]
    for t, deps in edges.items():
        for d in deps:
            lines.append(f"    {d} --> {t}")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Parse tasks.md into a dependency DAG")
    ap.add_argument("--tasks", required=True, help="path to tasks.md")
    ap.add_argument("--mermaid", help="write Mermaid DAG here")
    ap.add_argument("--text", help="write text graph + critical path here")
    args = ap.parse_args()

    text = Path(args.tasks).read_text()
    edges, ordered = parse_edges(text)
    print(f"parsed {len(edges)} tasks from {args.tasks}")

    viols = validate_topo(edges, ordered)
    if viols:
        print(f"topo violations: {len(viols)}")
        for v in viols[:10]:
            print(f"  - {v}")
    else:
        print("topological order: OK")

    path, length = critical_path(edges)
    print(f"critical path length: {length} nodes")
    print("critical path: " + " -> ".join(path))

    if args.mermaid:
        Path(args.mermaid).parent.mkdir(parents=True, exist_ok=True)
        Path(args.mermaid).write_text(mermaid(edges))
        print(f"wrote {args.mermaid}")
    if args.text:
        Path(args.text).parent.mkdir(parents=True, exist_ok=True)
        body = ["# Dependency DAG", "", f"Tasks: {len(edges)}",
                f"Critical path ({length}): " + " -> ".join(path), ""]
        for t in ordered:
            deps = ", ".join(edges[t]) if edges[t] else "(none)"
            body.append(f"- `{t}` -> deps: {deps}")
        Path(args.text).write_text("\n".join(body) + "\n")
        print(f"wrote {args.text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
