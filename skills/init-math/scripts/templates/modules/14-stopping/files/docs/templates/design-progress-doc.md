# Design: <one-line statement of what is being built or proved>

<!--
Use this as the README.md of the effort's work folder (`work/<slug>/README.md`), keeping
the status header of `work/TEMPLATE/README.md`, and fill it in. Use it when work
enters a multi-step design or proof-construction phase, especially an unattended one: the
deliberate design IS the work, so open this doc and proceed rather than stopping to report.
Keep RESUME HERE and the PROGRESS LOG current at every checkpoint, so that a session that
is reset or interrupted resumes from this file alone.
Anti-scope: a bounded one-brick fix does not need this doc; just do it.
Delete this comment once filled.
-->

**Restart marker:** this document is the living design and progress log for <the goal>.
If a session restarts, read **RESUME HERE** first, then `git log --oneline -25` for the
latest landed pieces.

## ▶ RESUME HERE (updated <date>; <"paused at ..." if paused>)

<!-- The exact next step, precise enough that a fresh agent continues without re-deriving
     anything. Keep it short and self-contained: the current target and the few file:line
     pointers needed. Move history down into the PROGRESS LOG; a long RESUME HERE defeats
     its purpose. -->

- **State:** <what is landed and committed; what the problem has been reduced to so far>
- **Next step:** <the precise next brick: target, approach, the lemmas, tools or files it uses>
- **Gotchas already found:** <false starts and non-obvious constraints, so nobody hits them again>

## 0. Where we are

<!-- What the whole problem has been reduced to, and what remains open. -->

## 1. The design / plan

<!-- The route: the steps, each with its approach, the key facts it relies on, and which
     are landed and which are open. Record CORRECTIONS here when the plan changes, so this
     stays the source of truth. Carry a hard step as an explicit hypothesis and finish the
     work around it (reduce before reporting blocked). -->

## Remaining bricks

1. <brick: a stateable next step, with its finish line>
2. <...>

## PROGRESS LOG (append every checkpoint; newest last)

<!-- One dated entry per checkpoint: what landed (with the commit or file), what an
     attempt found, a CORRECTION when the plan changed, and on a pause an entry pointing
     back to RESUME HERE. -->

- <YYYY-MM-DD>: design written; <initial state>. Starting <first step>.
