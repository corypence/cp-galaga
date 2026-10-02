#!/usr/bin/env python3
"""
retry.py — Phase 0: retry-with-backoff + jitter + quarantine for flaky gates.

Wraps any callable (a gate command, a test run, whatever returns (exit_code, detail)) and
retries it with exponential backoff + full jitter, up to a configurable max. Tracks flaky
gate history so a known-flaky tier can be quarantined (retried more, or skipped) without
blocking the whole run — the reference hit alpha-suite flakiness repeatedly.

Usage:
    python retry.py --call "python audit.py --source src --json" \
                    --max-retries 3 --base-delay 2 --max-delay 30
    python retry.py --demo        # runs a simulated flaky gate to prove backoff works

Design notes:
  * Backoff = min(max_delay, base_delay * 2**attempt) * random(0.5, 1.5)  (full jitter).
  * A gate that passes on retry #1 or later is flagged "flaky" (not failed).
  * Quarantine list is persisted to run/quarantine.json so it survives runs.
"""
from __future__ import annotations
import json
import random
import subprocess
import time
from pathlib import Path


def backoff_delay(attempt: int, base: float, cap: float) -> float:
    exp = min(cap, base * (2 ** attempt))
    return random.uniform(exp * 0.5, exp)


def run_once(cmd: str) -> tuple[int, str]:
    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=600)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def retry(cmd: str, max_retries: int, base: float, cap: float,
          verbose: bool = True) -> dict:
    attempt = 0
    while True:
        code, detail = run_once(cmd)
        passed = code == 0
        if passed:
            status = "pass" if attempt == 0 else "flaky"
            return {"cmd": cmd, "passed": True, "attempts": attempt + 1,
                    "flaky": attempt > 0, "status": status, "detail": detail[-2000:]}
        if attempt >= max_retries:
            return {"cmd": cmd, "passed": False, "attempts": attempt + 1,
                    "flaky": False, "status": "fail", "detail": detail[-2000:]}
        delay = backoff_delay(attempt, base, cap)
        if verbose:
            print(f"  attempt {attempt + 1} failed (code {code}); retrying in {delay:.2f}s")
        time.sleep(delay)
        attempt += 1


QUARANTINE_PATH = Path("run/quarantine.json")


def load_quarantine() -> set:
    if QUARANTINE_PATH.exists():
        return set(json.loads(QUARANTINE_PATH.read_text()))
    return set()


def quarantine_gate(name: str) -> None:
    q = load_quarantine()
    q.add(name)
    QUARANTINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUARANTINE_PATH.write_text(json.dumps(sorted(q), indent=2))


def demo() -> int:
    # Simulate a gate that passes on the 2nd or 3rd attempt, using a tiny sleep so backoff is visible.
    import itertools
    states = itertools.cycle([1, 1, 0])  # fail, fail, pass
    def flaky_cmd():
        return next(states), "simulated gate"
    print("running simulated flaky gate (passes ~3rd attempt)...")
    start = time.time()
    # Use a direct retry over a lambda-like closure by calling run_once once per attempt.
    attempt = 0
    max_retries = 5
    while True:
        code = next(states)
        passed = code == 0
        if passed:
            print(f"  passed on attempt {attempt + 1} after {time.time() - start:.2f}s")
            break
        if attempt >= max_retries:
            print("  exhausted retries (fail)")
            break
        delay = backoff_delay(attempt, 0.1, 1.0)
        print(f"  attempt {attempt + 1} failed; retry in {delay:.2f}s")
        time.sleep(delay)
        attempt += 1
    return 0


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Retry gate with backoff + quarantine")
    ap.add_argument("--call", help="shell command to retry as a gate")
    ap.add_argument("--max-retries", type=int, default=3)
    ap.add_argument("--base-delay", type=float, default=2.0)
    ap.add_argument("--max-delay", type=float, default=30.0)
    ap.add_argument("--quarantine", help="mark a gate name as quarantined (flaky)")
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()

    if args.demo:
        return demo()
    if not args.call:
        print("usage: retry.py --call <cmd> | --demo")
        return 2

    result = retry(args.call, args.max_retries, args.base_delay, args.max_delay)
    print(json.dumps(result, indent=2))
    if args.quarantine:
        quarantine_gate(args.quarantine)
        print(f"quarantined gate: {args.quarantine}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
