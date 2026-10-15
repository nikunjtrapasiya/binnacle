# Contributing

Issues and pull requests are welcome. One thing to know first, because it
is unusual and it decides how a change actually lands.

## This repo is a snapshot, not a working tree

Development happens in a private repo. What you see here is built from it
and published as a single commit with no parent, so this repo holds the
current release and nothing else. `git log` here has one entry, and each
release replaces it.

That has a consequence: **a pull request opened here cannot be merged.**
Merging would put a commit on `main` that the next release would silently
delete. So a PR is read as a proposal. If the change is right, it gets
made in the private repo and arrives in the next release, and the PR is
closed with a note naming the release that carries it.

Your commit authorship does not survive that trip. Credit goes in the
changed plugin's own `CHANGELOG.md` instead, naming you - for example
[logbook/CHANGELOG.md](logbook/CHANGELOG.md). If that is not a trade you
want to make, say so in the PR and nothing will be taken from it.

## What helps

- **An issue first, for anything behavioural.** A bug report with the
  command you ran, what you expected and what happened is worth more than
  a patch, because the fix usually belongs somewhere other than where the
  symptom showed up.
- **A test that fails before and passes after.** Each plugin has its own
  suite, run from the repo root:
  `python3 -m unittest discover -s logbook/tests`, and the same for
  `hail/tests` and `chartroom/tests`. Standard library only, Python 3.9
  and up. No dependencies, no build step, and nothing that needs
  network.
- **One change per PR.** A patch doing two things gets ported as two
  changes or not at all.

## What will not be taken

- A dependency. The no-dependency rule is the point, not an oversight.
- Anything that makes a hook able to block a command. All three hooks
  exit 0 on every error path by design; a broken reminder must never
  stop you working.
- Anything that widens where resolver commands may be read from. That
  boundary is the one thing standing between a config and arbitrary
  execution. See "Config is executable" in
  [logbook/README.md](logbook/README.md).

## Security

Do not open a public issue for a security problem. Email the address on
[the maintainer's GitHub profile](https://github.com/nikunjtrapasiya)
instead, with what you found and how to reproduce it.
