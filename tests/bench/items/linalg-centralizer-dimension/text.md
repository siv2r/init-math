# Proof: the centralizer of an n x n complex matrix has dimension at least n

Let L_A : M_n(C) → M_n(C) be the linear map L_A(X) = AX − XA. The matrices commuting with A
form ker L_A, so the claim is that rank L_A ≤ n^2 − n for every A.

Suppose first that A has n distinct eigenvalues. Its minimal polynomial has each of them as a
root, so it has degree n, and therefore I, A, ..., A^(n−1) are linearly independent. All of
them commute with A, so dim ker L_A ≥ n.

For general A we use a closure argument rather than a normal form. In the basis of matrix
units E_ij, L_A is given by an n^2 x n^2 matrix whose entries are linear in the entries of A.
The condition rank L_A ≤ n^2 − n says that every minor of size n^2 − n + 1 of this matrix
vanishes, and each such minor is a polynomial in the entries of A. So the set

  Z = { A : rank L_A ≤ n^2 − n }

is closed in M_n(C) = C^(n^2).

On the other hand, A has n distinct eigenvalues exactly when the discriminant of its
characteristic polynomial is nonzero. This discriminant is a polynomial Δ in the entries of
A, and it is not identically zero, as Δ(diag(1, 2, ..., n)) ≠ 0. A polynomial that vanishes on
a nonempty open subset of C^(n^2) is identically zero, so the set {Δ ≠ 0} is dense in
M_n(C). By the second paragraph it is contained in Z, and Z is closed, so Z = M_n(C).

Hence dim ker L_A ≥ n for every A. (The bound is attained, e.g. by a single Jordan block,
whose centralizer consists of the polynomials in it.)
