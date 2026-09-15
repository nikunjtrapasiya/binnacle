# Changelog

Notable changes per release. Newest first.

Versions follow [semantic versioning](https://semver.org). Before 1.0.0
the config schema may change between minor versions; `config.version`
gates that, and a mismatch refuses every command except `doctor` and
`--version` rather than running a policy you did not write.

## [Unreleased]

## [0.2.4] - 2026-09-15

### Changed

- Documentation only; no behaviour change. The `chartroom` screenshot is
  regenerated over new invented data, so nothing in it reads as one
  trade's vocabulary rather than any working session's.

## [0.2.3] - 2026-09-14

### Changed

- Documentation only; no behaviour change. The README's diagrams are
  plain text rather than Mermaid, which GitHub renders in a
  third-party frame that fails on a private repository and on browsers
  blocking third-party content.
- The README now shows the `chartroom` page and says plainly that it is
  optional, so the sessions `hail` indexes can be seen beside what they
  left open. The screenshot is the real renderer over invented data.

## [0.2.2] - 2026-09-13

Documentation only. No code changed, and no behaviour with it. Every
claim in the README, this file and the skill was read against the
source; these are the ones that were not true.

### Fixed

- The privacy inventory left out three stored fields, two of them the
  sensitive ones: the transcript's path on disk, `project`, and
  `last_prompt` - a prompt kept beyond the `index.prompts` cap, so a
  long session stores `index.prompts + 1` prompts rather than the
  documented maximum. Setting `index.prompts` to `0` does not switch
  prompt storage off; it leaves `last_prompt` alone.
- The cold-path guard was described as a per-file check on a cold
  build. It is a whole-build check that runs on every build, over
  reused records as well as fresh ones, so a warm run whose fresh files
  all lack a `cwd` is counted and reported rather than refused.
- `find` was said to search the ticket list. It does not: a full ticket
  key matches the list exactly, and anything else searches the title,
  branches, `cwd`, stored prompts and PRs. `find` is also the one
  command that does not refuse an unknown flag - it searches for it, so
  a typo reads as no matches.
- `show` was called the command that prints every stored field.
  `find --json` prints each record whole, including fields `show`
  never shows, and is the widest output hail has.
- `doctor` was said to report where every setting came from. For
  `index` and `scan` it compares against the default, so a config that
  restates a default reads as `default`. Only `ticket.pattern` and
  `ticket.reserved` carry a true source.
- A fatal config does not refuse `--version`, by design, so a consumer
  can detect the installation even when hail will not run.
- The session-start hook is silent on three paths - a config it cannot
  load, a missing transcripts directory, and any unexpected exception -
  so a broken config stops the index updating with no visible sign.
  That is why `doctor` treats a week-old index as a finding.
- Smaller corrections: `ls` prints a date, not an age, and cuts the
  branch to 24 characters; `*` marks a live session in `find` too;
  `doctor` exits 1 on a finding and 4 on a fatal config; the
  incremental guard also protects `tickets_from_branch`; a symlinked
  index path is refused; and there is no extraction table, only a
  one-line list of the keys hail reads.
- The 0.2.1 timeout note quoted a warm rescan of the whole corpus. The
  window means only part of it is ever read, and that release forces a
  cold pass; the entry now says which run was measured, on what.

## [0.2.1] - 2026-09-12

Five findings from a review of `ls --json`, `doctor`, the `SessionStart`
hook, and how a rejoin line and a branch name get built.

### Changed

- **The first run of 0.2.1 rescans every transcript.**
  `EXTRACTOR_VERSION` went to 3 because a detached-HEAD session used to
  scan into `branches: ["HEAD"]`, and a cached record still carrying
  that wrong value cannot fix itself: reused-unchanged, it never runs
  through the extractor again, and if it did the incremental guard
  would read the field shrinking to `[]` as a regression and keep the
  bad value rather than accept it. Bumping the signature forces every
  cached record to be re-derived once, so the stale `"HEAD"` clears out
  everywhere instead of on a schedule nobody controls.
- `hail scan_file` no longer records a session's `gitBranch` when its
  value is the literal string `"HEAD"` - that is git's word for
  detached, not a branch name. Left in, it became a join key that
  merged every detached-HEAD checkout into one fake branch downstream.
- The `SessionStart` hook's timeout went from 10s to 60s. On one
  machine - a local SSD, 186 transcripts on disk of which 104 (486MB)
  fall inside the default 10-day window - a full cold rescan measured
  about 1.3s. A larger corpus, a slower disk, or a network home crosses
  10s, and a killed hook never writes the index and prints nothing, so
  the same timeout repeats every session with no visible cause. Treat
  the number as one machine's, not a budget.

### Fixed

- `hail show`'s rejoin line now quotes the `cwd` with `shlex.quote`
  before building `cd <cwd> && claude -r <id>`. A directory with a
  space in it used to produce a line that breaks when pasted; the
  session id is left unquoted, and the format itself is unchanged,
  since the same string is compared across three plugins.

### Security

- `ls --json` used to print each stored record whole, which meant
  `prompts`, `last_prompt`, their truncation flags, and the
  transcript's on-disk `path` - a bulk export of everything typed into
  every indexed session, contradicting the README's claim that `ls`
  never prints a stored prompt beyond the title fallback. It now
  builds each emitted record from `LS_JSON_FIELDS`, an explicit
  allowlist of the structural fields a consumer actually needs. `show`
  still prints prompts; that has always been its job.

### Added

- `doctor` treats an index older than a heuristic seven-day threshold
  (`STALE_INDEX_SECONDS`) as a finding, exiting 1 the same way a
  regression or a cwd-less scan does. Before this, a dead index only
  ever showed up as a line of prose - "index age: Ns" - that nothing
  read, so every other answer `hail` gave could be silently wrong for
  weeks.

## [0.2.0] - 2026-09-12

What `chartroom` needs to read the index without reaching past the CLI.

### Added

- `hail --version`, printing the version. It is how a consumer tells a
  hail that has these commands from one that does not, without matching
  on the text of an error message. The number is a constant in
  `bin/hail`, checked against the plugin manifest and the marketplace
  entry at release time.
- `ls --json`, printing the whole index as an envelope:
  `{"version", "built_at", "days", "census", "sessions"}`. The
  `days` and `census` fields are the point - a reader of the index
  cannot otherwise tell "nothing worked this" from "what did has aged
  out of the window". `-n` with `--json` is an argument refusal rather
  than a truncated list beside a census describing the whole index.
  Note that `find --json` is still a bare list; the README says why the
  two shapes differ.
- `tickets_from_branch` on every record: the tickets derived from the
  session's own branch names, separate from `tickets`, which also holds
  every ticket key mentioned anywhere in the session. A consumer
  claiming "these sessions worked this ticket" needs the first and not
  the second. Both are derived by one function, so they cannot drift.

### Changed

- **The first run of 0.2.0 rescans every transcript.**
  `EXTRACTOR_VERSION` went to 2 because a record without
  `tickets_from_branch` is not one a cached record can grow into, and
  the scan signature is what stops a cached record being reused. The
  rescan is one-time and its cost was measured at 1.68s cold over 105
  transcripts, against the `SessionStart` hook's 10s budget. Nothing to
  do; this note exists so an unexpected pause at the next session start
  is a known cost rather than a bug report.
- `ls --json` refuses an index that predates this version rather than
  returning records missing `tickets_from_branch`, and says to run
  `hail index`. All three refusals - no index, an unreadable index, a
  stale one - print on stderr, so stdout is either JSON or empty.

## [0.1.0] - 2026-09-12

First release.

### Added

- `hail index|find|ls|show|doctor` over an index built from the Claude
  Code transcripts already on disk.
- `find` matches case-insensitively against the ticket list, the
  title, every branch, `cwd`, the stored prompts, and each PR's number
  and repo. A query that normalises to a ticket key matches the ticket
  list exactly, not as a substring.
- `ls` lists the most recent sessions, marking any still-running
  session `*`. `show <id-or-prefix>` prints one session in full,
  including the `cd ... && claude -r ...` line to rejoin it.
- Two guards between a transcript format change and a silently emptied
  index: an incremental rescan of an already-indexed file must never
  lose a field it had before, or the cached record is kept instead of
  the fresh one; a build with no cached record to compare against
  refuses outright, writing nothing, if a real sample of scanning
  turned up zero sessions with a `cwd`. Both are reported in a
  persisted census that `hail index` and `hail doctor` both print.
- `hail doctor` reporting the config path and the source of every
  setting, the index's path, mode, age and size, the persisted census,
  the extraction table, and a mismatch check against `hail.index` in
  logbook's own config. Exits 1 on a regression or a mismatch, so it
  can be used in a check rather than read by eye.
- Liveness resolved at read time from Claude Code's own session marker
  files, validating the pid and comparing process start times as
  epochs rather than as strings, to close a pid-reuse hole that a
  naive string comparison would silently reopen.
- Config at `~/.claude/binnacle/hail.json`: index window and prompt
  limits, the ticket pattern and its reserved prefixes, and the scan
  settings, including which lines are never real prompts. Every value
  has a default, so the tool works with no config at all.
  `ticket.pattern` and `ticket.reserved` inherit from `logbook.json`
  when that file exists, parses, and is on the same config version -
  independently, one key at a time, and never at the cost of failing a
  `hail` command over a `logbook.json` problem.
- Ships as a Claude Code plugin, with a `SessionStart` hook that
  rebuilds the index in-process and a skill describing when to reach
  for `hail find` instead of asking the user to remember.

### Security

- The index is mode 0600 and holds prompt text. `find`, `ls` and
  `show` print it because you run them by hand; no hook prints prompt
  text.
- The index path is fixed at
  `<account home>/.claude/binnacle/hail/index.json` and cannot be
  moved by config. `account home` is read from the account's own
  passwd entry, not the `HOME` environment variable, so a repointed
  `HOME` cannot move the write either.
- `id` and `cwd` are validated before a record is written, because
  logbook's own `SessionStart` brief prints a rejoin line built from
  exactly those two fields. A malformed value in either one would be a
  hook printing bad data into a session's own context.
- A build refuses to overwrite a good index with empty records. When a
  rescan of an already-indexed file loses a field it used to have, the
  cached record is kept and the fresh one is discarded. When a build
  with no cached record to compare against turns up no sessions with a
  `cwd` at all after a real sample, it writes nothing and exits
  nonzero, leaving the existing index untouched.
- `hail` executes nothing from config. `scan.transcripts` and
  `scan.live` are read from, never executed, and no config value ever
  becomes a subprocess argument. The one subprocess `hail` runs is a
  fixed, shell-free call to `ps`, taking only pids already validated as
  integers.
- The `SessionStart` hook exits 0 on every path, including its own
  crash, and a missing transcripts directory writes nothing rather
  than replacing a good index with an empty one.

### Exit codes

- `0` success
- `1` nothing matched, no such session, no index yet, or `doctor`
  reported at least one finding
- `2` argument refusal, including an ambiguous or too-short id prefix
- `4` config refused to load, for example an unknown `version`
- `5` index build refused: the scan looks broken and the index was
  left alone
