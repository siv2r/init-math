# Proof: a product of three positive definite matrices has real positive eigenvalues

The matrix ABC is in general not symmetric, so its eigenvalues have to be located by some
argument. For two factors this is the lemma quoted below: if P and Q are symmetric positive
definite, then PQ is diagonalizable with real positive eigenvalues (indeed PQ is similar, by
P^(1/2), to the symmetric positive definite matrix P^(1/2) Q P^(1/2)). We reduce the case of
three factors to that of two.

Apply the lemma to B and C: there are an invertible real matrix S and a diagonal matrix D with
positive diagonal entries such that BC = S D S^(-1). Then

  ABC = A S D S^(-1) = S (S^(-1) A S) D S^(-1),

so ABC is similar to A'D, where A' = S^(-1) A S. Now A' is similar to A, so it is
diagonalizable with the same eigenvalues as A, all of them positive; that is, A' is the
positive definite operator A written in the basis formed by the columns of S. The diagonal
matrix D, with positive diagonal entries, is positive definite as well. Applying the lemma to
the pair A', D, the product A'D is diagonalizable with real positive eigenvalues.

Since ABC is similar to A'D, it has the same eigenvalues, so every eigenvalue of ABC is real
and positive, consistent with det(ABC) = det A det B det C > 0.
