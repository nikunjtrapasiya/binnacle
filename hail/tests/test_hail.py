import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

# The tool is loaded from source on nearly every test. A cached
# bytecode file for it can outlive an edit and make a green run a
# statement about code that is no longer on disk.
sys.dont_write_bytecode = True

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HAIL_PATH = os.path.join(REPO, "bin", "hail")


def load_hail():
    """A fresh module, so each test gets its own config at import."""
    loader = importlib.machinery.SourceFileLoader("hail", HAIL_PATH)
    spec = importlib.util.spec_from_loader("hail", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class Base(unittest.TestCase):
    """Shared setup only.

    No test method may live on this class. logbook's suite learned this
    the hard way: a base class holding tests re-runs every one of them
    in every subclass, the count inflates, and dev/check.sh fails on the
    mismatch between tests run and tests defined.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = os.path.join(self.tmp.name, "home")
        os.makedirs(os.path.join(self.home, ".claude", "binnacle"))
        self.transcripts = os.path.join(self.home, ".claude", "projects")
        os.makedirs(self.transcripts)
        self.live = os.path.join(self.home, ".claude", "sessions")
        os.makedirs(self.live)
        # LOGBOOK_HOME as well as LOGBOOK_CONFIG: logbook reads both at
        # import (logbook:193-196), and Task 11 imports logbook
        for key in ("HOME", "LOGBOOK_CONFIG", "LOGBOOK_HOME", "TZ"):
            self.addCleanup(self._restore, key, os.environ.get(key))
        os.environ["HOME"] = self.home
        os.environ.pop("LOGBOOK_CONFIG", None)
        os.environ.pop("LOGBOOK_HOME", None)

    def _restore(self, key, value):
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    def config(self, body):
        """Write hail.json into the test's own home."""
        path = os.path.join(self.home, ".claude", "binnacle", "hail.json")
        with open(path, "w") as fh:
            json.dump(body, fh)
        return path

    def logbook_config(self, body):
        path = os.path.join(self.home, ".claude", "binnacle", "logbook.json")
        with open(path, "w") as fh:
            json.dump(body, fh)
        return path

    def bounded(self, mod):
        """Move the index-path boundary onto this test's own home.

        The boundary reads the account's passwd home on purpose, so a
        repointed HOME cannot move it. That also means it cannot be
        satisfied by a temp directory, so every test that writes an
        index replaces it, and the test of the boundary itself does not.
        """
        mod.account_home = lambda: os.path.realpath(self.home)
        return mod

    def loaded(self, scan=None):
        """A module whose scan paths and index path are all in the temp home."""
        mod = self.bounded(load_hail())
        mod.CFG["scan"]["transcripts"] = self.transcripts
        mod.CFG["scan"]["live"] = self.live
        if scan:
            mod.CFG["scan"].update(scan)
        return mod

    def transcript(self, session_id, records, project="-home-u-code",
                   sub=None):
        """Write a transcript from Python data. Returns its path.

        Fixtures are generated, not committed: *.jsonl is gitignored in
        both .gitignore files and CLAUDE.md forbids force-adding.
        """
        parent = os.path.join(self.transcripts, project)
        if sub:
            parent = os.path.join(parent, sub)
        os.makedirs(parent, exist_ok=True)
        path = os.path.join(parent, session_id + ".jsonl")
        with open(path, "w") as fh:
            for rec in records:
                fh.write(json.dumps(rec) + "\n")
        return path

    def user(self, text, cwd="/home/u/code", branch="abc-123-thing",
             ts="2026-09-12T09:00:00.000Z", sidechain=False):
        return {"type": "user", "isSidechain": sidechain, "cwd": cwd,
                "gitBranch": branch, "timestamp": ts,
                "message": {"role": "user", "content": text}}


UUID = "11111111-1111-4111-8111-111111111111"
OTHER = "1a2b3c4d-0000-4000-8000-000000000001"


class Config(Base):
    def test_defaults_with_no_config_file(self):
        mod = load_hail()
        self.assertEqual(mod.CFG["index"]["days"], 10)
        self.assertEqual(mod.CFG["index"]["prompts"], 2)
        self.assertEqual(mod.CFG["index"]["prompt_chars"], 300)
        self.assertEqual(mod.CONFIG_SOURCE["warnings"], [])
        self.assertIsNone(mod.CONFIG_SOURCE["fatal"])

    def test_unknown_key_warns_and_runs(self):
        self.config({"version": 1, "nope": {}})
        mod = load_hail()
        self.assertIsNone(mod.CONFIG_SOURCE["fatal"])
        self.assertTrue(any("nope" in w for w in mod.CONFIG_SOURCE["warnings"]))

    def test_wrong_type_keeps_the_default_and_warns(self):
        self.config({"version": 1, "index": {"days": "ten"}})
        mod = load_hail()
        self.assertEqual(mod.CFG["index"]["days"], 10)
        self.assertTrue(any("days" in w for w in mod.CONFIG_SOURCE["warnings"]))

    def test_wrong_version_is_fatal(self):
        self.config({"version": 2})
        mod = load_hail()
        self.assertIn("version", mod.CONFIG_SOURCE["fatal"])

    def test_unparseable_config_is_fatal(self):
        path = os.path.join(self.home, ".claude", "binnacle", "hail.json")
        with open(path, "w") as fh:
            fh.write("{not json")
        mod = load_hail()
        self.assertIsNotNone(mod.CONFIG_SOURCE["fatal"])

    def test_index_path_is_fixed_under_the_account_home(self):
        mod = self.bounded(load_hail())
        self.assertEqual(
            mod.index_path(),
            os.path.join(os.path.realpath(self.home),
                         ".claude", "binnacle", "hail", "index.json"))

    def test_index_path_reads_passwd_not_HOME(self):
        # deliberately NOT self.bounded: this is the test of the boundary
        import pwd          # Unix only, and so is every path this touches
        mod = load_hail()
        real = os.path.realpath(pwd.getpwuid(os.getuid()).pw_dir)
        os.environ["HOME"] = self.home
        self.assertTrue(mod.index_path().startswith(real + os.sep))


class Inheritance(Base):
    """Every bullet in spec section 5 bit in review. Each gets a test."""

    def test_pattern_and_reserved_are_both_inherited(self):
        self.logbook_config({"version": 1,
                             "ticket": {"pattern": r"[A-Z]{3}-\d+",
                                        "reserved": ["ZZZ"]}})
        mod = load_hail()
        self.assertEqual(mod.CFG["ticket"]["pattern"], r"[A-Z]{3}-\d+")
        self.assertEqual(mod.CFG["ticket"]["reserved"], ["ZZZ"])
        self.assertEqual(mod.CONFIG_SOURCE["ticket_from"]["pattern"],
                         "inherited from logbook.json")

    def test_hails_own_pattern_wins_and_says_nothing_about_reserved(self):
        # per key, not per section
        self.config({"version": 1, "ticket": {"pattern": r"[A-Z]{4}-\d+"}})
        self.logbook_config({"version": 1,
                             "ticket": {"pattern": r"[A-Z]{3}-\d+",
                                        "reserved": ["ZZZ"]}})
        mod = load_hail()
        self.assertEqual(mod.CFG["ticket"]["pattern"], r"[A-Z]{4}-\d+")
        self.assertEqual(mod.CFG["ticket"]["reserved"], ["ZZZ"])
        self.assertEqual(mod.CONFIG_SOURCE["ticket_from"]["pattern"], "file")

    def test_reserved_inherited_while_pattern_is_hails_own(self):
        self.config({"version": 1, "ticket": {"reserved": ["QQQ"]}})
        self.logbook_config({"version": 1,
                             "ticket": {"pattern": r"[A-Z]{3}-\d+"}})
        mod = load_hail()
        self.assertEqual(mod.CFG["ticket"]["pattern"], r"[A-Z]{3}-\d+")
        self.assertEqual(mod.CFG["ticket"]["reserved"], ["QQQ"])

    def test_a_logbook_config_at_another_version_is_not_inherited(self):
        # inheriting from a file logbook itself refuses (logbook:98-101)
        # would adopt a pattern the owner is not running under
        self.logbook_config({"version": 2,
                             "ticket": {"pattern": r"[A-Z]{3}-\d+"}})
        mod = load_hail()
        self.assertEqual(mod.CFG["ticket"]["pattern"],
                         mod.DEFAULTS["ticket"]["pattern"])
        self.assertTrue(any("version" in w
                            for w in mod.CONFIG_SOURCE["warnings"]))

    def test_an_unparseable_logbook_config_is_a_warning_not_fatal(self):
        # it makes logbook refuse to run; it must not make hail refuse
        path = os.path.join(self.home, ".claude", "binnacle",
                            "logbook.json")
        with open(path, "w") as fh:
            fh.write("{truncated")
        mod = load_hail()
        self.assertIsNone(mod.CONFIG_SOURCE["fatal"])
        self.assertTrue(mod.CONFIG_SOURCE["warnings"])

    def test_wrong_types_in_logbooks_ticket_are_not_inherited(self):
        self.logbook_config({"version": 1,
                             "ticket": {"pattern": 7, "reserved": "ZZZ"}})
        mod = load_hail()
        self.assertEqual(mod.CFG["ticket"]["pattern"],
                         mod.DEFAULTS["ticket"]["pattern"])
        self.assertEqual(mod.CFG["ticket"]["reserved"],
                         mod.DEFAULTS["ticket"]["reserved"])

    def test_an_uncompilable_inherited_pattern_falls_back(self):
        # logbook does the same (logbook:184-190) rather than
        # tracebacking inside the scan
        self.logbook_config({"version": 1, "ticket": {"pattern": "[unclosed"}})
        mod = load_hail()
        self.assertIsNotNone(mod.TICKET_RE)
        self.assertTrue(mod.TICKET_RE.fullmatch("ABC-123"))
        self.assertTrue(any("compile" in w
                            for w in mod.CONFIG_SOURCE["warnings"]))

    def test_LOGBOOK_CONFIG_is_ignored(self):
        # following logbook's override would have hail inherit from a
        # file logbook may not be using, and doctor would report
        # "inherited from logbook.json" truthfully about the wrong file
        elsewhere = os.path.join(self.tmp.name, "other-logbook.json")
        with open(elsewhere, "w") as fh:
            json.dump({"version": 1,
                       "ticket": {"pattern": r"[A-Z]{3}-\d+"}}, fh)
        os.environ["LOGBOOK_CONFIG"] = elsewhere
        mod = load_hail()
        self.assertEqual(mod.CFG["ticket"]["pattern"],
                         mod.DEFAULTS["ticket"]["pattern"])


class Scan(Base):
    def test_extracts_the_whole_record(self):
        mod = self.loaded()
        self.transcript(UUID, [
            self.user("fix ABC-123 please"),
            {"type": "ai-title", "aiTitle": "Fix the thing"},
            self.user("and the second", ts="2026-09-12T09:31:00.000Z"),
        ])
        rec = mod.scan_file(
            os.path.join(self.transcripts, "-home-u-code", UUID + ".jsonl"),
            "-home-u-code")
        self.assertEqual(rec["id"], UUID)
        self.assertEqual(rec["title"], "Fix the thing")
        self.assertEqual(rec["cwd"], "/home/u/code")
        self.assertEqual(rec["branches"], ["abc-123-thing"])
        self.assertEqual(rec["tickets"], ["ABC-123"])
        self.assertEqual(rec["turns"], 2)
        self.assertEqual(rec["prompts"], ["fix ABC-123 please",
                                          "and the second"])
        self.assertNotIn("last_prompt", rec)
        self.assertEqual(rec["first_ts"], "2026-09-12T09:00:00.000Z")
        self.assertEqual(rec["last_ts"], "2026-09-12T09:31:00.000Z")

    def test_a_task_notification_is_not_a_prompt(self):
        # A completed background agent posts its report as a user-role
        # record. Measured 2026-09-12: 1457 of them in the author's
        # corpus, and their agent ids and temp paths read as ticket
        # keys, which was 400 of the 495 keys extracted.
        mod = self.loaded()
        p = self.transcript(UUID, [
            self.user("the real question"),
            self.user("<task-notification>\n<task-id>a0ea</task-id>\n"
                      "/private/tmp/claude-502/x\n</task-notification>"),
        ])
        rec = mod.scan_file(p, "-home-u-code")
        self.assertEqual(rec["prompts"], ["the real question"])
        self.assertNotIn("last_prompt", rec)
        self.assertEqual(rec["turns"], 1)
        # the branch key survives; nothing from the notification body
        self.assertEqual(rec["tickets"], ["ABC-123"])
        self.assertNotIn("CLAUDE-502", rec["tickets"])

    def test_title_last_wins(self):
        mod = self.loaded()
        p = self.transcript(UUID, [
            {"type": "ai-title", "aiTitle": "first"},
            self.user("hello"),
            {"type": "ai-title", "aiTitle": "second"},
        ])
        self.assertEqual(mod.scan_file(p, "-home-u-code")["title"], "second")

    def test_last_prompt_appears_only_beyond_the_stored_prompts(self):
        mod = self.loaded()
        p = self.transcript(UUID, [self.user("one"), self.user("two"),
                                   self.user("three")])
        rec = mod.scan_file(p, "-home-u-code")
        self.assertEqual(rec["prompts"], ["one", "two"])
        self.assertEqual(rec["last_prompt"], "three")

    def test_prompts_zero_is_legal_and_keeps_last_prompt(self):
        mod = self.loaded()
        mod.CFG["index"]["prompts"] = 0
        p = self.transcript(UUID, [self.user("one"), self.user("two")])
        rec = mod.scan_file(p, "-home-u-code")
        self.assertEqual(rec["prompts"], [])
        self.assertEqual(rec["last_prompt"], "two")

    def test_truncation_is_marked_beside_the_value_not_inside_it(self):
        mod = self.loaded()
        mod.CFG["index"]["prompt_chars"] = 10
        p = self.transcript(UUID, [self.user("x" * 40)])
        rec = mod.scan_file(p, "-home-u-code")
        self.assertEqual(rec["prompts"], ["x" * 10])
        self.assertTrue(rec["prompts_truncated"])

    def test_noise_records_are_not_turns_and_not_stored(self):
        mod = self.loaded()
        p = self.transcript(UUID, [
            self.user("<command-name>/compact</command-name>"),
            self.user("ARGUMENTS: nothing"),
            self.user("the real one"),
        ])
        rec = mod.scan_file(p, "-home-u-code")
        self.assertEqual(rec["turns"], 1)
        self.assertEqual(rec["prompts"], ["the real one"])

    def test_an_injection_only_transcript_has_no_prompts(self):
        mod = self.loaded()
        p = self.transcript(UUID, [self.user("<system-reminder>x")])
        rec = mod.scan_file(p, "-home-u-code")
        self.assertEqual(rec["turns"], 0)
        self.assertEqual(rec["prompts"], [])
        self.assertEqual(rec["cwd"], "/home/u/code")

    def test_cwd_and_first_ts_come_from_the_first_user_record(self):
        # including a noise record: it carries the real directory and
        # the real clock, and 83 of 186 real transcripts hold more than
        # one cwd, so which one is stored has to be a rule
        mod = self.loaded()
        p = self.transcript(UUID, [
            self.user("<system-reminder>x", cwd="/home/u/first",
                      ts="2026-09-12T08:00:00.000Z"),
            self.user("real", cwd="/home/u/second",
                      ts="2026-09-12T09:00:00.000Z"),
        ])
        rec = mod.scan_file(p, "-home-u-code")
        self.assertEqual(rec["cwd"], "/home/u/first")
        self.assertEqual(rec["first_ts"], "2026-09-12T08:00:00.000Z")

    def test_both_directories_appear_in_branches_but_cwd_is_one(self):
        mod = self.loaded()
        p = self.transcript(UUID, [self.user("a", branch="one"),
                                   self.user("b", branch="two")])
        rec = mod.scan_file(p, "-home-u-code")
        self.assertEqual(sorted(rec["branches"]), ["one", "two"])

    def test_a_detached_HEAD_is_not_a_branch(self):
        # the literal string git prints for detached HEAD, not a real
        # branch name - keeping it would join unrelated checkouts
        mod = self.loaded()
        p = self.transcript(UUID, [self.user("a", branch="HEAD")])
        rec = mod.scan_file(p, "-home-u-code")
        self.assertEqual(rec["branches"], [])
        self.assertEqual(rec["tickets_from_branch"], [])

    def test_a_detached_HEAD_alongside_a_real_branch_keeps_only_the_real_one(
            self):
        mod = self.loaded()
        p = self.transcript(UUID, [self.user("a", branch="HEAD"),
                                   self.user("b", branch="abc-123-thing")])
        rec = mod.scan_file(p, "-home-u-code")
        self.assertEqual(rec["branches"], ["abc-123-thing"])

    def test_a_branch_ticket_outranks_a_more_mentioned_body_ticket(self):
        mod = self.loaded()
        p = self.transcript(UUID, [
            self.user("DEF-9 DEF-9 DEF-9", branch="abc-123-thing"),
        ])
        self.assertEqual(mod.scan_file(p, "-home-u-code")["tickets"],
                         ["ABC-123", "DEF-9"])

    def test_reserved_prefixes_are_not_tickets(self):
        mod = self.loaded()
        p = self.transcript(UUID, [self.user("UTF-8 and RFC-2119",
                                             branch="main")])
        self.assertEqual(mod.scan_file(p, "-home-u-code")["tickets"], [])

    def test_a_reserved_key_inside_a_word_is_not_matched(self):
        # x1UTF-8, not XUTF-8. Upper-cased that is X1UTF-8, and there is
        # no word boundary before the U, so the wrapped pattern cannot
        # match the UTF-8 inside it. XUTF-8 would be the wrong fixture:
        # the whole word matches, XUTF is four letters and not reserved,
        # so it is a legitimate key and the expected value would be
        # ["XUTF-8"]. Verified by execution.
        mod = self.loaded()
        p = self.transcript(UUID, [self.user("x1UTF-8", branch="main")])
        self.assertEqual(mod.scan_file(p, "-home-u-code")["tickets"], [])

    def test_a_word_ending_in_a_reserved_key_is_still_a_ticket(self):
        # the other half of the same rule, so nobody "fixes" the above
        # by dropping the word boundaries again
        mod = self.loaded()
        p = self.transcript(UUID, [self.user("XUTF-8", branch="main")])
        self.assertEqual(mod.scan_file(p, "-home-u-code")["tickets"],
                         ["XUTF-8"])

    def test_duplicate_pr_links_are_stored_once(self):
        mod = self.loaded()
        link = {"type": "pr-link", "prNumber": 7, "prRepository": "o/r",
                "prUrl": "u"}
        p = self.transcript(UUID, [self.user("hello"), link, link])
        self.assertEqual(len(mod.scan_file(p, "-home-u-code")["prs"]), 1)

    def test_pr_link_is_extracted(self):
        mod = self.loaded()
        p = self.transcript(UUID, [
            self.user("hello"),
            {"type": "pr-link", "prNumber": 7, "prRepository": "o/r",
             "prUrl": "https://example.invalid/o/r/pull/7"},
        ])
        self.assertEqual(mod.scan_file(p, "-home-u-code")["prs"],
                         [{"number": 7, "repo": "o/r",
                           "url": "https://example.invalid/o/r/pull/7"}])

    def test_malformed_lines_are_skipped_not_fatal(self):
        mod = self.loaded()
        path = self.transcript(UUID, [self.user("hello")])
        with open(path, "a") as fh:
            fh.write("{truncated\n")
        self.assertEqual(mod.scan_file(path, "-home-u-code")["turns"], 1)

    def test_a_transcript_with_no_user_record_is_not_a_record(self):
        mod = self.loaded()
        p = self.transcript(UUID, [{"type": "ai-title", "aiTitle": "x"}])
        self.assertIsNone(mod.scan_file(p, "-home-u-code"))

    def test_sidechain_records_are_not_turns(self):
        mod = self.loaded()
        p = self.transcript(UUID, [self.user("real"),
                                   self.user("agent", sidechain=True)])
        self.assertEqual(mod.scan_file(p, "-home-u-code")["turns"], 1)


class Walk(Base):
    def test_only_depth_one_jsonl_is_walked(self):
        mod = self.loaded()
        self.transcript(UUID, [self.user("main")])
        self.transcript("agent-x", [self.user("sidechain")],
                        sub=OTHER + "/subagents")
        found = [os.path.basename(p)
                 for _, p, _, _ in mod.walk_transcripts(self.transcripts)]
        self.assertEqual(found, [UUID + ".jsonl"])

    def test_non_jsonl_and_non_regular_entries_are_ignored(self):
        mod = self.loaded()
        self.transcript(UUID, [self.user("main")])
        project = os.path.join(self.transcripts, "-home-u-code")
        open(os.path.join(project, ".DS_Store"), "w").close()
        os.makedirs(os.path.join(project, "notes.jsonl"))
        found = [os.path.basename(p)
                 for _, p, _, _ in mod.walk_transcripts(self.transcripts)]
        self.assertEqual(found, [UUID + ".jsonl"])

    def test_a_missing_transcripts_directory_yields_nothing(self):
        mod = self.loaded()
        found = list(mod.walk_transcripts(
            os.path.join(self.tmp.name, "gone")))
        self.assertEqual(found, [])


class RecordShape(Base):
    def test_an_id_not_matching_the_filename_shape_is_refused(self):
        mod = self.loaded()
        rec = {"id": "not-a-uuid", "cwd": "/home/u/code"}
        self.assertIsInstance(mod.record_ok(rec), str)

    def test_a_relative_cwd_is_refused(self):
        mod = self.loaded()
        self.assertIsInstance(
            mod.record_ok({"id": UUID, "cwd": "code"}), str)

    def test_a_control_character_in_cwd_is_refused(self):
        # logbook prints `rejoin: cd <cwd>` into the session-start
        # context, so hail is the writer of a value another plugin
        # injects unescaped
        mod = self.loaded()
        self.assertIsInstance(
            mod.record_ok({"id": UUID, "cwd": "/home/u\nrm -rf /"}), str)

    def test_a_good_record_passes(self):
        mod = self.loaded()
        self.assertIs(mod.record_ok({"id": UUID, "cwd": "/home/u/code"}),
                      True)


class Writing(Base):
    def payload(self):
        return {"version": 1, "sessions": [], "census": {}}

    def test_writes_the_payload_at_mode_0600(self):
        mod = self.loaded()
        mod.write_index(self.payload())
        path = mod.index_path()
        with open(path) as fh:
            self.assertEqual(json.load(fh)["version"], 1)
        self.assertEqual(oct(os.stat(path).st_mode & 0o777), "0o600")

    def test_a_pre_existing_0644_index_ends_0600(self):
        mod = self.loaded()
        path = mod.index_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            json.dump({"version": 0}, fh)
        os.chmod(path, 0o644)
        mod.write_index(self.payload())
        self.assertEqual(oct(os.stat(path).st_mode & 0o777), "0o600")

    def test_a_symlink_at_the_target_is_refused(self):
        mod = self.loaded()
        path = mod.index_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        outside = os.path.join(self.tmp.name, "elsewhere.json")
        open(outside, "w").close()
        os.symlink(outside, path)
        with self.assertRaises(mod.Refused):
            mod.write_index(self.payload())
        with open(outside) as fh:
            self.assertEqual(fh.read(), "")

    def test_a_stale_temp_file_does_not_wedge_the_next_run(self):
        # a fixed index.json.tmp opened O_EXCL fails EEXIST forever after
        # one SIGKILL mid-write, and under the hook it fails silently
        mod = self.loaded()
        path = mod.index_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(os.path.join(os.path.dirname(path), "index.json.tmp"),
             "w").close()
        mod.write_index(self.payload())
        with open(path) as fh:
            self.assertEqual(json.load(fh)["version"], 1)

    def test_a_failure_after_the_temp_write_leaves_the_old_index(self):
        mod = self.loaded()
        path = mod.index_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            json.dump({"version": "old"}, fh)
        real = os.replace

        def boom(src, dst):
            raise OSError("disk full")

        mod.os.replace = boom
        self.addCleanup(setattr, mod.os, "replace", real)
        with self.assertRaises(OSError):
            mod.write_index(self.payload())
        with open(path) as fh:
            self.assertEqual(json.load(fh)["version"], "old")
        leftovers = [n for n in os.listdir(os.path.dirname(path))
                     if n != "index.json"]
        self.assertEqual(leftovers, [])

    def test_a_failing_passwd_lookup_refuses_rather_than_using_HOME(self):
        mod = load_hail()          # not bounded: the boundary is the subject
        import pwd
        real = pwd.getpwuid

        def boom(uid):
            raise KeyError("no such user")

        pwd.getpwuid = boom
        self.addCleanup(setattr, pwd, "getpwuid", real)
        with self.assertRaises(mod.Refused):
            mod.index_path()


class Signature(Base):
    def test_is_stable_across_runs_on_identical_config(self):
        self.assertEqual(self.loaded().scan_signature(),
                         self.loaded().scan_signature())

    def test_changes_with_the_ticket_pattern(self):
        a = self.loaded().scan_signature()
        mod = self.loaded()
        mod.CFG["ticket"]["pattern"] = r"[A-Z]{3}-\d+"
        self.assertNotEqual(a, mod.scan_signature())

    def test_changes_with_ignore_prefixes(self):
        a = self.loaded().scan_signature()
        mod = self.loaded()
        mod.CFG["scan"]["ignore_prefixes"] = ["<x"]
        self.assertNotEqual(a, mod.scan_signature())

    def test_changes_with_prompt_chars_and_prompts(self):
        a = self.loaded().scan_signature()
        for key, value in (("prompt_chars", 40), ("prompts", 5)):
            mod = self.loaded()
            mod.CFG["index"][key] = value
            self.assertNotEqual(a, mod.scan_signature())

    def test_does_not_change_with_days(self):
        # the window decides which files are looked at, not what a
        # record contains, so widening it must not invalidate the cache
        a = self.loaded().scan_signature()
        mod = self.loaded()
        mod.CFG["index"]["days"] = 40
        self.assertEqual(a, mod.scan_signature())

    def test_changes_when_logbooks_ticket_section_changes(self):
        a = self.loaded().scan_signature()
        self.logbook_config({"version": 1,
                             "ticket": {"pattern": r"[A-Z]{3}-\d+"}})
        self.assertNotEqual(a, self.loaded().scan_signature())


class LoadIndex(Base):
    def test_a_missing_index_is_None(self):
        self.assertIsNone(self.loaded().load_index())

    def test_an_unparseable_index_is_None(self):
        mod = self.loaded()
        path = mod.index_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write("{truncated")
        self.assertIsNone(mod.load_index())

    def test_a_written_index_round_trips(self):
        mod = self.loaded()
        mod.write_index({"version": 1, "sessions": [{"id": UUID}]})
        self.assertEqual(mod.load_index()["sessions"][0]["id"], UUID)


def rec(**over):
    base = {"id": UUID, "cwd": "/home/u/code", "title": "t",
            "branches": ["b"], "prs": [], "tickets": ["ABC-123"],
            "turns": 3, "first_ts": "2026-09-12T09:00:00.000Z"}
    base.update(over)
    return base


class Superset(Base):
    """Base, not TestCase: load_hail reads config at import.

    On a bare TestCase this class would read the owner's real
    ~/.claude/binnacle/*.json, which is read-only but breaks the rule
    that every config-reading test repoints HOME.
    """

    def setUp(self):
        super().setUp()
        self.mod = load_hail()

    def test_an_identical_record_is_no_violation(self):
        self.assertIsNone(self.mod.superset_violation(rec(), rec()))

    def test_growth_is_no_violation(self):
        fresh = rec(branches=["b", "c"], turns=9,
                    tickets=["ABC-123", "DEF-4"])
        self.assertIsNone(self.mod.superset_violation(rec(), fresh))

    def test_a_changed_cwd_is_a_violation(self):
        self.assertEqual(
            self.mod.superset_violation(rec(), rec(cwd="/elsewhere")), "cwd")

    def test_a_lost_cwd_is_a_violation(self):
        self.assertEqual(
            self.mod.superset_violation(rec(), rec(cwd=None)), "cwd")

    def test_a_lost_title_is_a_violation_but_a_changed_one_is_not(self):
        gone = rec()
        del gone["title"]
        self.assertEqual(self.mod.superset_violation(rec(), gone), "title")
        self.assertIsNone(
            self.mod.superset_violation(rec(), rec(title="renamed")))

    def test_shrinking_branches_is_a_violation(self):
        # gitBranch vanishing turns ["x"] into [], which is the partial
        # format change revision 1 admitted it could not catch
        self.assertEqual(
            self.mod.superset_violation(rec(), rec(branches=[])), "branches")

    def test_a_reordered_list_with_the_same_members_is_not(self):
        cached = rec(branches=["a", "b"])
        self.assertIsNone(
            self.mod.superset_violation(cached, rec(branches=["b", "a"])))

    def test_a_replaced_member_is_a_violation(self):
        cached = rec(branches=["a"])
        self.assertEqual(
            self.mod.superset_violation(cached, rec(branches=["z"])),
            "branches")

    def test_shrinking_turns_is_a_violation(self):
        self.assertEqual(
            self.mod.superset_violation(rec(), rec(turns=1)), "turns")

    def test_a_changed_first_ts_is_a_violation(self):
        # a timestamp format change is caught, since first_ts is
        # compared as the string the transcript wrote
        self.assertEqual(
            self.mod.superset_violation(
                rec(), rec(first_ts="2026-09-12 09:00:00")), "first_ts")

    def test_prompts_are_not_compared(self):
        # the whole point of last_prompt is that it moves
        fresh = rec(prompts=["different"], last_prompt="newer")
        self.assertIsNone(self.mod.superset_violation(rec(), fresh))


class Build(Base):
    def index_with(self, mod, records, signature=None, census=None):
        mod.write_index({
            "version": 1,
            "scan_signature": signature or mod.scan_signature(),
            "census": census or {},
            "sessions": records,
        })

    def test_a_clean_run_writes_every_record(self):
        mod = self.loaded()
        self.transcript(UUID, [self.user("hello")])
        payload, census, refusal = mod.build()
        self.assertIsNone(refusal)
        self.assertEqual(len(payload["sessions"]), 1)
        self.assertEqual(census["fresh"], 1)
        self.assertEqual(census["reused"], 0)

    def test_sessions_are_ordered_by_mtime_newest_first(self):
        # relative to now, not epoch 1000: absolute values that old are
        # outside the 10 day window and both files age off, leaving an
        # empty list and an assertion that fails against a correct build
        import time as _t
        mod = self.loaded()
        old = self.transcript(UUID, [self.user("old")])
        new = self.transcript(OTHER, [self.user("new")])
        now = _t.time()
        os.utime(old, (now - 600, now - 600))
        os.utime(new, (now - 60, now - 60))
        payload, _, _ = mod.build()
        self.assertEqual([s["id"] for s in payload["sessions"]],
                         [OTHER, UUID])

    def test_an_unchanged_file_is_reused_not_rescanned(self):
        mod = self.loaded()
        path = self.transcript(UUID, [self.user("hello")])
        st = os.stat(path)
        self.index_with(mod, [{"id": UUID, "cwd": "/home/u/code",
                               "mtime": st.st_mtime, "size": st.st_size,
                               "title": "cached", "branches": [],
                               "prs": [], "tickets": [], "turns": 1,
                               "first_ts": "2026-09-12T09:00:00.000Z"}])
        payload, census, _ = mod.build()
        self.assertEqual(census["reused"], 1)
        self.assertEqual(census["fresh"], 0)
        self.assertEqual(payload["sessions"][0]["title"], "cached")

    def test_the_same_mtime_with_a_different_size_is_rescanned(self):
        mod = self.loaded()
        path = self.transcript(UUID, [self.user("hello")])
        st = os.stat(path)
        self.index_with(mod, [{"id": UUID, "cwd": "/home/u/code",
                               "mtime": st.st_mtime, "size": st.st_size + 1,
                               "branches": [], "prs": [], "tickets": [],
                               "turns": 1,
                               "first_ts": "2026-09-12T09:00:00.000Z"}])
        _, census, _ = mod.build()
        self.assertEqual(census["fresh"], 1)

    def test_a_signature_change_rescans_everything(self):
        mod = self.loaded()
        path = self.transcript(UUID, [self.user("hello")])
        st = os.stat(path)
        self.index_with(mod, [{"id": UUID, "cwd": "/home/u/code",
                               "mtime": st.st_mtime, "size": st.st_size,
                               "branches": [], "prs": [], "tickets": [],
                               "turns": 1,
                               "first_ts": "2026-09-12T09:00:00.000Z"}],
                        signature="sha256:stale")
        _, census, _ = mod.build()
        self.assertEqual(census["fresh"], 1)

    def test_a_regression_keeps_the_cached_record_and_reports_it(self):
        mod = self.loaded()
        path = self.transcript(UUID, [{"type": "other"},
                                      self.user("hi", cwd="/moved")])
        st = os.stat(path)
        self.index_with(mod, [{"id": UUID, "cwd": "/home/u/code",
                               "mtime": st.st_mtime - 10, "size": 1,
                               "title": "cached", "branches": ["b"],
                               "prs": [], "tickets": [], "turns": 1,
                               "first_ts": "2026-09-12T09:00:00.000Z"}])
        payload, census, refusal = mod.build()
        self.assertIsNone(refusal)
        self.assertEqual(census["kept_on_regression"], 1)
        self.assertEqual(payload["sessions"][0]["cwd"], "/home/u/code")
        self.assertEqual(payload["sessions"][0]["title"], "cached")

    def test_a_kept_record_keeps_its_cached_mtime_and_size(self):
        # taking the new ones would let the next run reuse it from
        # cache, drop kept_on_regression back to zero, and freeze the
        # stale record with no trace
        mod = self.loaded()
        path = self.transcript(UUID, [self.user("hi", cwd="/moved")])
        self.index_with(mod, [{"id": UUID, "cwd": "/home/u/code",
                               "mtime": 1000.0, "size": 1,
                               "branches": [], "prs": [], "tickets": [],
                               "turns": 1,
                               "first_ts": "2026-09-12T09:00:00.000Z"}])
        payload, _, _ = mod.build()
        self.assertEqual(payload["sessions"][0]["mtime"], 1000.0)
        self.assertEqual(payload["sessions"][0]["size"], 1)
        _, census, _ = mod.build()
        self.assertEqual(census["kept_on_regression"], 1)
        self.assertEqual(census["reused"], 0)

    def test_a_signature_mismatch_suspends_part_one(self):
        # this is the revision 2 bug: narrowing the ticket pattern
        # legitimately shrinks tickets, and comparing across a
        # signature change would keep every stale record and silently
        # discard the config change
        mod = self.loaded()
        path = self.transcript(UUID, [self.user("ABC-123", branch="main")])
        st = os.stat(path)
        self.index_with(mod, [{"id": UUID, "cwd": "/home/u/code",
                               "mtime": st.st_mtime - 10, "size": 1,
                               "branches": ["main"], "prs": [],
                               "tickets": ["ABC-123", "GONE-1"], "turns": 1,
                               "first_ts": "2026-09-12T09:00:00.000Z"}],
                        signature="sha256:stale")
        payload, census, _ = mod.build()
        self.assertEqual(census["kept_on_regression"], 0)
        self.assertEqual(payload["sessions"][0]["tickets"], ["ABC-123"])

    def test_part_one_runs_before_the_no_cwd_exclusion(self):
        mod = self.loaded()
        path = self.transcript(
            UUID, [{"type": "user", "isSidechain": False,
                    "gitBranch": "b",
                    "timestamp": "2026-09-12T09:00:00.000Z",
                    "message": {"role": "user", "content": "hi"}}])
        self.index_with(mod, [{"id": UUID, "cwd": "/home/u/code",
                               "mtime": 1000.0, "size": 1,
                               "branches": ["b"], "prs": [], "tickets": [],
                               "turns": 1,
                               "first_ts": "2026-09-12T09:00:00.000Z"}])
        payload, census, _ = mod.build()
        self.assertEqual(census["kept_on_regression"], 1)
        self.assertEqual(census["user_records_no_cwd"], 0)
        self.assertEqual(payload["sessions"][0]["cwd"], "/home/u/code")

    def test_the_two_no_cwd_counters_are_separate(self):
        mod = self.loaded()
        self.transcript(UUID, [{"type": "ai-title", "aiTitle": "x"}])
        self.transcript(OTHER, [{"type": "user", "isSidechain": False,
                                 "timestamp": "2026-09-12T09:00:00.000Z",
                                 "message": {"role": "user",
                                             "content": "hi"}}])
        _, census, _ = mod.build()
        self.assertEqual(census["no_user_records"], 1)
        self.assertEqual(census["user_records_no_cwd"], 1)

    def test_the_cold_check_refuses_and_leaves_the_index_alone(self):
        mod = self.loaded(scan={"min_sample": 2, "min_bytes": 0})
        self.index_with(mod, [{"id": UUID, "cwd": "/home/u/code"}])
        for n in range(2):
            self.transcript("0000000%d-0000-4000-8000-000000000001" % n,
                            [{"type": "user", "isSidechain": False,
                              "timestamp": "2026-09-12T09:00:00.000Z",
                              "message": {"role": "user",
                                          "content": "hi"}}])
        payload, census, refusal = mod.build()
        self.assertIsNotNone(refusal)
        self.assertEqual(mod.load_index()["sessions"][0]["id"], UUID)

    def test_the_cold_check_does_not_fire_below_min_sample(self):
        mod = self.loaded(scan={"min_sample": 5, "min_bytes": 0})
        self.transcript(UUID, [{"type": "user", "isSidechain": False,
                                "timestamp": "2026-09-12T09:00:00.000Z",
                                "message": {"role": "user",
                                            "content": "hi"}}])
        _, _, refusal = mod.build()
        self.assertIsNone(refusal)

    def test_the_window_ages_files_off_without_opening_them(self):
        mod = self.loaded()
        path = self.transcript(UUID, [self.user("old")])
        os.utime(path, (1000, 1000))
        payload, census, _ = mod.build()
        self.assertEqual(payload["sessions"], [])
        self.assertEqual(census["aged_off"], 1)

    def test_days_widened_picks_up_a_previously_aged_off_file(self):
        mod = self.loaded()
        path = self.transcript(UUID, [self.user("old")])
        import time as _t
        os.utime(path, (_t.time() - 20 * 86400,) * 2)
        self.assertEqual(mod.build()[0]["sessions"], [])
        self.assertEqual(len(mod.build(days=40)[0]["sessions"]), 1)

    def test_days_narrowed_drops_a_file_without_opening_it(self):
        import time as _t
        mod = self.loaded()
        path = self.transcript(UUID, [self.user("recent")])
        os.utime(path, (_t.time() - 5 * 86400,) * 2)
        self.assertEqual(len(mod.build()[0]["sessions"]), 1)

        def refuse(*a, **kw):
            raise AssertionError("an aged-off file was opened")

        mod.scan_file = refuse
        payload, census, _ = mod.build(days=1)
        self.assertEqual(payload["sessions"], [])
        self.assertEqual(census["aged_off"], 1)

    def test_a_signature_mismatch_also_suspends_part_one_for_turns(self):
        # growing ignore_prefixes legitimately shrinks turns, the same
        # way narrowing the ticket pattern shrinks tickets
        mod = self.loaded()
        path = self.transcript(UUID, [self.user("ARGUMENTS: noise"),
                                      self.user("real")])
        self.index_with(mod, [{"id": UUID, "cwd": "/home/u/code",
                               "mtime": 1000.0, "size": 1,
                               "branches": ["abc-123-thing"], "prs": [],
                               "tickets": ["ABC-123"], "turns": 2,
                               "first_ts": "2026-09-12T09:00:00.000Z"}],
                        signature="sha256:stale")
        payload, census, _ = mod.build()
        self.assertEqual(census["kept_on_regression"], 0)
        self.assertEqual(payload["sessions"][0]["turns"], 1)

    def test_force_rescans_and_runs_under_part_two_alone(self):
        mod = self.loaded()
        path = self.transcript(UUID, [self.user("hi", cwd="/moved")])
        st = os.stat(path)
        self.index_with(mod, [{"id": UUID, "cwd": "/home/u/code",
                               "mtime": st.st_mtime, "size": st.st_size,
                               "branches": [], "prs": [], "tickets": [],
                               "turns": 1,
                               "first_ts": "2026-09-12T09:00:00.000Z"}])
        payload, census, _ = mod.build(force=True)
        self.assertEqual(census["fresh"], 1)
        self.assertEqual(census["kept_on_regression"], 0)
        self.assertEqual(payload["sessions"][0]["cwd"], "/moved")

    def test_a_refused_record_is_not_written(self):
        mod = self.loaded()
        self.transcript(UUID, [self.user("hi", cwd="relative/path")])
        payload, census, _ = mod.build()
        self.assertEqual(payload["sessions"], [])
        self.assertEqual(census["refused"], 1)

    def test_one_id_in_two_projects_yields_one_record(self):
        # resuming a session from another checkout writes a second
        # transcript under the new project with the same id. Measured on
        # the author's machine: 1 of 185 ids.
        mod = self.loaded()
        old = self.transcript(UUID, [self.user("first", cwd="/home/u/one")],
                              project="-home-u-one")
        new = self.transcript(UUID, [self.user("second", cwd="/home/u/two")],
                              project="-home-u-two")
        import time as _t
        now = _t.time()
        os.utime(old, (now - 600, now - 600))
        os.utime(new, (now - 60, now - 60))
        payload, census, _ = mod.build()
        self.assertEqual([r["id"] for r in payload["sessions"]], [UUID])
        self.assertEqual(payload["sessions"][0]["cwd"], "/home/u/two")
        self.assertEqual(census["superseded"], 1)

    def test_the_superseded_copy_is_never_opened(self):
        mod = self.loaded()
        old = self.transcript(UUID, [self.user("first", cwd="/home/u/one")],
                              project="-home-u-one")
        new = self.transcript(UUID, [self.user("second", cwd="/home/u/two")],
                              project="-home-u-two")
        import time as _t
        now = _t.time()
        os.utime(old, (now - 600, now - 600))
        os.utime(new, (now - 60, now - 60))
        opened = []
        real = mod.scan_file

        def spy(path, project):
            opened.append(path)
            return real(path, project)

        mod.scan_file = spy
        mod.build()
        self.assertEqual(opened, [new])

    def test_a_duplicate_id_is_not_a_regression_on_the_next_run(self):
        # the failure this guards: comparing one file against the
        # other's cached record reports a regression that is not one,
        # and a kept record keeps its cached mtime, so it repeats on
        # every run forever
        mod = self.loaded()
        old = self.transcript(UUID, [self.user("first", cwd="/home/u/one")],
                              project="-home-u-one")
        new = self.transcript(UUID, [self.user("second", cwd="/home/u/two")],
                              project="-home-u-two")
        import time as _t
        now = _t.time()
        os.utime(old, (now - 600, now - 600))
        os.utime(new, (now - 60, now - 60))
        payload, _, _ = mod.build()
        mod.write_index(payload)
        _, census, _ = mod.build()
        self.assertEqual(census["kept_on_regression"], 0)
        self.assertEqual(census["reused"], 1)

    def test_the_census_and_signature_are_persisted_in_the_header(self):
        import contextlib
        import io
        mod = self.loaded()
        self.transcript(UUID, [self.user("hello")])
        with contextlib.redirect_stdout(io.StringIO()):
            mod.cmd_index([])
        data = mod.load_index()
        self.assertEqual(data["scan_signature"], mod.scan_signature())
        self.assertEqual(data["census"]["fresh"], 1)
        self.assertEqual(data["days"], 10)
        self.assertTrue(data["built_at"].endswith("Z"))


class IndexCommand(Base):
    def run_index(self, mod, args):
        # both streams: cmd_index prints the refusal and the argument
        # errors to stderr, so a stdout-only capture asserts on an empty
        # string and passes whatever the command said
        import io
        import contextlib
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            code = mod.cmd_index(args)
        return code, out.getvalue() + err.getvalue()

    def test_a_clean_run_exits_0_and_prints_the_census(self):
        mod = self.loaded()
        self.transcript(UUID, [self.user("hello")])
        code, out = self.run_index(mod, [])
        self.assertEqual(code, 0)
        self.assertIn("fresh", out)

    def test_a_kept_record_still_writes_the_index_and_exits_0(self):
        mod = self.loaded()
        self.transcript(UUID, [self.user("hi", cwd="/moved")])
        mod.write_index({"version": 1,
                         "scan_signature": mod.scan_signature(),
                         "census": {},
                         "sessions": [{"id": UUID, "cwd": "/home/u/code",
                                       "mtime": 1000.0, "size": 1,
                                       "branches": [], "prs": [],
                                       "tickets": [], "turns": 1,
                                       "first_ts":
                                           "2026-09-12T09:00:00.000Z"}]})
        code, out = self.run_index(mod, [])
        self.assertEqual(code, 0)
        self.assertIn("kept", out)

    def test_the_cold_refusal_exits_5(self):
        mod = self.loaded(scan={"min_sample": 1, "min_bytes": 0})
        self.transcript(UUID, [{"type": "user", "isSidechain": False,
                                "timestamp": "2026-09-12T09:00:00.000Z",
                                "message": {"role": "user",
                                            "content": "hi"}}])
        mod.write_index({"version": 1, "sessions": [{"id": OTHER}],
                         "census": {}})
        code, out = self.run_index(mod, [])
        self.assertEqual(code, 5)
        self.assertIn("cwd", out)
        # the index is what the refusal exists to protect, so assert it
        # rather than assuming build's purity
        self.assertEqual(mod.load_index()["sessions"][0]["id"], OTHER)

    def test_days_zero_and_negative_are_refused(self):
        mod = self.loaded()
        for bad in ("0", "-1"):
            self.assertEqual(self.run_index(mod, ["--days", bad])[0], 2)

    def test_a_missing_transcripts_directory_writes_no_index(self):
        # writing an index with zero sessions would let a mistyped
        # scan.transcripts replace a good index with an empty one
        mod = self.loaded(scan={"transcripts":
                                os.path.join(self.tmp.name, "gone")})
        mod.write_index({"version": 1, "sessions": [{"id": UUID}],
                         "census": {}})
        code, _ = self.run_index(mod, [])
        self.assertEqual(code, 0)
        self.assertEqual(mod.load_index()["sessions"][0]["id"], UUID)


class Liveness(Base):
    def setUp(self):
        # Registered before super(), so it runs LAST: addCleanup is
        # LIFO, and Base's TZ restore has to happen before tzset reads
        # the variable back. Registered after, tzset runs while TZ is
        # still Melbourne and the process keeps a stale zone.
        import time as _t
        self.addCleanup(_t.tzset)
        super().setUp()
        # Forced before anything is computed. A test that derives its
        # expected value first and shifts the zone afterwards proves
        # nothing, because both sides of the comparison move together.
        os.environ["TZ"] = "Australia/Melbourne"
        _t.tzset()

    def session_file(self, pid, body):
        path = os.path.join(self.live, "%s.json" % pid)
        with open(path, "w") as fh:
            json.dump(body, fh)
        return path

    def ps_start(self, pid):
        """What the file's procStart would say for this pid.

        Straight from ps under TZ=UTC, so the assertion does not use the
        function under test as its own oracle.
        """
        out = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)],
                             capture_output=True, text=True,
                             env=dict(os.environ, TZ="UTC")).stdout.strip()
        self.assertTrue(out, "ps printed no start time for pid %s" % pid)
        return out

    def test_a_real_live_process_is_live(self):
        # The test revision 2 of the spec was missing entirely. This is
        # the one that would have caught it: the file's spelling is UTC,
        # this process runs in Melbourne, and ps prints local time.
        # It catches a plain string comparison, and a parse that reads
        # the ps output as local time. It does not catch swapping
        # timegm for mktime inside _ctime_epoch while the ps child is
        # still forced to UTC, because then both sides shift together -
        # and that variant is not a bug.
        mod = self.loaded()
        pid = os.getpid()
        self.session_file(pid, {"pid": pid, "sessionId": UUID,
                                "procStart": self.ps_start(pid)})
        self.assertIn(UUID, mod.live_session_ids()[0])

    def test_a_procStart_far_off_is_not_live(self):
        mod = self.loaded()
        pid = os.getpid()
        self.session_file(pid, {"pid": pid, "sessionId": UUID,
                                "procStart": "Fri Sep 11 00:00:00 2020"})
        self.assertEqual(mod.live_session_ids()[0], set())

    def test_a_procStart_five_minutes_off_is_not_live(self):
        import calendar
        import time as _t
        mod = self.loaded()
        pid = os.getpid()
        epoch = calendar.timegm(_t.strptime(self.ps_start(pid),
                                            "%a %b %d %H:%M:%S %Y"))
        drifted = _t.strftime("%a %b %d %H:%M:%S %Y",
                              _t.gmtime(epoch + 300))
        self.session_file(pid, {"pid": pid, "sessionId": UUID,
                                "procStart": drifted})
        self.assertEqual(mod.live_session_ids()[0], set())

    def test_a_procStart_a_second_off_is_still_live(self):
        import calendar
        import time as _t
        mod = self.loaded()
        pid = os.getpid()
        epoch = calendar.timegm(_t.strptime(self.ps_start(pid),
                                            "%a %b %d %H:%M:%S %Y"))
        close = _t.strftime("%a %b %d %H:%M:%S %Y", _t.gmtime(epoch + 1))
        self.session_file(pid, {"pid": pid, "sessionId": UUID,
                                "procStart": close})
        self.assertIn(UUID, mod.live_session_ids()[0])

    def test_a_missing_procStart_is_not_live_and_is_counted(self):
        mod = self.loaded()
        self.session_file(os.getpid(), {"pid": os.getpid(),
                                        "sessionId": UUID})
        self.assertEqual(mod.live_session_ids(), (set(), 1))

    def test_pids_that_must_never_be_signalled(self):
        # os.kill(0, 0) signals the caller's process group and
        # os.kill(-1, 0) every process the user owns, so the private
        # tool reads a corrupt sessions file as LIVE
        mod = self.loaded()
        for bad in (0, -1, 1, None, "123", 1.5):
            self.session_file("x", {"pid": bad, "sessionId": UUID,
                                    "procStart": "Fri Sep 11 07:07:58 2026"})
            self.assertEqual(mod.live_session_ids()[0], set(),
                             "pid %r marked something live" % bad)

    def test_a_key_sibling_is_never_opened(self):
        mod = self.loaded()
        with open(os.path.join(self.live, "secret.key"), "w") as fh:
            fh.write("not json")
        self.assertEqual(mod.live_session_ids()[0], set())

    def test_a_missing_sessions_directory_is_not_an_error(self):
        mod = self.loaded(scan={"live": os.path.join(self.tmp.name, "gone")})
        self.assertEqual(mod.live_session_ids(), (set(), 0))

    def test_ps_failing_means_nothing_is_live(self):
        mod = self.loaded()
        mod.process_start = lambda pids: {}
        self.session_file(os.getpid(), {"pid": os.getpid(),
                                        "sessionId": UUID,
                                        "procStart": "Fri Sep 11 07:07:58 2026"})
        self.assertEqual(mod.live_session_ids()[0], set())

    def test_one_ps_call_for_every_pid(self):
        mod = self.loaded()
        calls = []
        real = mod.subprocess.run

        def spy(args, **kw):
            calls.append(args)
            return real(args, **kw)

        mod.subprocess.run = spy
        self.addCleanup(setattr, mod.subprocess, "run", real)
        for pid in (os.getpid(), os.getppid()):
            self.session_file(pid, {"pid": pid, "sessionId": UUID,
                                    "procStart": "x"})
        mod.live_session_ids()
        self.assertEqual(len(calls), 1)


