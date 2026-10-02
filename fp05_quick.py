import yaml, json, os, shutil
from pathlib import Path
tmp = Path("/tmp/fp05x")
if tmp.exists():
    shutil.rmtree(tmp)
tmp.mkdir(parents=True)
os.chdir(tmp)
for m in ["spec", "scripts"]:
    shutil.copytree(f"C:/Users/Cory/project-pipeline/{m}", tmp/m, dirs_exist_ok=True)
b = {"tickets": [
    {"id":"T-01","module":"core:ui","col":"building","rounds":{"code":{"budget":3,"done":0},"test":{"budget":3,"done":0},"response":{"budget":5,"done":0}}},
    {"id":"T-02","module":"core:qa","col":"building","rounds":{"code":{"budget":3,"done":0},"test":{"budget":3,"done":0},"response":{"budget":5,"done":0}}},
], "run":{"columns":["ready","building","blocked","awaiting-merge","merged","escalated","external"],"stats":{}}}
yaml.safe_dump(b, open("run/board.yaml","w"), sort_keys=False)
os.makedirs("run/joblogs", exist_ok=True)
import sys; sys.path.insert(0,"scripts")
from dag import DAG
deps = DAG.load("run/board.yaml")
from reconciler import Reconciler
recon = Reconciler(b, deps, {t["id"]:0 for t in b["tickets"]}, {"escalate_after":999999,"worker":True})
import worker
jobs = worker.run(b, max_build=0, dry=False, logdir=Path("run/joblogs"))
print("jobs:", len(jobs), "joblogs:", len(list(Path("run/joblogs").glob("*.jsonl"))))
j = json.loads(Path("run/joblogs").glob("*.jsonl")[0].read_text().splitlines()[-1])
print("sample:", j["ticket_id"], j["verdict"], j["gate_pass"], j["cost_usd"])
acts = recon.tick()
for a in acts:
    if "promote" in a or "T-01" in a or "T-02" in a: print("  ", a)
t1 = next(t for t in b["tickets"] if t["id"]=="T-01")
print("T-01 col:", t1["col"], "pr:", t1.get("pr"))
ok = len(jobs)>0 and t1["col"] in ("awaiting-merge","merged")
print("FP-05:", "PASS" if ok else "FAIL")
