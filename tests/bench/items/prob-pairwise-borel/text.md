# Proof

Write p_k = P(A_k), let N_n = 1_{A_1} + ... + 1_{A_n} be the number of the first n events
that occur, and let N = lim N_n, the total number of events that occur (an increasing limit,
possibly infinite). Put mu_n = E[N_n] = p_1 + ... + p_n, so mu_n increases to infinity.

Variance of N_n. For j != k, pairwise independence gives
E[1_{A_j} 1_{A_k}] = P(A_j and A_k) = p_j p_k, so the indicators are uncorrelated and the
variance of their sum is the sum of their variances:

  Var(N_n) = sum over k <= n of p_k(1 - p_k) <= mu_n.

Only pairs of events enter a variance, which is why pairwise independence suffices here.

Concentration. For n with mu_n > 0, Chebyshev's inequality gives

  P(N_n <= mu_n / 2) <= P(|N_n - mu_n| >= mu_n / 2) <= 4 Var(N_n) / mu_n^2 <= 4 / mu_n.

Conclusion. Fix an integer M >= 0. Since N_n <= N, the event {N <= M} is contained in
{N_n <= M} for every n. Choose n so large that mu_n >= 2M and mu_n > 0; then
{N_n <= M} is contained in {N_n <= mu_n / 2}, and so

  P(N <= M) <= 4 / mu_n.

The left side does not depend on n and the right side tends to 0, so P(N <= M) = 0.
Taking the union over M = 0, 1, 2, ..., P(N < infinity) = 0. Thus N = infinity almost
surely: infinitely many of the A_n occur.
