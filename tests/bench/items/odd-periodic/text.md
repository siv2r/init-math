# Proof: p(n) is odd for infinitely many n

Mod 2 the signs in Euler's pentagonal theorem vanish, so P(q) E(q) = 1 in F2[[q]], where
P(q) = sum p(n) q^n and E(q) = sum over all integers k of q^(k(3k-1)/2). The generalized
pentagonal numbers k(3k-1)/2 are distinct, so E has a coefficient 1 exactly at them, and
infinitely many coefficients 1. Suppose p(n) is even for every n > N. Then P(q) is congruent
mod 2 to a polynomial f(q) of degree at most N with f(0) = 1, and f(q) E(q) = 1 in F2[[q]].
So E = 1/f; d = deg f is at least 1, since f = 1 would give E = 1, which has no coefficient
at q^1. Comparing coefficients in f E = 1 gives, for n >= 1,
e_n = f_1 e_(n-1) + ... + f_d e_(n-d): the coefficients of E satisfy a linear recurrence of
order d over F2. Its state, the last d coefficients, takes at most 2^d values and f_d = 1
makes each step invertible, so the coefficients are periodic, with some period T. A periodic
sequence with infinitely many 1s has gaps of at most T between consecutive 1s. But the gaps
between consecutive generalized pentagonal numbers grow without bound, a contradiction. So
p(n) is odd for infinitely many n.
