# Proof: p(n) is odd for infinitely many n

Mod 2 the signs in Euler's pentagonal theorem vanish, so P(q) E(q) = 1 in F2[[q]], where
P(q) = sum p(n) q^n and E(q) = sum over all integers k of q^(k(3k-1)/2). The generalized
pentagonal numbers k(3k-1)/2 are distinct, so E has a coefficient 1 exactly at them, and
infinitely many coefficients 1. Suppose p(n) is even for every n > N. Then P(q) is congruent
mod 2 to a polynomial f(q) of degree at most N with f(0) = 1, and f(q) E(q) = 1 in F2[[q]].
Now F2[q] is saturated in F2[[q]]: if a nonzero polynomial times a power series is a
polynomial, the power series is itself a polynomial (compare the coefficients above the
degree of the product). Since f E = 1 is a polynomial and f is nonzero, E is a polynomial.
But E has infinitely many nonzero coefficients, a contradiction. So p(n) is odd for
infinitely many n.
