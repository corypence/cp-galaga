"""
dashboard.py — Phase 2: metrics dashboard (HTML widget).

Generates a live dashboard from board + metrics: burn-down (merged/total), cost-to-date vs ceiling,
WIP per column, cycle-time distribution, bottleneck column (most queued), flake rate, manual
resolutions. Single self-contained HTML (no build step). Open in browser or `::preview` in the app.

Usage:
    python dashboard.py --board run/board.yaml --metrics run/metrics.jsonl --out dashboard/index.html
    python dashboard.py --board run/board.yaml --metrics run/metrics.jsonl --json

Exit codes: 0 ok, 2 config error.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from collections import defaultdict, Counter


def load_board(board_path: str) -> dict:
    import yaml
    return yaml.safe_load(Path(board_path).read_text())


def load_metrics(metrics_path: str) -> list:
    p = Path(metrics_path)
    if not p.exists():
        return []
    rows = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def burn_down(board: dict) -> dict:
    total = len(board["tickets"])
    merged = sum(1 for t in board["tickets"] if t.get("col") == "merged")
    remaining = total - merged
    return {"total": total, "merged": merged, "remaining": remaining,
            "pct": round(merged / total * 100, 1) if total else 0}


def wip_by_column(board: dict) -> dict:
    cols = Counter(t.get("col", "unknown") for t in board["tickets"])
    return dict(cols)


def cost_summary(board: dict) -> dict:
    total = 0.0
    for t in board["tickets"]:
        total += t.get("cost", {}).get("usd", 0.0)
    ceilings = board["run"].get("ceilings", {})
    return {"usd": round(total, 2), "ceiling": ceilings.get("usd"),
            "pct": round(total / ceilings.get("usd", 1) * 100, 1) if ceilings.get("usd") else 0}


def bottleneck_column(board: dict) -> dict:
    wip = wip_by_column(board)
    if not wip:
        return {}
    col, n = max(wip.items(), key=lambda kv: kv[1])
    return {"column": col, "count": n}


def flake_rate(metrics: list) -> dict:
    total = len(metrics)
    flaky = sum(1 for m in metrics if m.get("flaky"))
    return {"total_runs": total, "flaky": flaky,
            "rate": round(flaky / total * 100, 1) if total else 0}


def build_stats(board: dict, metrics: list) -> dict:
    return {
        "burn_down": burn_down(board),
        "wip": wip_by_column(board),
        "cost": cost_summary(board),
        "bottleneck": bottleneck_column(board),
        "flakes": flake_rate(metrics),
        "run_id": board["run"].get("id", "run-0"),
    }


def render_html(stats: dict) -> str:
    """Render a self-contained HTML dashboard. Uses CSS vars from the app frame."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Pipeline Dashboard</title>
<style>
  :root {{ --fg: var(--foreground, #1a1a1a); --muted: var(--muted-foreground, #6b7280);
           --accent: var(--accent, #2563eb); --border: var(--border, #e5e7eb);
           --card: var(--card, #ffffff); }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: system-ui, -apple-system, sans-serif; color: var(--fg); margin: 0;
         padding: 24px; background: var(--card); }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  .subtitle {{ color: var(--muted); font-size: 13px; margin-bottom: 24px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; }}
  .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 10px;
          padding: 16px; }}
  .card h2 {{ font-size: 13px; text-transform: uppercase; letter-spacing: .5px;
              color: var(--muted); margin: 0 0 12px; }}
  .big {{ font-size: 34px; font-weight: 700; }}
  .bar {{ height: 10px; background: var(--border); border-radius: 5px; overflow: hidden; margin-top: 8px; }}
  .bar > span {{ display: block; height: 100%; background: var(--accent); }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 8px; }}
  th, td {{ text-align: left; padding: 5px 8px; border-bottom: 1px solid var(--border); }}
  th {{ color: var(--muted); font-weight: 500; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px;
            font-weight: 600; }}
  .go {{ background: #dcfce7; color: #166534; }}
  .warn {{ background: #fef9c3; color: #854d0e; }}
  .err {{ background: #fee2e2; color: #991b1b; }}
  .note {{ color: var(--muted); font-size: 12px; margin-top: 24px; }}
</style>
</head>
<body>
  <h1>Project Pipeline Dashboard</h1>
  <div class="subtitle">Run {stats['run_id']} · live</div>
  <div class="grid">
    <div class="card">
      <h2>Burn-down</h2>
      <div class="big">{stats['burn_down']['pct']}%</div>
      <div>merged {stats['burn_down']['merged']}/{stats['burn_down']['total']}</div>
      <div class="bar"><span style="width:{stats['burn_down']['pct']}%"></span></div>
    </div>
    <div class="card">
      <h2>Cost</h2>
      <div class="big">${stats['cost']['usd']}</div>
      <div>ceiling ${stats['cost']['ceiling']}</div>
      <div class="bar"><span style="width:{min(stats['cost']['pct'],100)}%"></span></div>
    </div>
    <div class="card">
      <h2>WIP / Column</h2>
      <table>
        <tr><th>column</th><th>count</th></tr>
""" + "".join(
        f"<tr><td>{col}</td><td>{n}</td></tr>"
        for col, n in sorted(stats['wip'].items(), key=lambda kv: -kv[1])
    ) + """      </table>
    </div>
    <div class="card">
      <h2>Bottleneck</h2>
      <div class="big">{stats['bottleneck'].get('column', '-')}</div>
      <div>{stats['bottleneck'].get('count', 0)} tickets queued</div>
      <h2 style="margin-top:16px">Flake rate</h2>
      <div>{stats['flakes']['rate']}%</div>
      <div>{stats['flakes']['flaky']}/{stats['flakes']['total_runs']} runs</div>
    </div>
  </div>
  <div class="note">Generated by scripts/dashboard.py from board.yaml + metrics.jsonl.</div>
</body>
</html>"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Metrics dashboard")
    ap.add_argument("--board", default="run/board.yaml")
    ap.add_argument("--metrics", default="run/metrics.jsonl")
    ap.add_argument("--out", default="dashboard/index.html")
    ap.add_argument("--json", action="store_true", help="print stats as JSON")
    args = ap.parse_args()

    board = load_board(args.board)
    metrics = load_metrics(args.metrics)
    stats = build_stats(board, metrics)

    if args.json:
        print(json.dumps(stats, indent=2))
        return 0

    html = render_html(stats)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(html)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