class Reading(Base):
    def stocked(self, sessions=None):
        mod = self.loaded()
        mod.write_index({
            "version": 1, "days": 10,
            "scan_signature": mod.scan_signature(), "census": {},
            "sessions": sessions if sessions is not None else [
                {"id": UUID, "project": "-home-u-code",
                 "path": "/home/u/.claude/projects/x/%s.jsonl" % UUID,
                 "title": "Fix the thing", "cwd": "/home/u/code",
                 "branches": ["abc-123-thing"], "tickets": ["ABC-123"],
                 "prs": [{"number": 7, "repo": "o/r", "url": "u"}],
                 "prompts": ["the first thing I typed"],
                 "last_prompt": "half way through",
                 "turns": 12, "first_ts": "2026-09-12T09:00:00.000Z",
                 "last_ts": "2026-09-12T09:31:00.000Z",
                 "mtime": 2000.0, "size": 10},
                {"id": OTHER, "project": "-home-u-other",
                 "path": "/home/u/.claude/projects/y/%s.jsonl" % OTHER,
                 "cwd": "/home/u/other", "branches": ["main"],
                 "tickets": ["ABC-1270"], "prs": [],
                 "prompts": ["something else"], "turns": 1,
                 "first_ts": "2026-09-11T09:00:00.000Z",
                 "last_ts": "2026-09-11T09:00:00.000Z",
                 "mtime": 1000.0, "size": 10},
            ]})
        return mod

    def out(self, mod, fn, args):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = fn(args)
        return code, buf.getvalue()

    def test_find_matches_a_ticket_exactly(self):
        mod = self.stocked()
        code, out = self.out(mod, mod.cmd_find, ["ABC-1"])
        self.assertEqual(code, 1)
        self.assertNotIn(UUID[:8], out)
        self.assertNotIn(OTHER[:8], out)

    def test_find_matches_the_right_ticket(self):
        mod = self.stocked()
        code, out = self.out(mod, mod.cmd_find, ["abc-123"])
        self.assertEqual(code, 0)
        self.assertIn(UUID[:8], out)
        self.assertNotIn(OTHER[:8], out)

    def test_find_matches_title_cwd_branch_prompt_and_pr(self):
        mod = self.stocked()
        for query in ("fix the thing", "/home/u/code", "abc-123-thing",
                      "first thing I typed", "half way", "o/r", "7"):
            code, out = self.out(mod, mod.cmd_find, [query])
            self.assertEqual(code, 0, query)
            self.assertIn(UUID[:8], out, query)

    def test_find_returns_index_order(self):
        mod = self.stocked()
        _, out = self.out(mod, mod.cmd_find, ["/home/u"])
        self.assertLess(out.index(UUID[:8]), out.index(OTHER[:8]))

    def test_find_caps_results(self):
        mod = self.stocked()
        _, out = self.out(mod, mod.cmd_find, ["-n", "1", "/home/u"])
        self.assertNotIn(OTHER[:8], out)

    def test_find_json_is_the_records(self):
        mod = self.stocked()
        _, out = self.out(mod, mod.cmd_find, ["--json", "abc-123"])
        data = json.loads(out)
        self.assertEqual(data[0]["id"], UUID)
        self.assertNotIn("census", data[0])

    def test_ls_prints_the_title_and_no_prompt_text(self):
        mod = self.stocked()
        _, out = self.out(mod, mod.cmd_ls, [])
        self.assertIn("Fix the thing", out)
        self.assertNotIn("the first thing I typed", out)
        self.assertNotIn("half way through", out)

    def test_ls_falls_back_to_a_prompt_when_there_is_no_title(self):
        mod = self.stocked()
        _, out = self.out(mod, mod.cmd_ls, [])
        self.assertIn("something else", out)

    def test_ls_marks_a_live_session(self):
        mod = self.stocked()
        mod.live_session_ids = lambda: ({UUID}, 0)
        _, out = self.out(mod, mod.cmd_ls, [])
        line = [l for l in out.splitlines() if UUID[:8] in l][0]
        self.assertTrue(line.startswith("*"))

    def test_show_needs_six_characters(self):
        mod = self.stocked()
        self.assertEqual(self.out(mod, mod.cmd_show, ["7b3e"])[0], 2)

    def test_show_lists_candidates_on_an_ambiguous_prefix(self):
        mod = self.stocked([
            {"id": "aaaaaaaa-0000-4000-8000-000000000001",
             "cwd": "/a", "mtime": 2.0},
            {"id": "aaaaaaaa-0000-4000-8000-000000000002",
             "cwd": "/b", "mtime": 1.0},
        ])
        code, out = self.out(mod, mod.cmd_show, ["aaaaaaaa"])
        self.assertEqual(code, 2)
        self.assertIn("000000000001", out)
        self.assertIn("000000000002", out)

    def test_show_resolves_a_unique_prefix_and_prints_the_rejoin(self):
        mod = self.stocked()
        code, out = self.out(mod, mod.cmd_show, [UUID[:8]])
        self.assertEqual(code, 0)
        self.assertIn("claude -r %s" % UUID, out)
        self.assertIn("/home/u/code", out)
        self.assertIn("half way through", out)

    def test_the_rejoin_line_quotes_a_cwd_with_a_space(self):
        mod = self.stocked([
            {"id": UUID, "cwd": "/home/u/My Repo", "mtime": 1.0},
        ])
        code, out = self.out(mod, mod.cmd_show, [UUID[:8]])
        self.assertEqual(code, 0)
        self.assertIn("cd '/home/u/My Repo' && claude -r %s" % UUID, out)

    def test_show_marks_a_live_session(self):
        mod = self.stocked()
        mod.live_session_ids = lambda: ({UUID}, 0)
        _, out = self.out(mod, mod.cmd_show, [UUID[:8]])
        self.assertIn("live", out.lower())

    def test_show_on_an_unknown_id_exits_1(self):
        mod = self.stocked()
        self.assertEqual(
            self.out(mod, mod.cmd_show,
                     ["ffffffff-0000-4000-8000-000000000009"])[0], 1)

    def test_no_index_means_one_line_exit_1_and_no_build(self):
        mod = self.loaded()
        self.transcript(UUID, [self.user("hello")])
        for fn, args in ((mod.cmd_find, ["x"]), (mod.cmd_ls, []),
                         (mod.cmd_show, [UUID])):
            code, out = self.out(mod, fn, args)
            self.assertEqual(code, 1)
            self.assertIn("hail index", out)
        self.assertIsNone(mod.load_index())


