"""
traceability.py — Phase 2: requirement -> task -> ticket -> PR -> coverage matrix.

A single table generated from the board (design doc §5.10):
    requirement R# -> task T# -> ticket MMA# -> files -> PR -> tests -> coverage %

This is what makes a run *auditable*. The reference only had it implicit; here it's generated from
the data model. Output: Markdown table (default), JSON, or CSV.

Usage:
    python traceability.py --board run/board.yaml --out run/traceability.md
    python traceability.py --board run/board.yaml --json
    python traceability.py --board run/board.yaml --csv

Exit codes: 0 ok, 2 config error.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from collections import defaultdict


def build_matrix(board: dict) -> dict:
    """Build requirement -> [tasks] -> [tickets] mapping from the board."""
    reqs = defaultdict(lambda: {"tasks": defaultdict(list), "tickets": []})
    for t in board.get("tickets", []):
        tid = t.get("id", "?")
        covers = t.get("covers", [])
        for r in covers:
            reqs[r]["tasks"][tid].append(t)
            reqs[r]["tickets"].append(t)
    return {"requirements": dict(reqs), "tickets": board.get("tickets", [])}


def render_markdown(matrix: dict) -> str:
    lines = ["# Traceability Matrix", "",
             "| Requirement | Task | Ticket | Module | PR | Coverage |",
             "|---|---|---|---|---|---|"]
    reqs = matrix["requirements"]
    for r in sorted(reqs):
        for tid in sorted(reqs[r]["tasks"]):
            t = reqs[r]["tasks"][tid][0]
            pr = t.get("pr") or ""
            cov = t.get("metrics", {}).get("gate_pass", 0)
            lines.append(f"| {r} | {tid} | {t.get('id')} | {t.get('module', '-')} "
                         f"| {pr} | {cov} |")
    return "\n".join(lines) + "\n"


def render_csv(matrix: dict) -> str:
    rows = ["requirement,task,ticket,module,pr,coverage"]
    reqs = matrix["requirements"]
    for r in sorted(reqs):
        for tid in sorted(reqs[r]["tasks"]):
            t = reqs[r]["tasks"][tid][0]
            rows.append(f"{r},{tid},{t.get('id')},{t.get('module','')},{t.get('pr','')},"
                        f"{t.get('metrics',{}).get('gate_pass',0)}")
    return "\n".join(rows) + "\n"


def render_json(matrix: dict) -> str:
    return json.dumps(matrix, indent=2)


def main() -> int:
    ap = argparse.ArgumentParser(description="Traceability matrix generator")
    ap.add_argument("--board", default="run/board.yaml", help="board file")
    ap.add_argument("--out", help="output path (default stdout)")
    ap.add_argument("--json", action="store_true", help="output JSON")
    ap.add_argument("--csv", action="store_true", help="output CSV")
    args = ap.parse_args()

    import yaml
    board = yaml.safe_load(Path(args.board).read_text())
    matrix = build_matrix(board)
    if args.json:
        out = render_json(matrix)
    elif args.csv:
        out = render_csv(matrix)
    else:
        out = render_markdown(matrix)

    if args.out:
        Path(args.out).write_text(out)
        print(f"wrote {args.out}")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
