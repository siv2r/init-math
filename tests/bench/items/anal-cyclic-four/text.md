# Proof

Let L(a, b, c) = a^2 b + b^2 c + c^2 a + abc. The constraint and L are both unchanged by the
cyclic relabelling (a, b, c) -> (b, c, a). The three cyclic relabellings of a triple place
each of its three entries in the second position exactly once, so one of them puts a median
value of {a, b, c} in the second position. We may therefore assume that b lies between a and
c, that is,

  (b - a)(b - c) <= 0.

(Only cyclic relabellings are used; L is not symmetric, and no transposition is needed.)

Now compare L with b(a + c)^2 = a^2 b + 2abc + b c^2:

  L - b(a + c)^2 = b^2 c + c^2 a - abc - b c^2 = c(b^2 - ab - bc + ca) = c(b - a)(b - c).

Since c >= 0 and (b - a)(b - c) <= 0, we get L <= b(a + c)^2 = b(3 - b)^2.

It remains to bound g(b) = b(3 - b)^2 for 0 <= b <= 3:

  4 - g(b) = 4 - 9b + 6b^2 - b^3 = (1 - b)^2 (4 - b) >= 0.

Hence L <= 4. Equality forces b = 1 and c(b - a)(b - c) = 0: either c = 0, giving
(a, b, c) = (2, 1, 0), or b = a or b = c, giving (1, 1, 1). So, up to cyclic relabelling,
equality holds exactly at (1, 1, 1) and (2, 1, 0); the second shows that the bound cannot be
improved even when one variable is zero.
