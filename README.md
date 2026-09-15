# binnacle

Instruments for steering work across sessions.

A binnacle is the stand on deck that holds the compass and charts. The box
of instruments you steer by.

This is a Claude Code plugin marketplace. Each tool is a plugin you can
install on its own.

## You already lost something this week

You closed a session on Friday. It knew the reindex had only run against
staging. It knew why you paged by cursor instead of offset. It knew the
rate limiter was parked on a quota key that had not shipped.

Monday, you are on a different branch in a different checkout and none of
that exists. The thing you ship is the thing nobody verified.

**binnacle keeps the part of your work that has no home.** Not your
tickets, not your pull requests, not your logs. Those have owners. This
holds the loose ends: the claim you made without checking, the reason
behind a call you will be asked about in review, the work you parked at
6pm meaning to come back to.

## What you get

**Told, not reminded.** Start a session on a branch and the open items
for that ticket or PR are already on screen. Nothing to remember to
open, nothing to search.

**Caught before it ships.** Merge a PR with an unverified claim against
it and you get asked first. The deploy nobody confirmed stops being the
thing you discover in production.

**Findable again.** Every session you ran is indexed by ticket, branch,
PR and directory. One command rejoins the exact conversation that did
the work, instead of scrolling a list of untitled sessions guessing from
timestamps.

**One page, not two tools.** Open items sorted by urgency, and beside
each one the sessions that worked it, with the copy-paste command to
pick it back up.

**Entries that are worth reading later.** Every kind has to name one
field: parked says how to resume, blocked says what unblocks it, a
decision says why. You answer it while you still know the answer. An
item that cannot name its field is a unit of work, and the tool tells
you to put it in your tracker instead of quietly filing it here.

## The honest part

Plain files under your home directory. No account, no telemetry, no
update check, nothing leaves your machine. Standard library only, so
there is no dependency tree and no build step. Three commands, and
install takes a minute.

Worth it if your work jumps between branches, tickets and checkouts, and
you keep paying for context that died with a session. If you finish one
thing before starting the next, you do not need this.

## The three tools

```
  you, recording what a               Claude Code, writing a
  session leaves open                 transcript for every session
            |                                     |
            v                                     v
     +--------------+                      +--------------+
     |   logbook    |                      |     hail     |
     |  open items  |                      | the session  |
     |  by ticket   |                      |    index     |
     +--------------+                      +--------------+
            |                                     |
            | logbook ls --json                   | hail ls --json
            |                                     |
            +------------------+------------------+
                               v
                       +---------------+
                       |   chartroom   |  joins the two on ticket,
                       +---------------+  PR, branch, directory
                               |
                               v
                 one page: what is still open, and
                 the session to rejoin to work on it
```

## How the three fit together

They answer three different questions, and only the third one needs the
other two.

**`logbook` answers "what is still owed".** You record an obligation when
a session parks work, defers a follow-up, or makes a claim it did not
verify. Each entry is keyed by ticket or PR, and each kind has to name
one structural field: parked work says how to resume, blocked work says
what unblocks it, a decision says why. An item that cannot name its
field is a unit of work, and belongs in your tracker instead.

**`hail` answers "where was this last worked".** Claude Code already
writes a transcript per session; hail indexes those into a record per
session with its title, branch, ticket, working directory and prompts,
so a session can be found by what it was doing and rejoined with one
command.

**`chartroom` answers "what do I do next".** Neither of the others knows
about the other, so it reads both through their documented `--json`
output and joins them on ticket, then PR, then branch, then directory -
counting a PR only when the ledger names it. The result is one
self-contained HTML page: every work item with something open against
it, and beside it the sessions that worked it. It holds no data of its
own and writes nothing back to either.

Useful on its own, in this order: `logbook` if you lose context between
sessions, `hail` if you lose the sessions themselves, `chartroom` once
you have both and want one place to look.

## What that looks like

