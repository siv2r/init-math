# Proof

Write S = a^3 + b^3 + c^3, P = a^2 b + b^2 c + c^2 a, Q = a b^2 + b c^2 + c a^2 and
D(a, b, c) = 2S + 5P - 7Q. We show D >= 0 whenever a, b, c >= 0.

Each of S, P and Q is unchanged when (a, b, c) is replaced by (b, c, a), so D is invariant
under relabelling the variables cyclically, and we may assume a >= b >= c >= 0.

First, D changes in a simple way when the same amount t is added to all three variables.
Differentiating along the direction (1, 1, 1),

  d/dt S(a+t, b+t, c+t) = 3(a^2 + b^2 + c^2),
  d/dt P(a+t, b+t, c+t) = d/dt Q(a+t, b+t, c+t) = a^2 + b^2 + c^2 + 2(ab + bc + ca),

so d/dt D(a+t, b+t, c+t) = 4(a^2 + b^2 + c^2) - 4(ab + bc + ca)
= 2((a - b)^2 + (b - c)^2 + (c - a)^2). This depends only on the differences, which do
not change with t, so D(a+t, b+t, c+t) is linear in t. Taking t = -c,

  D(a, b, c) = D(a - c, b - c, 0) + 2c((a - b)^2 + (b - c)^2 + (c - a)^2).

The second term is nonnegative. For the first, put x = a - b >= 0 and y = b - c >= 0, so
that (a - c, b - c, 0) = (x + y, y, 0). With the third variable zero, P and Q reduce to one
term each, and

  D(x + y, y, 0) = 2(x + y)^3 + 2y^3 + 5(x + y)^2 y - 7(x + y) y^2
                 = 2x^3 + 11x^2 y + 9x y^2 + 2y^3,

a polynomial with nonnegative coefficients in x, y >= 0. Hence D(a, b, c) >= 0. Combining,

  D(a, b, c) = 4c(x^2 + xy + y^2) + 2x^3 + 11x^2 y + 9x y^2 + 2y^3,

which vanishes only when x = y = 0, i.e. at a = b = c, where indeed
D(1, 1, 1) = 6 + 15 - 21 = 0. This proves the inequality.
