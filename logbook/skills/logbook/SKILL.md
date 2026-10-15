---
name: logbook
description: >-
  How to use `logbook`, the cross-session record of open obligations across every checkout you work in. Invoke when a decision needs its why recorded, work is parked or blocked, a follow-up is deferred, a claim is made without evidence (test not run, deploy not confirmed), a deploy is triggered, a PR merges for a ticket with deploy history, or an obligation is met and needs closing. Also when a `logbook` write is refused with exit 2, 3, or 4.
---

# Cross-session ledger

`logbook` holds open obligations across every checkout you work in, keyed by
ticket or PR. Work switches between checkouts constantly, so anything left
open in one session must be recorded or it is lost.

## Write an entry, without being asked, at these moments

- a decision made that a cold reader would need the why for
- work parked or blocked
- a follow-up deliberately deferred inside the current ticket's scope
- a claim made without evidence: test not run, deploy not confirmed
- a deploy triggered
- a PR merged for a ticket that has deploy history

**The bar for every entry: would this hurt if lost.** Fails the bar, not an
entry.

**Never record** progress narration, step lists, or anything mirroring your
tracker's or your CI's own state. Those have owners. The ledger stores only
what none of them record.

## Writing

```
logbook add --kind K --text "what it is" [--ticket K] [--pr N] <the kind's own flag>
```

`--kind` and `--text` are always required. `--ticket` is inferred from the
branch when omitted; an entry with neither a ticket nor a `--pr` still
writes, but warns on stderr because it is hard to find later.

## Ticket-shaped work does not go here

Each kind requires a structural field. The table below is the shipped
default set; a site's config can add, remove, or rename kinds, so it is not
guaranteed to match what is actually active - run `logbook doctor` to see
the kinds in force.

| Kind | Required field |
|---|---|
| `parked` | `--resume` |
| `blocked` | `--unblocked-by` |
| `unverified` | `--verify` |
| `followup` | `--ticket` |
| `decision` | `--why` |
| `deploy` | `--stage --service --commit` |

If the item cannot name its field, it is a work unit: surface it to the user
as ticket-shaped and wait. Do not create the tracker ticket unprompted, and
do not retry the write under a different kind to get past the check.

| Exit code | Meaning |
|---|---|
| 1 | nothing matched, or `check` found open blockers |
| 2 | the shape check refused it |
| 3 | the ticket already has the cap's worth of open followups |
| 4 | config refused to load; run `logbook doctor` for why |

None of these is an error to route around. Each means stop and tell the
user.

## Close entries as work completes

Not only at close-out.

- `logbook resolve <id>` when the obligation is met
- `logbook drop <id> --note why` when it stopped mattering
- `logbook deploy-sync` closes deploy entries whose commit already shipped,
  but only where the site has configured a resolver for that stage. With no
  resolver configured, or with resolvers disabled, it closes nothing and
  says so. Read its output rather than assuming it resolved anything.
- `logbook retire` drops `decision` entries (and any other non-blocking
  kind the config names) whose ticket and PR are both closed, asking the
  site's configured `retire.ticket` and `retire.pr` resolvers. Run it when
  asked to review or prune the ledger, and `--dry-run` first when the
  count is large. It never touches a blocking kind: an obligation is
  closed by a person with `resolve` or `drop`, not by the tracker.
- When no `retire.ticket` resolver is configured but you have the tracker
  as an MCP tool, do the lookup yourself and hand the result in: collect
  the ticket keys from `logbook ls --kind decision --json`, ask the tracker
  once (`key in (...) AND statusCategory = Done`, or its equivalent), then
  `logbook retire --closed K,K,...`. Pass only keys the tracker actually
  returned as closed. A PR on the entry still needs its own verdict: the
  `retire.pr` resolver, or its number in `--closed` after `gh pr view`.

Writing without closing turns the session-start brief into wallpaper, and a
brief that gets skimmed past protects nothing.

## Reading

`logbook ls`, `logbook ls --ticket K`, `logbook ls --all`,
`logbook show <id|ticket>`, `logbook stale`, `logbook check --ticket K`.
