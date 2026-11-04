#!/usr/bin/env python3
"""Experiment driver: a working example of the contract with bin/exp-run. Replace the
example computation with yours; keep the contract.

Contract
  env EXP_TIER   smoke | full | deep   how big a sweep to do (smoke must take seconds)
  env EXP_OUT    the run bundle directory; write result.json (and any data files) there
  result.json    REQUIRED fields:
                   verdict             PASS | FAIL | INCONCLUSIVE (say which budget ran out)
                   params              everything needed to reproduce: ranges, sizes, seeds
                   known_answer_check  the outcome of re-computing a case whose answer is
                                       known independently of this code
                 anything else is free-form (counts, the counterexample, timings).
Print progress to stdout; bin/exp-run saves it as output.txt in the bundle.

The example: test "every even n with 4 <= n <= N is a sum of two primes" up to a
tier-dependent N. Swap in your own question; keep the structure (hard corners first, a
known-answer check, a three-valued verdict, the parameters recorded).
"""
import json
import os
import time
from pathlib import Path

TIER = os.environ.get("EXP_TIER", "smoke")
OUT = Path(os.environ.get("EXP_OUT", "."))
SIZES = {"smoke": 2_000, "full": 2_000_000, "deep": 50_000_000}
N = SIZES[TIER]


def primes_upto(n):
    sieve = bytearray([1]) * (n + 1)
    sieve[:2] = b"\x00\x00"
    for p in range(2, int(n ** 0.5) + 1):
        if sieve[p]:
            sieve[p * p::p] = bytearray(len(sieve[p * p::p]))
    return sieve


def first_failure(n_max, sieve):
    """Smallest even n in [4, n_max] that is NOT a sum of two primes, or None."""
    plist = [p for p in range(2, n_max + 1) if sieve[p]]
    for n in range(4, n_max + 1, 2):
        if not any(sieve[n - p] for p in plist if p <= n // 2):
            return n
    return None


def main():
    t0 = time.time()
    sieve = primes_upto(N)

    # Known-answer check: a value known independently of this code (pi(1000) = 168).
    pi_1000 = sum(sieve[:1001]) if N >= 1000 else None
    known = "pass" if pi_1000 == 168 else f"FAIL: pi(1000) computed as {pi_1000}, expected 168"

    # Hard corners first: the smallest cases, where off-by-one errors live.
    corners = {n: first_failure(n, sieve) is None for n in (4, 6, 8)}
    print("corners", corners, flush=True)

    bad = first_failure(N, sieve) if all(corners.values()) else min(n for n, ok in corners.items() if not ok)
    verdict = "FAIL" if bad is not None else "PASS"
    if known != "pass":
        verdict = "INCONCLUSIVE"  # the instrument failed its own check; the sweep proves nothing
    result = {
        "verdict": verdict,
        "params": {"tier": TIER, "N": N, "claim": "every even 4 <= n <= N is a sum of two primes"},
        "known_answer_check": known,
        "first_counterexample": bad,
        "seconds": round(time.time() - t0, 2),
    }
    (OUT / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print("verdict", verdict, flush=True)


if __name__ == "__main__":
    main()
