# Proof: x^2 + 2 = y^3 only for x = ±5, y = 3

Let x, y be integers with x^2 + 2 = y^3; then y^3 ≥ 2, so y ≥ 2. First, x is odd: if x were
even, then x^2 + 2 ≡ 2 (mod 4), so y^3 would be even, hence divisible by 8, which is
incompatible with y^3 ≡ 2 (mod 4).

Work in R = Z[√−2], a unique factorization domain, with norm N(a + b√−2) = a^2 + 2b^2. Its
units are the elements of norm 1, that is ±1, and both are cubes. In R,

  (x + √−2)(x − √−2) = y^3.

The two factors are coprime. A common prime factor π divides their difference
2√−2 = −(√−2)^3; and √−2 is prime in R, since its norm 2 is a rational prime, so π is
associate to √−2. Then √−2 divides x + √−2, hence divides x, and taking norms, 2 divides
x^2, contradicting that x is odd.

In a unique factorization domain, if two coprime elements have a product that is a cube, each
is a unit times a cube (compare the exponents of each prime). As the units are cubes,
x + √−2 = (a + b√−2)^3 for some integers a, b. Expanding,

  (a + b√−2)^3 = (a^3 − 6ab^2) + (3a^2 b − 2b^3)√−2,

so x = a^3 − 6ab^2 and 1 = b(3a^2 − 2b^2). Hence b = ±1. If b = −1, then 3a^2 − 2 = −1,
which has no integer solution. If b = 1, then 3a^2 − 2 = 1, so a = ±1, and
x = a^3 − 6a = ∓5. Taking norms, y^3 = N(x + √−2) = N(a + b√−2)^3, so y = a^2 + 2b^2 = 3.
Conversely 25 + 2 = 27 = 3^3, so (±5, 3) are solutions, and they are the only ones.
