---
name: chartroom
description: >-
  How to use `chartroom` to build one page joining open obligations to
  the sessions that worked them. Invoke when the user asks what is
  outstanding across their work, what state a ticket or PR is in, where
  something was last touched, or wants a handover view.
---

# The page over logbook and hail

`chartroom` reads `logbook` and `hail` and writes one HTML file: two
panes, what is still owed on the left grouped by work item, the
sessions that worked it on the right.

Reach for it when the question spans both:

- "what is outstanding" / "what am I in the middle of"
- "where was this last worked on"
- handover, standup, or picking work back up after a gap

For one ticket, `logbook show <ticket>` is faster and prints in the
terminal. For one session, `hail find`. `chartroom` is for the view
across everything.

## Build it, then hand over the path

```
chartroom build     write the page, print its path, do not open
chartroom doctor    the config in force, and what is wrong
```

Use `build`, not bare `chartroom`. Bare `chartroom` opens a browser,
which is the user's call to make, not yours. Print the path and let
them open it.

**Never start `chartroom serve` on your own.** It holds a socket until
somebody stops it, so it is the user's to start, in their own terminal,
having read what it opens. Suggest it when they say the page keeps
going stale; do not run it for them.

**Never read the page back to answer a question.** It is a rendering of
`logbook ls --json` and `hail ls --json`, and those are what to read
when you need the data yourself. Parsing HTML to recover JSON you could
have asked for is the wrong direction.

## What it cannot tell you

- **Only what hail still has.** Sessions age out at `index.days`, and
  an obligation can name no session simply because the session rolled
  off. A work item says `N aged off`, where `N` counts its open
  obligations whose recorded session is no longer in hail's index - not
  distinct sessions, and not only ones that aged out; a session hail
  never indexed counts the same. Do not read it as work nobody ever
  did.
- **Not everything open.** By default the page shows only what blocks:
  a work item with no open obligation is not rendered, and obligations
  of a kind logbook marks non-blocking - `decision`, by default - sit
  in a closed `on record` disclosure rather than the left pane. The
  masthead states both counts. So "nothing on the page" means nothing
  blocking, never an empty ledger; `logbook ls --all` is the full
  list.
- **It resumes nothing.** The page hands over a `cd ... && claude -r
  ...` line. A browser cannot drive a terminal, and neither can you
  from the page.
- **It decides nothing.** Severity, staleness and the window are
  logbook's and hail's numbers. If one looks wrong, the fix is in the
  tool that owns the number, not here.

If `chartroom` exits 4, read the message before repeating it: it means
the config would not load, or a sibling is missing, too old, or could
not answer `ls --json` - most often no hail index yet, fixed by
`hail index`. The message names which and what fixes it. Tell the user;
do not install or upgrade plugins for them.
