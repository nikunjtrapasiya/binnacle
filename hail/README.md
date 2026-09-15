# hail

Find a past session and rejoin it.

A Claude Code plugin, part of
[binnacle](https://github.com/nikunjtrapasiya/binnacle).

## The problem

You worked on this ticket last week, in another checkout. Or this
morning, in a session that ended before you finished. You remember a
fact about it - the branch, the directory, something you typed - but
not the session id, and Claude Code gives you no way to search by any
of that.

`hail` builds a small index over the transcripts already sitting on
your disk, and gives you `find`, `ls` and `show` to search it.

## How it works

```
  Claude Code writes a transcript as you work
                   |
                   | hail index scans it
                   v
  the index: title, branch, ticket, cwd, prompts
                   |
                   | hail find / ls / show
                   v
  you, rejoining a session
```

A `SessionStart` hook keeps the index current on its own: it rescans
whatever changed since the last run, which in steady state is only the
current session's own transcript. `find`, `ls` and `show` never build
the index themselves - see
["The transcript format is not an interface"](#the-transcript-format-is-not-an-interface)
for why a read command building on demand is the wrong shape here.

## Install

```
/plugin marketplace add nikunjtrapasiya/binnacle
/plugin install hail@binnacle
```

Nothing else to set up inside Claude Code. The hook wires itself, and
every setting has a default.

The install puts `hail` on `PATH` **inside a Claude Code session**. A
plain terminal has never heard of it, so the commands below either run
from a session, or need the installed binary on your own `PATH`:

```
ls ~/.claude/plugins/cache/binnacle/hail/*/bin/
```

That path carries the installed version, so it moves at every
`/plugin update`. A symlink from somewhere already on your `PATH` is
the version-independent way.

## Try it in a minute

```
hail index               # first build; the hook does this for you after
hail ls
hail find ABC-123
hail show <id-prefix>
hail doctor
```

## Commands

```
hail index [--days N] [--force]   rebuild, incremental by default
hail find <query> [--json] [-n N] ticket, title, branch, cwd, prompt, PR
hail ls [-n N] | ls --json        most recent, live sessions marked
hail show <id>                    one session in full
hail doctor                       settings in force, and scan health
hail --version                    print the version
```

**`--json` has two shapes, one per command, and this is deliberate.**
`find --json` prints a bare list of the matched records: a search
returns matches and nothing else. `ls --json` prints an envelope -
`{"version", "built_at", "days", "census", "sessions"}` - because a
reader of the whole index needs the numbers it must not invent: how far
back the window reaches, and what the last build counted. Without them
a consumer cannot tell "no sessions worked this" from "the sessions
that did have aged out of the window".

`ls --json` takes no `-n`. A truncated envelope still carries a census
describing the whole index, and the two together read as a complete
picture that is not one; `-n` with `--json` is an argument refusal
rather than a quietly misleading answer.

- **`find`** matches case-insensitively against the title, every
  branch, the `cwd`, the stored prompts, and each PR's number and repo.
  `cwd` is in there on purpose - "the session in the `o/r` checkout" is
  a real query. A query that normalises to a ticket key under the
  configured pattern (upper-cased, a full match, not a reserved prefix)
  is matched against the ticket list exactly instead, not as a
  substring, so `ABC-1` does not match `ABC-1270` - and a partial key
  like `ABC` searches the text above, not the ticket list. Results
  print in index order (most recent first), never ranked by match
  quality. A live session's line starts with `*`, as in `ls`, but
  `find` prints no legend line. Unlike `index` and `ls`, `find` does
  not refuse an unrecognised argument - anything that is not `--json`
  or `-n` becomes part of the query, so a mistyped flag reads as a
  search that found nothing. `--json` prints the matched records
  exactly as stored, header excluded - it is not a redaction boundary,
  and it is the widest output hail has.
- **`ls`** lists the most recent sessions, one line each:
  `<id-prefix>  <last-turn date>  <ticket or ->  <branch or -, cut to
  24 chars>  <title or first prompt>`. A live session's line starts
  with `*`, and a legend line
  prints once when any row is live. The line form never prints a
  stored prompt beyond that title fallback. `ls --json` prints the
  envelope described above instead, with each session trimmed to an
  allowlist of structural fields - `id`, `project`, `cwd`, `branches`,
  `tickets`, `tickets_from_branch`, `prs`, `turns`, `first_ts`,
  `last_ts`, `title`, `mtime`, `size` - so prompt text and the
  transcript's on-disk path never leave through this command either.
  It refuses - on stderr, with stdout left empty - when there is no
  index, when the index is unreadable, or when it predates this
  version and so has no `tickets_from_branch`.
- **`show <id>`** accepts a full session id or a unique prefix of at
  least six characters. A shorter prefix is refused; an ambiguous one
  lists the candidates and exits 2 rather than guessing. It is the
  command that prints a session's prompt text - `cwd`, branches,
  tickets, PRs, turn count, first and last timestamp, whether the
  session is still running, every stored prompt, and a
  `cd ... && claude -r ...` line to rejoin it. It is not the widest
  output hail has: `find --json` prints each matched record whole,
  including fields `show` never shows.
- **`doctor`** prints the config path, then for each `index` and `scan`
  setting whether its value differs from the default (`file`) or
  matches it (`default`) - a config that restates a default reads as
  `default` - and for `ticket.pattern` and `ticket.reserved` the true
  source: `default`, `file`, or `inherited from logbook.json`. Then the
  index's path, mode, age and size, the persisted census from the last
  build, and the list of transcript keys it extracts (`aiTitle`,
  `pr-link`, `type`/`isSidechain`, `cwd`, `gitBranch`, `timestamp`), so
  a format change can be checked against what hail is actually looking
  for. It exits 1 when that census shows a regression or a cwd-less
  scan, when the index is older than the staleness threshold (a
  heuristic seven days), or when `logbook.json`'s `hail.index` names a
  path hail does not write. Otherwise 0, except that a config `doctor`
  cannot load exits 4 - a `doctor` that always exits 0 cannot be used
  in a check.
- **`--days` must be a positive integer.** `0` or a negative number is
  an argument refusal, not a window that quietly indexes nothing.
- With no index built yet, `find`, `ls` and `show` print one line
  saying to run `hail index`, and exit 1.

## The transcript format is not an interface

Nothing about how Claude Code writes a transcript is documented or
promised. `hail` reads it anyway, because it is the only record of a
session that exists - matching lines like `"ai-title"` for a title,
`gitBranch` for a branch, `cwd` on a user turn. Any Claude Code release
can rename one of those keys, move a title into a different record, or
change how the file is serialised, with no announcement anywhere.

Without a guard, the failure is silent and destructive. The scan reads
every byte of an updated transcript, matches nothing, and writes empty
records over the good ones already in the index. `hail find` then
returns nothing for a session that used to be findable, and the natural
conclusion is that the session never existed. Nothing says "the format
changed" - it just looks like the index, or the session, was never
there.

Two guards sit between a format change and that outcome, one for each
way a transcript gets scanned:

```
  a transcript is scanned
    |
    +-- no cached record: first build, --force, or config changed
    |     |
    |     +-- at the end of the build: scanned at least min_sample
    |         files / min_bytes total, and no record at all has a cwd?
    |           yes:  write nothing, exit 5. The old index is left
    |                 exactly as it was.
    |           no:   write the index
    |
    +-- a cached record exists, under the same config: incremental rescan
          |
          +-- is the fresh record a superset of the cached one?
                yes:  write the index
                no:   keep the cached record.
                      census.kept_on_regression += 1.
                      The index is still written, exit 0.
```

**The incremental path** compares, per file, whether a rescan grew what
it had: `cwd` and `first_ts` unchanged, `title` never goes from present
to absent, and `branches`, `prs`, `turns`, `tickets` and
`tickets_from_branch` only grow. A
transcript is append-only, so a fresh scan that loses one of those
fields did not lose real data - it lost the ability to read what was
already there, which means the extractor broke, not that the session
changed. When that happens the cached record is kept and the fresh one
thrown away. The file is rescanned again on the next run, and the one
after that, until the extractor is fixed - that repetition is the
signal working as intended, not a bug.

**The cold path** is a whole-build check, run on every build, and it
carries the first build, a `--force` rebuild and a config change that
invalidates the cache. There is nothing to compare a fresh record
against, so the guard asks a different question, after the per-file
work rather than during it: does the index about to be written contain
a single record with a `cwd`? If a run freshly scanned at least
`scan.min_sample` files totalling at least `scan.min_bytes` and no
record - fresh or reused - carries a `cwd`, it refuses outright,
writes nothing, prints what it was looking for, and exits 5. The
existing index is left exactly as it was. A warm run where only the
fresh files lack a `cwd` is not a refusal: those are counted in
`user_records_no_cwd` and reported instead, because an index that is
mostly good should not be thrown away.

**What the census numbers mean when they are not zero.** `hail index`
and `hail doctor` both print a census - the counts from the last build.
Two of those fields exist only for this guard, and either one above
zero means something is worth looking at:

- `kept_on_regression` - one or more files lost fields on a rescan and
  their cached record was kept instead. Something about the transcript
  format changed under an extractor that has not caught up.
- `user_records_no_cwd` - user turns were found but none carried a
  `cwd`. Short of the cold-path refusal, this is the same signal
  arriving early.

`hail doctor` exits 1 when either is above zero, specifically so this
can be used in a check rather than requiring someone to read the census
by eye.

## What is stored, and who can read it

The index holds, per session: the session id, the project directory
name and the transcript's path on disk, the title, every branch and
ticket seen (twice - see below), `cwd`, PR links, the turn count,
first and last timestamp, the file's mtime and size, and prompt text:
the first `index.prompts` prompts plus, for a session longer than that,
its most recent prompt as `last_prompt`. Each stored prompt is cut to
`index.prompt_chars`, and a flag records whether the cut happened.

Tickets are kept twice, and the difference matters to anything reading
the index. `tickets` is every ticket key seen anywhere in the session,
including one merely mentioned in passing. `tickets_from_branch` is
only the keys derived from the session's own branch names. A consumer
whose claim is "these sessions worked this ticket" wants the second;
the first would let one mention put a session under work it never did.
The two are derived by one function, so they cannot drift apart.

- **`find`, `ls` and `show` print it. No hook does.** These three
  commands exist because printing this back to you is the point. Note
  that the bundled skill has Claude run them on your behalf, so a
  `hail show` it runs puts that session's stored prompts into the
  current session's context; uninstall the skill if that is not what
  you want.
- `ls` is the one partial exception worth naming precisely: its line
  never prints a stored prompt, except that a session with no title
  falls back to printing its first stored prompt as the label, or
  `last_prompt` when `index.prompts` is `0` and there is no first one.
  That is a prompt, and it is the only prompt text the line form of
  `ls` ever shows. `ls --json` shows none at all - it emits only the allowlisted
  structural fields above, never `prompts`, `last_prompt`, or the
  transcript `path`.
- The **one** thing that reaches a hook's output is logbook's own
  rejoin line, `cd <cwd> && claude -r <id>`, which logbook's
  `SessionStart` brief prints when it reads this index. That line is
  built from `id` and `cwd` only - never prompt text - which is why
  both fields are validated before a record is written at all: a
  malformed `id` or `cwd` reaching that line would be a hook printing
  bad data into a session's own context.
- The index file is mode **0600**. Nothing but your own account can
  read it.

## The index path is fixed, and config cannot move it

The index always lives at:

```
<your home>/.claude/binnacle/hail/index.json
```

There is no `index.path` setting, and that is deliberate, not an
oversight. A configurable write target guarded by "must be under your
home directory" is not actually constrained, because your home
directory already contains `~/.ssh` and `~/.claude` itself - a check
like that would happily let a config value point the write at either
one. The only setting that is actually safe here is no setting: one
path, fixed in code, never taken from a file you can edit.

"Your home" is read from the account's own passwd entry, not the
`HOME` environment variable, so a repointed `HOME` cannot move the
write either.

## Full config reference

Config lives at `~/.claude/binnacle/hail.json`, same loader discipline
as logbook: every key has a working default, an unknown key warns, a
wrong type keeps the default and warns, and an unparseable file or
unknown `version` is fatal for every command except `doctor` and
`--version`.

```json
{
  "version": 1,
  "index": {
    "days": 10,
    "prompts": 2,
    "prompt_chars": 300
  },
  "ticket": {
    "pattern": "[A-Z]{2,6}-\\d{1,7}",
    "reserved": ["ISO", "UTF", "SHA", "AES", "RGB", "RFC", "HTTP", "IPV"]
  },
  "scan": {
    "transcripts": "~/.claude/projects",
    "live": "~/.claude/sessions",
    "min_sample": 5,
    "min_bytes": 1048576,
    "ignore_prefixes": [
      "<command-", "<local-command", "<system-reminder", "Caveat:",
      "Base directory for this skill", "The following skills",
      "ARGUMENTS:", "This session is being continued",
      "Note: /Users", "Result of calling", "Called the ",
      "<bash-input", "<bash-stdout", "<ide-", "[Request interrupted",
      "<task-notification"
    ]
  }
}
```

| Key | Default | What it does |
|---|---|---|
| `version` | `1` | Config schema version. A mismatch refuses every command except `doctor`; `--version` still answers, so a consumer can detect the installation even when it refuses to run. |
| `index.days` | `10` | How many days back a session has to have been touched to stay in the index. Older sessions age out of the index, not out of the transcripts - the transcripts are the durable store, the index is a cache you can delete and rebuild. |
| `index.prompts` | `2` | How many prompts are kept from the start of a session, for `find` and `show` to search and print. A session with more prompts than this also keeps its most recent one as `last_prompt`, so the stored count is `index.prompts + 1`. Setting it to `0` does not switch prompt storage off - it leaves only `last_prompt`. |
| `index.prompt_chars` | `300` | How many characters of each stored prompt are kept. |
| `ticket.pattern` | `[A-Z]{2,6}-\d{1,7}` | The regex a ticket key must match, wrapped in word boundaries before use. Inherited from `logbook.json` when that file exists, parses, declares `version` 1, and carries a `ticket.pattern` - see below. |
| `ticket.reserved` | `["ISO", "UTF", "SHA", "AES", "RGB", "RFC", "HTTP", "IPV"]` | Prefixes that look like a ticket key but are not one, so `UTF-8` is never read as a ticket. Inherited from `logbook.json` the same way as `pattern`, independently. |
| `scan.transcripts` | `~/.claude/projects` | Where Claude Code writes transcripts. Read from, never written to. |
| `scan.live` | `~/.claude/sessions` | Where Claude Code writes the marker files a session's own process keeps alive. Used to prefix a live session's line with `*` in `ls` and `find`, and to print `live: yes` in `show`. |
| `scan.min_sample` | `5` | Part of the cold-path guard above: the minimum number of freshly scanned files before the zero-`cwd` check applies. |
| `scan.min_bytes` | `1048576` | Part of the same guard: the minimum total bytes scanned before it applies. |
| `scan.ignore_prefixes` | see above | Lines a user turn starts with that are not a real prompt - tool output, system reminders, and the like - so they never get stored as one or mined for tickets. The last entry, `<task-notification`, exists because a finished background agent posts its report as a user-shaped record; without filtering it, its temporary paths and agent ids were being read as ticket keys. |

`ticket.pattern` and `ticket.reserved` inherit from `logbook.json`
independently, one key at a time - `hail`'s own `ticket.pattern` in its
config wins over an inherited one and says nothing about whether
`reserved` is also inherited, and the reverse. Inheritance requires
`logbook.json` to exist, parse, and declare `version` 1 - a
`logbook.json` that fails any of those falls back to `hail`'s own
default rather than failing `hail`'s command, because `hail` does not
depend on `logbook` being installed or correct. An uncompilable pattern
falls back the same way. `hail` does not honour `LOGBOOK_CONFIG`; it
only ever reads `logbook.json` at its default path. `doctor` reports,
for `pattern` and `reserved` separately, whether each came from
`default`, `file`, or `inherited from logbook.json`.

`hail` runs no configured commands. `scan.transcripts` and `scan.live`
are read from, never executed, and no config value ever becomes a
subprocess argument. The one subprocess `hail` runs at all is a fixed,
shell-free call to `ps`, to check whether a session's process is still
alive.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | nothing matched, no such session, no index yet, or `doctor` reported at least one finding |
| 2 | argument refusal, including an ambiguous or too-short id prefix |
| 4 | config refused to load, for example an unknown `version` |
| 5 | index build refused: the scan looks broken and the index was left alone |

`3` is deliberately unused - in `logbook` it means the followup cap was
reached, and reusing the number for something unrelated across two
plugins in one marketplace would be worse than a gap.

A build that kept a cached record under the incremental guard still
exits **0**: the index was written and is usable, and only one record
in it is stale. `doctor` is where that becomes a nonzero exit, so the
hook that runs the build is never the thing that fails a session start.
Exit 5 is the other case, where nothing was written at all.

An index path that is a symlink is refused outright rather than written
through, and a home directory that cannot be resolved from passwd is
refused the same way. Both currently surface as a Python traceback and
exit 1 rather than a clean message.

## The hook

One `SessionStart` hook, matching the same events as logbook's brief.
It imports `hail` and builds the index in-process rather than shelling
out, because the index path above is fixed and unconfigurable - a
subprocess build would have no way to be pointed at a throwaway path
for a test, only at the one real index on your machine.

It exits 0 on every path, including its own crash: a hook that raises
blocks the session start it was only meant to keep current. What it
prints is deliberately narrow - nothing on a clean run, one line on the
cold-path refusal above, and one line (at most one; the two are
exclusive) when this build's census shows `kept_on_regression` or
`user_records_no_cwd` above zero. A guard whose whole purpose is
surfacing a silent failure cannot itself be silent, so that last line
is what tells you to go run `hail doctor` instead of finding out weeks
later that a run of `find` came back empty for the wrong reason.

It is silent on three other paths: a `hail.json` it cannot load, a
missing transcripts directory, and any unexpected exception, all of
which it swallows to keep from blocking the session start. That means a
broken config stops the index updating with no visible sign, which is
why `doctor` treats an index older than seven days as a finding - run
it if `find` starts coming back empty.

## Seeing it beside what those sessions left open

`hail` knows which session was which. It does not know what any of them
left unfinished. [`chartroom`](https://github.com/nikunjtrapasiya/binnacle),
installed alongside this and [`logbook`](../logbook/README.md), reads
both through their `--json` output and writes one page joining the two.

![The chartroom page: obligations on the left, the sessions that worked
them on the right](chartroom.png)

Invented data - no ticket, branch, repository or path in it belongs to
anyone. Optional: nothing here needs it, and `hail` neither knows nor
cares whether it is installed.

## Changelog

See [CHANGELOG.md](CHANGELOG.md). Before 1.0.0 the config schema may
change between minor versions; `config.version` gates that, and a
mismatch refuses every command except `doctor` and `--version` rather
than quietly running a policy you did not write.

## License

MIT. `LICENSE` sits at the repository root.

