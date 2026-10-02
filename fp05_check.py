#!/usr/bin/env python3
"""FP-05 end-to-end check: dispatch -> building -> worker writes joblog -> promote."""
import yaml, json, shutil, os, tempfile, subprocess
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="fp05_"))
for m in ["spec", "scripts"]:
    if Path(m).exists():
        shutil.copytree(m, tmp / m, dirs_exist_ok=True)

r = subprocess.run(
    ["python", "scripts/gen_board.py", "--spec", "spec/tasks.md", "--out", "run/board.yaml"],
    capture_output=True, text=True, cwd=tmp)
print("gen_board:", r.stdout.strip(), r.stderr.strip()[:200])

b = yaml.safe_load(open(tmp / "run/board.yaml"))
print("ticket count:", len(b["tickets"]))

os.chdir(tmp)
import sys
sys.path.insert(0, "scripts")
from dag import DAG
deps = DAG.load("run/board.yaml")

for t in b["tickets"]:
    t["col"] = "building"

from reconciler import Reconciler
recon = Reconciler(b, deps, {t["id"]: 0 for t in b["tickets"]},
                   {"escalate_after": 999999, "worker": True})

import worker
Path("run/joblogs").mkdir(parents=True, exist_ok=True)
jobs = worker.run(b, max_build=0, dry=False, logdir=Path("run/joblogs"))
njobs = len(list(Path("run/joblogs").glob("*.jsonl")))
print(f"worker ran {len(jobs)} jobs; joblogs: {njobs}")

if njobs:
    j = json.loads(Path("run/joblogs").glob("*.jsonl")[0].read_text().splitlines()[-1])
    print("sample:", j["ticket_id"], j["verdict"], "gate_pass=", j["gate_pass"], "cost=$", j["cost_usd"])

acts = recon.tick()
promote = [a for a in acts if "promote" in a or "T-01" in a]
print("\n--- promote/T-01 actions ---")
for p in promote:
    print("  ", p)

t1 = next((t for t in b["tickets"] if t["id"] == "T-01"), None)
print("\nT-01 col:", t1["col"] if t1 else "MISSING", "| pr:", t1.get("pr") if t1 else "N/A")

ok = njobs > 0 and (t1 is None or t1["col"] in ("awaiting-merge", "merged"))
print("\nFP-05:", "PASS" if ok else "FAIL")
print("tmp:", tmp)
