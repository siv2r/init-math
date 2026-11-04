# Workflow journal

Notes on how the work is going — not on the mathematics. A reflection pass reads every
entry added since the last review boundary and decides what to fix
([reflection loop](../docs/discipline/reflection-loop.md)).

**Three kinds of record** (all written with `bin/journal --add <log> "<text>"`):
`journal` is this file, for prose notes and each pass's own record; `friction` is a one-line
row in `logs/friction.jsonl` for something that went badly or wasted effort; `feedback` is a
row in `logs/feedback.jsonl` for the owner's corrections, praise or a gate bypass.

**What goes here:** a note too long for one row of `logs/friction.jsonl` (what happened,
what it cost, what might prevent it), and each reflection pass's own record. Short friction
goes to `logs/friction.jsonl` instead, via `bin/journal --add friction "<one line>"`; don't
write the same thing in both places.

**Format:** one bullet per entry, appended at the end, never edited afterwards:

    - [YYYY-MM-DD] KIND: text

`KIND` is `NOTE` for an ordinary note, `REFLECT` for a reflection pass's record of what it
applied, proposed or was declined (an auto-applied fix carries the tag `[auto-applied]`), or
another short uppercase tag that a skill defines. Add entries with
`bin/journal --add journal "<text>" [--kind REFLECT]`.

**Review boundaries:** a line of the form `<!-- reviewed YYYY-MM-DD -->` marks the point up
to which a reflection pass has read. `bin/journal --mark-reviewed` inserts it; don't type it
by hand. `REFLECT` lines are the pass's own output and are never shown as new input.

<!-- entries start -->
