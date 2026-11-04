# Proof

For a uniformly random permutation of {1, ..., n} let C_k = C_k(n) be its number of cycles
of length k, and let m = floor(n/3). Then p_n = P(C_1 = C_2 = ... = C_m = 0).

Factorial moments. For nonnegative integers r_1, ..., r_m with r_1 + 2r_2 + ... + m r_m <= n,

  E[(C_1)_(r_1) (C_2)_(r_2) ... (C_m)_(r_m)] = product over k <= m of k^(-r_k),

where (c)_r = c(c - 1)...(c - r + 1). These are exactly the factorial moments of a vector
(Z_1, ..., Z_m) of independent Poisson variables with E[Z_k] = 1/k. For fixed m, letting
n -> infinity, all factorial moments eventually agree, and (C_1, ..., C_m) converges in
distribution to (Z_1, ..., Z_m); in particular

  P(C_1 = ... = C_m = 0) -> P(Z_1 = ... = Z_m = 0) = exp(-(1 + 1/2 + ... + 1/m)) = e^(-H_m).

Uniformity in m. We need this with m = floor(n/3), which grows with n. Expanding the event
{C_1 = ... = C_m = 0} by inclusion and exclusion, its probability is an alternating sum of
the factorial moments above, and e^(-H_m) is the same alternating sum for the Poisson
vector. When m <= n/3, every r with r_1 + ... + r_m <= 3 satisfies r_1 + 2r_2 + ... + m r_m
<= 3m <= n, so the two expansions agree term by term through the third order. The standard
Bonferroni argument then shows that p_n = e^(-H_m)(1 + o(1)) uniformly for m <= n/3: the
cycles of length up to a fixed fraction of n are, for this purpose, asymptotically
independent Poisson variables, which is the familiar small-cycle heuristic made exact.

Conclusion. Since H_m = log m + gamma + O(1/m), we have e^(-H_m) = e^(-gamma) (1 + O(1/m)) / m.
With m = floor(n/3) we have n/m -> 3, so

  n p_n = (n/m) e^(-gamma) (1 + o(1)) -> 3 e^(-gamma).

As a check, a direct count for n = 100 gives 100 p_100 = 1.6856..., against
3 e^(-gamma) = 1.6844....