class Doctor(Base):
    def out(self, mod, args=None):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = mod.cmd_doctor(args or [])
        return code, buf.getvalue()

    def test_a_clean_setup_exits_0_and_names_the_paths(self):
        mod = self.loaded()
        code, out = self.out(mod)
        self.assertEqual(code, 0)
        self.assertIn(mod.config_path(), out)
        self.assertIn(mod.index_path(), out)

    def test_reports_the_source_of_each_ticket_key(self):
        self.logbook_config({"version": 1,
                             "ticket": {"pattern": r"[A-Z]{3}-\d+"}})
        self.config({"version": 1, "ticket": {"reserved": ["ZZZ"]}})
        mod = self.loaded()
        _, out = self.out(mod)
        self.assertIn("inherited from logbook.json", out)
        self.assertIn("file", out)

    def test_a_logbook_hail_index_pointing_elsewhere_is_a_finding(self):
        self.logbook_config({"version": 1,
                             "hail": {"index": "~/.claude/somewhere.json"}})
        mod = self.loaded()
        code, out = self.out(mod)
        self.assertEqual(code, 1)
        self.assertIn("somewhere.json", out)

    def test_logbook_pointing_at_the_right_path_is_not_a_finding(self):
        mod = self.loaded()
        self.logbook_config({"version": 1,
                             "hail": {"index": mod.index_path()}})
        self.assertEqual(self.out(self.loaded())[0], 0)

    def test_an_absent_hail_key_is_not_a_finding(self):
        self.logbook_config({"version": 1, "ticket": {}})
        self.assertEqual(self.out(self.loaded())[0], 0)

    def test_a_persisted_regression_makes_doctor_exit_1(self):
        mod = self.loaded()
        mod.write_index({"version": 1, "sessions": [],
                         "scan_signature": mod.scan_signature(),
                         "census": {"kept_on_regression": 2}})
        code, out = self.out(mod)
        self.assertEqual(code, 1)
        self.assertIn("kept", out)

    def test_a_persisted_no_cwd_count_makes_doctor_exit_1(self):
        mod = self.loaded()
        mod.write_index({"version": 1, "sessions": [],
                         "scan_signature": mod.scan_signature(),
                         "census": {"user_records_no_cwd": 3}})
        self.assertEqual(self.out(mod)[0], 1)

    def test_reports_the_index_mode_and_age(self):
        # "%04o" % mode, not oct(mode): oct gives "0o600", which does
        # not contain "0600" and fails this assertion
        mod = self.loaded()
        mod.write_index({"version": 1, "sessions": [], "census": {}})
        _, out = self.out(mod)
        self.assertIn("0600", out)

    def test_a_fresh_index_is_not_a_staleness_finding(self):
        mod = self.loaded()
        mod.write_index({"version": 1, "sessions": [], "census": {}})
        code, out = self.out(mod)
        self.assertEqual(code, 0)
        self.assertNotIn("stale", out)

    def test_a_stale_index_is_a_finding_and_exits_1(self):
        mod = self.loaded()
        mod.write_index({"version": 1, "sessions": [], "census": {}})
        old = time.time() - mod.STALE_INDEX_SECONDS - 1
        os.utime(mod.index_path(), (old, old))
        code, out = self.out(mod)
        self.assertEqual(code, 1)
        self.assertIn("stale", out)

    def test_reports_how_many_sessions_files_lacked_procStart(self):
        mod = self.loaded()
        with open(os.path.join(self.live, "4242.json"), "w") as fh:
            json.dump({"pid": 4242, "sessionId": UUID}, fh)
        _, out = self.out(mod)
        self.assertIn("procStart", out)

    def test_a_home_reached_through_a_symlink_is_not_a_mismatch(self):
        # index_path realpaths, logbook's config value does not, so
        # comparing them unresolved reports a false mismatch
        mod = self.loaded()
        link = os.path.join(self.tmp.name, "link-home")
        os.symlink(self.home, link)
        self.logbook_config({"version": 1, "hail": {"index": os.path.join(
            link, ".claude", "binnacle", "hail", "index.json")}})
        self.assertEqual(self.out(self.loaded())[0], 0)

    def test_doctor_runs_under_a_fatal_config(self):
        # the one command that must work when nothing else does
        self.config({"version": 99})
        mod = self.loaded()
        code, out = self.out(mod)
        self.assertEqual(code, 4)
        self.assertIn("version", out)

    def test_reports_the_extraction_table(self):
        mod = self.loaded()
        _, out = self.out(mod)
        for key in ("aiTitle", "gitBranch", "isSidechain", "cwd"):
            self.assertIn(key, out)


