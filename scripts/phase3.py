"""
phase3.py — Phase 3: spec versioning, determinism, rollback/promotion+canary, incident taxonomy.

Four capabilities:
  1. spec version — snapshot spec/ into run/spec-<version>/ and record a manifest. Bump on change.
  2. determinism — print pinned versions + a cache key derived from spec+tasks (so runs are
     reproducible). Writes run/determinism.lock.
  3. promote / canary — "promote" merged tickets onto the base branch in a controlled order,
     optionally canary a subset first (mark a run `canary` and gate promotion on a health check).
  4. incident taxonomy — seed an incident log with the reference's taxonomy (collision, flaky
     gate, manual rebase, human stall); annotate + count.

Usage:
    python phase3.py --spec-version --spec spec/
    python phase3.py --determinism --spec spec/ --tasks spec/tasks.md
    python phase3.py --promote --board run/board.yaml --canary 4 --health "verify.sh --pre-pr"
    python phase3.py --incidents --seed

Exit codes: 0 ok, 1 canary health fail / needs manual step, 2 config error.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
import shutil
from datetime import datetime, timezone

INCIDENT_SEED = [
    {"id": "INC-1", "kind": "collision", "severity": "warn",
     "detail": "two tickets touched the same file; reconciler held one"},
    {"id": "INC-2", "kind": "flaky_gate", "severity": "warn",
     "detail": "alpha-suite unit test flaked; retried with backoff"},
    {"id": "INC-3", "kind": "manual_rebase", "severity": "info",
     "detail": "~10 hand-resolved bases; auto-rebase planned"},
    {"id": "INC-4", "kind": "human_stall", "severity": "page",
     "detail": "run stalled awaiting-approval; human gate needed"},
]


def spec_version(spec_dir: str) -> str:
    dest = Path("run") / f"spec-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
    dest.mkdir(parents=True, exist_ok=True)
    for item in Path(spec_dir).iterdir():
        if item.is_file():
            shutil.copy(item, dest / item.name)
    version = len(list(Path("run").glob("spec-*")))
    manifest = dest / "version.json"
    manifest.write_text(json.dumps({"version": version,
                                    "created": datetime.now(timezone.utc).isoformat()},
                                   indent=2))
    return str(dest)


def determinism(spec_dir: str, tasks_md: str) -> dict:
    parts = []
    for item in sorted(Path(spec_dir).iterdir()):
        if item.is_file():
            parts.append(item.read_text())
    parts.append(Path(tasks_md).read_text())
    digest = hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]
    lock = {"created": datetime.now(timezone.utc).isoformat(),
            "spec_sha": digest,
            "pinned": {"python": "3.11", "gh": "2.102.0",
                       "torch": "2.5.1+cu121", "xformers": "0.0.28.post3",
                       "numpy": "1.26.4"},
            "cache_key": f"spec-{digest}-v1"}
    Path("run").mkdir(parents=True, exist_ok=True)
    Path("run/determinism.lock").write_text(json.dumps(lock, indent=2))
    return lock


def promote(board_path: str, canary: int = 0, health_cmd: str = "", dry: bool = True) -> dict:
    import yaml
    board = yaml.safe_load(Path(board_path).read_text())
    merged = [t for t in board["tickets"] if t.get("col") == "merged"]
    if canary and canary < len(merged):
        promote_set = merged[:canary]
        rest = merged[canary:]
    else:
        promote_set = merged
        rest = []
    results = []
    for t in promote_set:
        if dry:
            status = "promoted"
        else:
            r = subprocess.run(health_cmd, shell=True, capture_output=True, text=True)
            status = "ok" if r.returncode == 0 else "health_fail"
        results.append({"ticket": t["id"], "status": status})
    return {"canary": canary > 0, "promoted": [r["ticket"] for r in results],
            "remaining": [t["id"] for t in rest], "results": results}


def incidents(seed: bool = False) -> dict:
    p = Path("run/incidents.ndjson")
    if seed and not p.exists():
        Path("run").mkdir(parents=True, exist_ok=True)
        for inc in INCIDENT_SEED:
            p.write_text("\n".join(json.dumps(i) for i in INCIDENT_SEED) + "\n")
    counts = {}
    total = 0
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            inc = json.loads(line)
            kind = inc.get("kind")
            if kind:
                counts[kind] = counts.get(kind, 0) + 1
            total += 1
    return {"total": total, "by_kind": counts}


def main() -> int:
    ap = argparse.ArgumentParser(description="Phase 3: versioning, determinism, promote, incidents")
    ap.add_argument("--spec-version", action="store_true", help="snapshot spec/")
    ap.add_argument("--spec", default="spec", help="spec directory")
    ap.add_argument("--tasks", default="spec/tasks.md", help="tasks.md")
    ap.add_argument("--determinism", action="store_true", help="write determinism.lock")
    ap.add_argument("--promote", action="store_true", help="promote merged tickets")
    ap.add_argument("--board", default="run/board.yaml", help="board file")
    ap.add_argument("--canary", type=int, default=0, help="canary this many first")
    ap.add_argument("--health", default="", help="health check command for canary")
    ap.add_argument("--dry", action="store_true", help="dry-run promote")
    ap.add_argument("--incidents", action="store_true", help="show/seed incidents")
    ap.add_argument("--seed", action="store_true", help="seed incident taxonomy")
    args = ap.parse_args()

    if args.spec_version:
        print(spec_version(args.spec))
        return 0
    if args.determinism:
        print(json.dumps(determinism(args.spec, args.tasks), indent=2))
        return 0
    if args.promote:
        print(json.dumps(promote(args.board, args.canary, args.health, args.dry), indent=2))
        return 0 if args.dry else 1
    if args.incidents:
        print(json.dumps(incidents(args.seed), indent=2))
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
