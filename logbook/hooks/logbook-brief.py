#!/usr/bin/env python3
"""SessionStart: surface open logbook items for this branch.

Prints nothing when nothing is open. Silence is the point; a brief that
fires every session stops being read.
"""
import json
import os
import subprocess
import sys

import importlib.machinery
import importlib.util

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(PLUGIN_ROOT, "bin", "logbook")


def load_tool():
    loader = importlib.machinery.SourceFileLoader("logbook", LEDGER)
    spec = importlib.util.spec_from_loader("logbook", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}

    if not os.path.exists(LEDGER):
        return 0

    tool = load_tool()
    tool.refresh_gate_copy(os.path.join(PLUGIN_ROOT, "hooks",
                                        "logbook-gate.py"))

    cwd = payload.get("cwd") or os.getcwd()
    out = subprocess.run([sys.executable, LEDGER, "brief"], cwd=cwd,
                         capture_output=True, text=True, timeout=15)
    if out.returncode == 4:
        first = (out.stderr or "").strip().splitlines()
        print("[logbook] config refused: %s"
              % (first[0] if first else "see logbook doctor"))
        return 0
    text = out.stdout.strip()
    if text:
        print(text)
    check = subprocess.run([sys.executable, LEDGER, "gate-check"],
                           capture_output=True, text=True, timeout=15)
    if check.stdout.strip():
        print(check.stdout.strip())
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
