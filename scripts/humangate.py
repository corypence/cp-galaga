"""
humangate.py — Phase 2: human Go/NO-GO gates with recorded decisions.

Three explicit gates (design doc §5.11), not "when stuck":
    1. Spec Go/NO-GO    — before any dispatch: are tasks/splits sane?
    2. Pre-merge Go/NO-GO — global gates green, cost within ceiling, approvals in?
    3. Release Go/NO-GO — changelog + metrics ready?

Each gate has an owner (you) and a one-line decision recorded in events.ndjson. The reconciler waits
at the gate (board stays in its current state) until a human records a decision.

Usage:
    python humangate.py --gate spec       # prompt for a decision (or --dec go/no-go)
    python humangate.py --gate pre-merge --dec go --owner cory
    python humangate.py --list            # list all gates + last decision
    python humangate.py --status --gate spec   # show gate state

Decisions: go / no-go / hold. Recorded to run/humangate.ndjson (append-only) and surfaced from
run/board.yaml run.human_gate_state if present.

Exit codes: 0 = go, 1 = no-go/hold, 2 = config error.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

GATE_FILE = "run/humangate.ndjson"

GATES = {
    "spec": {"desc": "Spec Go/NO-GO: tasks/splits sane before dispatch"},
    "pre-merge": {"desc": "Pre-merge Go/NO-GO: gates green, cost ok, approvals in"},
    "release": {"desc": "Release Go/NO-GO: changelog + metrics ready"},
}


def record(gate: str, decision: str, owner: str, detail: str = ""):
    Path("run").mkdir(parents=True, exist_ok=True)
    rec = {"ts": datetime.now(timezone.utc).isoformat(), "gate": gate,
           "decision": decision, "owner": owner, "detail": detail}
    with Path(GATE_FILE).open("a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def last_decision(gate: str) -> dict | None:
    p = Path(GATE_FILE)
    if not p.exists():
        return None
    last = None
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("gate") == gate:
            last = rec
    return last


def main() -> int:
    ap = argparse.ArgumentParser(description="Human Go/NO-GO gates")
    ap.add_argument("--gate", choices=list(GATES), help="which gate")
    ap.add_argument("--dec", choices=["go", "no-go", "hold"],
                    help="decision (omit to prompt)")
    ap.add_argument("--owner", help="decision owner (you)")
    ap.add_argument("--detail", help="one-line decision note")
    ap.add_argument("--list", action="store_true", help="list all gates + last decision")
    ap.add_argument("--status", action="store_true", help="show a gate's state")
    args = ap.parse_args()

    if args.list:
        for g, meta in GATES.items():
            last = last_decision(g)
            state = last["decision"] if last else "pending"
            print(f"{g:12s} {state:8s} <- {meta['desc']}")
            if last:
                print(f"             last: {last['decision']} by {last['owner']} "
                      f"@ {last['ts']} — {last.get('detail','')}")
        return 0

    if args.status and args.gate:
        last = last_decision(args.gate)
        print(json.dumps({"gate": args.gate, "last": last}, indent=2))
        return 0

    if not args.gate:
        ap.print_help()
        return 2

    decision = args.dec
    if decision is None:
        # Prompt: read a line from stdin.
        try:
            decision = input("Decision (go/no-go/hold): ").strip().lower()
        except EOFError:
            print("no input; defaulting to hold")
            decision = "hold"
    if decision not in ("go", "no-go", "hold"):
        print(f"unknown decision: {decision}")
        return 2

    owner = args.owner or "human"
    rec = record(args.gate, decision, owner, args.detail or "")
    print(json.dumps(rec, indent=2))
    return 0 if decision == "go" else 1


if __name__ == "__main__":
    raise SystemExit(main())
