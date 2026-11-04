# Proof: a finite group with a fixed-point-free automorphism of order 3 is abelian

Write σ^2 for σ∘σ, so σ^3 = id, σ^(-1) = σ^2, and σ(x) = x only for x = 1.

First, the map x ↦ x^(-1)σ(x) is injective: if x^(-1)σ(x) = y^(-1)σ(y), then
yx^(-1) = σ(y)σ(x)^(-1) = σ(yx^(-1)), so yx^(-1) is fixed by σ and y = x. As G is finite,
the map is a bijection, and every g in G can be written g = x^(-1)σ(x) for some x.

For such g, g σ(g) σ^2(g) = x^(-1)σ(x) · σ(x)^(-1)σ^2(x) · σ^2(x)^(-1)σ^3(x) = x^(-1)x = 1. So

  (1)  g σ(g) σ^2(g) = 1  for every g in G.

Applying σ to (1) gives σ(g) σ^2(g) g = 1. Applying (1) to g^(-1) and taking inverses gives
σ^2(g) σ(g) g = 1. Comparing the two, σ(g)σ^2(g) = σ^2(g)σ(g), and applying σ^2 to this,

  (2)  g σ(g) = σ(g) g  for every g in G.

Together with (1), which gives σ^2(g) = (gσ(g))^(-1), this shows that g, σ(g) and σ^2(g)
pairwise commute; in particular σ(g) = g^(-1)σ^2(g)^(-1) for every g.

Now let g, h be elements of G and apply (2) to the product gh:

  g h σ(g) σ(h) = σ(g) σ(h) g h.

Rewriting σ(g) and σ(h) on both sides by σ(g) = g^(-1)σ^2(g)^(-1) and
σ(h) = h^(-1)σ^2(h)^(-1), and cancelling, this reduces to h σ(g) = σ(g) h.

Since σ is a bijection of G, σ(g) runs over all of G as g does. So h commutes with every
element of G, and as h was arbitrary, G is abelian.
