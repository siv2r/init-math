# Proof

Let G be connected, k-regular, with an even number of vertices. For S a subset of V(G) write
o(G - S) for the number of components of G - S with an odd number of vertices. By Tutte's
theorem it suffices to show that o(G - S) <= |S| for every S.

The case S empty. G itself is connected and has an even number of vertices, so it has no
odd component: o(G) = 0.

The case S nonempty. Let C be an odd component of G - S. Every edge with exactly one end in
C has its other end in S, since C is a component of G - S. Write e(C) for the number of edges
with both ends in C and e(C, S) for the number of edges between C and S. Summing degrees over
the vertices of C,

  k|C| = 2 e(C) + e(C, S).

As G is simple, e(C) <= |C|(|C| - 1)/2, and therefore

  e(C, S) >= k|C| - |C|(|C| - 1) = |C|(k + 1 - |C|).

The right side is a concave function of |C| taking the value k at |C| = 1 and at |C| = k,
so e(C, S) >= k: every odd component of G - S sends at least k edges to S.

The edges counted for different odd components are different, and each of them has an end
in S. Since every vertex of S has degree k,

  k o(G - S) <= sum over odd components C of e(C, S) <= sum over v in S of deg(v) = k|S|.

Dividing by k gives o(G - S) <= |S|. Tutte's condition holds for every S, so G has a perfect
matching. (For k = 1 and k = 2 this is the familiar fact that K_2 and the even cycles have
perfect matchings; the content is in k >= 3.)
