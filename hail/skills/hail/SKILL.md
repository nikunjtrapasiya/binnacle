---
name: hail
description: >-
  How to use `hail` to find a past Claude Code session and rejoin it.
  Invoke when the user refers to a past session, a decision made
  "yesterday" or "last time", work started in another checkout, or a
  ticket that has history you were not there for.
---

# Finding a past session

`hail` searches an index of your Claude Code transcripts, kept current
by its own hook. Reach for it instead of asking the user to
re-describe work that already happened:

- "what did we decide about X" / "what did I say last time"
- a ticket that clearly has history, and you were not in that session
- work that started in another checkout or another branch
- "the session where I was debugging Y"

## Read only. Never build.

```
hail find <query>      ticket, title, branch, cwd, prompt, or PR
hail ls                most recent sessions
hail show <id-prefix>  one session in full, including how to rejoin it
```

The prefix must be at least six characters, and must match exactly one
session - a shorter or ambiguous prefix exits 2 and lists the
candidates. Take the prefix from an `ls` or `find` line, which prints
eight.

`hail` is a read tool here. Run `find` or `ls`, never `hail index` - the
`SessionStart` hook already keeps the index current, and running the
build yourself is not something an agent should ever need to do.

If there is no index yet, `find` and `ls` say so and exit 1. Tell the
user, and let them run `hail index` themselves rather than running it
for them.

`find` with no result is not proof the work never happened - the index
only covers `index.days` days back, and only what the transcript format
still yields (see the README's "transcript format is not an interface"
section). Say so rather than concluding the session never existed.
