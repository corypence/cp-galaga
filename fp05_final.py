import sys, os
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
import yaml, json, worker
from reconciler import Reconciler
from dag import DAG

# Build a 2-ticket board with both 'building'
b = {"tickets": [
    {"id":"T-01","module":"core:ui","col":"building","rounds":{"code":{"budget":3,"done":0},"test":{"budget":3,"done":0},"response":{"budget":5,"done":0}}},
    {"id":"T-02","module":"core:qa","col":"building","rounds":{"code":{"budget":3,"done":0},"test":{"budget":3,"done":0},"response":{"budget":5,"done":0}}},
], "run":{"columns":["ready","building","blocked","awaiting-merge","merged","escalated","external"],"stats":{}}}
Path("run/joblogs").mkdir(parents=True, exist_ok=True)
deps = DAG.load_dict(b)
recon = Reconciler(b, deps, {t["id"]:0 for t in b["tickets"]}, {"escalate_after":999999,"worker":True})
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
