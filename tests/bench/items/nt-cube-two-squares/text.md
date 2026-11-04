# Proof: odd prime factors of z in x^2 + y^2 = z^3 are 1 mod 4

The equation x^2 + y^2 = z^3 is invariant under the weighted scaling
(x, y, z) ↦ (t^3 x, t^3 y, t^2 z) for every positive integer t, so after removing common
factors it suffices to treat solutions with gcd(x, y) = 1. We assume this from now on.

Let q be an odd prime dividing z. Then q divides z^3 = x^2 + y^2. If q divided x, it would
divide y^2 = z^3 − x^2 and hence y, contradicting gcd(x, y) = 1. So q does not divide x, and
in the same way q does not divide y.

Let u be an inverse of x modulo q, and put w = uy. Multiplying the congruence
x^2 + y^2 ≡ 0 (mod q) by u^2 gives

  w^2 ≡ −1 (mod q).

Since q is odd, −1 ≢ 1 (mod q), so w^2 is not the identity of the group (Z/qZ)^×, while
w^4 ≡ 1 (mod q). Hence w has order exactly 4 in (Z/qZ)^×, a group of order q − 1, and by
Lagrange's theorem 4 divides q − 1. That is, q ≡ 1 (mod 4).

As q was an arbitrary odd prime factor of z, every odd prime factor of z is congruent to 1
modulo 4.
