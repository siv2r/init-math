# Proof: a ring with finitely many primes, all maximal, and nilpotent nilradical is Artinian

Let m_1, ..., m_r be the prime ideals of R, all of them maximal, and let N be the nilradical,
with N^t = 0. Since N is the intersection of all prime ideals, N = m_1 ∩ ... ∩ m_r. Distinct
maximal ideals are pairwise comaximal, so by the Chinese remainder theorem

  R/N ≅ R/m_1 × ... × R/m_r = k_1 × ... × k_r,

a finite product of fields.

Consider the chain of ideals R = N^0 ⊇ N^1 ⊇ ... ⊇ N^t = 0, and its quotients
Q_j = N^j / N^(j+1) for 0 ≤ j < t. Each Q_j is an R-module annihilated by N, hence a module
over R/N, and its R-submodules are exactly its R/N-submodules. Let e_1, ..., e_r be the
idempotents of k_1 × ... × k_r corresponding to the factors. Then

  Q_j = e_1 Q_j ⊕ ... ⊕ e_r Q_j,

and e_i Q_j is a vector space over k_i whose R-submodules are its k_i-subspaces. So Q_j is a
semisimple module, a direct sum of copies of the simple modules k_1, ..., k_r, and therefore
has finite length as an R-module.

Length is additive along the short exact sequences 0 → N^(j+1) → N^j → Q_j → 0. By
descending induction on j, starting from N^t = 0, each N^j has finite length, and in
particular R = N^0 has finite length ℓ(R) = ℓ(Q_0) + ... + ℓ(Q_(t−1)) as a module over
itself. A module of finite length ℓ satisfies the descending chain condition on submodules,
since a strictly descending chain of submodules has at most ℓ + 1 terms. The submodules of R
are its ideals, so every descending chain of ideals of R stabilizes: R is Artinian.
