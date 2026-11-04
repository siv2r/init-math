# Proof

Fix a red/blue colouring of the edges of K_n. For a vertex v let r(v) and b(v) be the
numbers of red and blue edges at v, so r(v) + b(v) = n - 1.

Call an unordered pair of edges {vu, vw} with a common endpoint v an angle at v, and call it
mixed if its two edges have different colours. There are r(v) b(v) mixed angles at v. Every
angle {vu, vw} lies in exactly one triangle, namely uvw, and every triangle has three
angles, one at each of its vertices.

A monochromatic triangle has no mixed angle. A triangle that is not monochromatic has two
edges of one colour and one edge e of the other; its angle opposite e is not mixed, and its
two angles at the endpoints of e are mixed. So it has exactly two mixed angles. Counting
mixed angles by vertices and by triangles, the number N of non-monochromatic triangles
satisfies

  2N = sum over v of r(v) b(v).

Since r(v) + b(v) = n - 1, we have r(v) b(v) <= (n - 1)^2 / 4, so N <= n(n - 1)^2 / 8.
The number M of monochromatic triangles is therefore

  M = C(n, 3) - N >= n(n - 1)(n - 2)/6 - n(n - 1)^2/8
    = n(n - 1)(4(n - 2) - 3(n - 1))/24 = n(n - 1)(n - 5)/24.

For n <= 5 the bound is at most 0 and says nothing; for n = 6 it gives M >= 5/4, so every
two-colouring of K_6 has at least two monochromatic triangles, and for n = 7 it gives
M >= 7/2, so at least four.
