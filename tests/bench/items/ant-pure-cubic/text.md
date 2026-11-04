# Proof: 3 is totally ramified in Q(α), α^3 = 10

The polynomial f(x) = x^3 − 10 is irreducible over Q by Eisenstein's criterion at 5, so
[K : Q] = 3 and f is the minimal polynomial of α. Its discriminant is −27 · 10^2 = −2700,
since a polynomial x^3 + a has discriminant −27a^2.

We first identify O_K. Since 10 = 2 · 5 is squarefree, the description of the ring of integers
of a pure cubic field quoted below gives O_K = Z[α]. Thus 1, α, α^2 is an integral basis, and
d_K = disc(f) = −2700 = −2^2 · 3^3 · 5^2. In particular 3 divides d_K, so 3 ramifies in K,
and it remains to determine how.

Because [O_K : Z[α]] = 1, the Dedekind–Kummer theorem applies to every prime, in particular to
p = 3. Reduce f modulo 3: we have 10 ≡ 1 (mod 3), and

  (x − 1)^3 = x^3 − 3x^2 + 3x − 1 ≡ x^3 − 1 (mod 3),

so f(x) ≡ (x − 1)^3 (mod 3), with x − 1 irreducible of degree 1. By Dedekind–Kummer,

  3O_K = P^3,  P = (3, α − 1),  N(P) = 3^1 = 3.

So 3 is totally ramified in K, with residue degree 1. The ramification is wild, as the index
e = 3 equals the residue characteristic; this is consistent with the exponent of 3 in d_K,
which is 3, since a wildly ramified prime of index e and residue degree 1 contributes an
exponent of at least e to the discriminant.
