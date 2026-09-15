#!/usr/bin/env python3
"""Tests for chartroom. Run: python3 -m unittest discover -s tests"""
import contextlib
import datetime
import importlib.machinery
import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHARTROOM_PATH = os.path.join(REPO, "bin", "chartroom")


# What logbook 0.3.0 reports about its own kinds. chartroom reads
# `blocking` from here rather than knowing any kind by name.
DEFAULT_KINDS = {
    "parked": {"requires": ["resume"], "blocking": True},
    "blocked": {"requires": ["unblocked_by"], "blocking": True},
    "followup": {"requires": ["ticket"], "blocking": True, "capped": True},
    "unverified": {"requires": ["verify"], "blocking": True},
    "deploy": {"requires": ["stage", "service", "commit"],
               "blocking": True},
    "decision": {"requires": ["why"], "blocking": False},
}


def load_chartroom():
    """A fresh module, so each test gets its own config at import."""
    loader = importlib.machinery.SourceFileLoader("chartroom",
                                                   CHARTROOM_PATH)
    spec = importlib.util.spec_from_loader("chartroom", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


FAKE_TEMPLATE = """#!/usr/bin/env python3
import sys, time

VERSION = %(version)r
EXIT = %(exit_code)r
STDERR = %(stderr)r
STDOUT = %(stdout)r
SLEEP = %(sleep)r


def main():
    args = sys.argv[1:]
    if args[:1] == ["--version"]:
        if VERSION is None:
            return 2
        sys.stdout.write(VERSION + "\\n")
        return 0
    if SLEEP:
        time.sleep(SLEEP)
    if STDOUT:
        sys.stdout.write(STDOUT)
    if STDERR:
        sys.stderr.write(STDERR)
    return EXIT


sys.exit(main())
"""


class Base(unittest.TestCase):
    """Shared setup only. No test method may live on this class."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = os.path.join(self.tmp.name, "home")
        os.makedirs(os.path.join(self.home, ".claude", "binnacle"))
        for key in ("HOME", "PATH"):
            self.addCleanup(self._restore, key, os.environ.get(key))
        os.environ["HOME"] = self.home

    def _restore(self, key, value):
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    def loaded(self, env=None, config=None):
        """A freshly imported module, optionally under a fake PATH/HOME
        and with config sections patched directly onto its CFG."""
        if env:
            for key in ("PATH", "HOME"):
                if key in env:
                    os.environ[key] = env[key]
        mod = load_chartroom()
        if config:
            for section, values in config.items():
                mod.CFG.setdefault(section, {})
                mod.CFG[section].update(values)
        return mod

    # -- fake sibling executables -----------------------------------

    def _default_logbook_json(self):
        return json.dumps({
            "version": 1,
            "thresholds": {"followup_cap": 3, "followup_expiry_days": 14,
                           "stale_days": 7},
            "kinds": dict(DEFAULT_KINDS),
            "entries": [],
        })

    def _default_hail_json(self, days):
        return json.dumps({
            "version": 1, "built_at": "2026-09-12T00:00:00Z",
            "days": days, "census": {"aged_off": 0}, "sessions": [],
        })

    def _write_fake(self, bindir, name, version, exit_code, stderr,
                    stdout, sleep):
        path = os.path.join(bindir, name)
        with open(path, "w") as fh:
            fh.write(FAKE_TEMPLATE % {
                "version": version, "exit_code": exit_code,
                "stderr": stderr or "", "stdout": stdout or "",
                "sleep": sleep or 0,
            })
        mode = os.stat(path).st_mode
        os.chmod(path, mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    def fake_siblings(self, logbook_present=True, hail_present=True,
                      logbook_version="0.3.0", hail_version="0.2.0",
                      logbook_exit=0, hail_exit=0,
                      logbook_stderr="", hail_stderr="",
                      logbook_stdout=None, hail_stdout=None,
                      logbook_sleep=0, hail_sleep=0, hail_days=10):
        bindir = os.path.join(self.tmp.name, "bin-%d" % id(object()))
        os.makedirs(bindir, exist_ok=True)
        fakehome = os.path.join(self.tmp.name,
                                "fakehome-%d" % id(bindir))
        os.makedirs(os.path.join(fakehome, ".claude", "binnacle"),
                   exist_ok=True)

        if logbook_present:
            stdout = (logbook_stdout if logbook_stdout is not None
                      else self._default_logbook_json())
            self._write_fake(bindir, "logbook", logbook_version,
                             logbook_exit, logbook_stderr, stdout,
                             logbook_sleep)
        if hail_present:
            stdout = (hail_stdout if hail_stdout is not None
                      else self._default_hail_json(hail_days))
            self._write_fake(bindir, "hail", hail_version, hail_exit,
                             hail_stderr, stdout, hail_sleep)

        env = dict(os.environ)
        # Not the inherited PATH. Prepending to it left the real
        # logbook and hail reachable, so once the plugins were actually
        # installed the "sibling is missing" test found one anyway and
        # the suite only passed on a machine without binnacle on it.
        # The interpreter's own directory is here because the fakes
        # start with `#!/usr/bin/env python3`.
        env["PATH"] = os.pathsep.join(
            [bindir, os.path.dirname(sys.executable), "/usr/bin", "/bin"])
        env["HOME"] = fakehome
        return env

    def page_path(self, env):
        return os.path.join(env["HOME"], ".claude", "binnacle",
                            "chartroom", "chartroom.html")

    def write_config(self, body, home=None):
        """A config on disk for the next import or subprocess. A string
        is written as-is, so a test can plant one that does not parse."""
        path = os.path.join(home or self.home, ".claude", "binnacle",
                           "chartroom.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(body if isinstance(body, str) else json.dumps(body))
        return path

    def run_chartroom(self, env, *args, config=None, timeout_seconds=None):
        body = dict(config or {})
        if timeout_seconds is not None:
            tools = dict(body.get("tools") or {})
            tools["timeout_seconds"] = timeout_seconds
            body["tools"] = tools
        if body:
            body.setdefault("version", 1)
            cfg_path = os.path.join(env["HOME"], ".claude", "binnacle",
                                    "chartroom.json")
            os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
            with open(cfg_path, "w") as fh:
                json.dump(body, fh)
        return subprocess.run(
            [sys.executable, CHARTROOM_PATH] + list(args),
            capture_output=True, text=True, env=env, timeout=30)

    def tree(self, env):
        out = []
        for root, _dirs, files in os.walk(env["HOME"]):
            for name in files:
                out.append(os.path.relpath(os.path.join(root, name),
                                           env["HOME"]))
        return sorted(out)

    # -- data fixtures -------------------------------------------------

    def entry(self, eid, **overrides):
        """One logbook entry, carrying no key until a test gives it
        one, so a row can be built at any of the four levels."""
        record = {"id": eid, "kind": "unverified", "status": "open",
                 "ts": "2026-09-11T09:00:00", "text": "entry %s" % eid}
        record.update(overrides)
        return record

    def session(self, index, **overrides):
        """One hail session, likewise keyless until a test says
        otherwise. The id is minted from the index, never a real one."""
        record = {"id": "0000000a-0000-4000-8000-%012d" % index,
                 "title": "session %d" % index, "cwd": None, "turns": 3,
                 "first_ts": "2026-09-10T09:00:00Z",
                 "last_ts": "2026-09-12T09:00:00Z",
                 "branches": [], "tickets_from_branch": [], "prs": []}
        record.update(overrides)
        return record

    def logbook_body(self, tickets=None, prs=None, session=None,
                     count=None, include_keyless=False, entries=None):
        thresholds = {"followup_cap": 3, "followup_expiry_days": 14,
                     "stale_days": 7}
        kinds = dict(DEFAULT_KINDS)
        if entries is not None:
            return {"version": 1, "thresholds": thresholds,
                   "kinds": kinds, "entries": list(entries)}
        entries = []
        if count:
            for i in range(count):
                entry = {"id": "e%04d" % i, "kind": "unverified",
                         "status": "open",
                         "ts": "2026-09-%02dT09:00:00" % (1 + i % 28),
                         "text": "entry %d" % i}
                if not (include_keyless and i % 7 == 0):
                    entry["ticket"] = "ABC-%d" % (100 + i)
                entries.append(entry)
            return {"version": 1, "thresholds": thresholds,
                   "kinds": kinds, "entries": entries}

        if prs is not None:
            for i, number in enumerate(prs):
                entries.append({"id": "p%03d" % i, "kind": "unverified",
                                "status": "open",
                                "ts": "2026-09-11T09:00:00",
                                "text": "pr entry", "pr": number})
            return {"version": 1, "thresholds": thresholds,
                   "kinds": kinds, "entries": entries}

        for i, ticket in enumerate(tickets or ["ABC-241"]):
            entry = {"id": "a%05d" % i, "kind": "unverified",
                     "status": "open", "ticket": ticket,
                     "ts": "2026-09-11T09:00:00", "text": "verify x"}
            if session:
                entry["session"] = session
            entries.append(entry)
        return {"version": 1, "thresholds": thresholds, "kinds": kinds,
               "entries": entries}

    def hail_body(self, prs=None, days=10, sessions=None, count=None,
                 mixed_keys=False, aged_off=0):
        if sessions is not None:
            recs = sessions
        elif count:
            recs = []
            for i in range(count):
                sid = "%08x-0000-4000-8000-%012d" % (i, i)
                rec = {"id": sid, "title": "session %d" % i,
                      "cwd": "/home/u/code", "turns": 5,
                      "first_ts": "2026-09-10T09:00:00Z",
                      "last_ts": "2026-09-12T09:00:00Z",
                      "branches": [], "tickets_from_branch": [], "prs": []}
                variant = i % 4 if mixed_keys else 0
                if variant == 0:
                    rec["tickets_from_branch"] = ["ABC-%d" % i]
                    rec["branches"] = ["abc-%d-thing" % i]
                elif variant == 1:
                    rec["prs"] = [{"number": 2000 + i, "repo": "o/r"}]
                elif variant == 2:
                    rec["branches"] = ["feat/x-%d" % i]
                else:
                    rec["cwd"] = "/home/u/code/dir-%d" % i
                recs.append(rec)
        elif prs is not None:
            recs = [{
                "id": "9f000000-0000-4000-8000-000000000001",
                "title": "pr session", "cwd": "/home/u/code", "turns": 3,
                "first_ts": "2026-09-10T09:00:00Z",
                "last_ts": "2026-09-11T09:00:00Z",
                "branches": [], "tickets_from_branch": [], "prs": prs,
            }] if prs else []
        else:
            recs = [{
                "id": "00000000-0000-4000-8000-000000000001",
                "title": "tune the alert threshold",
                "cwd": "/home/u/code", "turns": 41,
                "first_ts": "2026-09-10T09:00:00Z",
                "last_ts": "2026-09-12T09:00:00Z",
                "branches": ["abc-241-thing"],
                "tickets_from_branch": ["ABC-241"],
                "prs": [{"number": 4242, "repo": "o/r"}],
            }]
        return {"version": 1, "built_at": "2026-09-12T09:00:00Z",
               "days": days, "census": {"aged_off": aged_off},
               "sessions": recs}

    def row(self, items, key):
        for item in items:
            if item["key"] == key:
                return item
        self.fail("no row for key %r" % key)

    def meta(self, **overrides):
        base = {"built_at": "2026-09-12T00:00:00Z", "days": 10,
               "stale_days": 7, "aged_off": 0,
               "versions": {"logbook": "0.3.0", "hail": "0.2.0"}}
        base.update(overrides)
        return base

    def items(self, branch=None, prompts=None):
        session = {
            "id": "00000000-0000-4000-8000-000000000001",
            "title": "tune the alert threshold",
            "cwd": "/home/u/code",
            "turns": 41,
            "first_ts": "2026-09-10T09:00:00Z",
            "last_ts": "2026-09-12T09:00:00Z",
            "branches": [branch] if branch else ["xyz-241-thing"],
            "tickets_from_branch": ["XYZ-241"],
            "prs": [{"number": 4242, "repo": "o/r", "url": "x"}],
        }
        if prompts is not None:
            session["prompts"] = prompts
            session["last_prompt"] = prompts[0] if prompts else ""
        entry = {"id": "e91c3f", "kind": "unverified", "ticket": "XYZ-241",
                "status": "open", "ts": "2026-09-11T09:00:00",
                "text": "verify x", "session": session["id"]}
        return [{"key": "XYZ-241", "via": "ticket", "label": "XYZ-241",
                "obligations": [entry], "aside": [], "sessions": [session],
                "aged_out": 0}]

    def embedded(self, page_html):
        marker = "const CHARTROOM_DATA = "
        start = page_html.index(marker) + len(marker)
        end = page_html.index(";</script>", start)
        return json.loads(page_html[start:end])


class Config(Base):
    """What the loader does with each shape of config file, and what
    each outcome does to a run. A loader that quietly accepts anything
    is a page built from settings nobody chose."""

    def test_defaults_when_there_is_no_config_file(self):
        mod = self.loaded()
        self.assertEqual(mod.CFG, mod.DEFAULTS)
        self.assertEqual(mod.CONFIG_SOURCE["warnings"], [])
        self.assertIsNone(mod.CONFIG_SOURCE["fatal"])

    def test_an_unknown_key_warns_and_the_run_continues(self):
        self.write_config({"version": 1, "nope": {}, "page": {"nope": 1}})
        mod = self.loaded()
        self.assertIsNone(mod.CONFIG_SOURCE["fatal"])
        self.assertEqual(len(mod.CONFIG_SOURCE["warnings"]), 2)
        self.assertTrue(any("nope" in w
                            for w in mod.CONFIG_SOURCE["warnings"]))
        self.assertEqual(mod.CFG["page"], mod.DEFAULTS["page"])

    def test_a_wrong_type_keeps_the_default_and_warns(self):
        self.write_config({"version": 1, "rows": {"only_open": "yes"},
                           "tools": {"timeout_seconds": "20"}})
        mod = self.loaded()
        self.assertIs(mod.CFG["rows"]["only_open"], True)
        self.assertEqual(mod.CFG["tools"]["timeout_seconds"], 20)
        for key in ("rows.only_open", "tools.timeout_seconds"):
            self.assertTrue(any(key in w
                                for w in mod.CONFIG_SOURCE["warnings"]),
                            key)

    def test_a_config_at_another_version_is_fatal(self):
        self.write_config({"version": 2, "rows": {"blocking_only": False}})
        mod = self.loaded()
        self.assertIn("version", mod.CONFIG_SOURCE["fatal"])
        self.assertIs(mod.CFG["rows"]["blocking_only"], True)

    def test_a_config_that_does_not_parse_is_fatal(self):
        self.write_config("{ not json")
        self.assertIsNotNone(self.loaded().CONFIG_SOURCE["fatal"])

    def test_a_config_that_is_not_an_object_is_fatal(self):
        self.write_config("[]")
        self.assertIsNotNone(self.loaded().CONFIG_SOURCE["fatal"])

    def test_build_refuses_under_a_fatal_config_and_doctor_reports(self):
        # doctor is the one command that must still answer, because it
        # is the command that says what is wrong with the config
        env = self.fake_siblings()
        self.write_config({"version": 2}, home=env["HOME"])
        build = self.run_chartroom(env, "build")
        self.assertEqual(build.returncode, 4)
        self.assertIn("version", build.stderr)
        self.assertFalse(os.path.exists(self.page_path(env)))
        doctor = self.run_chartroom(env, "doctor")
        self.assertEqual(doctor.returncode, 4)
        self.assertIn("fatal:", doctor.stdout)


class Version(Base):
    """chartroom's own version. A marketplace install reads it out of
    the manifest, so the two drifting apart is a shipped lie."""

    def test_the_version_flag_prints_and_exits_zero(self):
        out = subprocess.run([sys.executable, CHARTROOM_PATH, "--version"],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0)
        self.assertRegex(out.stdout.strip(), r"^\d+\.\d+\.\d+$")

    def test_the_binary_and_the_manifest_agree(self):
        mod = self.loaded()
        manifest = os.path.join(REPO, ".claude-plugin", "plugin.json")
        with open(manifest) as fh:
            self.assertEqual(json.load(fh)["version"], mod.VERSION)

    def test_the_version_answers_under_a_broken_config(self):
        # main checks argv[0] before the fatal-config branch, so this
        # keeps working when nothing else does
        env = self.fake_siblings()
        self.write_config("{ not json", home=env["HOME"])
        out = subprocess.run([sys.executable, CHARTROOM_PATH, "--version"],
                             capture_output=True, text=True, env=env)
        self.assertEqual(out.returncode, 0)
        self.assertRegex(out.stdout.strip(), r"^\d+\.\d+\.\d+$")


class Siblings(Base):

    def test_a_good_pair_is_read(self):
        env = self.fake_siblings(logbook_version="0.2.0",
                                 hail_version="0.2.0")
        mod = self.loaded(env)
        self.assertEqual(mod.read_sibling("logbook")["version"], 1)

    def test_a_sibling_too_old_is_exit_four(self):
        env = self.fake_siblings(logbook_version=None)
        self.assertEqual(self.run_chartroom(env, "build").returncode, 4)

    def test_a_sibling_missing_from_path_is_exit_four(self):
        env = self.fake_siblings(logbook_present=False)
        out = self.run_chartroom(env, "build")
        self.assertEqual(out.returncode, 4)
        self.assertIn("logbook", out.stderr)

    def test_a_version_that_is_not_a_version_is_exit_four(self):
        env = self.fake_siblings(logbook_version="dev-build")
        self.assertEqual(self.run_chartroom(env, "build").returncode, 4)

    def test_a_sibling_below_the_floor_is_exit_four(self):
        env = self.fake_siblings(logbook_version="0.1.9")
        self.assertEqual(self.run_chartroom(env, "build").returncode, 4)

    def test_a_fatal_config_in_a_sibling_is_exit_four(self):
        env = self.fake_siblings(logbook_exit=4,
                                 logbook_stderr="refused: bad config")
        out = self.run_chartroom(env, "build")
        self.assertEqual(out.returncode, 4)
        self.assertIn("bad config", out.stderr)

    def test_an_index_that_predates_hail_is_exit_four(self):
        env = self.fake_siblings(hail_exit=1,
                                 hail_stderr="index predates this hail")
        self.assertEqual(self.run_chartroom(env, "build").returncode, 4)

    def test_unparseable_output_is_exit_five(self):
        env = self.fake_siblings(hail_stdout="not json at all")
        self.assertEqual(self.run_chartroom(env, "build").returncode, 5)

    def test_a_timeout_is_exit_five(self):
        env = self.fake_siblings(hail_sleep=5)
        self.assertEqual(
            self.run_chartroom(env, "build", timeout_seconds=1).returncode,
            5)

    def test_no_file_is_written_on_any_failure_path(self):
        env = self.fake_siblings(hail_stdout="not json at all")
        self.run_chartroom(env, "build")
        self.assertFalse(os.path.exists(self.page_path(env)))

    # -- the envelope, not just the JSON -------------------------------
    #
    # The version check is a floor with no ceiling, so a future sibling
    # that renames a key parses fine and renders "0 open" - the worst
    # answer available from a tool whose whole claim is what is
    # outstanding, and indistinguishable from an empty ledger. Each of
    # these must be a named refusal, never a traceback and never a
    # quietly empty page.

    def test_a_sibling_returning_a_list_is_exit_five(self):
        env = self.fake_siblings(logbook_stdout="[]")
        out = self.run_chartroom(env, "build")
        self.assertEqual(out.returncode, 5)
        self.assertNotIn("Traceback", out.stderr)

    def test_a_sibling_returning_a_bare_string_is_exit_five(self):
        env = self.fake_siblings(hail_stdout="\"nothing to report\"")
        out = self.run_chartroom(env, "build")
        self.assertEqual(out.returncode, 5)
        self.assertNotIn("Traceback", out.stderr)

    def test_an_envelope_with_no_entries_is_exit_five(self):
        env = self.fake_siblings(logbook_stdout=json.dumps(
            {"version": 1, "thresholds": {}}))
        out = self.run_chartroom(env, "build")
        self.assertEqual(out.returncode, 5)
        self.assertIn("entries", out.stderr)
        self.assertNotIn("Traceback", out.stderr)

    def test_an_envelope_with_no_sessions_is_exit_five(self):
        env = self.fake_siblings(hail_stdout=json.dumps(
            {"version": 1, "days": 10, "census": {}}))
        out = self.run_chartroom(env, "build")
        self.assertEqual(out.returncode, 5)
        self.assertIn("sessions", out.stderr)
        self.assertNotIn("Traceback", out.stderr)

    def test_an_envelope_whose_entries_are_not_a_list_is_exit_five(self):
        env = self.fake_siblings(logbook_stdout=json.dumps(
            {"version": 1, "thresholds": {}, "entries": {}}))
        out = self.run_chartroom(env, "build")
        self.assertEqual(out.returncode, 5)
        self.assertNotIn("Traceback", out.stderr)


class Keys(Base):
    """Which rows one record lands on. Entries and sessions go through
    the same two functions, so a key an entry can reach is a key a
    session can reach."""

    def test_a_session_with_two_branch_tickets_appears_under_both(self):
        mod = self.loaded()
        self.assertEqual(
            mod.rows_for({"tickets_from_branch": ["ABC-1", "ABC-2"]},
                         set()),
            [("ticket", "", "ABC-1"), ("ticket", "", "ABC-2")])

    def test_a_ticketed_session_does_not_also_key_by_branch(self):
        mod = self.loaded()
        record = {"tickets_from_branch": ["ABC-1"],
                  "branches": ["abc-1-thing"]}
        self.assertEqual(mod.rows_for(record, set()),
                         [("ticket", "", "ABC-1")])
        # the branch is still a level the record answers at: that is
        # what witnesses the alias, and it lands on no row of its own
        self.assertIn(("branch", "", "abc-1-thing"),
                      mod.all_keys(record, set()))

    def test_a_body_only_ticket_falls_through_to_the_branch(self):
        mod = self.loaded()
        self.assertEqual(
            mod.rows_for({"tickets": ["ABC-9"],
                          "tickets_from_branch": [],
                          "branches": ["feat/x"]}, set()),
            [("branch", "", "feat/x")])

    def test_a_pr_dict_and_a_pr_number_meet(self):
        mod = self.loaded()
        self.assertEqual(
            mod.rows_for({"prs": [{"number": 4242, "repo": "o/r"}]},
                         set()),
            mod.rows_for({"pr": 4242}, set()))

    def test_a_pr_with_no_number_falls_through(self):
        mod = self.loaded()
        self.assertEqual(
            mod.rows_for({"prs": [{"number": None}],
                          "branches": ["feat/x"]}, set()),
            [("branch", "", "feat/x")])

    def test_a_keyless_entry_keys_by_branch_then_path(self):
        mod = self.loaded()
        self.assertEqual(mod.rows_for({"branch": "feat/x"}, set()),
                         [("branch", "", "feat/x")])
        entry = {"repo_path": "/home/u/code"}
        self.assertEqual(mod.rows_for(entry, mod.repo_roots([entry])),
                         [("dir", "", "/home/u/code")])

    def test_an_entry_from_outside_a_repo_is_unkeyed_not_empty(self):
        mod = self.loaded()
        self.assertEqual(mod.rows_for({"id": "a1"}, set()), [mod.UNKEYED])

    def test_no_record_on_either_side_ever_gets_an_empty_row_list(self):
        mod = self.loaded()
        for record in ({}, {"id": "a1"}, {"branch": "main"},
                       {"prs": [{"number": None}]}, {"repo_path": "  "}):
            self.assertTrue(mod.rows_for(record, set()), record)

    def test_a_branch_that_names_no_particular_work_is_dropped(self):
        # spelled out rather than read back off the constant: a test
        # that iterates the set it is pinning passes on an empty one
        mod = self.loaded()
        for name in ("HEAD", "main", "master", "develop", "trunk"):
            self.assertIn(name, mod.UNSCOPED_BRANCHES, name)
            self.assertEqual(mod.rows_for({"branch": name}, set()),
                             [mod.UNKEYED], name)

    def test_the_longest_checkout_root_claims_a_path(self):
        mod = self.loaded()
        roots = {"/home/u/code", "/home/u/code/vendor/dep"}
        self.assertEqual(mod.place_of("/home/u/code/vendor/dep/src", roots),
                         "/home/u/code/vendor/dep")
        self.assertEqual(mod.place_of("/home/u/code/services/x", roots),
                         "/home/u/code")
        self.assertEqual(mod.place_of("/elsewhere/entirely", roots),
                         "/elsewhere/entirely")


class Join(Base):

    def test_an_entry_and_a_session_sharing_a_key_land_in_one_row(self):
        mod = self.loaded()
        items = mod.build_items(self.logbook_body(), self.hail_body())
        row = self.row(items, "ABC-241")
        self.assertEqual(len(row["obligations"]), 1)
        self.assertEqual(len(row["sessions"]), 1)

    def test_an_entry_with_no_session_still_gets_a_row(self):
        mod = self.loaded()
        items = mod.build_items(
            self.logbook_body(tickets=["ABC-777"]), self.hail_body())
        self.assertEqual(self.row(items, "ABC-777")["sessions"], [])

    def test_a_session_with_no_entry_still_gets_a_row(self):
        mod = self.loaded()
        items = mod.build_items({"entries": [], "thresholds": {}},
                                self.hail_body())
        self.assertTrue(items)

    def test_the_pr_label_uses_the_repo_when_hail_knows_it(self):
        mod = self.loaded()
        items = mod.build_items(self.logbook_body(prs=[4242]),
                                self.hail_body(prs=[{"number": 4242,
                                                     "repo": "o/r"}]))
        self.assertEqual(self.row(items, "4242")["label"], "o/r#4242")

    def test_the_pr_label_is_bare_when_only_logbook_knows_it(self):
        mod = self.loaded()
        items = mod.build_items(self.logbook_body(prs=[4242]),
                                self.hail_body(prs=[]))
        self.assertEqual(self.row(items, "4242")["label"], "#4242")


class Checkouts(Base):
    """A PR number is unique inside its repository and a branch name
    inside its checkout. Both meet across checkouts in one dataset, and
    what the join does about it decides whether unrelated work merges."""

    def test_one_pr_number_in_two_checkouts_is_two_rows(self):
        mod = self.loaded()
        entries = [self.entry("e1", pr=42, repo_path="/home/u/alpha"),
                   self.entry("e2", pr=42, repo_path="/home/u/beta")]
        sessions = [
            self.session(0, cwd="/home/u/alpha/services/x",
                         prs=[{"number": 42, "repo": "o/alpha"}]),
            self.session(1, cwd="/home/u/beta",
                         prs=[{"number": 42, "repo": "o/beta"}]),
        ]
        items = mod.build_items(self.logbook_body(entries=entries),
                                self.hail_body(sessions=sessions))
        self.assertEqual(len(items), 2)
        self.assertEqual(sorted(i["label"] for i in items),
                         ["o/alpha#42", "o/beta#42"])
        for item in items:
            self.assertEqual(len(item["obligations"]), 1)
            self.assertEqual(len(item["sessions"]), 1)

    def test_a_pr_in_one_checkout_still_joins_a_session_with_no_path(self):
        # the common case: hail saw no cwd, or the session ran outside
        # any repository. Scoping every PR number would split this row.
        mod = self.loaded()
        entries = [self.entry("e1", pr=99, repo_path="/home/u/alpha")]
        sessions = [self.session(0, prs=[{"number": 99, "repo": "o/alpha"}])]
        items = mod.build_items(self.logbook_body(entries=entries),
                                self.hail_body(sessions=sessions))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["label"], "o/alpha#99")
        self.assertEqual(len(items[0]["obligations"]), 1)
        self.assertEqual(len(items[0]["sessions"]), 1)

    def test_an_obligation_keyed_only_by_pr_meets_the_ticket_row(self):
        mod = self.loaded()
        entries = [self.entry("e1", pr=77)]
        sessions = [self.session(0, cwd="/home/u/code",
                                 branches=["abc-5-thing"],
                                 tickets_from_branch=["ABC-5"],
                                 prs=[{"number": 77, "repo": "o/r"}])]
        items = mod.build_items(self.logbook_body(entries=entries),
                                self.hail_body(sessions=sessions))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["key"], "ABC-5")
        self.assertEqual(items[0]["via"], "ticket")
        self.assertEqual(len(items[0]["obligations"]), 1)
        self.assertEqual(len(items[0]["sessions"]), 1)

    def test_a_weak_key_seen_beside_two_tickets_binds_to_neither(self):
        mod = self.loaded()
        entries = [self.entry("e1", pr=55)]
        sessions = [
            self.session(0, tickets_from_branch=["ABC-1"],
                         prs=[{"number": 55, "repo": "o/r"}]),
            self.session(1, tickets_from_branch=["ABC-2"],
                         prs=[{"number": 55, "repo": "o/r"}]),
        ]
        items = mod.build_items(self.logbook_body(entries=entries),
                                self.hail_body(sessions=sessions))
        self.assertEqual(sorted(i["key"] for i in items),
                         ["55", "ABC-1", "ABC-2"])
        self.assertEqual(len(self.row(items, "55")["obligations"]), 1)
        self.assertEqual(self.row(items, "55")["sessions"], [])
        for key in ("ABC-1", "ABC-2"):
            self.assertEqual(self.row(items, key)["obligations"], [])
            self.assertEqual(len(self.row(items, key)["sessions"]), 1)

    def test_main_master_and_a_detached_head_do_not_merge(self):
        mod = self.loaded()
        sessions = [self.session(0, cwd="/home/u/one", branches=["main"]),
                    self.session(1, cwd="/home/u/two", branches=["master"]),
                    self.session(2, cwd="/home/u/three", branches=["HEAD"])]
        items = mod.build_items(self.logbook_body(entries=[]),
                                self.hail_body(sessions=sessions))
        self.assertEqual(sorted(i["key"] for i in items),
                         ["/home/u/one", "/home/u/three", "/home/u/two"])
        self.assertEqual([i["via"] for i in items], ["dir"] * 3)

    def test_an_entry_at_the_toplevel_joins_a_session_below_it(self):
        mod = self.loaded()
        entries = [self.entry("e1", repo_path="/home/u/code")]
        sessions = [self.session(0, cwd="/home/u/code/services/matters")]
        items = mod.build_items(self.logbook_body(entries=entries),
                                self.hail_body(sessions=sessions))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["key"], "/home/u/code")
        self.assertEqual(items[0]["via"], "dir")
        self.assertEqual(len(items[0]["obligations"]), 1)
        self.assertEqual(len(items[0]["sessions"]), 1)

    def test_a_truncated_repo_path_mints_no_phantom_row(self):
        mod = self.loaded()
        entries = [self.entry("e1", repo_path="/home/u/code"),
                   self.entry("e2",
                              repo_path="/home/u/code/services/ma...")]
        self.assertEqual(mod.repo_roots(entries), {"/home/u/code"})
        items = mod.build_items(self.logbook_body(entries=entries),
                                self.hail_body(sessions=[]))
        self.assertEqual(sorted(i["key"] for i in items),
                         ["", "/home/u/code"])
        self.assertEqual(self.row(items, "")["via"], "unkeyed")


class UnnamedPrs(Base):
    """A PR the ledger never names is not evidence of what a session
    worked on.

    Claude Code stamps a session with a PR of its own accord, and it
    gets that wrong: one session here carried 720 records claiming a PR
    merged months earlier on somebody else's branch. hail records what
    the harness says, correctly. Left at full rank, one such claim
    outranks the branch and carries the session off its own work item,
    leaving the obligations with no session and the PR with no
    obligations."""

    def test_a_pr_no_obligation_names_falls_through_to_the_branch(self):
        mod = self.loaded()
        entries = [self.entry("e1", branch="feat/export")]
        sessions = [self.session(0, branches=["feat/export"],
                                 prs=[{"number": 12, "repo": "o/r"}])]
        items = mod.build_items(self.logbook_body(entries=entries),
                                self.hail_body(sessions=sessions))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["key"], "feat/export")
        self.assertEqual(items[0]["via"], "branch")
        self.assertEqual(len(items[0]["obligations"]), 1)
        self.assertEqual(len(items[0]["sessions"]), 1)

    def test_a_pr_an_obligation_names_still_outranks_the_branch(self):
        mod = self.loaded()
        entries = [self.entry("e1", pr=12)]
        sessions = [self.session(0, branches=["feat/export"],
                                 prs=[{"number": 12, "repo": "o/r"}])]
        items = mod.build_items(self.logbook_body(entries=entries),
                                self.hail_body(sessions=sessions))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["via"], "pr")
        self.assertEqual(len(items[0]["obligations"]), 1)
        self.assertEqual(len(items[0]["sessions"]), 1)

    def test_an_obligation_carrying_a_pr_always_names_its_own(self):
        # the set is built from the obligations themselves, so an
        # entry can never demote the key it is the evidence for
        mod = self.loaded()
        entries = [self.entry("e1", pr=77, branch="feat/x")]
        items = mod.build_items(self.logbook_body(entries=entries),
                                self.hail_body(sessions=[]))
        self.assertEqual(items[0]["via"], "pr")
        self.assertEqual(items[0]["key"], "77")

    def test_a_demoted_pr_with_no_branch_falls_to_the_directory(self):
        mod = self.loaded()
        entries = [self.entry("e1", repo_path="/home/u/code")]
        sessions = [self.session(0, cwd="/home/u/code",
                                 prs=[{"number": 12, "repo": "o/r"}])]
        items = mod.build_items(self.logbook_body(entries=entries),
                                self.hail_body(sessions=sessions))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["via"], "dir")
        self.assertEqual(len(items[0]["sessions"]), 1)

    def test_a_ticket_still_outranks_a_pr_the_ledger_names(self):
        mod = self.loaded()
        entries = [self.entry("e1", ticket="ABC-1", pr=12)]
        sessions = [self.session(0, tickets_from_branch=["ABC-1"],
                                 prs=[{"number": 12, "repo": "o/r"}])]
        items = mod.build_items(self.logbook_body(entries=entries),
                                self.hail_body(sessions=sessions))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["via"], "ticket")

    def test_a_demoted_pr_binds_no_alias(self):
        # an unnamed PR must not reach build_alias either: binding it
        # to a ticket would put the false claim back on the page by
        # another road
        mod = self.loaded()
        entries = [self.entry("e1", ticket="ABC-1"),
                   self.entry("e2", branch="feat/export")]
        sessions = [self.session(0, tickets_from_branch=["ABC-1"],
                                 prs=[{"number": 12, "repo": "o/r"}]),
                    self.session(1, branches=["feat/export"],
                                 prs=[{"number": 12, "repo": "o/r"}])]
        items = mod.build_items(self.logbook_body(entries=entries),
                                self.hail_body(sessions=sessions))
        branch_row = self.row(items, "feat/export")
        self.assertEqual(len(branch_row["sessions"]), 1)
        self.assertEqual(len(branch_row["obligations"]), 1)

    def test_every_pr_demotes_when_the_ledger_names_none(self):
        mod = self.loaded()
        sessions = [self.session(0, branches=["feat/a"],
                                 prs=[{"number": 1, "repo": "o/r"}]),
                    self.session(1, branches=["feat/b"],
                                 prs=[{"number": 2, "repo": "o/r"}])]
        items = mod.build_items({"entries": [], "thresholds": {},
                                 "kinds": dict(DEFAULT_KINDS)},
                                self.hail_body(sessions=sessions))
        self.assertEqual(sorted(i["key"] for i in items),
                         ["feat/a", "feat/b"])


class Render(Base):

    def destamped(self, page, stamp):
        """The page with both renderings of one build time removed.

        The stamp reaches the page twice: UTC in the embedded data, and
        the reader's own wall clock in the masthead. A normaliser that
        knows only the first leaves the second behind and reports a
        difference that is still just the timestamp.
        """
        mod = self.loaded()
        return page.replace(stamp, "STAMP").replace(
            mod._local_stamp(stamp), "STAMP")

    def test_a_hostile_branch_name_renders_inert(self):
        mod = self.loaded()
        html = mod.render(
            self.items(branch="</script><script>alert(1)</script>"),
            self.meta())
        self.assertNotIn("<script>alert(1)</script>", html)

    def test_two_builds_differ_only_in_the_timestamp(self):
        # The probes are whole timestamps, not single letters. A
        # one-character probe makes this a test that the page contains
        # no capital A or B anywhere, which is a property of the
        # stylesheet and the fixtures rather than of determinism, and
        # the only way to pass it is to deform the page.
        #
        # Same calendar day on purpose. Severity is aged against
        # built_at, so two builds either side of a staleness boundary
        # are meant to differ in more than the stamp - that is the
        # point of aging, and a neighbouring test pins it.
        first = "2026-09-20T00:00:00Z"
        second = "2026-09-20T23:59:59Z"
        mod = self.loaded()
        a = mod.render(self.items(), self.meta(built_at=first))
        b = mod.render(self.items(), self.meta(built_at=second))
        self.assertNotEqual(a, b)
        self.assertEqual(self.destamped(a, first),
                         self.destamped(b, second))

    def test_the_same_input_twice_is_byte_identical(self):
        mod = self.loaded()
        stamp = "2026-01-01T00:00:00Z"
        self.assertEqual(mod.render(self.items(), self.meta(built_at=stamp)),
                         mod.render(self.items(), self.meta(built_at=stamp)))

    def test_the_page_carries_no_prompt_text(self):
        mod = self.loaded()
        html = mod.render(self.items(prompts=["SENTINEL-PROMPT"]),
                          self.meta())
        self.assertNotIn("SENTINEL-PROMPT", html)

    def test_the_page_carries_only_the_allowlist(self):
        mod = self.loaded()
        data = self.embedded(mod.render(self.items(), self.meta()))
        self.assertEqual(
            sorted(data["items"][0]["sessions"][0]),
            sorted(["id", "title", "cwd", "turns", "first_ts", "last_ts",
                    "branches", "tickets_from_branch", "prs"]))

    def test_the_page_carries_only_the_obligation_allowlist(self):
        mod = self.loaded()
        items = self.items()
        items[0]["obligations"][0].update(
            {"why": "SENTINEL-WHY", "verify": "SENTINEL-VERIFY",
             "resume": "SENTINEL-RESUME", "note": "SENTINEL-NOTE"})
        page = mod.render(items, self.meta())
        for sentinel in ("SENTINEL-WHY", "SENTINEL-VERIFY",
                         "SENTINEL-RESUME", "SENTINEL-NOTE"):
            self.assertNotIn(sentinel, page, sentinel)
        data = self.embedded(page)
        self.assertEqual(sorted(data["items"][0]["obligations"][0]),
                         sorted(["id", "kind", "ts", "text", "session"]))

    def test_the_page_declares_a_doctype_a_charset_and_a_policy(self):
        mod = self.loaded()
        html = mod.render(self.items(), self.meta())
        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertIn("<meta charset=\"utf-8\">", html)
        self.assertIn("http-equiv=\"Content-Security-Policy\"", html)
        self.assertIn("default-src 'none'", html)

    def test_two_builds_of_one_input_on_one_day_differ_only_in_the_stamp(self):
        # the whole pipeline this time, not a hand-built item list:
        # build_items ages the strip and render ages the severity, and
        # either reaching for the clock would show up here.
        mod = self.loaded()
        first = "2026-09-20T00:00:00Z"
        second = "2026-09-20T23:59:59Z"
        logbook_body = self.logbook_body()
        hail_body = self.hail_body()
        a = mod.render(mod.build_items(logbook_body, hail_body, first),
                       self.meta(built_at=first))
        b = mod.render(mod.build_items(logbook_body, hail_body, second),
                       self.meta(built_at=second))
        self.assertNotEqual(a, b)
        self.assertEqual(self.destamped(a, first),
                         self.destamped(b, second))

    def test_session_ids_are_full_uuids(self):
        mod = self.loaded()
        data = self.embedded(mod.render(self.items(), self.meta()))
        self.assertEqual(len(data["items"][0]["sessions"][0]["id"]), 36)

    def test_the_resume_string_matches_the_siblings(self):
        mod = self.loaded()
        html = mod.render(self.items(), self.meta())
        self.assertIn("cd /home/u/code &amp;&amp; claude -r", html)

    def test_the_page_loads_no_network_resource(self):
        mod = self.loaded()
        html = mod.render(self.items(), self.meta())
        for marker in ("http://", "https://", "//cdn"):
            self.assertNotIn(marker, html)


class OnlyOpen(Base):
    """Rows with nothing owed, and the preview that replaces a click."""

    def pair(self):
        """One row that owes something, one that owes nothing."""
        owed = self.items()[0]
        idle = dict(owed, key="XYZ-999", label="XYZ-999", obligations=[])
        return [owed, idle]

    def test_a_row_with_nothing_open_is_dropped_by_default(self):
        mod = self.loaded()
        kept, hidden = mod.only_open_rows(self.pair())
        self.assertEqual([i["key"] for i in kept], ["XYZ-241"])
        self.assertEqual(hidden, 1)

    def test_only_open_false_keeps_every_row(self):
        mod = self.loaded(config={"rows": {"only_open": False}})
        kept, hidden = mod.only_open_rows(self.pair())
        self.assertEqual(len(kept), 2)
        self.assertEqual(hidden, 0)

    def test_the_masthead_shows_the_build_time_in_local_time(self):
        """A reader should not convert from UTC in their head.

        Computed rather than hardcoded: the expected string is whatever
        this machine's zone makes of that instant, so the test states
        the property on any machine instead of pinning one zone.
        """
        mod = self.loaded()
        stamp = "2026-09-12T00:00:00Z"
        page = mod.render(self.items(), self.meta(built_at=stamp))
        local = (datetime.datetime(2026, 9, 12, tzinfo=datetime.timezone.utc)
                 .astimezone())
        self.assertIn("built %s" % local.strftime("%Y-%m-%d %H:%M %Z"), page)

    def test_the_masthead_does_not_show_the_raw_utc_stamp(self):
        mod = self.loaded()
        stamp = "2026-09-12T00:00:00Z"
        page = mod.render(self.items(), self.meta(built_at=stamp))
        self.assertNotIn("built %s" % stamp, page)

    def test_the_embedded_data_keeps_the_build_time_in_utc(self):
        """Ages are computed against built_at in the browser.

        Only the masthead is localised. Localising the data too would
        make every age wrong by the reader's offset.
        """
        mod = self.loaded()
        stamp = "2026-09-12T00:00:00Z"
        page = mod.render(self.items(), self.meta(built_at=stamp))
        self.assertEqual(self.embedded(page)["built_at"], stamp)

    def test_an_unreadable_build_time_is_shown_as_given(self):
        """Losing the stamp entirely is worse than showing it raw."""
        mod = self.loaded()
        page = mod.render(self.items(), self.meta(built_at="not a time"))
        self.assertIn("built not a time", page)

    def test_the_masthead_states_what_it_hid(self):
        """A row removed without a word is a page lying by omission."""
        mod = self.loaded()
        page = mod.render(self.items(), self.meta(hidden=7))
        self.assertIn("7 with nothing open hidden", page)

    def test_the_masthead_is_silent_when_it_hid_nothing(self):
        mod = self.loaded()
        page = mod.render(self.items(), self.meta(hidden=0))
        self.assertNotIn("nothing open hidden", page)

    def test_the_card_carries_the_obligation_text(self):
        mod = self.loaded()
        page = mod.render(self.items(), self.meta())
        card = page.split("<article")[1].split("</article>")[0]
        self.assertIn("verify x", card)
        self.assertIn("unverified", card)

    def test_every_obligation_gets_its_own_card(self):
        mod = self.loaded()
        item = self.items()[0]
        base = item["obligations"][0]
        item["obligations"] = [
            dict(base, id="e%d" % n, text="thing %d" % n) for n in range(6)]
        page = mod.render([item], self.meta())
        card = page.split("<article")[1].split("</article>")[0]
        for n in range(6):
            self.assertIn("thing %d" % n, card)

    def test_the_whole_text_survives_its_newlines(self):
        # the preview kept one line per obligation to stop a pasted
        # stack trace filling the screen; the card shows the trace
        mod = self.loaded()
        item = self.items()[0]
        item["obligations"][0]["text"] = "first line\nsecond line\nthird"
        page = mod.render([item], self.meta())
        card = page.split("<article")[1].split("</article>")[0]
        self.assertIn("first line", card)
        self.assertIn("second line", card)

    def test_the_preview_escapes_like_everything_else(self):
        mod = self.loaded()
        item = self.items()[0]
        item["obligations"][0]["text"] = "</script><script>alert(1)</script>"
        page = mod.render([item], self.meta())
        self.assertNotIn("<script>alert(1)</script>", page)


class Blocking(Base):
    """Splitting what blocks from what is only on record."""

    def mixed(self):
        return self.logbook_body(entries=[
            self.entry("d1", kind="decision", ticket="ABC-1",
                       text="chose the passwd home"),
            self.entry("u1", kind="unverified", ticket="ABC-1",
                       text="export test unrun"),
            self.entry("d2", kind="decision", ticket="ABC-2",
                       text="only a decision here"),
        ])

    def test_the_split_follows_logbooks_flag_not_a_name(self):
        mod = self.loaded()
        items = mod.build_items(self.mixed(), self.hail_body(sessions=[]))
        row = self.row(items, "ABC-1")
        self.assertEqual([e["id"] for e in row["obligations"]], ["u1"])
        self.assertEqual([e["id"] for e in row["aside"]], ["d1"])

    def test_a_kind_logbook_calls_blocking_stays_in_front(self):
        # the flag is read, so renaming decision to anything else and
        # marking something else non-blocking must follow
        body = self.mixed()
        body["kinds"] = dict(DEFAULT_KINDS)
        body["kinds"]["unverified"] = {"requires": ["verify"],
                                       "blocking": False}
        body["kinds"]["decision"] = {"requires": ["why"], "blocking": True}
        mod = self.loaded()
        row = self.row(mod.build_items(body, self.hail_body(sessions=[])),
                       "ABC-1")
        self.assertEqual([e["id"] for e in row["obligations"]], ["d1"])
        self.assertEqual([e["id"] for e in row["aside"]], ["u1"])

    def test_an_undeclared_kind_is_shown_not_swallowed(self):
        # the page's whole claim is what is outstanding, so the safe
        # side of not knowing is to put it in front of the reader
        body = self.logbook_body(entries=[
            self.entry("x1", kind="wildcard", ticket="ABC-9")])
        mod = self.loaded()
        row = self.row(mod.build_items(body, self.hail_body(sessions=[])),
                       "ABC-9")
        self.assertEqual([e["id"] for e in row["obligations"]], ["x1"])
        self.assertEqual(row["aside"], [])

    def test_blocking_only_off_puts_everything_back_in_front(self):
        mod = self.loaded(config={"rows": {"blocking_only": False}})
        row = self.row(mod.build_items(self.mixed(),
                                       self.hail_body(sessions=[])),
                       "ABC-1")
        self.assertEqual([e["id"] for e in row["obligations"]],
                         ["d1", "u1"])
        self.assertEqual(row["aside"], [])

    def test_an_item_owing_only_decisions_leaves_the_front(self):
        mod = self.loaded()
        items = mod.build_items(self.mixed(), self.hail_body(sessions=[]))
        kept, hidden = mod.only_open_rows(items)
        self.assertEqual([i["key"] for i in kept], ["ABC-1"])
        self.assertEqual(hidden, 1)

    def test_its_decisions_survive_into_the_disclosure(self):
        # ABC-2 is gone from the page. Its decision is the reason
        # somebody will come looking, so losing it with the row would
        # be the page destroying the record it exists to keep.
        mod = self.loaded()
        items = mod.build_items(self.mixed(), self.hail_body(sessions=[]))
        aside = mod.aside_items(items)
        self.assertEqual(sorted(i["key"] for i in aside),
                         ["ABC-1", "ABC-2"])
        self.assertEqual(
            sorted(e["id"] for i in aside for e in i["obligations"]),
            ["d1", "d2"])

    def test_the_envelope_must_carry_the_kinds(self):
        # a logbook that answers without them cannot say what blocks,
        # and a page that guesses renders a confident wrong answer
        env = self.fake_siblings(
            logbook_stdout=json.dumps({
                "version": 1, "thresholds": {"stale_days": 7},
                "entries": []}))
        # not a version refusal: this logbook is new enough and still
        # answered without them
        out = self.run_chartroom(env, "build")
        self.assertEqual(out.returncode, 5)
        self.assertIn("kinds", out.stderr)


class Panes(Base):
    """The page is two panes, not a table."""

    def paged(self):
        mod = self.loaded()
        items = mod.build_items(self.mixed_body(), self.hail_body())
        kept, hidden = mod.only_open_rows(items)
        meta = self.meta(hidden=hidden)
        return mod, mod.render(kept, meta, mod.aside_items(items))

    def mixed_body(self):
        return self.logbook_body(entries=[
            self.entry("u1", kind="unverified", ticket="ABC-241",
                       text="export test unrun",
                       session="00000000-0000-4000-8000-000000000001"),
            self.entry("d1", kind="decision", ticket="ABC-241",
                       text="chose the passwd home"),
        ])

    def test_there_is_no_table_and_no_activity_readout(self):
        _mod, html = self.paged()
        self.assertNotIn("<table", html)
        self.assertNotIn("activity", html)

    def test_obligation_text_is_on_the_page_not_behind_a_click(self):
        _mod, html = self.paged()
        front = html.split("<main")[1].split("<details")[0]
        self.assertIn("export test unrun", front)
        self.assertNotIn("<td", front)

    def test_the_sessions_pane_is_its_own_section(self):
        _mod, html = self.paged()
        self.assertIn("id=\"sessions\"", html)
        self.assertIn("tune the alert threshold", html)

    def test_a_session_pane_card_carries_a_resume_line(self):
        _mod, html = self.paged()
        self.assertIn("claude -r 00000000-0000-4000-8000-000000000001",
                      html)

    def test_every_session_hail_holds_reaches_the_pane_once(self):
        # deduped by id: a session keyed under two levels sits on two
        # work items and is still one session to rejoin
        mod = self.loaded()
        body = self.hail_body(sessions=[
            self.session(1, tickets_from_branch=["ABC-1"],
                         branches=["abc-1-x"]),
            self.session(1, tickets_from_branch=["ABC-1"],
                         branches=["abc-1-x"]),
            self.session(2, last_ts="2026-09-13T09:00:00Z"),
        ])
        listed, _dropped = mod.session_list(body)
        self.assertEqual(len(listed), 2)
        self.assertEqual(listed[0]["id"], self.session(2)["id"])

    def test_the_pane_stops_at_the_configured_number(self):
        mod = self.loaded(config={"sessions": {"limit": 3}})
        body = self.hail_body(sessions=[
            self.session(i, last_ts="2026-09-%02dT09:00:00Z" % (1 + i))
            for i in range(9)])
        listed, dropped = mod.session_list(body)
        self.assertEqual(len(listed), 3)
        self.assertEqual(dropped, 6)
        # the most recent survive, not an arbitrary three
        self.assertEqual(listed[0]["id"], self.session(8)["id"])

    def test_a_capped_pane_says_how_many_it_did_not_list(self):
        # 182 cards is the problem this page was built to fix; a cap
        # that says nothing is the page lying by omission again
        mod = self.loaded(config={"sessions": {"limit": 2}})
        body = self.hail_body(sessions=[self.session(i) for i in range(5)])
        listed, dropped = mod.session_list(body)
        html = mod.render(self.items(), self.meta(), [], listed,
                          dropped=dropped)
        self.assertIn("3 older session(s) not listed", html.split("<main")[0])

    def test_zero_means_no_cap(self):
        mod = self.loaded(config={"sessions": {"limit": 0}})
        body = self.hail_body(sessions=[self.session(i) for i in range(5)])
        listed, dropped = mod.session_list(body)
        self.assertEqual((len(listed), dropped), (5, 0))

    def test_the_pane_holds_sessions_no_work_item_kept(self):
        # "where was I working" is a different question from "what do
        # I owe", and the old page answered both side by side
        mod = self.loaded()
        listed, _dropped = mod.session_list(self.hail_body(sessions=[
            self.session(7, title="unrelated spike")]))
        self.assertEqual([s["title"] for s in listed], ["unrelated spike"])

    def test_a_card_names_the_session_its_obligation_was_written_in(self):
        _mod, html = self.paged()
        front = html.split("id=\"aside")[0]
        self.assertIn("tune the alert threshold", front)


class Aside(Base):

    def built(self, entries):
        mod = self.loaded()
        items = mod.build_items(self.logbook_body(entries=entries),
                                self.hail_body(sessions=[]))
        kept, hidden = mod.only_open_rows(items)
        return mod, mod.render(kept, self.meta(hidden=hidden),
                               mod.aside_items(items))

    def test_decisions_are_closed_behind_a_disclosure(self):
        mod, html = self.built([
            self.entry("u1", kind="unverified", ticket="ABC-1"),
            self.entry("d1", kind="decision", ticket="ABC-1",
                       text="chose the passwd home")])
        self.assertIn("<details", html)
        self.assertIn("chose the passwd home", html)
        summary = html.split("<summary")[1].split("</summary>")[0]
        self.assertIn("1", summary)

    def test_the_disclosure_says_what_it_holds(self):
        mod, html = self.built([
            self.entry("u1", kind="unverified", ticket="ABC-1"),
            self.entry("d1", kind="decision", ticket="ABC-1"),
            self.entry("d2", kind="decision", ticket="ABC-2")])
        summary = html.split("<summary")[1].split("</summary>")[0]
        self.assertIn("2", summary)
        self.assertIn("decision", summary)

    def test_nothing_on_record_means_no_disclosure_at_all(self):
        # an empty details element is a control that does nothing
        mod, html = self.built([
            self.entry("u1", kind="unverified", ticket="ABC-1")])
        self.assertNotIn("<details", html)

    def test_the_masthead_counts_what_it_set_aside(self):
        mod, html = self.built([
            self.entry("u1", kind="unverified", ticket="ABC-1"),
            self.entry("d1", kind="decision", ticket="ABC-1"),
            self.entry("d2", kind="decision", ticket="ABC-2")])
        head = html.split("<main")[0]
        self.assertIn("2 on record", head)
        self.assertIn("1 open", head)


class Escaping(Base):
    """Every string on the page came out of a ledger somebody else
    wrote into, so every field is attacker-shaped until it has been
    through _esc. One test per place a hostile string can enter."""

    HOSTILE = {
        "title": "<img src=x onerror=alert(1)>",
        "cwd": "<script>alert(2)</script>",
        "text": "\"><svg onload=alert(3)>",
    }

    def hostile_items(self):
        items = self.items()
        items[0]["sessions"][0]["title"] = self.HOSTILE["title"]
        items[0]["sessions"][0]["cwd"] = self.HOSTILE["cwd"]
        items[0]["obligations"][0]["text"] = self.HOSTILE["text"]
        return items

    def test_no_hostile_field_reaches_the_page_as_markup(self):
        mod = self.loaded()
        html = mod.render(self.hostile_items(), self.meta())
        for field, raw in sorted(self.HOSTILE.items()):
            self.assertNotIn(raw, html, field)

    def test_the_hostile_text_is_still_there_to_read(self):
        # escaping by deletion would pass the test above and lose the
        # one field a reader needs to see what they are looking at
        mod = self.loaded()
        html = mod.render(self.hostile_items(), self.meta())
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", html)
        self.assertIn("&lt;script&gt;alert(2)&lt;/script&gt;", html)


class Timestamps(Base):
    """Both siblings' shapes, because staleness depends on reading them.

    A parser that handles only one shape does not misreport staleness,
    it makes it unreachable - which reads as "nothing is stale yet".
    """

    def test_both_sibling_shapes_parse(self):
        mod = self.loaded()
        cases = [
            ("2026-09-12T09:00:00Z", (2026, 9, 12)),
            ("2026-09-02T21:48:11.648Z", (2026, 9, 2)),
            # what logbook actually writes: a local offset, no fraction
            ("2026-08-25T20:44:14+10:00", (2026, 8, 25)),
            ("2026-08-25T20:44:14.123456+10:00", (2026, 8, 25)),
            # 3.9's fromisoformat takes 3 or 6 fraction digits, no other
            ("2026-08-25T20:44:14.1234+10:00", (2026, 8, 25)),
            ("2026-09-11T09:00:00", (2026, 9, 11)),
        ]
        for text, expected in cases:
            day = mod._parse_date(text)
            self.assertIsNotNone(day, text)
            self.assertEqual((day.year, day.month, day.day), expected, text)

    def test_an_offset_is_normalised_to_utc(self):
        mod = self.loaded()
        # 08:00+10:00 is the previous day in UTC
        day = mod._parse_date("2026-09-12T08:00:00+10:00")
        self.assertEqual((day.month, day.day), (9, 11))

    def test_nonsense_is_none_not_a_crash(self):
        mod = self.loaded()
        for bad in (None, 7, "", "not a date", "2026-13-45T99:99:99Z"):
            self.assertIsNone(mod._parse_date(bad))

    def test_an_old_entry_with_an_offset_reads_as_aging(self):
        mod = self.loaded()
        items = self.items()
        items[0]["obligations"][0]["ts"] = "2026-08-01T20:44:14+10:00"
        html = mod.render(items, self.meta(stale_days=7))
        self.assertIn("sev sev-aging", html)

    def test_aging_is_measured_against_the_build_not_the_clock(self):
        mod = self.loaded()
        items = self.items()
        items[0]["obligations"][0]["ts"] = "2026-08-01T20:44:14+10:00"
        fresh = mod.render(items, self.meta(stale_days=7,
                                            built_at="2026-08-02T00:00:00Z"))
        self.assertNotIn("sev sev-aging", fresh)


class Severity(Base):
    """Four outcomes in strict precedence. Only the strongest shows, so
    each test states what the row would have said without it."""

    def note(self, mod, obligations, built_at="2026-09-20T00:00:00Z",
             stale_days=7):
        item = {"key": "ABC-1", "via": "ticket", "label": "ABC-1",
                "obligations": obligations, "sessions": [],
                "aged_out": 0, "strip": []}
        return mod._severity_note(item, stale_days,
                                  mod._parse_date(built_at))

    def test_blocked_outranks_aging(self):
        mod = self.loaded()
        old = self.entry("e1", ts="2026-08-01T09:00:00")
        blocked = self.entry("e2", kind="blocked",
                             ts="2026-09-19T09:00:00")
        self.assertEqual(self.note(mod, [old]), "aging")
        self.assertEqual(self.note(mod, [old, blocked]), "blocked")

    def test_aging_outranks_open(self):
        mod = self.loaded()
        fresh = self.entry("e1", ts="2026-09-19T09:00:00")
        old = self.entry("e2", ts="2026-08-01T09:00:00")
        self.assertEqual(self.note(mod, [fresh]), "open")
        self.assertEqual(self.note(mod, [fresh, old]), "aging")

    def test_open_outranks_nothing_at_all(self):
        mod = self.loaded()
        self.assertEqual(
            self.note(mod, [self.entry("e1", ts="2026-09-19T09:00:00")]),
            "open")
        self.assertEqual(self.note(mod, []), "")

    def test_a_row_with_no_stale_threshold_never_ages(self):
        mod = self.loaded()
        old = self.entry("e1", ts="2026-08-01T09:00:00")
        self.assertEqual(self.note(mod, [old], stale_days=None), "open")

    def test_the_blocked_row_says_so_on_the_page(self):
        mod = self.loaded()
        items = self.items()
        items[0]["obligations"][0]["kind"] = "blocked"
        html = mod.render(items, self.meta(built_at="2026-09-20T00:00:00Z"))
        self.assertIn("sev sev-blocked", html)
        self.assertIn("sev-blocked\">blocked<", html)


class ShippedDocs(Base):
    """The two copies of the defaults that ship to users.

    Both are prose, so nothing else notices when they drift from
    DEFAULTS. A stale default in the README is worse than none: it is
    read as a promise about what the tool does.
    """

    def documented(self, text):
        start = text.index("```json") + len("```json")
        return json.loads(text[start:text.index("```", start)])

    def test_the_example_config_is_the_defaults(self):
        mod = self.loaded()
        with open(os.path.join(REPO, "examples", "chartroom.json")) as fh:
            example = json.load(fh)
        self.assertEqual(example.get("version"), mod.CONFIG_VERSION)
        self.assertEqual(example, mod.DEFAULTS)

    def test_the_readme_documents_the_defaults(self):
        mod = self.loaded()
        with open(os.path.join(REPO, "README.md")) as fh:
            block = self.documented(fh.read())
        self.assertEqual(block, mod.DEFAULTS)

    def test_the_readme_names_every_sort_key(self):
        mod = self.loaded()
        with open(os.path.join(REPO, "README.md")) as fh:
            readme = fh.read()
        for key in mod.SORT_KEYS:
            self.assertIn("`%s`" % key, readme)


class Masthead(Base):
    """What the page claims about itself, all derived."""

    def test_both_sibling_versions_are_named(self):
        mod = self.loaded()
        html = mod.render(self.items(), self.meta(
            versions={"logbook": "0.3.0", "hail": "0.9.9"}))
        self.assertIn("logbook 0.3.0", html)
        self.assertIn("hail 0.9.9", html)

    def test_the_versions_are_the_ones_the_siblings_reported(self):
        env = self.fake_siblings(logbook_version="0.3.4",
                                 hail_version="0.3.1")
        out = self.run_chartroom(env, "build")
        self.assertEqual(out.returncode, 0)
        with open(out.stdout.strip()) as fh:
            page = fh.read()
        self.assertIn("logbook 0.3.4", page)
        self.assertIn("hail 0.3.1", page)

    def test_the_census_counts_rows_open_and_sessions(self):
        mod = self.loaded()
        census = mod._census(mod.build_items(self.logbook_body(),
                                             self.hail_body()))
        self.assertEqual(census["work_items"], 1)
        self.assertEqual(census["open"], 1)
        self.assertEqual(census["sessions"], 1)
        self.assertEqual(census["by_via"], {"ticket": 1})

    def test_a_session_on_two_rows_is_counted_once(self):
        mod = self.loaded()
        session = {
            "id": "00000000-0000-4000-8000-000000000001",
            "title": "two tickets", "cwd": "/home/u/code", "turns": 2,
            "first_ts": "2026-09-10T09:00:00Z",
            "last_ts": "2026-09-12T09:00:00Z",
            "branches": ["abc-1-and-abc-2"],
            "tickets_from_branch": ["ABC-1", "ABC-2"], "prs": [],
        }
        items = mod.build_items(self.logbook_body(tickets=["ABC-1"]),
                                self.hail_body(sessions=[session]))
        census = mod._census(items)
        self.assertEqual(census["work_items"], 2)
        self.assertEqual(census["sessions"], 1)

    def test_zero_aged_off_is_not_stated(self):
        mod = self.loaded()
        self.assertNotIn("aged off",
                         mod.render(self.items(), self.meta(aged_off=0)))
        self.assertIn("71 aged off",
                      mod.render(self.items(), self.meta(aged_off=71)))


class Controls(Base):
    """Ordering and filtering happen in the page, per spec 7."""

    def test_the_page_carries_a_filter_and_a_sort_control(self):
        html = self.loaded().render(self.items(), self.meta())
        for marker in ("id=\"q\"", "id=\"by\"", "id=\"dir\""):
            self.assertIn(marker, html)

    def test_every_sort_key_is_offered(self):
        mod = self.loaded()
        html = mod.render(self.items(), self.meta())
        for key in mod.SORT_KEYS:
            self.assertIn("<option value=\"%s\"" % key, html)

    def test_the_control_opens_on_the_configured_order(self):
        mod = self.loaded(config={"sort": {"by": "open", "dir": "desc"}})
        html = mod.render(self.items(), self.meta())
        self.assertIn("<option value=\"open\" selected>", html)
        self.assertIn("data-dir=\"desc\"", html)
        self.assertIn(">descending</button>", html)

    def test_a_session_carries_a_timestamp_not_an_age(self):
        html = self.loaded().render(self.items(), self.meta())
        self.assertIn("data-ts=\"2026-09-12T09:00:00Z\"", html)

    def test_an_obligation_carries_its_own_timestamp(self):
        html = self.loaded().render(self.items(), self.meta())
        self.assertIn("data-ts=\"2026-09-11T09:00:00\"", html)

    def test_the_filter_reaches_text_the_row_does_not_show(self):
        # The haystack is the embedded record, so obligation text
        # inside a collapsed detail row is filterable.
        mod = self.loaded()
        data = self.embedded(mod.render(self.items(), self.meta()))
        self.assertEqual(data["items"][0]["obligations"][0]["text"],
                         "verify x")


class KindFilter(Base):
    """One chip per kind actually on the page.

    Typing a kind into the search box nearly works and is a trap: the
    haystack is the whole record, so `deploy` also matches an
    obligation whose text mentions deploying, and it matches the whole
    work item rather than the cards inside it."""

    def rendered_args(self, mod, items):
        """What cmd_build hands render(), for a built item list."""
        shown, _hidden = mod.only_open_rows(items)
        return shown, self.meta(), mod.aside_items(items), [], 0

    def mixed(self, mod=None):
        """Items covering three blocking kinds and one aside kind."""
        mod = mod or self.loaded()
        entries = [
            self.entry("e1", kind="deploy", ticket="ABC-1"),
            self.entry("e2", kind="followup", ticket="ABC-1"),
            self.entry("e3", kind="unverified", ticket="ABC-2"),
            self.entry("e4", kind="decision", ticket="ABC-2"),
        ]
        return mod, mod.build_items(self.logbook_body(entries=entries),
                                    self.hail_body(sessions=[]))

    def test_every_card_declares_its_kind(self):
        mod, items = self.mixed()
        html = mod.render(*self.rendered_args(mod, items))
        for kind in ("deploy", "followup", "unverified"):
            self.assertIn("data-kind=\"%s\"" % kind, html)

    def test_a_chip_is_offered_for_each_kind_present(self):
        mod, items = self.mixed()
        html = mod.render(*self.rendered_args(mod, items))
        for kind in ("deploy", "followup", "unverified"):
            self.assertIn("data-chip=\"%s\"" % kind, html)

    def test_an_aside_kind_gets_a_chip_too(self):
        # a decision is still a kind somebody wants to see on its own,
        # and it is the one the disclosure hides by default
        mod, items = self.mixed()
        html = mod.render(*self.rendered_args(mod, items))
        self.assertIn("data-chip=\"decision\"", html)

    def test_a_kind_with_nothing_on_the_page_gets_no_chip(self):
        # the chips describe this page, not logbook's whole vocabulary
        mod, items = self.mixed()
        html = mod.render(*self.rendered_args(mod, items))
        self.assertNotIn("data-chip=\"parked\"", html)
        self.assertNotIn("data-chip=\"blocked\"", html)

    def test_each_chip_carries_its_count(self):
        mod, items = self.mixed()
        html = mod.render(*self.rendered_args(mod, items))
        chip = html.split("data-chip=\"deploy\"")[1].split("</button>")[0]
        self.assertIn("1", chip)

    def test_no_chip_row_when_there_is_nothing_to_filter(self):
        # a control that can only be a no-op should not be there
        mod = self.loaded()
        entries = [self.entry("e1", kind="deploy", ticket="ABC-1")]
        items = mod.build_items(self.logbook_body(entries=entries),
                                self.hail_body(sessions=[]))
        html = mod.render(*self.rendered_args(mod, items))
        self.assertNotIn("id=\"kinds\"", html)

    def test_the_chips_start_unset_so_the_page_opens_whole(self):
        # scoped to the chip row: the selected-state string also lives
        # in the stylesheet and the script, where it means nothing
        mod, items = self.mixed()
        html = mod.render(*self.rendered_args(mod, items))
        row = html.split("id=\"kinds\"")[1].split("</div>")[0]
        self.assertIn("data-chip=", row)
        self.assertNotIn("data-on", row)

    def test_the_sessions_pane_can_say_why_it_is_empty(self):
        """A kind filter narrows the right pane to the sessions those
        obligations name, and often that is none of the listed ones -
        the session that left a deploy six weeks ago is past
        sessions.limit. An empty column with no words in it reads as a
        bug."""
        mod, items = self.mixed()
        html = mod.render(*self.rendered_args(mod, items))
        self.assertIn("id=\"nosess\"", html)
        self.assertIn("hidden", html.split("id=\"nosess\"")[1][:40])

    def test_the_script_filters_cards_not_only_items(self):
        # the point of the feature: picking `deploy` on a work item
        # holding a deploy and a followup shows the deploy alone
        mod, _items = self.mixed()
        self.assertIn("data-kind", mod._SCRIPT)
        self.assertIn("chosen", mod._SCRIPT)


class Ordering(Base):
    """sort.by decides the order build_items hands over, and the page's
    own controls only re-sort what already arrived in that order. Each
    key gets rows that are distinguishable on it and on nothing else,
    inserted in an order that is not the answer."""

    def keys_in_order(self, by, direction, logbook_body, hail_body):
        mod = self.loaded(config={"sort": {"by": by, "dir": direction}})
        return [i["key"] for i in mod.build_items(logbook_body, hail_body)]

    def both_ways(self, by, logbook_body, hail_body, expected):
        self.assertEqual(
            self.keys_in_order(by, "asc", logbook_body, hail_body),
            expected)
        self.assertEqual(
            self.keys_in_order(by, "desc", logbook_body, hail_body),
            list(reversed(expected)))

    def test_by_key_orders_the_rows_by_name(self):
        self.both_ways("key",
                       self.logbook_body(tickets=["ABC-3", "ABC-1",
                                                  "ABC-2"]),
                       self.hail_body(sessions=[]),
                       ["ABC-1", "ABC-2", "ABC-3"])

    def test_by_open_orders_the_rows_by_how_much_is_owed(self):
        entries = ([self.entry("a%d" % i, ticket="ABC-A") for i in range(2)]
                   + [self.entry("b%d" % i, ticket="ABC-B")
                      for i in range(1)]
                   + [self.entry("c%d" % i, ticket="ABC-C")
                      for i in range(3)])
        self.both_ways("open", self.logbook_body(entries=entries),
                       self.hail_body(sessions=[]),
                       ["ABC-B", "ABC-A", "ABC-C"])

    def test_by_sessions_orders_the_rows_by_how_many_worked_them(self):
        sessions = [self.session(0, tickets_from_branch=["ABC-A"])]
        sessions += [self.session(1 + i, tickets_from_branch=["ABC-B"])
                     for i in range(3)]
        sessions += [self.session(4 + i, tickets_from_branch=["ABC-C"])
                     for i in range(2)]
        self.both_ways("sessions", self.logbook_body(entries=[]),
                       self.hail_body(sessions=sessions),
                       ["ABC-A", "ABC-C", "ABC-B"])

    def test_by_age_orders_the_rows_by_when_they_were_last_worked(self):
        sessions = [
            self.session(0, tickets_from_branch=["ABC-A"],
                         last_ts="2026-09-10T09:00:00Z"),
            self.session(1, tickets_from_branch=["ABC-B"],
                         last_ts="2026-09-12T09:00:00Z"),
            self.session(2, tickets_from_branch=["ABC-C"],
                         last_ts="2026-09-11T09:00:00Z"),
        ]
        self.both_ways("age", self.logbook_body(entries=[]),
                       self.hail_body(sessions=sessions),
                       ["ABC-A", "ABC-C", "ABC-B"])


class Written(Base):

    def test_the_file_is_private(self):
        mod = self.loaded()
        path = mod.write_page("<p>x</p>")
        self.assertEqual("%04o" % (os.stat(path).st_mode & 0o777), "0600")

    def test_the_directory_is_private(self):
        mod = self.loaded()
        path = mod.write_page("<p>x</p>")
        self.assertEqual(
            "%04o" % (os.stat(os.path.dirname(path)).st_mode & 0o777),
            "0700")

    def test_nothing_partial_is_left_behind(self):
        mod = self.loaded()
        path = mod.write_page("<p>x</p>")
        leftovers = [f for f in os.listdir(os.path.dirname(path))
                    if f != os.path.basename(path)]
        self.assertEqual(leftovers, [])


class AgedOut(Base):

    def test_a_row_whose_sessions_all_aged_out_says_so(self):
        mod = self.loaded()
        items = mod.build_items(
            self.logbook_body(
                session="deadbeef-0000-0000-0000-000000000000"),
            self.hail_body(sessions=[]))
        self.assertEqual(items[0]["aged_out"], 1)

    def test_the_page_wide_figure_comes_from_the_census(self):
        mod = self.loaded()
        meta = mod.page_meta(self.logbook_body(),
                             self.hail_body(aged_off=71))
        self.assertEqual(meta["aged_off"], 71)


class Doctor(Base):

    def test_doctor_writes_nothing(self):
        env = self.fake_siblings()
        before = self.tree(env)
        self.run_chartroom(env, "doctor")
        self.assertEqual(self.tree(env), before)

    def test_setting_aside_nothing_is_a_finding(self):
        # blocking_only on and every kind blocking means the setting
        # is either doing nothing or hiding a mislabelled kind
        kinds = {"unverified": {"requires": ["verify"], "blocking": True}}
        env = self.fake_siblings(
            hail_days=40,
            logbook_stdout=json.dumps({
                "version": 1, "thresholds": {"stale_days": 7},
                "kinds": kinds, "entries": []}))
        out = self.run_chartroom(env, "doctor")
        self.assertEqual(out.returncode, 1)
        self.assertIn("blocking_only", out.stdout)

    def test_the_kinds_in_force_are_reported(self):
        env = self.fake_siblings(hail_days=40)
        out = self.run_chartroom(env, "doctor")
        self.assertIn("decision (aside)", out.stdout)

    def test_a_short_hail_window_is_a_finding(self):
        env = self.fake_siblings(hail_days=10)
        out = self.run_chartroom(env, "doctor")
        self.assertEqual(out.returncode, 1)
        self.assertIn("index.days", out.stdout)

    def test_a_healthy_pair_has_no_findings(self):
        env = self.fake_siblings(hail_days=60)
        out = self.run_chartroom(env, "doctor")
        self.assertEqual(out.returncode, 0)
        self.assertIn("no findings", out.stdout)

    def test_an_unknown_sort_key_is_exit_two(self):
        out = self.run_chartroom(self.fake_siblings(), "doctor",
                                 config={"sort": {"by": "nope",
                                                  "dir": "asc"}})
        self.assertEqual(out.returncode, 2)
        for allowed in ("key", "open", "sessions", "age"):
            self.assertIn(allowed, out.stderr)


class Recorder:
    """Stands in for the webbrowser module, so that the open attempt is
    observable without a window."""

    def __init__(self):
        self.opened = []

    def open(self, url):
        self.opened.append(url)
        return True


class Invocation(Base):
    """chartroom with no subcommand at all, which is how it is meant to
    be run and the only path on which page.open is consulted."""

    def test_no_argument_builds_the_page_and_names_it(self):
        env = self.fake_siblings()
        out = self.run_chartroom(env, config={"page": {"open": False}})
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout.strip(), self.page_path(env))
        self.assertTrue(os.path.exists(self.page_path(env)))

    def ran(self, env, argv):
        """main() in process, with the browser replaced and its stdout
        held, so a test can watch the open attempt without a window."""
        mod = self.loaded(env, config={"page": {"open": True}})
        recorder = Recorder()
        mod.webbrowser = recorder
        held = io.StringIO()
        with contextlib.redirect_stdout(held):
            code = mod.main(argv)
        return code, held.getvalue().strip(), recorder.opened

    def test_no_argument_offers_the_written_page_to_the_browser(self):
        env = self.fake_siblings()
        code, printed, opened = self.ran(env, [])
        self.assertEqual(code, 0)
        self.assertEqual(printed, self.page_path(env))
        self.assertEqual(opened, ["file://" + self.page_path(env)])

    def test_the_build_subcommand_opens_nothing(self):
        env = self.fake_siblings()
        code, printed, opened = self.ran(env, ["build"])
        self.assertEqual(code, 0)
        self.assertEqual(printed, self.page_path(env))
        self.assertEqual(opened, [])


class Invariants(Base):
    """Three promises, each of which failed silently in an earlier
    draft of the design."""

    def test_every_session_hail_returned_reaches_the_page(self):
        # not "minus those the window dropped": a dropped session was
        # never in the payload. A key-precedence bug that loses
        # sessions is invisible by eye on a page with 14 rows.
        mod = self.loaded()
        hail_body = self.hail_body(count=40, mixed_keys=True)
        items = mod.build_items(self.logbook_body(), hail_body)
        seen = set()
        for row in items:
            for session in row["sessions"]:
                seen.add(session["id"])
        self.assertEqual(len(seen), len(hail_body["sessions"]))

    def test_every_entry_logbook_returned_reaches_the_page(self):
        mod = self.loaded()
        logbook_body = self.logbook_body(count=30, include_keyless=True)
        items = mod.build_items(logbook_body, self.hail_body())
        seen = set()
        for row in items:
            for obligation in row["obligations"]:
                seen.add(obligation["id"])
        self.assertEqual(len(seen), len(logbook_body["entries"]))

    def test_no_prompt_text_reaches_the_page(self):
        mod = self.loaded()
        body = self.hail_body()
        for record in body["sessions"]:
            record["prompts"] = ["SENTINEL-PROMPT-TEXT"]
            record["last_prompt"] = "SENTINEL-PROMPT-TEXT"
        html = mod.render(mod.build_items(self.logbook_body(), body),
                          self.meta())
        self.assertNotIn("SENTINEL-PROMPT-TEXT", html)


class Serve(Base):
    """`serve` puts a listening socket where there was only a file.

    Everything here is about what that socket refuses. The page carries
    parked work, branch names and the prose of every obligation, and
    before this subcommand the only thing between that and another
    process on the machine was file permissions.

    Every test drives a server running its own accept loop, not one
    hand-fed request: a first draft of these tests called
    handle_request() once per server and passed while the shipped
    server hung on its second request.
    """

    def running(self, env=None, config=None):
        """A live server on an ephemeral port, and its URL."""
        import threading
        mod = self.loaded(env or self.fake_siblings(), config=config)
        server = mod.build_server(0)
        thread = threading.Thread(target=server.serve_forever)
        thread.daemon = True
        thread.start()

        def stop():
            server.shutdown()
            server.server_close()
            thread.join(timeout=10)

        self.addCleanup(stop)
        url = "http://127.0.0.1:%d/?t=%s" % (server.server_address[1],
                                             server.token)
        return mod, server, url

    def fetch(self, url, method="GET", host=None, timeout=10):
        """status and body, HTTP errors included rather than raised."""
        import urllib.error
        import urllib.request
        request = urllib.request.Request(url, method=method)
        if host:
            request.add_header("Host", host)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                return resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", "replace")

    def test_it_binds_the_loopback_address_only(self):
        # the difference between "a page only I can read" and "a page
        # anyone on this network can read"
        _mod, server, _url = self.running()
        self.assertEqual(server.server_address[0], "127.0.0.1")

    def test_the_right_token_gets_the_page(self):
        _mod, _server, url = self.running()
        status, body = self.fetch(url)
        self.assertEqual(status, 200)
        self.assertIn("obligations", body)

    def test_a_second_request_is_answered_too(self):
        """The regression that shipped past the first draft of these
        tests.

        HTTP/1.1 keeps a connection alive, and a single-threaded server
        sat in the dead connection waiting for another request on it.
        The first page arrived, every page after it hung until the
        client timed out - which on a page you reload is every use
        after the first.
        """
        _mod, _server, url = self.running()
        self.assertEqual(self.fetch(url)[0], 200)
        self.assertEqual(self.fetch(url)[0], 200)
        self.assertEqual(self.fetch(url)[0], 200)

    def test_one_stalled_connection_does_not_close_the_page(self):
        # a local process can open a socket and say nothing. It must
        # not be able to take the page away from its owner.
        import socket
        _mod, server, url = self.running()
        stalled = socket.create_connection(server.server_address)
        self.addCleanup(stalled.close)
        self.assertEqual(self.fetch(url)[0], 200)

    def test_a_request_with_no_token_is_refused(self):
        _mod, server, _url = self.running()
        status, body = self.fetch(
            "http://127.0.0.1:%d/" % server.server_address[1])
        self.assertEqual(status, 403)
        self.assertNotIn("obligations", body)

    def test_a_request_with_a_wrong_token_is_refused(self):
        _mod, server, _url = self.running()
        status, body = self.fetch(
            "http://127.0.0.1:%d/?t=not-the-token"
            % server.server_address[1])
        self.assertEqual(status, 403)
        self.assertNotIn("obligations", body)

    def test_the_token_is_not_in_the_page_it_serves(self):
        # a screenshot of the page, or its HTML pasted into a ticket,
        # must not hand over the key to the socket
        _mod, server, url = self.running()
        self.assertNotIn(server.token, self.fetch(url)[1])

    def test_two_servers_do_not_share_a_token(self):
        _mod, first, _url = self.running()
        _mod2, second, _url2 = self.running()
        self.assertNotEqual(first.token, second.token)
        self.assertGreaterEqual(len(first.token), 32)

    def test_an_unknown_path_is_refused_even_with_the_token(self):
        _mod, server, _url = self.running()
        status, _body = self.fetch(
            "http://127.0.0.1:%d/secrets?t=%s"
            % (server.server_address[1], server.token))
        self.assertEqual(status, 404)

    def test_a_post_is_refused(self):
        # the page writes nothing back, so nothing needs a method that
        # could
        _mod, _server, url = self.running()
        self.assertEqual(self.fetch(url, method="POST")[0], 405)

    def test_a_foreign_host_header_is_refused(self):
        # DNS rebinding: a page on the open web can point a name at
        # 127.0.0.1 and make the browser talk to this socket. It cannot
        # forge the Host header the browser sends.
        _mod, _server, url = self.running()
        self.assertEqual(self.fetch(url, host="attacker.example")[0], 403)

    def test_a_refusing_sibling_is_a_503_not_a_traceback(self):
        _mod, _server, url = self.running(
            env=self.fake_siblings(logbook_present=False))
        status, body = self.fetch(url)
        self.assertEqual(status, 503)
        self.assertIn("logbook", body)
        self.assertNotIn("Traceback", body)

    def test_every_request_rebuilds(self):
        # the whole point of serving rather than opening a file
        mod, _server, url = self.running()
        calls = []
        real = mod._fetch_both

        def counted():
            calls.append(1)
            return real()

        mod._fetch_both = counted
        self.fetch(url)
        self.fetch(url)
        self.assertEqual(len(calls), 2)

    def test_serving_writes_no_page_to_disk(self):
        env = self.fake_siblings()
        _mod, _server, url = self.running(env=env)
        self.fetch(url)
        self.assertFalse(os.path.exists(self.page_path(env)))

    def test_the_request_log_keeps_the_token_out(self):
        _mod, server, _url = self.running()
        handler = server.RequestHandlerClass.__new__(
            server.RequestHandlerClass)
        handler.server = server
        handler.client_address = ("127.0.0.1", 1234)
        requestline = "GET /?t=%s HTTP/1.1" % server.token
        held = io.StringIO()
        with contextlib.redirect_stderr(held):
            handler.log_message("%s", requestline)
        self.assertNotIn(server.token, held.getvalue())

    def test_the_url_reaches_a_pipe_before_the_server_blocks(self):
        """The URL is the only way in, and `serve` then blocks forever.

        Python block-buffers stdout when it is not a terminal, so
        without an explicit flush the one line a caller needs sits in
        the buffer until the process is killed - and the token dies
        with it. Piping `chartroom serve` anywhere at all hits this.
        """
        import threading
        env = self.fake_siblings()
        proc = subprocess.Popen(
            [sys.executable, CHARTROOM_PATH, "serve", "--port", "0"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, env=env)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        line = []
        reader = threading.Thread(
            target=lambda: line.append(proc.stdout.readline()))
        reader.daemon = True
        reader.start()
        reader.join(timeout=15)
        self.assertTrue(line, "no URL reached the pipe before serving")
        self.assertRegex(line[0].strip(),
                         r"^http://127\.0\.0\.1:\d+/\?t=\S+$")


    def test_a_bad_port_is_refused_before_anything_binds(self):
        mod = self.loaded(self.fake_siblings())
        with self.assertRaises(mod.Refused) as caught:
            mod.build_server(70000)
        self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
