---
id: LNNN
target: QNNN          # QNNN | CNNN | work/<slug>#<brick-number> | lemma:<slug>
status: active        # active | set-aside | refuted | dormant | succeeded
status-since: YYYY-MM-DD
# Optional (bin/attempts new writes them):
# small-cases: informative   # informative | not-informative; overrides [field_profile] for this target
# budget: 6                  # worker returns or sessions; default [attempts] budget_returns
# moves: [toy-model]         # the moves this approach uses (bin/attempts --moves)
---
# LNNN: <the approach in one line>

## Why it looked promising
(Optional. One or two lines, written when the line starts, not reconstructed later.)

## Prediction
(Optional. What you expect to happen, and how likely: likely / even / unlikely.)

## Alternatives not chosen
(Optional. One line each, or "in parallel: LNNN".)

## Log
- YYYY-MM-DD: status → active: started
  (bin/attempts appends one dated entry per event: a worker return, a decision, a status
  change. Entries are never edited or deleted; a correction is a new entry.)

## Where it broke
(Required once set aside: the exact step — obstruction is to: method | this execution | unknown)

## What it established
(Partial lemmas, reductions, a parameter boundary, a counterexample; or "nothing".)

## Revive if
(Required once set aside: what new tool, lemma or representation would remove the obstruction.)

## Refuted statement
(Required when refuted: the precise statement that was disproved, and where.)

## At close
(Written at close with --contributed: the moves that actually helped, in hindsight.)
