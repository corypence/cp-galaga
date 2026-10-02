#!/usr/bin/env python3
"""
metrics.py — Phase 0: per-ticket cost + latency observability.

Ingests cost/latency signals from ticket job logs (the reference run format) and writes
`run/metrics.jsonl`, one JSON line per ticket. Designed to be data-source agnostic:

  * Job logs: lines like `**Result:** green through --full (VERIFY: PASS).` and
    timestamps of the form `2026-08-27T23:39:34Z`.
  * Optional: a `--cost` table parsed from job logs (tokens/usd if the agent recorded them).

Usage:
    python metrics.py --logs DIR [--out run/metrics.jsonl] [--pretty]

With no logs dir, emits a sample line so downstream dashboards have a schema.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)")
RESULT_RE = re.compile(r"\*\*Result:\*\*\s*(.+)", re.IGNORECASE)
PASS_RE = re.compile(r"(PASS|green)", re.IGNORECASE)

# Round counts like "code 0/3 · test 0/3 · response 1/5" (separator is a middle dot).
ROUND_PATTERNS = [
    ("code", r"code\s*(\d+)\s*/\s*(\d+)"),
    ("test", r"test\s*(\d+)\s*/\s*(\d+)"),
    ("response", r"response\s*(\d+)\s*/\s*(\d+)"),
]


def parse_ts(line: str) -> datetime | None:
    m = TS_RE.search(line)
    if not m:
        return None
    return datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))


def parse_ticket_id(path: Path) -> str:
    # job-<id>.log  ->  <id>
    name = path.stem
    return name.replace("job-", "")


def analyze(path: Path) -> dict:
    text = path.read_text(errors="replace")
    lines = text.splitlines()
    start = next((parse_ts(l) for l in lines if parse_ts(l)), None)
    end = None
    for l in reversed(lines):
        if parse_ts(l):
            end = parse_ts(l)
            break
    wall_s = 0
    if start and end:
        wall_s = max(0, (end - start).total_seconds())
    result = RESULT_RE.search(text)
    verdict = "unknown"
    if result:
        verdict = "pass" if PASS_RE.search(result.group(1)) else "fail"
    # Round counts like "rounds: code 0/3 · test 0/3 · response 1/5"
    rounds = {}
    for kind, pat in ROUND_PATTERNS:
        m = re.search(pat, text)
        if m:
            rounds[kind] = {"done": int(m.group(1)), "budget": int(m.group(2))}
    return {
        "ticket_id": parse_ticket_id(path),
        "verdict": verdict,
        "wall_s": wall_s,
        "start_ts": start.isoformat() if start else None,
        "end_ts": end.isoformat() if end else None,
        "rounds": rounds,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest job logs into metrics.jsonl")
    ap.add_argument("--logs", help="dir of job-<id>.log files")
    ap.add_argument("--out", default="run/metrics.jsonl")
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    if not args.logs:
        sample = {
            "ticket_id": "MMA-XXXX",
            "verdict": "pass",
            "wall_s": 0,
            "start_ts": None,
            "end_ts": None,
            "rounds": {"code": {"done": 0, "budget": 3},
                       "test": {"done": 0, "budget": 3},
                       "response": {"done": 0, "budget": 5}},
        }
        mode = "w"
        records = [sample]
    else:
        logdir = Path(args.logs)
        records = [analyze(p) for p in sorted(logdir.glob("job-*.log"))]
        mode = "w" if args.pretty else "w"

    with open(out, mode) as f:
        if args.pretty:
            json.dump(records, f, indent=2)
        else:
            for r in records:
                f.write(json.dumps(r) + "\n")

    print(f"wrote {len(records)} records to {out}")
    if args.logs:
        by_verdict = defaultdict(int)
        for r in records:
            by_verdict[r["verdict"]] += 1
        print("verdicts:", dict(by_verdict))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
