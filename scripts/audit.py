#!/usr/bin/env python3
"""
audit.py — Phase 0: secrets + dependency-audit gate.

A fast, dependency-light gate that runs before a ticket's PR and can sit anywhere in the
gates ladder. Two checks:

  1. Secrets scan      — grep source for high-signal patterns (API keys, tokens, passwords,
                         private keys, connection strings). Ignores generated/built dirs and a
                         small allowlist.
  2. Dependency audit  — parses requirements files (pip), package.json (npm), and
                         go.mod (go) for pinned versions, then prints them so a human can
                         eyeball or pipe to a vuln source. Fully offline.

Usage:
    python audit.py --source DIR [--json] [--fail-on SECRET]

Exit codes: 0 = clean, 1 = finding(s) found, 2 = usage error.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

# (name, regex, hint)
PATTERNS = [
    ("github_token", r"github_pat_[A-Za-z0-9_]{20,}", "GitHub PAT"),
    ("github_pat", r"gh[pousr]_[A-Za-z0-9]{20,}", "GitHub token"),
    ("slack", r"xox[baprs]-[A-Za-z0-9-]{10,}", "Slack token"),
    ("aws_key", r"AKIA[0-9A-Z]{16}", "AWS access key"),
    ("google_api", r"AIza[0-9A-Z]{35}", "Google API key"),
    ("stripe", r"sk_live_[0-9A-Z]{20,}", "Stripe secret key"),
    ("openai", r"sk-[A-Za-z0-9]{20,}", "OpenAI key"),
    ("private_key", r"-----BEGIN (RSA |EC |OPENSSH |PGP |)PRIVATE KEY-----", "Private key"),
    ("password_eq", r"(password|passwd|secret)\s*=\s*['\"][^'\"]{6,}['\"]", "password= assignment"),
    ("conn_str", r"(mongodb\+mongodb|postgres|mysql|redis)://[^\s'\"]+", "connection string"),
]

# Directories we never scan.
SKIP_DIRS = {"build", "dist", "node_modules", ".git", "__pycache__", "venv", ".venv",
             ".mypy_cache", ".pytest_cache", "target", ".next", ".turbo"}
SKIP_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".woff", ".woff2", ".ttf",
             ".otf", ".mp4", ".mp3", ".zip", ".gz", ".jar", ".class"}

# (matcher, extractor) for dependency files
DEP_FILES = [
    (lambda p: p.name == "requirements.txt" or p.name == "requirements-dev.txt", "pip"),
    (lambda p: p.name == "package.json", "npm"),
    (lambda p: p.name == "go.mod", "go"),
]


def iter_files(root: Path):
    for p in root.rglob("*"):
        if p.is_dir():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.suffix.lower() in SKIP_EXTS:
            continue
        yield p


def scan_secrets(root: Path):
    findings = []
    for f in iter_files(root):
        try:
            text = f.read_text(errors="replace")
        except Exception:
            continue
        for name, rx, hint in PATTERNS:
            for m in re.finditer(rx, text):
                findings.append({"file": str(f), "pattern": name, "hint": hint})
    return findings


def audit_deps(root: Path):
    pins = []
    for f in root.rglob("*"):
        if not f.is_file():
            continue
        matched = False
        for matcher, engine in DEP_FILES:
            if matcher(f):
                matched = True
                break
        if not matched:
            continue
        try:
            text = f.read_text(errors="replace")
        except Exception:
            continue
        lines = text.splitlines()
        for ln in lines:
            ln = ln.strip().strip("#").strip()
            if not ln:
                continue
            if engine == "pip" and "=" in ln and not ln.startswith("#"):
                pkg = ln.split("=", 1)[0].strip()
                ver = ln.split("=", 1)[1].strip()
                pins.append({"engine": "pip", "package": pkg, "version": ver})
            elif engine == "npm":
                m = re.search(r'"([^"]+)"\s*:\s*"~?\^?([0-9][^"]*)"', ln)
                if m:
                    pins.append({"engine": "npm", "package": m.group(1), "version": m.group(2)})
            elif engine == "go":
                m = re.search(r"\S+\s+v[0-9].*", ln)
                if m:
                    pins.append({"engine": "go", "package": ln.split()[0], "version": ln.split()[1]})
    return pins


def main() -> int:
    ap = argparse.ArgumentParser(description="Secrets + dependency audit gate")
    ap.add_argument("--source", help="source root to scan")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    ap.add_argument("--fail-on", default="SECRET", choices=["SECRET", "DEPS"],
                    help="which finding fails the gate (default: SECRET)")
    args = ap.parse_args()

    root = Path(args.source) if args.source else Path(".")
    secrets = scan_secrets(root)
    deps = audit_deps(root)

    result = {"root": str(root), "secrets": secrets, "dependencies": deps}
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"secrets: {len(secrets)}  deps scanned: {len(deps)}")
        for s in secrets:
            print(f"  SECRET  {s['file']}  ({s['hint']})")
        for d in deps:
            print(f"  dep     {d['package']}=={d['version']}  [{d['engine']}]")

    failed = (args.fail_on == "SECRET" and secrets) or (args.fail_on == "DEPS" and not deps)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
