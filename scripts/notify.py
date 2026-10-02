"""
notify.py — Phase 2: notifications + escalation with severity-scoped delivery.

Emits events to a notifications channel (default: stdout + run/notifications.log), severity-scoped:
    info    (dispatch/merge/promote)     -> normal
    warn    (collision, gate retry, near budget cap)  -> attention
    error   (gate fail, escalation)      -> attention
    page    (stalled > X min, budget ceiling hit)      -> page

Escalation: the reconciler auto-escalates a ticket stuck in `reviewing`/`awaiting-approval` > threshold;
run stalls on human-action state. `page` events should page the lead (Slack/Teams/email via a webhook
URL if configured).

Usage:
    python notify.py --emit --ticket T-01 --sev warn --msg "collision on T-05"
    python notify.py --stalled --reviewing --threshold 1800
    python notify.py --emit --sev page --msg "cost ceiling hit: $480/$500"
    python notify.py --config --webhook URL --channel slack

Exit codes: 0 ok, 2 config error.
"""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

CHANNEL_FILE = "run/notify.conf"


def load_config() -> dict:
    p = Path(CHANNEL_FILE)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except json.JSONDecodeError:
            return {}
    return {"channel": "stdout", "webhook": None}


def emit(ticket: str, severity: str, message: str, cfg: dict) -> dict:
    """Emit a severity-scoped notification."""
    rec = {"ts": datetime.now(timezone.utc).isoformat(), "ticket": ticket,
           "severity": severity, "message": message}
    # Always append to the log.
    Path("run").mkdir(parents=True, exist_ok=True)
    with Path("run/notifications.log").open("a") as f:
        f.write(json.dumps(rec) + "\n")
    # Route to channel.
    channel = cfg.get("channel", "stdout")
    if channel == "slack" and cfg.get("webhook"):
        payload = {"text": f"[{severity.upper()}] {ticket}: {message}"}
        try:
            subprocess.run(["curl", "-s", "-X", "POST", "-H",
                            "Content-Type: application/json", "--data",
                            json.dumps(payload), cfg["webhook"], "-o", "/dev/null"],
                           check=True, timeout=10)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            rec["delivery"] = "error"
            rec["detail"] = str(e)
        else:
            rec["delivery"] = "sent"
    else:
        rec["delivery"] = "stdout"
    return rec


def check_stalled(board_path: str, threshold_s: int, cfg: dict) -> list[dict]:
    """Check for tickets stuck in a column > threshold seconds; page if found."""
    import yaml
    board = yaml.safe_load(Path(board_path).read_text())
    now = datetime.now(timezone.utc)
    pages = []
    for t in board["tickets"]:
        col = t.get("col")
        ts = t.get("col_ts")
        if not ts:
            continue
        dt = datetime.fromisoformat(ts)
        age = (now - dt).total_seconds()
        if age > threshold_s and col in ("reviewing", "awaiting-approval"):
            rec = emit(t["id"], "page", f"stuck in {col} for {int(age)}s", cfg)
            pages.append(rec)
    return pages


def main() -> int:
    ap = argparse.ArgumentParser(description="Notifications + escalation")
    ap.add_argument("--emit", action="store_true", help="emit a notification")
    ap.add_argument("--ticket", help="ticket id")
    ap.add_argument("--sev", default="info",
                    choices=["info", "warn", "error", "page"], help="severity")
    ap.add_argument("--msg", help="message")
    ap.add_argument("--stalled", action="store_true", help="check for stalled tickets")
    ap.add_argument("--reviewing", action="store_true", help="column to check (reviewing)")
    ap.add_argument("--threshold", type=int, default=1800, help="seconds (30 min)")
    ap.add_argument("--config", action="store_true", help="show config")
    ap.add_argument("--webhook", help="webhook URL for channel config")
    ap.add_argument("--channel", help="channel: stdout, slack, teams, email")
    args = ap.parse_args()
    cfg = load_config()

    if args.config:
        if args.webhook or args.channel:
            if args.channel:
                cfg["channel"] = args.channel
            if args.webhook:
                cfg["webhook"] = args.webhook
        Path("run").mkdir(parents=True, exist_ok=True)
        Path(CHANNEL_FILE).write_text(json.dumps(cfg, indent=2))
        print(json.dumps(cfg, indent=2))
        return 0

    if args.emit:
        rec = emit(args.ticket or "T-01", args.sev, args.msg or "", cfg)
        print(json.dumps(rec, indent=2))
        return 0

    if args.stalled:
        pages = check_stalled("run/board.yaml", args.threshold, cfg)
        print(json.dumps({"pages": pages}, indent=2))
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
