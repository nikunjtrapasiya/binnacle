#!/usr/bin/env python3
"""PreToolUse: hold a PR close or a ticket Done when the logbook has items.

Resolves the key cheaply. PR number off the command line first, branch
ticket second, silence third. Never calls `gh pr view`: that is a network
round trip on every merge, and `check` takes either key directly.
"""
import json
import os
import re
import shlex
import subprocess
import sys

import importlib.machinery
import importlib.util

def find_ledger():
    """The tool, whether this file runs in the plugin or as the copy.

    doctor --fix and the session brief copy this file to a flat path
    under the plugin data dir, where the nesting this file sits at in
    the plugin no longer holds. The copy gets a sibling `plugin-root`
    naming the install it came from; without it the copy computed a
    path that never existed and exited silently, so the opt-in tracker
    gate could never fire.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    nested = os.path.join(os.path.dirname(here), "bin", "logbook")
    if os.path.exists(nested):
        return nested
    sidecar = os.path.join(here, "plugin-root")
    try:
        with open(sidecar) as fh:
            root = fh.read().strip()
    except OSError:
        return nested
    return os.path.join(root, "bin", "logbook")


LEDGER = find_ledger()
# number can sit after flags, so scan the segment rather than the next token
PR_NUMBER = re.compile(r"(?<![\w./-])(\d+)(?![\w./-])")
SEGMENT = re.compile(r"[;&|\n]")
# gh must start a command, else a doc or echo mentioning it fires
ENV_PREFIX = re.compile(r"(?:^|\s)\w+=\S*\s*$")


def load_tool():
    loader = importlib.machinery.SourceFileLoader("logbook", LEDGER)
    spec = importlib.util.spec_from_loader("logbook", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def flat(value):
    """Recorded text that cannot start a line of its own.

    An entry may be written from material the agent read, so its text
    is not always the user's. With newlines intact it could close the
    list and add an all-clear, and the human reading the permission
    prompt would see this tool saying the merge was safe.
    """
    text = str(value if value is not None else "")
    return ("\n      ").join(l.rstrip() for l in text.splitlines()) or ""


# wrappers that leave the next word running as the command
WRAPPER = re.compile(
    r"(^|[&|;(\n])\s*(?:\\?(?:command|sudo|env|nohup|xargs|time|"
    r"builtin|exec)\s+(?:-\S+\s+)*)+$")


def in_quotes(command, pos):
    """True when pos sits inside a quoted run.

    A commit message mentioning the phrase should not raise a merge
    prompt: a prompt held for nothing teaches the habit of clicking
    through the real one.
    """
    single = double = False
    i = 0
    while i < pos:
        ch = command[i]
        if ch == "\\" and not single:
            i += 2
            continue
        if ch == "'" and not double:
            single = not single
        elif ch == '"' and not single:
            double = not double
        i += 1
    return single or double


def at_command_start(command, pos):
    if in_quotes(command, pos):
        return False
    head = command[:pos]
    # a leading backslash is the ordinary way to bypass an alias
    if head.rstrip().endswith("\\"):
        head = head.rstrip()[:-1]
    while True:
        stripped = ENV_PREFIX.sub("", head)
        # keep the separator that preceded the wrapper, drop the wrapper
        stripped = WRAPPER.sub(lambda m: m.group(1), stripped)
        if stripped == head:
            break
        head = stripped
    return not head.strip() or head.rstrip()[-1:] in "&|;(\n"


def close_out_pr(command, patterns):
    """(matched, pr number or None)."""
    for raw in patterns:
        try:
            pattern = re.compile(raw)
        except re.error:
            continue
        for match in pattern.finditer(command):
            if not at_command_start(command, match.start()):
                continue
            if match.groups():
                return True, match.group(1)
            tail = SEGMENT.split(command[match.end():])[0]
            return True, positional_pr(tail)
    return False, None


def positional_pr(tail):
    """The number gh would take, not the first one in the line.

    Scanning for any integer read `-t "Release 2 of 3"` as PR 2 and
    `--body "closes 42"` as PR 42, so the gate checked an unrelated PR,
    found it clear, and let the real merge through unexamined.
    """
    try:
        tokens = shlex.split(tail)
    except ValueError:
        tokens = tail.split()
    skip_value = False
    for token in tokens:
        if skip_value:
            skip_value = False
            continue
        if token.startswith("-"):
            # a flag's value is a separate token unless it used `=`
            skip_value = "=" not in token and token not in (
                "--auto", "--squash", "--merge", "--rebase", "--admin",
                "--delete-branch")
            continue
        if token.isdigit():
            return token
        # the first non-flag token is gh's positional slot; if it is not
        # a number there is no PR here and the branch key is the answer
        return None
    return None


def dotted(data, path):
    node = data
    for part in (path or "").split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def tracker_key(data, spec, done_words):
    name = str(dotted(data, spec.get("status_path")) or "")
    opaque = not name and bool(dotted(data, spec.get("opaque_path")))
    if not opaque and not any(w in name.lower() for w in done_words):
        return None
    issue = data.get(spec.get("issue_field") or "")
    return str(issue) if issue else None


def branch_here(cwd):
    try:
        out = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                             cwd=cwd or os.getcwd(), capture_output=True,
                             text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def emit(gate, reason):
    decision = "deny" if gate.get("mode") == "deny" else "ask"
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }}))
    return 0


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not os.path.exists(LEDGER):
        return 0
    tool = load_tool()
    gate = tool.GATE
    if gate.get("mode") == "off":
        return 0
    name = payload.get("tool_name", "")
    data = payload.get("tool_input")
    data = data if isinstance(data, dict) else {}
    key = None
    if name == "Bash":
        matched, pr = close_out_pr(data.get("command") or "",
                                   gate.get("pr_close_patterns") or [])
        if matched:
            if pr:
                key = ("--pr", pr)
            else:
                ticket = tool.infer_ticket(branch_here(payload.get("cwd")))
                key = ("--ticket", ticket) if ticket else None
    else:
        for spec in gate.get("tracker_tools") or []:
            # one entry of the wrong shape used to raise here, and the
            # catch-all exit 0 then disarmed every later spec silently
            if not isinstance(spec, dict) or spec.get("tool") != name:
                continue
            issue = tracker_key(data, spec, gate.get("done_words") or [])
            key = ("--ticket", issue) if issue else None
            break
    if not key:
        return 0

    # only once the command is one we would have acted on: asking on
    # every ls and cat until the config is fixed trains the habit of
    # approving this prompt without reading it, which is the only
    # defence the close-out gate has
    if tool.CONFIG_SOURCE["fatal"]:
        return emit(gate, "logbook cannot check %s %s: config refused: %s"
                          % (key[0], key[1], tool.CONFIG_SOURCE["fatal"]))

    out = subprocess.run([sys.executable, LEDGER, "check", key[0], key[1],
                          "--json"], capture_output=True, text=True,
                         timeout=15)
    result = json.loads(out.stdout or "{}")
    blockers = result.get("blockers") or []
    if not blockers:
        return 0
    lines = ["%s has %d open logbook item(s) before close-out:"
             % (result.get("key", key[1]), len(blockers))]
    for entry in blockers:
        lines.append("  [%s] %s" % (entry.get("kind"), flat(entry.get("text"))))
        for field in tool.SHAPE.get(entry.get("kind"), ()):
            if entry.get(field):
                lines.append("      %s: %s" % (field, flat(entry[field])))
    lines.append("Resolve them, or confirm to proceed anyway.")
    return emit(gate, "\n".join(lines))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
