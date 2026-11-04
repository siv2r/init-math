# Proof

For A a subset of X write N(A) for the set of neighbours of A in Y. If X is finite the claim
is Hall's theorem, so assume X is infinite and enumerate it as x_1, x_2, x_3, ....

For n >= 1 let X_n = {x_1, ..., x_n}, and let V_n be the set of matchings covering X_n and
no other vertex of X; equivalently, V_n is the set of injective maps phi from X_n to Y with
phi(x_i) in N(x_i) for each i <= n. Let V_0 consist of the single empty map.

Each V_n is nonempty. The sets N(x_1), ..., N(x_n) are finitely many subsets of Y, and for
every I contained in {1, ..., n} their union over I is N({x_i : i in I}), which has at least
|I| elements by hypothesis. By Hall's theorem for finitely many sets these sets have a system
of distinct representatives, which is exactly an element of V_n.

Now build a graph H whose vertex set is the disjoint union of V_0, V_1, V_2, ..., joining
each phi in V_n (n >= 1) to its restriction phi|X_(n-1), which lies in V_(n-1): a matching
of X_(n-1) obtained by forgetting the partner of x_n. Thus every vertex of V_n with n >= 1
has a neighbour in V_(n-1). By König's infinity lemma, H contains a ray
phi_0 phi_1 phi_2 ... with phi_n in V_n for all n.

Along the ray, consecutive maps are joined in H, and the only edges between V_n and
V_(n-1) join a map to its restriction; so phi_(n-1) is the restriction of phi_n, and the maps
extend one another. Define phi on X by phi(x_i) = phi_i(x_i) = phi_n(x_i) for any n >= i.
Then phi(x) is in N(x) for every x in X, and phi is injective, since any two vertices x_i,
x_j of X lie in a common X_n and phi_n is injective. The edges x phi(x), for x in X, form a
matching of G covering X.