![The chartroom page: obligations on the left, the sessions that worked
them on the right](chartroom.png)

The real page, over invented data - no ticket, branch, repository or
path in it belongs to anyone. Obligations on the left, most urgent
first, each one saying which session left it. Sessions on the right,
most recent first, each with the command that rejoins it. Decisions
are folded into the disclosure at the bottom: they are a record, not
work, and in front of you they bury the things somebody has to act
on.

| Plugin | What it does | Status |
|---|---|---|
| [logbook](logbook/README.md) | Remembers what one working session owes the next: parked work, deferred follow-ups, unverified claims. Briefs you when a session starts, and asks before you close something out with work still open against it. | 0.3.3 |
| [hail](hail/README.md) | Finds a past session by ticket, branch, title, working directory or what was typed into it, and rejoins it. | 0.2.4 |
| [chartroom](chartroom/README.md) | Joins what is still open to the sessions that worked it, and writes one self-contained page you open from a file. Needs the other two. | 0.4.3 |

## Install

Add the marketplace once, then install whichever of the three you want:

```
/plugin marketplace add nikunjtrapasiya/binnacle

/plugin install logbook@binnacle
/plugin install hail@binnacle
/plugin install chartroom@binnacle
```

`logbook` and `hail` each stand alone and can be installed in either
order. `chartroom` is only the join between them: install it last, and
only if you have both, because it reads their command output and has no
data of its own.

Each plugin has its own README with its commands, config and security
notes: [logbook](logbook/README.md), [hail](hail/README.md),
[chartroom](chartroom/README.md).

## If you use another tool

These are packaged as Claude Code plugins, but they are three Python
command line tools underneath, and they do not all depend on Claude Code
to the same degree. What you can expect elsewhere:

**`logbook` works anywhere.** It is argv in, a file out. Any editor,
agent, shell or git hook that can run a command can write and read
entries, and concurrent writers do not corrupt each other. What you lose
outside Claude Code is the automation, not the ledger: the brief that
prints at session start and the gate that stops a close-out are declared
as Claude Code hooks. `logbook brief` and `logbook gate-check` are
ordinary commands, so another host with a hook system of its own can
call them, but you would wire that yourself.

**`hail` is Claude Code only.** It indexes Claude Code's own session
transcripts, and the command it hands you to rejoin a session is
`claude -r`. Neither has an equivalent in a tool that does not write
those transcripts.

**`chartroom` works wherever both of its inputs do.** It shells out to
whatever `tools.logbook` and `tools.hail` name in its config and joins
the JSON they return, so anything producing that shape can stand in for
either side.

There is no install path outside this marketplace today. If you want one,
open an issue saying which tool and what it gives you: a session id, a
working directory and branch per session, and a command that rejoins one
by id are what decide whether an equivalent of `hail` is possible at all.

## What these have in common

- **Standard library only.** No dependencies, no build step, no
  `pyproject.toml`. Python 3.9 and up.
- **Your data stays yours.** Everything is a plain file under your home
  directory, and nothing here talks to the internet - no telemetry, no
  update check, no upload, ever. The one socket in the marketplace is
  `chartroom serve`, which you start by hand: loopback only, a token in
  the URL, read-only, and gone when you stop it. Its README says
  exactly what it refuses. What a session-start hook prints does join
  that session's context, which is the point of a brief; each plugin's
  README says exactly what its hooks print.
- **Nothing blocks you.** Hooks fail open: if one breaks, you lose a
  reminder, never the ability to run a command.
- **Config, not code.** Anything specific to your tracker, your deploy
  process or your naming is a config value with a working default.

## Contributing

Issues and pull requests are welcome, but this repo is a published
snapshot rather than a working tree, so a PR here is read as a proposal
and ported rather than merged. Read
[CONTRIBUTING.md](CONTRIBUTING.md) before opening one.

## License

MIT. See [LICENSE](LICENSE).
