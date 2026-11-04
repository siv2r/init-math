# Proof

Each X_i has mean 0 and E[X_i^2] = 1, and for i != j pairwise independence gives
E[X_i X_j] = E[X_i] E[X_j] = 0. Hence E[S^2] = n: S has the same variance as a sum of n
independent signs, and the bound to be proved is the matching sub-Gaussian tail. We obtain
it by the exponential moment method.

Fix lambda > 0. The variable e^(lambda S) is nonnegative and S >= t implies
e^(lambda S) >= e^(lambda t), so by Markov's inequality

  P(S >= t) <= e^(-lambda t) E[e^(lambda S)].

Next, e^(lambda S) = e^(lambda X_1) e^(lambda X_2) ... e^(lambda X_n). The factors are
bounded functions of distinct variables X_i, hence independent, and the expectation of a
product of independent bounded variables is the product of the expectations:

  E[e^(lambda S)] = E[e^(lambda X_1)] ... E[e^(lambda X_n)] = (cosh lambda)^n,

since E[e^(lambda X_i)] = (e^lambda + e^(-lambda))/2 = cosh lambda.

To bound cosh lambda, compare power series term by term:

  cosh lambda = sum over k >= 0 of lambda^(2k) / (2k)!
             <= sum over k >= 0 of lambda^(2k) / (2^k k!) = e^(lambda^2 / 2),

because (2k)! = product over j = 1..k of (2j)(2j - 1) >= product over j = 1..k of 2j = 2^k k!.
Therefore P(S >= t) <= exp(-lambda t + n lambda^2 / 2) for every lambda > 0. The exponent is
minimized at lambda = t/n, where it equals -t^2/n + t^2/(2n) = -t^2/(2n). This gives
P(S >= t) <= exp(-t^2 / (2n)). (For t > n the left side is 0 and the bound holds trivially.)
