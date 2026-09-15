# Changelog

Notable changes per release. Newest first.

Versions follow [semantic versioning](https://semver.org). Before 1.0.0
the config schema may change between minor versions; `config.version`
gates that, and a mismatch refuses every command except `doctor` rather
than running a policy you did not write.

## [Unreleased]

## [0.3.3] - 2026-09-15

### Changed

- Documentation only; no behaviour change. The `chartroom` screenshot is
  regenerated over new invented data, so nothing in it reads as one
  trade's vocabulary rather than any working session's.

## [0.3.2] - 2026-09-14

### Changed

- Documentation only; no behaviour change. The README's diagrams are
  plain text rather than Mermaid, which GitHub renders in a
  third-party frame that fails on a private repository and on browsers
  blocking third-party content.
- The README now shows the `chartroom` page and says plainly that it is
  optional, so what `logbook` records can be seen beside the sessions
  that left it. The screenshot is the real renderer over invented data.

## [0.3.1] - 2026-09-14

Documentation only. No code changed.

### Fixed

- The README gave the `ls --json` envelope as
  `{"version", "thresholds", "entries"}`. 0.3.0 added `kinds` and did
  not say so, which left the one field a reader needs to tell an
  obligation that holds a close-out from one that is only on record
  undocumented in the tool that owns it.

## [0.3.0] - 2026-09-14

### Added

- `ls --json` carries the `kinds` map, each with its `blocking` flag,
  the way it already carried `thresholds`. A reader deciding what to
  put in front of a person needs to know which obligations hold a
  close-out and which are only on record, and that is this config's
  answer to give. Without it the only way to ask was to hardcode the
  name `decision`, which stops being true the moment a config declares
  a kind logbook has never heard of. `chartroom` 0.3.0 reads it.

## [0.2.3] - 2026-09-13

Two ways the tracker gate could be configured and then not run, both
found while wiring it on a real machine.

### Fixed

- A `gate.tracker_tools` entry that is a bare string instead of an
  object crashed `doctor` with a traceback, and silently disarmed the
  gate. The hook reads `spec["tool"]`, so a string raised there and the
  fail-open catch exited 0: the tool named in the config was gated by
  nothing, and no output said so. The hook now skips an entry of the
  wrong shape rather than taking every later entry down with it, and
  `doctor` names the bad entry and the shape it needs.
- `doctor --fix` hid the finding that tells you the job is not done.
  After writing the gate copy it dropped every finding whose text
  contained "doctor --fix", which was meant to clear the now-stale
  "gate copy is missing" finding. The tracker-gating finding says "Run
  `logbook doctor --fix`, then add to settings.json ...", so it was
  dropped too - and that finding carries the only instruction for step
  3 of the three-step procedure the README sets out, in which `--fix`
  is step 2. The copy is now written before the gate is examined, so a
  finding the write settles is never raised in the first place and
  nothing is filtered by wording.

## [0.2.2] - 2026-09-13

Documentation only. No code changed, and no behaviour with it. Every
claim in the README, this file and the skill was read against the
source; these are the ones that were not true.

### Fixed

- The README said a bad config made the gate get out of the way. It
  does not. A crash inside the hook falls open; a config the tool
  refuses to load makes the gate ask, on the close-out it could not
  check, because a gate that cannot read its policy must not pass a
  close-out silently.
- This file said the gate does not deny. `gate.mode: deny` makes it
  deny. Only the other half was true: it can never allow something
  another hook would refuse.
- `--field` was documented as refusing any built-in field's name. Only
  `ticket` and `pr` are refused, because only those two have a typed
  flag that normalises the value. The reserved list also left out
  `repo_path`, which is refused.
- The required-value guard was described as applying to every kind. It
  skips the identifier fields, so `deploy` and `followup` get only a
  non-blank check, not the three-character one.
- `doctor` was said to report an `environment` origin. Nothing writes
  one. `LOGBOOK_HOME` moves the whole store and was documented nowhere,
  which made `home default` on the origin line actively misleading.
- `gate-check` is a subcommand, and the session-start hook runs it
  every session. It appeared in no document.
- `LOGBOOK_CONFIG` was said to disable resolvers by being set at all.
  It is the path that decides: pointed at the default path, resolvers
  stay on.
- `deploy.env_passthrough` works and was missing from a section headed
  "Full config reference". The resolver environment allowlist, the
  `--session` flag, the `hail.index` rejoin line, and the fact that
  `gh pr ready` trips the gate were all undocumented.
- Smaller corrections: `check` exits 0 with decisions still on record,
  the brief's other-ticket rows do show the ticket, resolver stdout is
  lower-cased before it is matched, resolvers run under
  `subprocess.Popen` rather than `subprocess.run`, exit 4 covers three
  fatal config paths rather than one, and the tool also runs
  `git merge-base` and itself.
- The gate copy's write boundary was described as always passing. That
  was the design that was rejected; the shipped check refuses.

## [0.2.1] - 2026-09-12

### Changed

- `git_context` no longer records a detached checkout's branch as the
  literal string "HEAD". That string used to become a join key, so a
  detached checkout's entries were merged with anything else that ever
  had a branch named "HEAD". A detached checkout now carries no branch
  at all.
- The resume hint's `cd` target is quoted before it is printed, so a
  checkout path with a space in it does not break when the command is
  pasted into a shell. The session id stays unquoted; the format still
  matches the same string printed by the other two plugins that build it.

### Security

- The ledger directory is now created `0700` and the log file `0600`,
  rather than whatever the process umask allowed. Entry text is the
  most sensitive thing this tool stores, and a fresh ledger used to be
  briefly readable by anyone else with an account on the machine. A
  file that already existed before this change keeps whatever mode it
  had.

## [0.2.0] - 2026-09-12

What `chartroom` needs to read the ledger without reaching past the CLI.

### Added

- `logbook --version`, printing the tool's own version constant, kept in
  step with `.claude-plugin/plugin.json` by hand. It is how a consumer
  tells a logbook that has these commands from one that does not,
  without matching on the text of an error message.
- `ls --json`, printing the same selection `ls` prints as an envelope:
  `{"version", "thresholds", "entries"}`. The thresholds travel with
  the entries so a reader deciding what counts as stale uses the number
  this logbook enforces rather than one of its own. Every existing
  filter applies identically to both outputs.

### Changed

- `branch` joined the keys that are never shortened when an oversized
  event is shrunk to fit an atomic append. It routes an entry to a work
  item when there is no ticket, so a truncated branch is a misfiled
  entry. `repo_path` deliberately did not join them: losing the write
  entirely is worse than misfiling one row.
- The refusal raised when nothing shrinkable is left now names the
  field that would not shrink and how long it is, instead of saying
  only that the event was too big.

## [0.1.0] - 2026-09-11

First release. `logbook` only; `hail` and `chartroom` follow.

### Added

- `logbook add|ls|show|resolve|drop` over an append-only JSONL store.
  Concurrent sessions in separate checkouts never clobber each other:
  state is a replay of the log, and each event is a single append under
  the atomic write size.
- Six entry kinds, each requiring one structural field: `parked` needs
  `resume`, `blocked` needs `unblocked_by`, `followup` needs a ticket,
  `unverified` needs `verify`, `deploy` needs stage, service and commit,
  `decision` needs `why`. An entry that cannot name its field is a work
  unit and belongs in a tracker.
- Custom kinds and custom fields. Declare your own in config, or attach
  any field with `--field name=value`. A kind not declared in config
  blocks close-out rather than passing silently.
- `logbook check` as a close-out gate, exiting 1 while obligations are
  open against a ticket or PR.
- `logbook brief` for session start, listing what is open elsewhere,
  what is stale, and what expired. Only entries on the current ticket
  print their text; one on another ticket shows its id, kind and age.
  `brief.remote_text` prints every entry's text instead.
- `logbook doctor` explaining where every setting came from, and
  reporting config that cannot do what it looks like it does: a kind
  requiring nothing, a capped kind with no ticket to group by, a ticket
  pattern that cannot normalise, tracker gating that nothing runs.
- `logbook deploy-sync`, resolving open deploy obligations by running
  commands you supply per stage. Stages match by exact name, then glob,
  then `*`.
- A `PreToolUse` hook that holds a PR merge or a tracker transition
  with `ask` while obligations are open, and a `SessionStart` hook that
  prints the brief.
- Config at `~/.claude/binnacle/logbook.json`: ticket pattern and
  example, tracker name, thresholds, kinds, gate behaviour, deploy
  stages. Every value has a default, so the tool works with no config
  at all.
- Ships as a Claude Code plugin, with a skill describing when to write
  an entry.

### Security

- Resolver commands from config are executed with a shell. This is the
  design, since the command is yours. The boundary is that the config
  must be the file at the default path under your account's own home,
  read from the passwd entry rather than `$HOME`: nothing a repository
  you clone can set will move that. Setting `LOGBOOK_CONFIG`, a symlink
  at that path, or a repointed `HOME` all leave resolvers off, and
  `deploy-sync` says why.
- A resolver receives a small allowlisted environment plus the
  `LOGBOOK_*` values, not every credential in your session. Name extra
  variables with `deploy.env_passthrough` if a script needs them. Quote
  every `$LOGBOOK_` expansion in your own scripts: the values come from
  entries, and an entry may be written from material an agent read.
- A timed-out resolver has its whole process group killed, so a
  pipeline's far side cannot outlive the timeout holding credentials.
  Output is capped.
- Both hooks exit 0 on every error path, including a malformed payload.
  A hook that raises would block the tool call it was inspecting.
- The gate asks by default and can never allow something another hook
  would refuse. `gate.mode` chooses between `ask`, `deny` and `off`;
  only a config that sets `deny` makes it refuse a close-out outright.
  Under a config it cannot read it asks only on a close-out it could
  not check, not on every command.
- The session-start brief withholds the text of entries on other
  tickets. The hook's output is sent to the model on every session
  start, and an entry parked under unrelated work has no reason to
  travel there. Id, kind and age still print, so the escalation is
  still visible. `brief.remote_text` restores the full text for anyone
  who wants it.
- The gate copy's write boundary reads the account's passwd home, not
  `HOME`. Using `HOME` for both would have moved the target and the
  boundary together, so the check would always have passed; against the
  passwd home a repointed `HOME` moves the target outside it and the
  write is refused instead.
- Recorded text is rendered so it can never begin a line. An entry
  could otherwise close the gate's list and add an all-clear, and the
  human reading the permission prompt would see this tool saying the
  merge was safe.
- An event that cannot be brought under the size a single append is
  atomic at is refused rather than written, so the guarantee that
  concurrent sessions never clobber each other holds for every write.
- A config that cannot be parsed, or whose version does not match,
  refuses every command except `doctor` rather than falling back to
  defaults. Silently substituting a weaker policy than the one you
  wrote is the failure this prevents.
- The store is never committed: `*.jsonl` and `index.json` are ignored,
  because entries hold whatever you recorded.

### Exit codes

- `0` success
- `1` blockers found, or nothing matched
- `2` refused on shape: a required field is missing or unusable
- `3` followup cap reached for one ticket
- `4` config refused: unreadable, unparseable, not an object, or a
  `version` that is not 1. Run `logbook doctor`.
