# Changelog

Notable changes per release. Newest first.

Versions follow [semantic versioning](https://semver.org). Before 1.0.0
the config schema may change between minor versions; `config.version`
gates that, and a mismatch refuses every command rather than running a
policy you did not write. `doctor` refuses too, but names the file and
the problem on its way out.

## [Unreleased]

## [0.4.3] - 2026-09-15

### Changed

- The masthead shows the build time on the reader's own wall clock with
  the zone named, rather than a raw UTC stamp. The value carried in the
  page stays UTC, so every age is computed exactly as before.

## [0.4.2] - 2026-09-15

### Changed

- Documentation only; no behaviour change. The screenshot is regenerated
  over new invented data, so nothing in it reads as one trade's
  vocabulary rather than any working session's.

## [0.4.1] - 2026-09-14

### Added

- Kind chips: one toggle per kind actually on the page, each carrying
  how many there are, so the page can be narrowed to `deploy`, or to
  `followup` and `unverified` together. Nothing starts selected, so it
  opens whole rather than making you clear a filter you did not set,
  and a kind with nothing behind it gets no chip.

  The chips hide cards, not only work items: picking `deploy` on an
  item holding a deploy and a followup shows the deploy alone. The
  search box nearly did this and was a trap - its haystack is the whole
  record, so `deploy` also matched an obligation whose text mentioned
  deploying, and it kept or dropped whole items.

  Two details that decide whether it reads as working: the sessions
  pane narrows to the sessions those obligations name, and says so
  when none of the listed ones did rather than going blank - the
  session that left a deploy six weeks ago is usually past
  `sessions.limit`. And a kind that only lives in the `on record`
  disclosure opens it, instead of answering with a page that looks
  empty.

## [0.4.0] - 2026-09-14

### Added

- `chartroom serve [--port N]`, which listens on loopback and rebuilds
  the page for every request. The file goes stale silently - nothing
  rebuilds it, and a tab left open overnight says so only in a masthead
  line nobody reads twice. Serving makes a reload current.
- `serve.port` (default `8787`) and `serve.open` (default `true`).

  This is the only socket in the marketplace, so what it refuses is
  part of the feature: `127.0.0.1` only; a 32-byte token in the URL,
  minted per run, never written to disk, compared with
  `hmac.compare_digest`, kept out of the page and out of the request
  log; 403 on a `Host` header that is not loopback, which is what
  stands between the page and DNS rebinding; `GET /` and nothing else,
  404 for any other path and 405 for any writing method. It writes no
  file at all, not even the one `build` produces, and it ends with the
  process. A port already in use is exit 5, never a second server bound
  somewhere else.

  One request per connection, and a thread per connection with a read
  timeout: any local process can open a socket and then say nothing,
  and on a single-threaded server that one silent connection owns the
  accept loop and the owner's own reload hangs behind it - a local
  denial of service needing no token at all.

  The URL is flushed before the server blocks. stdout is
  block-buffered into a pipe, so without that the one line a caller
  needs sits in the buffer until the process is killed, taking the
  token with it.

  The skill tells Claude never to start it: it holds a socket until
  somebody stops it, so that is the user's call, in their own terminal.

### Changed

- `page_html()` factored out of `cmd_build`, so building a page and
  serving one cannot drift apart.

## [0.3.4] - 2026-09-14

### Fixed

- A PR number no obligation carries no longer keys a work item. Claude
  Code attaches a PR to a session on its own and can attach the wrong
  one: the session this was found on carried 720 records claiming a PR
  merged months earlier on somebody else's branch. A PR outranks a
  branch, so that one false claim carried the session off its own work
  item - the obligations left with no session beside them, the PR with
  no obligations under it, on a page whose whole job is joining the
  two. Such a PR is now dropped before keying and the record falls
  through to its branch. Measured on a live index of 189 sessions: six
  work items were PR-keyed, all six had no obligations at all, and one
  of them was a real split. After the fix, none.
- The same PR is kept out of the alias, so it cannot bind to a ticket
  and reach the page by the other road.

## [0.3.3] - 2026-09-14

Documentation only. No code changed.

### Changed

- The README's diagram is plain text rather than Mermaid, which GitHub
  renders in a third-party frame that fails on a private repository and
  on browsers blocking third-party content.
- The README shows the page itself, rendered by this version over
  invented data: no ticket, branch, repository or path in the
  screenshot belongs to anyone.

## [0.3.2] - 2026-09-14

Documentation only. No code changed.

### Fixed

- The README still documented the six table columns, the severity
  colour "would make the whole table red", and `N aged off` as a cell -
  all of which 0.3.0 removed. It described a page that no longer
  exists.
- The README and the skill called a work item a row. There are no rows
  on the page any more, so the word named nothing a reader could point
  at.

## [0.3.1] - 2026-09-14

### Fixed

- The sessions pane listed every session hail holds. On a 60-day index
  that was 182 cards, and a pane nobody can reach the bottom of is the
  crowding 0.3.0 set out to undo - the page came out larger than the
  one it replaced. It now stops at `sessions.limit`, 60 by default and
  most recent first, and the masthead states how many were not listed.
  Set it to `0` to list every one.

## [0.3.0] - 2026-09-14

Needs `logbook` 0.3.0 or newer; `hail` 0.2.0 still.

The page showed everything it had and left the reader to find the work
in it. On the ledger this was built against that meant 109 rows, of
which 74 owed nothing, and 103 open obligations, of which 71 were
decisions - so 32 things somebody had to act on, behind two layers of
things nobody did.

### Changed

- Two panes, not a table: what is owed on the left, the sessions that
  worked it on the right. Obligation text is on the card in full rather
  than three capped lines with the rest behind a click. A work item's
  obligations sit under its key as a group.
- The sessions pane lists every session hail holds, most recent first,
  deduplicated, each with its resume line. "Where was I working" is a
  different question from "what do I owe", and it is answered for work
  that owes nothing too.
- The filter reaches both panes. A search that left the sessions
  untouched was half an answer.

### Added

- `rows.blocking_only`, default `true`: an obligation of a kind logbook
  marks non-blocking moves into a closed `N decisions on record`
  disclosure instead of the left pane. A decision was true when it was
  written and nothing ever arrives to close it, so decisions
  accumulate and bury the work.
  - The split reads logbook's own `blocking` flag rather than a list of
    kind names kept here, so a kind you declare in logbook's config is
    placed correctly without chartroom being told about it. A kind
    logbook does not declare stays in front of you: this page's whole
    claim is what is outstanding, so the safe side of not knowing is to
    show it.
  - A work item whose obligations are all decisions leaves the page,
    and its decisions still reach the disclosure. They are exactly what
    somebody reopening the ticket in a month goes looking for; dropping
    them with the row would be the page destroying the record it exists
    to keep.
- `doctor` reports the kinds in force and which are set aside, and
  raises a finding when `rows.blocking_only` is on while logbook marks
  no kind non-blocking - either the setting is doing nothing, or a kind
  that belongs on record is being shown as work.

### Removed

- The activity readout, and the `strip` config section with it. One
  character per day over hail's window read as a row of zeroes on a
  real ledger, because most work items are touched on one day and not
  again. `doctor`'s finding about `strip.days` outrunning the window
  goes too. A `strip` block left in a config is an ignored key, which
  `doctor` names; delete it.
- The preview lines, the expanding row, and the per-row last-worked
  cell. The card shows the text, and every age on the page now belongs
  to an obligation or a session.

### Fixed

- The sibling version floor is per tool. It was one number for both,
  so raising the floor for one sibling would have refused a perfectly
  good copy of the other.

## [0.2.0] - 2026-09-14

The page was readable on a fresh ledger and not on a real one. On a
store with a hundred open obligations across 109 work items, two
thirds of the rows owed nothing and every row that did owe something
needed a click to find out what.

### Added

- `rows.only_open`, default `true`: a row with no open obligation is
  not rendered. Those are sessions with nothing owed on them, and they
  outnumbered the rows that did owe something 74 to 35 on the ledger
  this was found on, so the work was read past rather than read. The
  masthead states how many were hidden, because a row removed without
  a word is a page lying by omission. Set it `false` for the old
  behaviour, which is still the honest view of "where has work
  happened".
- Each row carries the first line of up to three of its obligations,
  kind first, then `N more`. One line per obligation whatever the text
  holds, so a pasted stack trace cannot make one row taller than the
  screen. The full text is still behind the click, where it was.

### Fixed

- The test harness prepended its fake `PATH` to the inherited one, so
  the test that a missing sibling is exit 4 found the real `logbook`
  once the plugins were actually installed. It passed only on a
  machine without binnacle on it, which is not the machine that runs
  the release gate. The fake `PATH` no longer inherits.

## [0.1.2] - 2026-09-13

Documentation only. No code changed, and no behaviour with it. Every
claim in the README, this file and the skill was read against the
source; these are the ones that were not true.

### Fixed

- `N aged off` counts open obligations whose session is no longer in
  hail's index, not sessions, and it cannot tell a session that aged
  out from one hail never held. The skill told Claude to read it as
  sessions that aged out, which is a wrong answer handed to a user.
  The README documented the badge nowhere at all.
- The skill said exit 4 means a sibling is missing or too old. It also
  covers a config that will not load and a sibling that could not
  answer `ls --json` - most often hail having no index yet, which
  `hail index` fixes, not a plugin upgrade.
- The reason given for keying severity off the kind named `blocked`
  rather than logbook's `blocking` flag was wrong: `decision` entries
  are open and are not blocking. The conclusion stands, the reason did
  not.
- The directory level was described as comparing `repo_path` against
  `cwd` directly. Since 0.1.1 a session's directory resolves to the
  longest checkout root containing it, and a truncated `repo_path` keys
  nothing.
- The alias rule left out its restriction: only a PR or a branch can
  hop to a ticket. A directory is a place, not a piece of work.
- The privacy list enumerated the allowlisted session and obligation
  fields but not the row key, which carries a checkout's absolute path
  on a directory-keyed row and a branch name on a branch-keyed one.
- `doctor` was said to print every setting in force. It does not echo
  `tools.*`; an ignored `tools` entry surfaces as a warning instead.
  Loader warnings print only from `doctor`, never from a build.
- A version mismatch refuses `doctor` too. It differs only in naming
  the file and the problem on its way out.
- Smaller corrections: a sibling's version is checked before that
  sibling is read, not both before either; a sibling that cannot report
  three dot-separated numbers is refused like an old one; the severity
  column has no header; and `page.path` is also refused for being
  relative or a directory.

## [0.1.1] - 2026-09-12

Mostly the join. The first release keyed rows in a way that merged
unrelated work and split related work, and did both quietly.

### Fixed

- A PR number and a branch name are only unique inside a checkout, so
  two repositories each holding a PR 42 were one row, labelled with
  whichever repository was read last. Both are now scoped by checkout,
  but only where the ambiguity is real: a value seen under two
  checkouts splits, everything else stays whole. Scoping
  unconditionally was tried first and was worse, because an obligation
  written outside a repository can name no checkout and was split away
  from its own work.
- `main`, `master`, `develop`, `trunk` and the `HEAD` a detached
  checkout reports no longer key a row. On a real ledger `HEAD` had
  collected three unrelated checkouts into one work item.
- The two sides can settle at different levels: an obligation carrying
  only a PR never met the sessions that only knew the branch. A weak
  key now follows one hop to a ticket some record witnessed it beside.
  One hop, and never when two different tickets were witnessed, so a
  session that glanced at a second ticket cannot weld two work items
  together.
- The fourth key level compared two different things - logbook's
  `repo_path` is the checkout root, hail's `cwd` is wherever the
  session was launched - so it never joined at all. A session's
  directory now resolves to the checkout containing it.
- A `repo_path` that logbook truncated to fit an atomic append no
  longer keys a row, having named a directory that does not exist.
- The activity strip aged against the wall clock while severity aged
  against the build. One page, two clocks; now one.
- The page is written as utf-8 explicitly rather than in the locale's
  codec, which failed the build under a C locale on the first
  character outside ASCII.
- A directory containing a space now survives the copied resume line.

### Added

- The page carries a doctype, a charset and a
  `Content-Security-Policy`, so "loads no network resource" is the
  browser's rule and not this file's promise, and the page is no
  longer parsed in quirks mode.
- Open obligations whose session is no longer in hail's index are
  counted on the row. The count was computed from the first release
  and shown nowhere.
- The masthead names the `chartroom` that built the page, as it
  already named both siblings.
- A filter matching nothing says so, and an empty half of an expanded
  row says which half is empty.
- Severity colours are theme tokens, legible on a dark background.
  Wide tables scroll inside their own box rather than carrying the
  page sideways.

### Changed

- A sibling that answers with JSON of the wrong shape is refused at
  exit 5, naming what was missing. It previously became a traceback
  and exit 1, and a future sibling renaming a key would have rendered
  a confident "0 open" - the worst available answer from a tool whose
  whole claim is what is outstanding.
- `page.path` is checked before anything is written: an empty
  directory part, a path that is a directory, and an unwritable parent
  were three tracebacks and are now three refusals that name the
  setting.
- The refusal for a sibling that is not on `PATH` says what is
  actually wrong. A marketplace install only puts the binaries on
  `PATH` inside a Claude Code session, so telling someone to install a
  plugin they already have was the one fix that could not help.
- The timeout refusal names the setting that raises it.

### Security

- `tools.logbook` and `tools.hail` name executables, and are now
  honoured only from a config inside the account's own home, read from
  the passwd entry rather than `$HOME`. A repointed `HOME` plus a
  planted config could otherwise choose what ran. Both siblings
  already drew this line; this one did not. Every other setting is
  still honoured wherever the config is found.
- A `tools` entry that is a relative path is refused rather than
  resolved against whatever directory `chartroom` was started in,
  which is a repository often enough to matter.

## [0.1.0] - 2026-09-12

First release. Needs `logbook` 0.2.0 and `hail` 0.2.0 or newer.

### Added

- `chartroom`, `chartroom build` and `chartroom doctor`, writing one
  self-contained HTML page that joins logbook's open obligations to the
  hail sessions that worked them.
- A row per work item, keyed at the first level that answers: ticket,
  then PR, then branch, then directory, the same four levels on both
  sides. Anything with none of the four still gets a row, under
  `unkeyed` - unticketed work dropped from the page would look exactly
  like having nothing to do.
- Sessions key on branch-derived tickets only, so a session that merely
  mentioned a ticket falls through to its branch row rather than
  claiming it worked that ticket.
- Ordering and filtering in the page, over data embedded in the file:
  the filter reaches obligation text and session titles inside a
  collapsed row, and the sort control offers `key`, `open`, `sessions`
  and `age`. Both controls open on `sort.by` and `sort.dir`, and
  nothing is remembered between builds.
- An activity readout, one character per day, that follows hail's own
  index window by default so it cannot outrun the data. A day at or
  beyond the window renders as absent, never as zero.
- `doctor` reporting the config in force, both sibling versions,
  logbook's thresholds and hail's window and census, plus two findings
  about the window: an activity readout wider than hail keeps, and a
  hail window under 30 days on a page about obligations that run for
  months. Exits 1 on a finding, so it can be used in a check.
- Both siblings read through their own `--json` commands rather than
  their storage files, with the version checked before anything is
  read. A missing, too old or misconfigured sibling names itself and
  the command that fixes it.

### Security

- The page is written 0600, into a directory created 0700, through a
  temporary file renamed into place, so a reader never sees a partial
  page and no other account sees it at all.
- The page carries no prompt text. Sessions are cut to an allowlist -
  `id`, `title`, `cwd`, `turns`, `first_ts`, `last_ts`, `branches`,
  `tickets_from_branch`, and each PR's number and repo - and
  obligations to `id`, `kind`, `ts`, `text`, `session`. A test asserts
  a sentinel prompt never reaches the file.
- Obligation text is rendered in full and is the most sensitive thing
  on the page. That is what 0600 is for.
- Every value is HTML-escaped, and the embedded JSON escapes `<` as
  well, so a branch named `</script><script>alert(1)</script>` renders
  as text. A test asserts that exact branch is inert.
- The page loads no network resource. No CDN, no external stylesheet,
  no font; it opens from `file://` with the machine offline.
- Nothing is written on any failure path: a refusal leaves the previous
  page exactly as it was rather than replacing it with one built from
  half an answer.
- Read-only in both directions. `chartroom` writes only the page, and
  nothing in the page can write back to either sibling.
- Siblings are run directly, never through a shell, and no config value
  becomes a subprocess argument.

### Exit codes

- `0` the page was built, or `doctor` found nothing
- `1` `doctor` found something
- `2` argument refusal, or a `sort` setting naming something that is
  not a sort
- `4` config refused to load, or a sibling is missing, too old,
  misconfigured, or has no index
- `5` a sibling answered, but not with usable JSON, or did not answer
  in time
