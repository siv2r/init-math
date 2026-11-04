# Proof: the splitting field of x^n − 2 has degree n·φ(n)

Let α = 2^(1/n) be the positive real n-th root of 2 and ζ = e^(2πi/n). The roots of x^n − 2
are the numbers ζ^j α, 0 ≤ j < n, so the splitting field is L = Q(α, ζ). By Eisenstein's
criterion at 2, x^n − 2 is irreducible, so [Q(α) : Q] = n; and [Q(ζ) : Q] = φ(n) by the
irreducibility of the cyclotomic polynomial. Since Q(ζ)/Q is Galois, the compositum formula
quoted below gives

  [L : Q] = n · φ(n) / [F : Q],  where F = Q(α) ∩ Q(ζ).

So it suffices to show F = Q. Two facts about F: it is Galois over Q, being a subfield of the
abelian extension Q(ζ)/Q; and it is real, being a subfield of Q(α) ⊂ R.

Let d = [F : Q]; then d divides n, and m = n/d = [Q(α) : F]. The minimal polynomial h of α
over F divides x^n − 2, so its roots are m of the numbers ζ^j α, and its constant term is
(−1)^m ζ^s α^m for some integer s. This constant term lies in F ⊂ R, and α^m > 0, so ζ^s is a
real root of unity, ζ^s = ±1, and α^m lies in F. But α^m = 2^(1/d) has degree d over Q,
again by Eisenstein, so Q(2^(1/d)) ⊆ F with equal degrees, that is, F = Q(2^(1/d)).

Since F is Galois over Q and contains the root 2^(1/d) of the irreducible polynomial x^d − 2,
it contains all its roots, in particular ζ_d · 2^(1/d), where ζ_d = e^(2πi/d). As F is real,
ζ_d is real, which forces d = 1. Hence F = Q, and [L : Q] = n · φ(n).
