# Proof: the least primitive root modulo p lifts to every power of p

Let g be the least positive primitive root modulo p. It exists because (Z/pZ)^× is cyclic,
and 1 < g < p. The case k = 1 holds by the choice of g.

Step 1: g is a primitive root modulo p^2. The order of g modulo p^2 is a multiple of its order
modulo p, which is p − 1, and it divides φ(p^2) = p(p − 1); so it is p − 1 or p(p − 1). It is
p(p − 1) as soon as g^(p−1) ≢ 1 (mod p^2), and for a primitive root g modulo p with 1 < g < p
this is the standard lifting step. So g^(p−1) = 1 + pt with p ∤ t, and g is a primitive root
modulo p^2.

Step 2: for every k ≥ 2, g^(p^(k−2)(p−1)) = 1 + p^(k−1) t_k with p ∤ t_k. For k = 2 this is
Step 1, with t_2 = t. Suppose it holds for k and raise to the p-th power:

  (1 + p^(k−1) t_k)^p = 1 + p^k t_k + C(p,2) p^(2k−2) t_k^2 + ... + p^(p(k−1)) t_k^p.

The term with C(p,2) is divisible by p^(2k−1), as p divides C(p,2), and 2k − 1 ≥ k + 1. For
2 < j < p the j-th term is divisible by p^(1 + j(k−1)), and the last term by p^(p(k−1)); both
exponents are at least 3(k − 1) ≥ k + 1, since p ≥ 3 and k ≥ 2. Hence
g^(p^(k−1)(p−1)) = 1 + p^k t_(k+1) with t_(k+1) ≡ t_k ≢ 0 (mod p), which is the claim for k + 1.

Step 3: let k ≥ 2. The order of g modulo p^k is a multiple of p − 1 and divides
φ(p^k) = p^(k−1)(p − 1), so it equals p^j (p − 1) for some j ≤ k − 1. If j ≤ k − 2, then
g^(p^(k−2)(p−1)) ≡ 1 (mod p^k), contradicting Step 2. So j = k − 1, and g is a primitive root
modulo p^k.
