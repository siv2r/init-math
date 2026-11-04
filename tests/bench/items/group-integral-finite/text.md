# Proof: finite subgroups of GL_n(Z) embed in GL_n(F_3)

Reduction of entries modulo 3 gives a group homomorphism π : GL_n(Z) → GL_n(F_3); its image
lies in GL_n(F_3) because det A = ±1 reduces to a nonzero element of F_3. We show that the
kernel of π contains no element of finite order other than I. Then for a finite subgroup G
of GL_n(Z), G ∩ ker π is trivial, π is injective on G, and G ≅ π(G) ≤ GL_n(F_3).

Suppose A ≠ I lies in ker π and has finite order m. Pick a prime q dividing m; then A^(m/q)
lies in ker π and has order q, so we may assume A has prime order q. As A ≡ I (mod 3) and
A ≠ I, there is a largest k ≥ 1 with A ≡ I (mod 3^k), and we write A = I + 3^k B with B an
integer matrix, B ≢ 0 (mod 3). Since I and B commute, the binomial theorem gives

  0 = A^q − I = q 3^k B + C(q,2) 3^(2k) B^2 + ... + 3^(qk) B^q.

If q ≠ 3: every term after the first is divisible by 3^(2k), hence by 3^(k+1), so
q 3^k B ≡ 0 (mod 3^(k+1)), i.e. qB ≡ 0 (mod 3); as 3 does not divide q, B ≡ 0 (mod 3), a
contradiction.

If q = 3: 0 = 3^(k+1) B + 3^(2k+1) B^2 + 3^(3k) B^3. Since k ≥ 1 we have 2k + 1 ≥ k + 2 and
3k ≥ k + 2, so 3^(k+1) B ≡ 0 (mod 3^(k+2)), i.e. B ≡ 0 (mod 3), again a contradiction.

So π is injective on finite subgroups. Finally, |GL_n(F_3)| is the number of ordered bases of
F_3^n, which is (3^n − 1)(3^n − 3)···(3^n − 3^(n−1)), and by Lagrange's theorem the order of
π(G) ≅ G divides it. (Reduction modulo 2 would not do: −I lies in its kernel; the case q = 2,
k = 1 is exactly where the estimate above breaks down for the prime 2.)
