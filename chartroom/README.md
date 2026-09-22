# chartroom

One page joining what you owe to the sessions that worked it.

A Claude Code plugin, part of
[binnacle](https://github.com/nikunjtrapasiya/binnacle).

## The problem

`logbook` knows what is still open. `hail` knows which sessions worked
on it. Neither knows about the other, so answering "what is owed on
this, and where was it last touched" means running two tools and
joining the answers in your head, every time.

`chartroom` does that join once and writes it to a single HTML file you
open from `file://`.

## How it works

```
  logbook ls --json ---+
                       |
                       +--> join on ticket, PR, branch, dir
                       |                  |
  hail ls --json    ---+                  v
                              one self-contained HTML page
```

Both siblings are read through their own CLIs, never through their
storage files. A file shape rots without announcing it; a documented
`--json` output is a promise. `chartroom` writes nothing but the page,
and nothing in the page can write back. `serve` opens one loopback
socket and writes not even that; **Serving it** below says exactly what
it refuses.

## The page

![The chartroom page: obligations on the left, the sessions that worked
them on the right](chartroom.png)

The real page, over invented data - no ticket, branch, repository or
path in it belongs to anyone. Obligations on the left, most urgent
first, each one saying which session left it. Sessions on the right,
most recent first, each with the command that rejoins it. Decisions
are folded into the disclosure at the bottom: they are a record, not
work, and in front of you they bury the things somebody has to act
on.

## Install

```
/plugin marketplace add nikunjtrapasiya/binnacle
/plugin install chartroom@binnacle
```

`logbook` 0.3.0 and `hail` 0.2.0 or newer must be installed too -
`chartroom` is the join between them and has no data of its own. It
checks a sibling's version before it reads that sibling, and says which
one to upgrade if either is too old, or cannot report a version as three
dot-separated numbers on the first line of `--version`.

### Running it from a terminal

A marketplace install puts the three commands on `PATH` **inside a
Claude Code session**. A plain terminal has never heard of them. Either
run them from a session, or point `chartroom` at the binaries and put
them on your own `PATH`:

```
ls ~/.claude/plugins/cache/binnacle/*/*/bin/
```

That path carries the installed version in it, so it changes under you
at every `/plugin update`. If you would rather not chase it, set
`tools.logbook` and `tools.hail` in the config to absolute paths, or
symlink the binaries somewhere already on your `PATH`.

## Try it in a minute

```
chartroom doctor         what the settings are, and what is wrong
chartroom                build the page and open it
```

## Commands

```
chartroom                 build the page and open it
chartroom build           build it, print the path, do not open
chartroom serve [--port N]  serve it on loopback, rebuilt per request
chartroom doctor          the effective config, and what is wrong
chartroom --version       print the version
```

- **`chartroom`** with no argument builds and opens. `page.open: false`
  makes it behave as `build`. The path is printed either way, so a
  browser that fails to open is not a failed build.
- **`build`** never opens, whatever `page.open` says. It prints the
  path on stdout and nothing else, so it composes.
- **`serve`** listens on loopback and rebuilds the page for every
  request, so a reload is current instead of showing whenever you last
  ran `build`. It writes no file at all. Read **Serving it** below
  before you use it: it puts a socket where there was only a file.
- **`doctor`** prints the config path, every `page`, `rows` and `sort`
  setting in force, any loader warnings, both sibling versions,
  logbook's thresholds, hail's window and census, and then the two
  window findings below. It does not echo `tools.*`; a `tools` entry
  that was ignored shows up as a warning instead. It writes no page. It
  exits 1 when it has a finding, so it can be used in a check rather
  than read by eye.

## What a work item is

One entry per **work item**, keyed at the first level that answers, the
same four levels on both sides:

| Level | logbook entry | hail session |
|---|---|---|
| ticket | `ticket` | `tickets_from_branch` |
| PR | `pr` | each PR with a number |
| branch | `branch` | `branches` |
| directory | `repo_path`, the checkout root | `cwd`, resolved to the longest checkout root containing it |

Only logbook knows a checkout root, because only logbook asks git; a
session's launch directory is resolved into one, so a session started in
a subdirectory keys to the checkout above it and a nested checkout keeps
its own identity. A `repo_path` logbook truncated to fit an atomic
append keys nothing, having named a directory that does not exist.

Anything with none of the four still gets one, under `unkeyed`.
Unticketed work being dropped from the page would be the one failure
that looks exactly like having nothing to do.

A session keys on **branch-derived tickets only**. A session that merely
mentioned a ticket in passing falls through to its branch item: the
page's claim is "these sessions worked this", and a passing mention did
not. A session whose branch names two tickets appears under both.

`chartroom` infers nothing of its own. hail derives tickets from
branches, logbook normalises the ones you type, and a third inference
in a third place would be drift.

**A PR number and a branch name only mean something inside a
checkout.** Two repositories can both have a PR 42 and both sit on a
branch called `fix-login`. `chartroom` scopes those keys by checkout,
but only when it can see the ambiguity: a value that turns up under two
different checkouts in your own data gets split, and everything else
stays whole. Scoping unconditionally would be worse, because an
obligation written outside a repository can name no checkout at all and
would be split away from the work it belongs to. `main`, `master`,
`develop`, `trunk` and the `HEAD` a detached checkout reports are
dropped outright: they name no particular work and would otherwise
collect every repository at once.

**The two sides can settle at different levels.** An obligation may
carry only a PR while the session that did the work only ever knew the
branch. When some record has seen a weak key beside a ticket,
`chartroom` follows that one hop, so both land on the ticket. One
hop only, and a weak key seen beside two different tickets follows
neither: chaining these would let a single session that glanced at a
second ticket weld two work items together for good.

Only a PR or a branch can make that hop. A directory is a place, not a
piece of work - many tickets share one checkout, so binding it would
sweep every unticketed obligation there into whichever ticket a session
in that directory happened to name. And a record that names two tickets
at once witnesses nothing: it binds no weak key either.

**A PR nothing is owed against is not a key.** A session's PR comes
from Claude Code, which attaches one on its own and can get it wrong -
the session this was found on carried 720 records claiming a PR merged
months earlier on somebody else's branch. Since a PR outranks a branch,
one false claim was enough to carry that session off its own work item,
leaving the obligations with no session beside them and the PR with no
obligations under it. So a PR number no obligation carries is dropped
before keying, and the record falls through to its branch. Your ledger
is the only side that says what a PR means to you; if you owe something
against a PR, you wrote that down.

A work item's heading carries its key, the level the key came from,
its severity, and `N aged off` where that applies. Its obligations are
the cards below it.

Severity: an entry whose kind is literally `blocked` makes the item
blocked; otherwise an entry older than `thresholds.stale_days` makes it
aging; otherwise any open entry makes it open. The threshold is
logbook's own number, travelling with the entries, and `chartroom`
invents none of its own.

The red flag keys on the kind **named** `blocked`, not on logbook's
`blocking` flag - even though the `on record` split below does read
that flag. They answer different questions: `blocking` means "holds
close-out", which is true of every kind logbook ships except
`decision`, so colouring by it would make the whole page red and say
nothing. The cost is that if you rename the `blocked` kind in your
logbook config, nothing ever reads blocked.

`N aged off` counts that item's open obligations whose recorded session
is no longer in hail's index - not distinct sessions, and not only ones
that aged out: a session hail never indexed counts the same. The
masthead states hail's own `aged_off` census number as well, when it is
not zero; that one is hail's count of sessions dropped from its
window.

Every age on the page is measured against the build's own timestamp,
not the clock. A page is a build artifact; a card that quietly turned
amber while the file sat unopened would be describing a build that
never happened.

The masthead shows that timestamp on your own wall clock, with the zone
named, because a build time you have to convert from UTC in your head
is one you skip reading. The ages themselves are still computed from
the UTC value carried in the page, so moving zone changes what the
masthead says and nothing else.

Obligation text is on the card, in full. The card names its kind, its
age, and the session it was written in.

By default a work item with no open obligation is not rendered at all -
see `rows.only_open`. Those are sessions with nothing owed on them, and
on a real ledger they outnumber the items that do owe something, so
leaving them in means reading past most of the page to find the work.
The masthead says how many were hidden.

The right pane lists the most recent `sessions.limit` sessions, 60 by
default. The masthead says how many were not listed.

Each session in the right pane carries a button copying
`cd <cwd> && claude -r <id>` - the same string `logbook`'s brief and
`hail show` produce. The `cd` is load-bearing; resuming from the wrong
directory is the failure it prevents.

**A browser cannot drive a terminal.** No click resumes anything. The
page hands over the command and that is the ceiling.

## Ordering and filtering happen in the page

The data is embedded in the page, so the controls at the top work with
the machine offline and with no rebuild:

- the filter box matches against everything on a work item and every
  session, including fields the card does not print. Both panes follow
  it: a search that left the sessions untouched would be half an answer
- the sort control offers `key`, `open`, `sessions` and `age`, and the
  button beside it flips the direction
- the kind chips below them - `deploy`, `followup`, `unverified` and
  whatever else this page holds - narrow to those kinds. Pick several
  and you get all of them. Nothing starts selected, so the page opens
  whole rather than making you clear a filter you did not set

The chips hide **cards**, not only work items: pick `deploy` on an item
holding a deploy and a followup and you see the deploy alone. Each chip
carries how many of that kind are on the page, and a kind with nothing
behind it gets no chip, because its only possible result is an empty
page.

Typing a kind into the filter box nearly does this and is a trap: that
box matches the whole record, so `deploy` also finds an obligation
whose text mentions deploying, and it keeps or drops whole work items
rather than the cards inside them.

Two things the chips do that are not obvious. The sessions pane
narrows to the sessions those obligations actually name - "who left
these" without a click - and when none of the listed sessions did, it
says so rather than going quietly blank, because the session that left
a deploy six weeks ago is usually past `sessions.limit`. And picking a
kind that only lives in the `on record` disclosure opens it, so the
answer is not hidden behind a closed control.

Both open on whatever `sort.by` and `sort.dir` say, so the controls
always describe the order the items are already in. Nothing is
remembered between builds: the page opens the same way every time, and
a sort you left behind yesterday never silently becomes today's view.

## Decisions are on record, not in front of you

A `decision` entry records why something was done. It was true when it
was written and nothing ever arrives to close it, so decisions
accumulate: on the ledger this was built against, seven of every ten
open entries were decisions, and they buried the thirty that somebody
had to act on.

So the page splits them out. What is left is what blocks: `parked`,
`blocked`, `unverified`, `followup`, `deploy`. Everything else sits in
a closed `N decisions on record` disclosure at the foot of the left
pane - one click, nothing deleted, and a work item that owes nothing
but decisions still has them there after it leaves the page.

The split follows logbook's own `blocking` flag, read from
`logbook ls --json`, not a list of kind names kept here. Declare a kind
of your own in logbook's config and `chartroom` places it correctly
without being told. A kind logbook does not declare stays in front of
you: this page's whole claim is what is outstanding, so the safe side
of not knowing is to show it.

Set `rows.blocking_only` to `false` to put everything back in one list.

## hail's window

`doctor` reports a finding when hail's `index.days` is under 30.
`chartroom` is a page about what is owed, and obligations run for
months, so a short window means the sessions pane cannot reach back as
far as the obligations do. It is a finding rather than an error - the
page is correct, just narrower than the question being asked of it.

The other finding is `rows.blocking_only` being on while logbook marks
no kind non-blocking. Either the setting is doing nothing, or a kind
that belongs on record is being shown as work.

## Serving it

`chartroom serve` exists because the file goes stale silently. Nothing
rebuilds it: a tab left open overnight shows last night's page and says
so only in the masthead line nobody reads twice. `serve` rebuilds on
every request, so a reload is always current.

```
chartroom serve
http://127.0.0.1:8787/?t=z9Q2...
rebuilt on every request. ctrl-c to stop.
```

It is the one part of this marketplace that opens a socket, so it is
worth being exact about what that socket does.

**It binds `127.0.0.1` only.** Not `0.0.0.0`, not a name that might
resolve outward. Nothing off this machine can reach it, on any network
you join.

**The URL carries a token, and the token is the access control.**
Binding loopback is not protection on its own: every process running as
any user on this machine can connect to a loopback port. The token is
32 bytes of `secrets.token_urlsafe`, minted per run, never written to
disk, compared with `hmac.compare_digest`, and kept out of the page it
serves so a screenshot or a pasted page body does not hand it over. The
request log drops the query string for the same reason. A caller
without it gets 403 and no content.

**A `Host` header that is not loopback gets 403.** A site on the open
web can point a name at `127.0.0.1` and make your browser talk to this
socket; what it cannot do is forge the `Host` your browser sends. That
check is what stands between this page and DNS rebinding.

**One path, and read-only.** `GET /` is the page. Any other path is
404. `POST`, `PUT`, `PATCH` and `DELETE` are 405. There is no endpoint
that writes anything, to either sibling or to disk, because `serve`
writes nothing at all - not even the HTML file `build` produces.

**It is exactly as fresh as it looks, and no fresher.** Rebuilt per
request means a reload re-runs both siblings. It does not push: a tab
sitting open does not update itself, and nothing in the page polls.

**It ends when you stop it.** Ctrl-C, and the socket is gone. Nothing
is installed, no launch agent, no daemon, nothing survives the
terminal. A port already in use is exit 5 rather than a second server
quietly bound somewhere else.

What it does not defend against: another process running as you, on
this machine, that can read your terminal, your scrollback or your
browser's session. That process could already read the ledger itself.

## Privacy

The page is a file, and a file is easy to move, attach or commit by
accident. It carries less than hail's index on purpose.

**It contains, per session:** `id`, `title`, `cwd`, `turns`,
`first_ts`, `last_ts`, `branches`, `tickets_from_branch`, and each PR's
number and repo. **Per obligation:** `id`, `kind`, `ts`, `text`,
`session`. Plus the work item's own key, the strongest of an entry's
`ticket`, `pr`, `branch` or `repo_path` - so a directory-keyed item
carries that checkout's absolute path, and a branch-keyed one carries
the branch name.

**It contains no prompt text.** hail stores prompts and `chartroom`
never reads them onto the page. A test asserts it, against a session
whose prompt is a sentinel string.

**Obligation text is on the page in full**, not truncated. That is the
point of the page - a summary of an obligation is not an obligation -
and it is also the reason for the mode below.

The page is written **0600**, into a directory created **0700**, by a
temporary file renamed into place so a reader never sees a partial one.
Nothing but your own account can read it.

Every value on the page is HTML-escaped, and the embedded JSON escapes
`<` as well, so a branch named `</script><script>alert(1)</script>`
renders as text. A test asserts that exact branch is inert.

The page loads no network resource: no CDN, no external stylesheet, no
font. It opens with the machine offline. It also carries a
`Content-Security-Policy` naming that as the rule, so the browser
enforces it rather than taking the file's word for it.

**The config may not choose which binaries run** unless it is inside
your account's own home. `tools.logbook` and `tools.hail` name
executables, so a config found anywhere else has those two settings
ignored, with a warning from `doctor` saying so. Nothing a repository
you clone can set will move that boundary. Every other setting is
honoured wherever the config is found, because the worst it can do is
shape a page.

## Full config reference

Config lives at `~/.claude/binnacle/chartroom.json`, same loader
discipline as its siblings: every key has a working default, an unknown
key warns, a wrong type keeps the default and warns - both warnings are
printed by `doctor`, not by a build - and an unparseable file or unknown
`version` is fatal.

```json
{
  "version": 1,
  "page": {
    "path": "~/.claude/binnacle/chartroom/chartroom.html",
    "open": true
  },
  "sort": {
    "by": "age",
    "dir": "asc"
  },
  "rows": {
    "only_open": true,
    "blocking_only": true
  },
  "sessions": {
    "limit": 60
  },
  "serve": {
    "port": 8787,
    "open": true
  },
  "tools": {
    "logbook": "logbook",
    "hail": "hail",
    "timeout_seconds": 20
  }
}
```

| Key | Default | What it does |
|---|---|---|
| `version` | `1` | Config schema version. A mismatch refuses every command; `doctor` is the one that names the config file and the problem before exiting 4, rather than only saying it is refused. |
| `page.path` | `~/.claude/binnacle/chartroom/chartroom.html` | Where the page is written. Written 0600 into a 0700 directory. |
| `page.open` | `true` | Whether bare `chartroom` opens the page after building it. `build` never opens, whatever this says. |
| `sort.by` | `age` | Initial work-item order: `key`, `open`, `sessions` or `age`. An unknown value is exit 2 naming the allowed set, never a silently ignored key. |
| `sort.dir` | `asc` | `asc` or `desc`. |
| `rows.only_open` | `true` | Whether a work item with no open obligation is dropped. On a real ledger those are most of the page, and the page is about what is owed. The masthead states how many were hidden. Set `false` to see every work item hail knows about. |
| `rows.blocking_only` | `true` | Whether obligations of a kind logbook marks non-blocking - `decision`, by default - are moved into the `on record` disclosure instead of the left pane. Set `false` to show them inline with everything else. |
| `sessions.limit` | `60` | How many sessions the right pane lists, most recent first. A wide hail window puts hundreds there, and a pane nobody reaches the bottom of is the crowding this page exists to undo. The masthead states how many were not listed. `0` lists every one. |
| `serve.port` | `8787` | The loopback port `serve` binds. `0` takes whatever the system hands out, which the printed URL then names. A port already in use is exit 5, never a silent second server. |
| `serve.open` | `true` | Whether `serve` opens the tokened URL in your browser once it is listening. The URL is printed either way. |
| `tools.logbook` | `logbook` | How to run logbook. A bare name is looked up on `PATH`; an absolute path is used as given. A relative path is refused, exit 2. |
| `tools.hail` | `hail` | The same, for hail. |
| `tools.timeout_seconds` | `20` | How long either sibling gets to answer before the run is refused. |

`tools.logbook` and `tools.hail` are run directly, never through a
shell, and every other config value is data that never becomes a
subprocess argument.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | the page was built, or `doctor` found nothing |
| 1 | `doctor` found something |
| 2 | argument refusal, or a setting that cannot mean what it says: a `sort` that is not a sort, a `page.path` that is relative, is a directory, or is not writable, a `tools` entry that is a relative path |
| 4 | config refused to load, or a sibling is missing, too old, misconfigured, or has no index |
| 5 | a sibling answered, but not with usable JSON, not with the envelope this `chartroom` reads, or not in time; or `serve` could not bind its port |

`3` is deliberately unused. In `logbook` it means the followup cap was
reached; reusing the number across two plugins in one marketplace would
be worse than a gap.

**Nothing is written on any failure path.** A refusal leaves the
previous page exactly as it was, rather than replacing it with a
narrower one built from half an answer.

## Changelog

See [CHANGELOG.md](CHANGELOG.md). Before 1.0.0 the config schema may
change between minor versions; `config.version` gates that, and a
mismatch refuses every command rather than quietly running a policy you
did not write. `doctor` refuses too, but names the file and the problem
on its way out.

## License

MIT. `LICENSE` sits at the repository root.
