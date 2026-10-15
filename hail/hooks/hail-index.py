#!/usr/bin/env python3
"""SessionStart: keep the session index current.

Prints nothing on a clean run. It speaks only when the scan looks
broken, because a guard against a silent failure cannot itself be
silent.
"""
import json
import os
import sys

import importlib.machinery
import importlib.util

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HAIL = os.path.join(PLUGIN_ROOT, "bin", "hail")


def load_tool():
    loader = importlib.machinery.SourceFileLoader("hail", HAIL)
    spec = importlib.util.spec_from_loader("hail", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def main():
    try:
        json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        pass
    if not os.path.exists(HAIL):
        return 0
    try:
        # in-process, not a subprocess: the index path is fixed and
        # unconfigurable, so a subprocess build could not be tested
        # without writing over the real index
        tool = load_tool()
        if tool.CONFIG_SOURCE["fatal"]:
            return 0
        payload, census, refusal = tool.build()
        if refusal:
            print("[hail] index refused: the transcript format may have "
                  "changed. Run: hail doctor")
            return 0
        if payload is None:
            return 0
        tool.write_index(payload)
        if census.get("kept_on_regression"):
            print("[hail] kept %d cached record(s): a rescan lost fields "
                  "it had before. Run: hail doctor"
                  % census["kept_on_regression"])
        elif census.get("user_records_no_cwd"):
            print("[hail] %d transcript(s) had user records but no cwd. "
                  "Run: hail doctor" % census["user_records_no_cwd"])
    except Exception:
        # a hook that raises blocks the thing it was inspecting, and a
        # lost index is never worth a blocked session
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