class Hook(Base):
    HOOK = os.path.join(REPO, "hooks", "hail-index.py")

    def load_hook(self):
        loader = importlib.machinery.SourceFileLoader("hail_hook", self.HOOK)
        spec = importlib.util.spec_from_loader("hail_hook", loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        return module

    def run_hook(self, mod=None):
        # sys.stdin must be replaced. main() reads the hook payload from
        # it, and in-process under `python3 -m unittest` that is the
        # terminal: the call blocks until EOF and the suite hangs.
        # logbook's hook tests avoid this by passing input="{}" to a
        # subprocess (test_logbook.py:2033); in-process the equivalent
        # is a StringIO.
        import io
        import contextlib
        hook = self.load_hook()
        tool = mod or self.loaded()
        hook.load_tool = lambda: tool
        real_stdin = sys.stdin
        sys.stdin = io.StringIO("{}")
        self.addCleanup(setattr, sys, "stdin", real_stdin)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = hook.main()
        return code, buf.getvalue()

    def test_prints_nothing_and_exits_0_on_a_clean_run(self):
        self.transcript(UUID, [self.user("hello")])
        code, out = self.run_hook()
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_the_index_is_actually_built(self):
        mod = self.loaded()
        self.transcript(UUID, [self.user("hello")])
        self.run_hook(mod)
        self.assertEqual(mod.load_index()["sessions"][0]["id"], UUID)

    def test_prints_one_line_on_the_cold_refusal(self):
        mod = self.loaded(scan={"min_sample": 1, "min_bytes": 0})
        self.transcript(UUID, [{"type": "user", "isSidechain": False,
                                "timestamp": "2026-09-12T09:00:00.000Z",
                                "message": {"role": "user",
                                            "content": "hi"}}])
        code, out = self.run_hook(mod)
        self.assertEqual(code, 0)
        self.assertEqual(len(out.strip().splitlines()), 1)

    def test_prints_one_line_when_a_record_was_kept(self):
        # a guard whose whole purpose is surfacing a silent failure
        # cannot itself be silent
        mod = self.loaded()
        self.transcript(UUID, [self.user("hi", cwd="/moved")])
        mod.write_index({"version": 1,
                         "scan_signature": mod.scan_signature(),
                         "census": {},
                         "sessions": [{"id": UUID, "cwd": "/home/u/code",
                                       "mtime": 1000.0, "size": 1,
                                       "branches": [], "prs": [],
                                       "tickets": [], "turns": 1,
                                       "first_ts":
                                           "2026-09-12T09:00:00.000Z"}]})
        code, out = self.run_hook(mod)
        self.assertEqual(code, 0)
        self.assertIn("hail doctor", out)

    def test_prints_one_line_when_a_transcript_had_no_cwd(self):
        mod = self.loaded()
        self.transcript(UUID, [{"type": "user", "isSidechain": False,
                                "gitBranch": "b",
                                "timestamp": "2026-09-12T09:00:00.000Z",
                                "message": {"role": "user",
                                            "content": "hi"}}])
        code, out = self.run_hook(mod)
        self.assertEqual(code, 0)
        self.assertIn("hail doctor", out)

    def test_exits_0_on_a_fatal_config(self):
        self.config({"version": 99})
        code, _ = self.run_hook()
        self.assertEqual(code, 0)

    def test_exits_0_on_a_missing_transcripts_directory(self):
        mod = self.loaded(scan={"transcripts":
                                os.path.join(self.tmp.name, "gone")})
        self.assertEqual(self.run_hook(mod)[0], 0)

    def test_a_missing_transcripts_directory_writes_no_index(self):
        mod = self.loaded(scan={"transcripts":
                                os.path.join(self.tmp.name, "gone")})
        mod.write_index({"version": 1, "sessions": [{"id": UUID}],
                         "census": {}})
        self.run_hook(mod)
        self.assertEqual(mod.load_index()["sessions"][0]["id"], UUID)

    def test_exits_0_when_the_build_raises(self):
        mod = self.loaded()

        def boom(**kw):
            raise RuntimeError("anything at all")

        mod.build = boom
        self.assertEqual(self.run_hook(mod)[0], 0)

    def test_its_output_never_contains_a_prompt(self):
        mod = self.loaded()
        self.transcript(UUID, [self.user("a distinctive fixture prompt")])
        _, out = self.run_hook(mod)
        self.assertNotIn("distinctive fixture", out)

    def test_hooks_json_declares_only_SessionStart(self):
        with open(os.path.join(REPO, "hooks", "hooks.json")) as fh:
            data = json.load(fh)
        self.assertEqual(list(data["hooks"]), ["SessionStart"])

    def test_hooks_json_declares_a_timeout(self):
        with open(os.path.join(REPO, "hooks", "hooks.json")) as fh:
            data = json.load(fh)
        entry = data["hooks"]["SessionStart"][0]["hooks"][0]
        self.assertEqual(entry["timeout"], 60)


class LogbookContract(Base):
    def logbook_module(self):
        # REPO is hail/public, so two levels up is the repo root and
        # one level up is the published root. Three levels would leave
        # the repo entirely and both tests would skip forever while
        # looking like they ran.
        for rel in (os.path.join("..", "..", "logbook", "public",
                                 "bin", "logbook"),
                    os.path.join("..", "logbook", "bin", "logbook")):
            path = os.path.normpath(os.path.join(REPO, rel))
            if os.path.exists(path):
                loader = importlib.machinery.SourceFileLoader("logbook",
                                                              path)
                spec = importlib.util.spec_from_loader("logbook", loader)
                module = importlib.util.module_from_spec(spec)
                loader.exec_module(module)
                return module
        return None

    def test_logbook_turns_hails_index_into_a_rejoin_hint(self):
        mod = self.loaded()
        self.transcript(UUID, [self.user("hello")])
        payload, _, _ = mod.build()
        mod.write_index(payload)
        logbook = self.logbook_module()
        if logbook is None:
            self.skipTest("logbook is not installed beside hail")
        logbook.SESSION_INDEX = mod.index_path()
        hint = logbook.resume_hint(UUID)
        self.assertIsNotNone(hint)
        self.assertIn(UUID, hint)
        self.assertIn("/home/u/code", hint)

    def test_a_six_character_prefix_resolves_through_logbook(self):
        # logbook matches prefixes in both directions (logbook:584)
        mod = self.loaded()
        self.transcript(UUID, [self.user("hello")])
        payload, _, _ = mod.build()
        mod.write_index(payload)
        logbook = self.logbook_module()
        if logbook is None:
            self.skipTest("logbook is not installed beside hail")
        logbook.SESSION_INDEX = mod.index_path()
        self.assertIsNotNone(logbook.resume_hint(UUID[:8]))

    def test_the_private_layout_actually_resolves(self):
        # Without this the two tests above are a permanent green
        # no-op. One ".." too many in logbook_module makes it return
        # None, both skip, and a skip reads as a pass in the summary
        # line. The path here is written out independently on purpose:
        # comparing it against the helper is the whole point.
        sibling = os.path.normpath(os.path.join(
            REPO, "..", "..", "logbook", "public", "bin", "logbook"))
        if not os.path.exists(sibling):
            self.skipTest("not the private checkout")
        self.assertIsNotNone(self.logbook_module())


class Version(Base):
    """The version is now load-bearing: chartroom refuses a sibling
    that cannot report one, so a wrong number is worse than none."""

    def test_version_flag_prints_and_exits_zero(self):
        out = subprocess.run([sys.executable, HAIL_PATH, "--version"],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0)
        self.assertRegex(out.stdout.strip(), r"^\d+\.\d+\.\d+$")

    def test_the_binary_and_the_manifest_agree(self):
        mod = self.loaded()
        manifest = os.path.join(REPO, ".claude-plugin", "plugin.json")
        with open(manifest) as fh:
            self.assertEqual(json.load(fh)["version"], mod.VERSION)

    def test_version_answers_under_a_broken_config(self):
        # main checks argv[0] == "--version" before the fatal-config
        # branch, so this keeps working when nothing else does.
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        os.makedirs(os.path.join(home, ".claude", "binnacle"))
        with open(os.path.join(home, ".claude", "binnacle",
                               "hail.json"), "w") as fh:
            fh.write("{ not json")
        out = subprocess.run([sys.executable, HAIL_PATH, "--version"],
                             capture_output=True, text=True,
                             env=dict(os.environ, HOME=home))
        self.assertEqual(out.returncode, 0)


class BranchTickets(Base):
    """tickets_from_branch: the subset of tickets a branch name carries."""

    def test_a_body_mention_is_not_a_branch_key(self):
        mod = self.loaded()
        p = self.transcript(UUID, [
            self.user("looks like ABC-999 is related", branch="feat/x"),
        ])
        rec = mod.scan_file(p, "-home-u-code")
        self.assertEqual(rec["tickets"], ["ABC-999"])
        self.assertEqual(rec["tickets_from_branch"], [])

    def test_a_branch_key_is_a_branch_key(self):
        mod = self.loaded()
        p = self.transcript(UUID, [
            self.user("anything", branch="abc-123-thing"),
        ])
        rec = mod.scan_file(p, "-home-u-code")
        self.assertEqual(rec["tickets_from_branch"], ["ABC-123"])

    def test_a_key_in_both_branch_and_body_counts_once_as_branch(self):
        mod = self.loaded()
        p = self.transcript(UUID, [
            self.user("ABC-123 again and ABC-123 again",
                      branch="abc-123-thing"),
        ])
        rec = mod.scan_file(p, "-home-u-code")
        self.assertEqual(rec["tickets_from_branch"], ["ABC-123"])
        self.assertEqual(rec["tickets"].count("ABC-123"), 1)

    def test_a_reserved_prefix_is_not_a_branch_key(self):
        mod = self.loaded()
        p = self.transcript(UUID, [
            self.user("x", branch="utf-8-encoding-fix"),
        ])
        rec = mod.scan_file(p, "-home-u-code")
        self.assertEqual(rec["tickets_from_branch"], [])

    def test_the_extractor_version_forces_a_rescan(self):
        # without this the new field is absent from every cached record
        # forever, on exactly the machines that upgrade
        mod = self.loaded()
        self.assertGreaterEqual(mod.EXTRACTOR_VERSION, 2)

    def test_the_new_field_is_guarded_against_regression(self):
        self.assertIn("tickets_from_branch", self.loaded().SUPERSET_LISTS)


class LsJson(Base):
    """hail ls --json: the whole envelope, refusals on stderr."""

    def call(self, mod, args):
        import contextlib
        import io
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            code = mod.cmd_ls(args)
        return code, out.getvalue(), err.getvalue()

    def record(self, n):
        return {"id": "aaaaaaaa-0000-4000-8000-%012d" % n,
                "cwd": "/home/u/code", "branches": ["abc-1-thing"],
                "tickets": ["ABC-1"], "tickets_from_branch": ["ABC-1"],
                "prs": [], "turns": 1,
                "first_ts": "2026-09-12T09:00:00.000Z",
                "last_ts": "2026-09-12T09:00:00.000Z",
                "mtime": 1000.0 + n, "size": 10}

    def stocked(self, count=1, days=10, aged_off=0, strip_records=False):
        mod = self.loaded()
        sessions = [self.record(i) for i in range(count)]
        if strip_records:
            for r in sessions:
                del r["tickets_from_branch"]
        mod.write_index({
            "version": 1, "built_at": "2026-09-12T01:00:00Z", "days": days,
            "scan_signature": mod.scan_signature(),
            "census": {"aged_off": aged_off},
            "sessions": sessions})
        return mod

    def test_the_envelope_carries_days_and_census(self):
        # chartroom reads the window and the aged-off figure from here
        # rather than from hail.json, so the CLI stays the contract
        mod = self.stocked(aged_off=5)
        code, out, err = self.call(mod, ["--json"])
        self.assertEqual(code, 0)
        body = json.loads(out)
        self.assertEqual(body["version"], 1)
        self.assertIn("days", body)
        self.assertEqual(body["census"]["aged_off"], 5)
        self.assertNotIn("scan_signature", body)

    def test_json_returns_every_record_not_the_first_ten(self):
        mod = self.stocked(count=25)
        code, out, err = self.call(mod, ["--json"])
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(out)["sessions"]), 25)

    def test_n_with_json_is_refused(self):
        # hail refuses meaningless arguments everywhere else; a silently
        # truncated page is a page that lies quietly
        mod = self.stocked()
        code, out, err = self.call(mod, ["--json", "-n", "5"])
        self.assertEqual(code, 2)

    def test_an_index_predating_the_field_is_refused(self):
        mod = self.stocked(strip_records=True)
        code, out, err = self.call(mod, ["--json"])
        self.assertEqual(code, 1)
        self.assertIn("predates", err)
        self.assertEqual(out, "")

    def test_absent_and_unreadable_are_told_apart(self):
        mod = self.loaded()
        code, out, err = self.call(mod, ["--json"])
        self.assertEqual(code, 1)
        self.assertIn("no index", err)

        os.makedirs(os.path.dirname(mod.index_path()), exist_ok=True)
        with open(mod.index_path(), "w") as fh:
            fh.write("{ not json")
        code, out, err = self.call(mod, ["--json"])
        self.assertEqual(code, 1)
        self.assertIn("unreadable", err)

    def test_refusals_go_to_stderr_and_the_human_path_is_unchanged(self):
        mod = self.loaded()
        code, out, err = self.call(mod, ["--json"])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("no index", err)

        code, out, err = self.call(mod, [])
        self.assertEqual(code, 1)
        self.assertIn("no index", out)
        self.assertEqual(err, "")

    def test_json_does_not_build_an_index(self):
        mod = self.loaded()
        self.call(mod, ["--json"])
        self.assertFalse(os.path.exists(mod.index_path()))

    def test_prompts_and_path_never_leave_through_json(self):
        # a full record, so the emitted key set can be checked exactly
        # rather than merely "the sentinel is not in there somewhere"
        sentinel = "SENTINEL-do-not-export-this"
        mod = self.loaded()
        record = {
            "id": "aaaaaaaa-0000-4000-8000-000000000001",
            "project": "-home-u-code",
            "path": "/home/u/.claude/projects/%s.jsonl" % sentinel,
            "title": "t", "cwd": "/home/u/code", "branches": ["b"],
            "tickets": ["ABC-1"], "tickets_from_branch": ["ABC-1"],
            "prs": [], "prompts": [sentinel], "prompts_truncated": False,
            "last_prompt": sentinel, "last_prompt_truncated": False,
            "turns": 1, "first_ts": "2026-09-12T09:00:00.000Z",
            "last_ts": "2026-09-12T09:00:00.000Z",
            "mtime": 1000.0, "size": 10,
        }
        mod.write_index({
            "version": 1, "built_at": "2026-09-12T01:00:00Z", "days": 10,
            "scan_signature": mod.scan_signature(), "census": {},
            "sessions": [record]})
        code, out, err = self.call(mod, ["--json"])
        self.assertEqual(code, 0)
        self.assertNotIn(sentinel, out)
        emitted = json.loads(out)["sessions"][0]
        self.assertEqual(set(emitted), set(mod.LS_JSON_FIELDS))


class ShippedDocs(Base):
    """The two copies of the defaults that ship to users.

    Both are prose, so nothing else notices when they drift from
    DEFAULTS. A stale default in the README is worse than none: it is
    read as a promise about what the tool does.
    """

    def documented(self, text):
        start = text.index("```json") + len("```json")
        return json.loads(text[start:text.index("```", start)])

    def without_version(self, body):
        return {k: v for k, v in body.items() if k != "version"}

    def test_the_example_config_is_the_defaults(self):
        mod = self.loaded()
        with open(os.path.join(REPO, "examples", "hail.json")) as fh:
            example = json.load(fh)
        self.assertEqual(example.get("version"), mod.CONFIG_VERSION)
        self.assertEqual(self.without_version(example), mod.DEFAULTS)

    def test_the_readme_documents_the_defaults(self):
        mod = self.loaded()
        with open(os.path.join(REPO, "README.md")) as fh:
            block = self.documented(fh.read())
        self.assertEqual(self.without_version(block), mod.DEFAULTS)
