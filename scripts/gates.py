"""
gates.py — Phase 1/2: the gates ladder.

Each tier must pass before the next. Gates fail fast at the cheapest tier. A ticket advances only
when its tier is green. Tiers (from the design doc §5.6):

    unit -> integration -> contract -> security -> coverage -> perf -> global

Each tier is a command (configurable). If it fails, the tier may retry with exponential backoff +
jitter (flaky tiers) up to `max_retries`, and a tier can be quarantined so a flaky test can't block
the run. A ticket is green when every tier in its ladder is green.

Usage:
    python gates.py --ticket T-01 --ladder unit:integration:security:coverage --dry
    python gates.py --list-ladder                 # print the default ladder + tiers
    python gates.py --run --ticket T-01 --dry      # run all tiers, print pass/fail
    python gates.py --quarantine add --tier unit --test alpha-suite

Exit codes: 0 = all green, 1 = one or more tiers red, 2 = config error.
"""
from __future__ import annotations
import argparse
import json
import re
import random
import subprocess
import time
import sys
from pathlib import Path
from datetime import datetime, timezone

# Default ladder: tier -> (command template, retry budget, flaky?).
# Commands use {module} placeholder; run from repo root with MODULE env set.
DEFAULT_LADDER: dict[str, dict] = {
    "unit":      {"cmd": "verify.sh --inner --module {module}", "budget": 2, "flaky": False},
    "integration": {"cmd": "verify.sh --integration --module {module}", "budget": 1, "flaky": False},
    "contract":  {"cmd": "verify.sh --contract --module {module}", "budget": 1, "flaky": False},
    "security":  {"cmd": "verify.sh --security", "budget": 1, "flaky": False},
    "coverage":  {"cmd": "verify.sh --coverage --min 80", "budget": 1, "flaky": False},
    "perf":      {"cmd": "verify.sh --perf", "budget": 1, "flaky": True},
    "global":    {"cmd": "verify.sh --pre-pr", "budget": 1, "flaky": False},
}

# Track quarantined (flaky) test names per tier: {tier: [test,...]}.
QUARANTINE_FILE = "run/quarantine.json"


def load_quarantine() -> dict:
    p = Path(QUARANTINE_FILE)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_quarantine(q: dict):
    Path(QUARANTINE_FILE).parent.mkdir(parents=True, exist_ok=True)
    Path(QUARANTINE_FILE).write_text(json.dumps(q, indent=2))


def _sleep(base: float, attempt: int):
    """Full jitter backoff: sleep in [0, base * 2**attempt]."""
    delay = min(base * (2 ** attempt), 30.0)
    return random.uniform(0, delay)


def run_tier(cmd: str, module: str, max_retries: int = 2, flaky: bool = False,
             quarantine: dict | None = None, dry: bool = False) -> dict:
    """Run a single tier command. Retry with backoff if flaky. Returns a result dict."""
    actual = cmd.format(module=module)
    result = {"tier": "", "command": actual, "attempts": 0, "pass": False,
              "exit": None, "detail": ""}
    attempt = 0
    while attempt <= max_retries:
        result["attempts"] = attempt + 1
        if dry:
            result["pass"] = True
            result["exit"] = 0
            result["detail"] = "dry-run"
            break
        proc = subprocess.run(actual, shell=True, capture_output=True, text=True)
        result["exit"] = proc.returncode
        if proc.returncode == 0:
            result["pass"] = True
            break
        if not flaky or attempt == max_retries:
            result["detail"] = (proc.stdout or "")[-500:] + (proc.stderr or "")[-500:]
            break
        time.sleep(_sleep(0.5, attempt))
        attempt += 1
    return result


def run_ticket(ticket: str, ladder: dict[str, str], module: str, dry: bool = False,
               quarantine: dict | None = None) -> dict:
    """Run every tier in the ladder for a ticket. Stops at first red tier (fail fast)."""
    out = {"ticket": ticket, "module": module, "tiers": {}, "green": True, "cost": 0.0}
    start = time.time()
    for tier, cfg in ladder.items():
        cmd = cfg["cmd"] if isinstance(cfg, dict) else cfg
        max_retries = cfg["budget"] if isinstance(cfg, dict) else 2
        flaky = cfg.get("flaky", False) if isinstance(cfg, dict) else False
        res = run_tier(cmd, module, max_retries=max_retries, flaky=flaky,
                       dry=dry, quarantine=quarantine)
        res["tier"] = tier
        out["tiers"][tier] = res
        if not res["pass"]:
            out["green"] = False
            out["cost"] = time.time() - start
            return out
    out["cost"] = time.time() - start
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Gates ladder")
    ap.add_argument("--ticket", help="ticket to run gates for")
    ap.add_argument("--module", help="module name for the run")
    ap.add_argument("--ladder", help="tier list, colon-separated (e.g. unit:integration:security)")
    ap.add_argument("--dry", action="store_true", help="dry-run: no commands")
    ap.add_argument("--run", action="store_true", help="run the ladder for --ticket")
    ap.add_argument("--list-ladder", action="store_true", help="print the default ladder")
    ap.add_argument("--quarantine", nargs="?", choices=["add", "remove"],
                    help="quarantine a test name in a tier")
    ap.add_argument("--tier", default="unit", help="tier for quarantine ops")
    ap.add_argument("--test", help="test name for quarantine ops")
    args = ap.parse_args()

    if args.list_ladder:
        for tier, cfg in DEFAULT_LADDER.items():
            print(f"{tier:12s} budget={cfg['budget']} flaky={cfg['flaky']}")
            print(f"             cmd: {cfg['cmd']}")
        return 0

    if args.quarantine:
        q = load_quarantine()
        q.setdefault(args.tier, [])
        if args.quarantine == "add" and args.test not in q[args.tier]:
            q[args.tier].append(args.test)
        else:
            q[args.tier] = [t for t in q[args.tier] if t != args.test]
        save_quarantine(q)
        print(json.dumps(q, indent=2))
        return 0

    ladder = dict(DEFAULT_LADDER)
    if args.ladder:
        keep = {t: DEFAULT_LADDER[t] for t in args.ladder.split(":") if t in DEFAULT_LADDER}
        ladder = {t: cfg for t, cfg in keep.items()}
    else:
        ladder = dict(DEFAULT_LADDER)

    if not args.run:
        ap.print_help()
        return 0

    res = run_ticket(args.ticket or "T-01", ladder, args.module or "core:ui",
                     dry=args.dry, quarantine=load_quarantine())
    print(json.dumps(res, indent=2))
    return 0 if res["green"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
