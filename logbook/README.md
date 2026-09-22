# logbook

Remembers what one working session owes the next.

A Claude Code plugin, part of
[binnacle](https://github.com/nikunjtrapasiya/binnacle).

## The problem

You are deep in a task. Something blocks you, so you park it. You promise
yourself a follow-up. You deploy and mean to check it landed. Then the
session ends.

Tomorrow, or in another checkout, none of that is in front of you. Your
tracker does not know, because these are not tickets. Your notes are in a
chat log that scrolled away.

`logbook` writes those promises down and puts them back in front of you.

## How it works

```
  Session on Monday                    Session on Wednesday
        |                                   ^        |
        | records what                      |        | resolves
        | it owes                 brief at  |        | what is done
        |                    session start  |        |
        v                                   |        v
  +-------------------------------------------------------+
  |              logbook: an append-only log              |
  +-------------------------------------------------------+
                            |
                            | holds the merge while work is open
                            v
                         Close-out
```

Three things happen on their own, without you asking:

1. **At session start** you get a short brief: what is still open, what has
   gone stale, what a follow-up has outlived.
2. **While you work** you record an obligation in one line.
3. **At close-out** merging a PR, marking one ready, or closing a ticket
   asks you first, if something is still open against it.

## An entry, start to finish

```
  you      logbook add --kind parked --text "auth rewrite"
                       --resume "finish the token refresh"
  logbook  does it name what it needs? yes
  logbook  appends one line to the log file
  logbook  4f2a91

           ... days later, another checkout ...

  logbook  replays the log
  logbook  brief: 1 parked item on ABC-123
  you      logbook resolve 4f2a91 --note "shipped"
  logbook  appends the resolve
```

Nothing is ever edited or deleted. Every change is a new line, so two
sessions in two checkouts can write at the same time and neither loses the
other's work.

## The one rule that makes it useful

Every kind of entry must name one specific thing. A parked item must say
how to resume. A blocked item must say what unblocks it. If you cannot
fill that in, the tool refuses to store it.

```
            logbook add --kind parked
                        |
                        v
            Does it say how to resume?
              |                    |
             yes                   no
              |                    |
              v                    v
   Stored. The next        Refused, exit 2. This is a work
   session can act         unit, not a note. It belongs in
   on it.                  your tracker.
```

This sounds strict. It is the whole point. A note that says "come back to
the auth thing" helps nobody, including the person who wrote it. Forcing
one concrete field means anything in the log can actually be picked up.

## What holds your merge

```
            you run: gh pr merge 7
                        |
                        v
            open items against PR 7?
              |                    |
             none            one or more
              |                    |
              v                    v
   Proceeds. You          Claude asks you first, listing
   see nothing.           what is open. Resolve them, or
                          confirm anyway.
```

It asks. It never silently blocks, and it never overrides a decision you
make. A crash inside the hook gets out of the way and lets your command
through, because a broken reminder must not stop you working. A config the
tool refuses to load does not: the gate cannot check anything under it, so
on a close-out - and only on a close-out - it asks once and says why.

## Three pieces

```
  skills/logbook   when to write an entry  ---+
                                              |
                                              +--> bin/logbook --> your log file
                                              |    the tool
  hooks/           brief and gate          ---+
```

- **The policy** is `skills/logbook/SKILL.md`: when an entry is worth
  writing, when to close it, and what the refusal exit codes mean. An agent
  reads this before deciding to use the tool at all.
- **The tool** is `bin/logbook`, one Python file. Standard library only, no
  dependencies, Python 3.9 and up.
- **The enforcement** is two hooks. One runs on session start, `/clear`,
  `/compact`, resume and fork: it refreshes the stable gate copy, prints the
  brief, and warns if tracker gating is configured but unwired. The other
  asks before a close-out. Both fail open, so a problem inside them costs
  you a warning, never a blocked command.

Each piece is useful without the others. The tool works on its own from a
terminal, once the binary is on your `PATH` - see [Install](#install).

## Install

```
/plugin marketplace add nikunjtrapasiya/binnacle
/plugin install logbook@binnacle
```

Nothing else to set up inside Claude Code. The plugin wires the brief and
the gate itself, and every setting has a default, so it works with no
config file at all.

The install puts `logbook` on `PATH` **inside a Claude Code session**. A
plain terminal has never heard of it, so to use it there, put the
installed binary on your own `PATH`:

```
ls ~/.claude/plugins/cache/binnacle/logbook/*/bin/
```

That path carries the installed version, so it moves at every
`/plugin update`. A symlink from somewhere already on your `PATH` is the
version-independent way.

To gate tracker transitions as well as PR merges, see
[Tracker gating is opt-in](#tracker-gating-is-opt-in).

## Try it in a minute

```
logbook add --kind parked --text "auth rewrite" \
  --resume "finish the token refresh in session.py" --ticket ABC-123
logbook ls
logbook check --ticket ABC-123     # exit 1, one open item
logbook brief --ticket ABC-123     # shows the item you just added
logbook doctor                     # where every setting came from
```

## The six kinds, and why one required field is the point

| Kind | Required field | Blocking |
|---|---|---|
| `parked` | `--resume` | yes |
| `blocked` | `--unblocked-by` | yes |
| `followup` | `--ticket` | yes, capped |
| `unverified` | `--verify` | yes |
| `deploy` | `--stage --service --commit` | yes |
| `decision` | `--why` | no |

A kind without a required field could hold anything, which means it would
end up holding everything - a junk drawer nobody reads. Forcing one
structural field per kind means an entry has to say what it needs before it
can be written at all: a `parked` item without a `--resume` line is not
useful even to the person who wrote it, so the tool refuses it rather than
storing something nobody will act on.

`decision` is the one kind that does not block anything. It is a record, not
an obligation - a place to write down a "why" a cold reader would otherwise
have to ask about.

These six are the shipped defaults. Your config can add, remove, or rename
kinds - see "Custom kinds" below.

## Commands

```
logbook add --kind K --text T [--why ...] [--ticket ...] [--pr N] ...
logbook ls [--ticket K] [--repo R] [--kind K] [--all] [--json]
logbook show <id|ticket|pr>
logbook resolve <id> [--note "..."]
logbook drop <id> [--note "..."]
logbook check [--ticket K] [--pr N] [--json]      # at least one key
logbook stale [--days N]
logbook brief [--ticket K]
logbook deploy-sync [--ticket K] [--dry-run]
logbook retire [--ticket K] [--closed K,K,N] [--dry-run]
logbook doctor [--fix]
logbook gate-check
logbook --version
```

- **`add`** writes one entry. `--ticket` is inferred from the current
  branch when omitted. A ticket or a PR is not required to write an entry,
  but an entry with neither is much harder to find later, and `add` warns
  about that on stderr.
- **`ls`** lists open entries (or every entry, with `--all`), filtered by
  ticket, repo, or kind. `--json` prints the same selection as an
  envelope - `{"version", "thresholds", "kinds", "entries"}` - rather
  than a bare list. `thresholds` and `kinds` travel with the entries
  because a reader deciding what counts as stale, or which obligations
  hold a close-out, must not invent its own answer; the ones in the
  envelope are the ones this logbook enforces. `kinds` is the config's
  own map, each kind with its `requires` list and its `blocking` flag,
  so a kind you declare here needs no second declaration anywhere else.
  Filters apply identically to both outputs.
- **`show`** prints the full history for one id, ticket, or PR.
- **`resolve`** and **`drop`** close an entry - resolved because the
  obligation was met, dropped because it stopped mattering. Both take an
  optional `--note`.
- **`check`** is the close-out gate: exit 1 when a blocking entry is open
  against the key, exit 0 otherwise. Given both a ticket and a PR it unions
  the blockers of both, which is what the hook sends for a numbered merge on
  a ticket branch: the second PR on a ticket is merged before any entry
  names its number, so the ticket is the key that finds those. Exit 0 still prints any `decision`
  entries on record and a count of open keyless entries, neither of which
  blocks. This is what the `PreToolUse` hook calls under the hood.
- **`stale`** lists entries untouched for more than `thresholds.stale_days`
  (default 7).
- **`brief`** is what the `SessionStart` hook prints: open items for the
  current ticket, escalations from elsewhere, and followups past their
  expiry. Entries on another ticket show their id, kind, ticket and age but
  not their text - see "What the brief sends" below.
- **`deploy-sync`** asks each `deploy` entry's configured resolver whether
  the commit has actually shipped (or the stage has actually torn down) and
  resolves the ones that have. See "Deploy resolvers" below.
- **`retire`** asks the tracker and the forge whether each non-blocking
  entry's ticket and PR are closed, and drops the entries where every key
  present says closed. Decisions are records of *why*, not obligations, so
  once the ticket and PR they explain are shut, nothing is owed and they
  can leave the brief. See "Retiring decisions" below.
- **`doctor`** prints the effective config, whether each section came from
  the defaults or from your config file, the store path actually in force
  (which `LOGBOOK_HOME` can move without changing the origin line), and any
  findings - unusable kinds, unwired tracker gating, a misconfigured stage,
  and so on. `--fix` also refreshes the gate copy used by the opt-in tracker
  matcher (see below).
- **`gate-check`** prints only the tracker-gating findings, and nothing at
  all when gating is either unconfigured or correctly wired. The
  `SessionStart` hook runs it after the brief, which is why an unwired gate
  nags you once per session.

## Custom kinds

`add` has one flag per built-in field (`--resume`, `--verify`, `--why`,
`--unblocked-by`, `--stage`, `--service`, `--commit`, `--ticket`, `--pr`),
`--session` to stamp a session id other than `$CLAUDE_SESSION_ID`, plus a
general-purpose `--field name=value`, repeatable, for anything a custom kind
needs. Field names must match `[a-z][a-z0-9_]{0,30}` and cannot collide with
a name the log already owns (`id ts op kind status note text repo repo_path
branch session`) or with `ticket` or `pr`, which have typed flags that
normalise the value. The other built-in fields can be set either way; naming
the same one through both its flag and `--field` is refused (exit 2), not
silently resolved by picking one.

Honest note: the required-value guard is shallow for every kind, built-in or
custom. For the free-text fields (`resume`, `unblocked_by`, `verify`, `why`,
and a custom kind's own) it checks that a value is non-blank, at least three
characters, and not identical to `--text` - enough to block an empty
`--resume`, not enough to block `--resume "n/a"`. The identifier fields
(`stage`, `service`, `commit`, `ticket`, `pr`) only have to be non-blank at
all. `doctor` prints a warning for every custom kind
for exactly this reason: the shape check is advisory, not a proof that the
value means anything. It is not stricter for the built-in kinds either;
they are just less likely to be gamed because their names already say what
they need.

## Full config reference

Config lives at `~/.claude/binnacle/logbook.json` by default, overridden by
the `LOGBOOK_CONFIG` environment variable. A path that does not exist is not
an error - it just means every default below is used as-is. This is both
the first-run experience and how the test suite isolates itself.
`LOGBOOK_CONFIG` is meant for testing and one-off overrides, not daily use -
pointing it at any path other than the default one turns off deploy
resolvers. See "Config is executable" below.

The store location is the `home` key, overridden in turn by `LOGBOOK_HOME`;
`logbook doctor` prints the store path actually in force on its `store:`
line.

Every section merges key by key into the defaults below, so a file setting
one threshold leaves the other two alone. **`kinds` is the exception: it
replaces the whole default set.** This is deliberate - replacing is the only
way to actually drop a kind you never use, so a config that adds one custom
kind must restate the full set it wants.

```json
{
  "version": 1,
  "home": "~/.claude/binnacle/logbook",
  "ticket": {
    "pattern": "[A-Z]{2,6}-\\d{1,7}",
    "reserved": ["ISO", "UTF", "SHA", "AES", "RGB", "RFC", "HTTP", "IPV"],
    "example": "ABC-123",
    "tracker_name": "your tracker"
  },
  "thresholds": {
    "followup_cap": 3,
    "followup_expiry_days": 14,
    "stale_days": 7
  },
  "kinds": {
    "parked":     { "requires": ["resume"],       "blocking": true },
    "blocked":    { "requires": ["unblocked_by"], "blocking": true },
    "followup":   { "requires": ["ticket"],       "blocking": true, "capped": true },
    "unverified": { "requires": ["verify"],       "blocking": true },
    "deploy":     { "requires": ["stage", "service", "commit"], "blocking": true },
    "decision":   { "requires": ["why"],          "blocking": false }
  },
  "brief": {
    "remote_text": false
  },
  "gate": {
    "mode": "ask",
    "done_words": ["done", "closed", "resolved", "complete"],
    "pr_close_patterns": [
      "\\bgh\\s+pr\\s+(?:merge|close|ready)\\b",
      "\\bgh\\s+api\\b[^;&|\\n]*?/pulls/(\\d+)/merge"
    ],
    "tracker_tools": []
  },
  "deploy": { "timeout_seconds": 60, "env_passthrough": [], "stages": {} },
  "retire": { "timeout_seconds": 60, "env_passthrough": [], "kinds": ["decision"],
              "ticket": "", "pr": "" },
  "hail": { "index": "~/.claude/binnacle/hail/index.json" }
}
```

`ticket.pattern` must be `PREFIX-NUMBER` shaped - reserved-prefix filtering
splits on `-` and normalisation upper-cases the match, so a pattern with no
`-` will never normalise, and `doctor` warns when it sees one. GitHub-style
`#123` keys are not supported yet.

`gate.mode` is `ask` (default), `deny`, or `off`. Only `deny` makes the gate
refuse a close-out outright; on `ask` it can never allow something another
hook would refuse.

`deploy.env_passthrough` names extra environment variables to forward to
resolvers, on top of the built-in allowlist below. It has no default
entries.

`hail.index` points at the sibling `hail` plugin's session index. When an
entry carries a session id found there, `show` and `brief` print a `rejoin:`
line that reopens that session in its original checkout.

See `examples/logbook.json` and `examples/linear.json` for a worked config
against a deploy-log resolver and a second tracker.

## Deploy resolvers

`deploy.stages` maps a stage name, a glob, or `*` to one of two shapes.
Match precedence is exact name, then glob, then `*`, then no match at all -
which holds the entry rather than guessing.

```json
"deploy": {
  "timeout_seconds": 60,
  "stages": {
    "prod":      { "resolve": "$LOGBOOK_CONFIG_DIR/deployed-commit-aws-logs.sh" },
    "test":      { "resolve": "$LOGBOOK_CONFIG_DIR/deployed-commit-aws-logs.sh" },
    "preview-*": { "exists":  "$LOGBOOK_CONFIG_DIR/stage-exists-aws-ssm.sh" }
  }
}
```

Which key is present decides the shape, not the stage name:

- **`resolve`** - a commit obligation. The command's stdout, first
  whitespace-separated token, is lower-cased and must then match
  `^[0-9a-f]{7,40}$` - that token is
  passed straight to `git merge-base --is-ancestor`, so anything else
  (including a resolver's own `--help` text on an error path) is treated as
  unparseable. Non-zero exit, empty stdout, an unparseable token, or a
  timeout all mean the same thing: hold the entry, print "could not
  determine".
- **`exists`** - a teardown obligation. Exit 0 means the stage is still up
  (teardown still owed). Exit 1 means the stage is definitely gone (the
  entry resolves). Any other exit code, and any timeout, means hold - "gone"
  has to be a positive finding, not the fallback for every kind of failure,
  or an expired SSO session would falsely resolve a teardown that never
  happened.

A stage entry with both `resolve` and `exists` is a config error - `doctor`
flags it and that stage holds until it is fixed.

Worked examples, both written as multi-outcome scripts rather than one-line
wrappers, because a bare CLI call maps its own error codes onto "gone" or
"deployed" in ways that are wrong more often than they are right:

- `examples/deployed-commit-aws-logs.sh` - pages a CloudWatch Logs group
  with `--start-time` and a `nextToken` loop, filters to the service named
  in `$LOGBOOK_SERVICE`, and prints the commit from the most recent matching
  event.
- `examples/stage-exists-aws-ssm.sh` - reads an SSM parameter and maps three
  outcomes explicitly: exit 0 on a successful read (stage up), exit 1 when
  the error mentions `ParameterNotFound` (stage gone), exit 2 on anything
  else (unknown - hold). The AWS CLI itself returns a generic error exit
  code for both "parameter missing" and "your session expired," so those
  two cases have to be told apart by the error text, not the exit code
  alone.

Both scripts use `REGION` and `PROFILE` as placeholders - substitute your
own region and AWS CLI profile before use.

Environment passed to every resolver: an allowlist of `PATH`, `HOME`,
`LANG`, `LC_ALL`, `TZ`, `TERM`, `SHELL`, `USER`, `LOGNAME` and `TMPDIR`; the
entry's own `LOGBOOK_STAGE`, `LOGBOOK_SERVICE`, `LOGBOOK_COMMIT`,
`LOGBOOK_TICKET`, `LOGBOOK_REPO`, `LOGBOOK_ENTRY_ID` and
`LOGBOOK_CONFIG_DIR`; and anything you name in `deploy.env_passthrough`.
Nothing else in your session reaches the resolver, so a variable a script
needs - `AWS_PROFILE`, say - has to be listed there. The entry's values are
never interpolated into the command string - see "Config is executable"
below for why that distinction matters.

## Retiring decisions

A `decision` entry is on record so a cold reader can find the why. It
blocks nothing, and once the ticket it explains is closed and its PR is
merged, the why lives in the ticket and the PR, and the entry is only
weight in the brief. `retire` drops those, on evidence from the tracker
and the forge, never on age.

```json
"retire": {
  "timeout_seconds": 30,
  "kinds": ["decision"],
  "env_passthrough": ["JIRA_EMAIL", "JIRA_API_TOKEN"],
  "ticket": "$LOGBOOK_CONFIG_DIR/ticket-closed-jira.sh",
  "pr":     "$LOGBOOK_CONFIG_DIR/pr-closed-gh.sh"
}
```

Two resolvers, one per key an entry can carry. Each is a command with the
same tri-state contract as `exists`: exit 0 means the key is closed (ticket
done, PR merged or closed), exit 1 means it is still open, anything else
means the resolver could not tell and the entry holds. "Closed" has to be
a positive finding, because an expired token, a deleted issue and a
network failure all exit non-zero too, and none of them means the work is
finished.

For each entry of a kind in `retire.kinds`:

- every key the entry carries (`ticket`, `pr`, or both) is asked, and all
  of them must answer closed before the entry drops. An entry with a
  ticket and no PR needs only the ticket; one with both needs both.
- an entry with neither key holds, and says so. Nothing can vouch for it.
- a key present on the entry with no resolver configured holds, and names
  the config key to add.
- the drop note records what closed: `retired: ticket ABC-123 closed, pr 42
  closed`.

When the session already knows a key is closed - because the model just
asked the tracker through its own MCP tool, say - it can hand that in
instead of configuring a resolver:

```
logbook retire --closed ABC-123,ABC-124,42 [--dry-run]
```

Tokens are ticket keys and bare PR numbers, comma-separated, and the flag
repeats. A token that is neither is refused (exit 2) rather than skipped,
so a typo cannot read as "still open". With `--closed` given, only entries
carrying one of those keys are considered. A key vouched for this way runs
no command and needs no boundary; any other key the entry carries is still
asked of its resolver, so an entry with an asserted ticket and a PR still
needs the PR resolver, or the PR number in `--closed` too. The drop note
marks the source: `ticket ABC-123 (asserted) closed`.

`retire.kinds` can only name kinds declared non-blocking. A blocking kind
is an obligation a person meets; a closed ticket says nothing about
whether it was met, so `retire` refuses those and `doctor` says so. The
default is `["decision"]`.

The example scripts:

- `examples/ticket-closed-jira.sh` - reads the issue's status *category*
  from the Jira REST API and maps `done` to exit 0, `new` and
  `indeterminate` to exit 1, and any HTTP or parse failure to exit 2.
  Category rather than status name, so a workflow whose last column is
  "Shipped" or "Released" still counts as closed. Needs `JIRA_EMAIL` and
  `JIRA_API_TOKEN` forwarded through `retire.env_passthrough`, and
  `myorg.atlassian.net` replaced with your site.
- `examples/pr-closed-gh.sh` - runs `gh pr view --json state` in the
  checkout the entry was written from (`LOGBOOK_REPO_PATH`), so the
  repository is the one the PR number meant. `MERGED` and `CLOSED` exit 0,
  `OPEN` exits 1, and a `gh` failure of any kind exits 2, because `gh`
  itself exits 1 for "no such PR" and "not logged in" alike.

Resolvers here run under the same boundary as deploy resolvers - see
"Config is executable" below - and receive the same environment, plus
`LOGBOOK_PR` and `LOGBOOK_REPO_PATH`. `retire.timeout_seconds` and
`retire.env_passthrough` are this section's own, not shared with `deploy`.

## Tracker gating is opt-in

The plugin ships a `PreToolUse` hook for `Bash` only - that is what lets it
hold a `gh pr merge` or similar. Watching a tracker tool (a Jira transition,
a Linear update, anything else reached through an MCP tool) needs one more
line, because the plugin's own `hooks.json` is a static file and cannot know
which MCP tool your config names in `gate.tracker_tools`.

1. Add the tool to `gate.tracker_tools` in your config (see
   `examples/logbook.json` for a Jira-shaped entry and `examples/linear.json`
   for a second tracker). Each entry is an object, not a bare tool name:
   `{"tool": "...", "issue_field": "...", "status_path": "..."}`. An entry
   of any other shape gates nothing, and `doctor` says so.
2. Run `logbook doctor --fix` once, after installing the plugin, to write a
   stable copy of the gate script to `~/.claude/plugins/data/binnacle/gate`.
   This copy is refreshed automatically every session after that.
3. Add a `PreToolUse` entry to your own `settings.json`, matcher set to the
   tool name(s), running that stable path. `logbook doctor` warns you if
   `tracker_tools` is configured but no such hook is wired - the warning
   looks at the hook's command, not just whether some matcher happens to
   cover the tool, because a catch-all matcher on an unrelated hook would
   otherwise hide the gap.

## Config is executable, and the security boundary that makes that OK

Resolver commands (the `resolve` and `exists` entries in `deploy.stages`,
and `retire.ticket` and `retire.pr`) are run with a shell (`subprocess.Popen(..., shell=True)`, so a timeout can
signal the whole process group). This is by design
- a resolver is a shell script or a one-liner, and forcing it through
`argv` instead would make the common cases (a pipe, a glob, an `&&`) far
more awkward to write. But it means: **anything in your config's resolver
commands runs with your permissions, exactly as if you had typed it.**

The boundary that makes this acceptable: resolvers run only when the config
actually in effect resolves to the one default path,
`~/.claude/binnacle/logbook.json`, under the account's own home directory -
read from the account's passwd entry, not the `HOME` environment variable.
There is no check for "inside a repository" any more, and no exemption of
any kind. Any other path, however it got there, turns resolvers off:

- `LOGBOOK_CONFIG` pointed at any path other than the default one,
  including a copy of your own config placed somewhere else.
- A symlink sitting at the default path itself - the check follows it to
  the real file and compares that.
- `HOME` repointed at another directory - the check reads the account's
  actual home from the passwd entry, so a repointed `HOME` only makes the
  path the process is reading disagree with the one that is trusted.

`deploy-sync` and `retire` hold every entry when resolvers are disabled and
print why. `doctor` always reports the effective config path, and reports
that resolvers will not run whenever `deploy.stages` or a `retire` resolver
is configured and the config in force is not the trusted default one.

**In short: `LOGBOOK_CONFIG` is for testing and for pointing at a config
temporarily. Pointed anywhere other than the default path, it disables
resolvers.**
Keep your real config at the default path if you want deploy resolvers to
run. Entry field values (`stage`, `service`, `commit`, and so on) are passed
to resolvers as environment variables, never interpolated into the command
string, so an entry's own free-text fields cannot become shell code even if
a resolver command is compromised in some other way. Nothing else in this
tool executes user or repository content - the hooks and the tool itself
only call `git rev-parse`, `git merge-base --is-ancestor` and `logbook`
itself, and read the log.

## What the brief sends

The `SessionStart` hook runs `logbook brief`, so whatever it prints joins
the session's context and is sent to the model. That is the point for the
ticket you are on. It is not the point for everything else you have open.

So only entries on the current ticket print in full. An entry on another
ticket shows its id, kind, ticket and age, and its text is withheld:

```
  blocked or stale elsewhere:
  r1  unverified ABC-9999   30d old
  r2  blocked    ABC-777    0d old
  other tickets' text withheld: logbook show <id>
```

You still learn that something is blocked and how long it has sat, which
is all that block is for. `logbook show r1` prints the one you care about.

Set `brief.remote_text` to `true` to print every entry's text regardless.
It is a real trade, not a safety setting with an obvious answer: the
fuller brief is easier to act on without a second command, and it sends
the text of every blocked or stale entry to the model at every session
start, including sessions working on something unrelated.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | not found, or `check` found open blockers |
| 2 | shape or argument refusal |
| 3 | a capped kind (`followup`) is already at its cap for this ticket |
| 4 | config refused to load (for example, an unsupported `version`) - run `logbook doctor` |

## Fail-open promise

Both hooks catch every exception and exit 0 no matter what goes wrong
inside them. A broken config, a missing file, a crash in the tool itself -
none of it blocks a session or a tool call. The worst case is that you stop
getting the brief and the gate stops asking, silently, which is why
`doctor` exists: run it any time something feels quiet that shouldn't be.

## Seeing it beside the sessions that caused it

`logbook` knows what is open. It does not know which session left it
there. [`chartroom`](https://github.com/nikunjtrapasiya/binnacle),
installed alongside this and [`hail`](../hail/README.md), reads both
through their `--json` output and writes one page joining the two.

![The chartroom page: obligations on the left, the sessions that worked
them on the right](chartroom.png)

Invented data - no ticket, branch, repository or path in it belongs to
anyone. Optional: nothing here needs it, and `logbook` neither knows
nor cares whether it is installed.

## Changelog

See [CHANGELOG.md](CHANGELOG.md). Before 1.0.0 the config schema may change
between minor versions; `config.version` gates that, and a mismatch refuses
every command except `doctor` rather than quietly running a policy you did
not write.

## License

MIT. `LICENSE` sits at the repository root.
