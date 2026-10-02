#!/usr/bin/env python3
"""FP-05 end-to-end test: dispatch -> building -> worker writes joblog -> promote off joblog."""
import os, yaml, shutil, tempfile
from pathlib import Path
from collections import Counter

# Work in a temp copy so we don't clobber run/board.yaml
tmp = Path(tempfile.mkdtemp(prefix="fp05_"))
os.chdir(tmp)
shutil.copy(Path("/c/Users/Cory/project-pipeline/spec/tasks.md"), "tasks.md")
shutil.copy(Path("/c/Users/Cory/project-pipeline/scripts/gen_board.py"), "gen_board.py")
shutil.copy(Path("/c/Users/Cory/project-pipeline/scripts/dag.py"), "dag.py")
shutil.copy(Path("/c/Users/Cory/project-pipeline/scripts/reconciler.py"), "reconciler.py")
shutil.copy(Path("/c/Users/Cory/project-pipeline/scripts/worker.py"), "worker.py")
for m in ["dag", "gen_board", "reconciler", "worker"]:
    Path(m).chmod(0o755)

# Build the board from the (1-task) spec; check if it's 1 or 32 tasks
import subprocess
r = subprocess.run(["python", "gen_board.py", "--spec", "tasks.md", "--out", "run/board.yaml"],
                   capture_output=True, text=True)
print("gen_board:", r.stdout.strip(), r.stderr.strip()[:200])

b = yaml.safe_load(open("run/board.yaml"))
print("ticket count:", len(b["tickets"]))

from dag import DAG
deps = DAG.load("run/board.yaml")

# Force ALL tickets to building
for t in b["tickets"]:
    t["col"] = "building"

from reconciler import Reconciler
recon = Reconciler(b, deps, {t["id"]: 0 for t in b["tickets"]},
                   {"escalate_after": 999999, "worker": True})

# Run the worker (FP-05)
import worker
Path("run/joblogs").mkdir(parents=True, exist_ok=True)
jobs = worker.run(b, max_build=0, dry=False, logdir=Path("run/joblogs"))
njobs = len(list(Path("run/joblogs").glob("*.jsonl")))
print(f"worker ran {len(jobs)} jobs; joblogs on disk: {njobs}")
# Show one joblog
first = Path("run/joblogs").glob("*.jsonl")
first = list(first)[0] if first else None
if first:
    j = yaml.safe_load(first.read_text().splitlines()[-1]) if False else __import__("json").loads(open(first).read().splitlines()[-1])
    print("sample job:", j["ticket_id"], j["verdict"], "gate_pass=", j["gate_pass"], "cost=$", j["cost_usd"])

# Now tick -> promote lane should drive T-01 off its joblog
acts = recon.tick()
promote = [a for a in acts if "promote" in a or "T-01" in a]
print("\n--- tick actions (promote/T-01) ---")
for p in promote:
    print("  ", p)

t1 = next((t for t in b["tickets"] if t["id"] == "T-01"), None)
print("\nT-01 col after tick:", t1["col"] if t1 else "MISSING", "| pr:", t1.get("pr") if t1 else "N/A")

# Assertions
ok = True
if njobs == 0:
    print("FAIL: worker wrote no joblogs"); ok = False
if t1 and t1["col"] not in ("awaiting-merge", "merged"):
    print("FAIL: T-01 not promoted past building"); ok = False
print("\nFP-05:", "PASS" if ok else "FAIL")
print("tmp:", tmp)
