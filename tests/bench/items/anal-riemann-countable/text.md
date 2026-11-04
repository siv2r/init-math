# Proof

Let F(x) = integral from 0 to x of f(t) dt, so that F is identically 0 on [0, 1]. Let D be
the set of points of [0, 1] at which f is discontinuous.

Step 1: f vanishes off D. Let x_0 be a point at which f is continuous. By the fundamental
theorem of calculus F is differentiable at x_0 with F'(x_0) = f(x_0) (one-sided at the
endpoints). Since F is identically 0, F'(x_0) = 0, so f(x_0) = 0. Hence the set
{x : f(x) != 0} is contained in D.

Step 2: D is countable. Since f is Riemann integrable on [0, 1], it is a uniform limit of
step functions (the step functions bounding f below and above in Riemann's criterion can be
taken as close to f as desired): there are step functions s_1, s_2, ... with sup over
[0, 1] of |f - s_j| < 1/j. Each s_j is constant on the open intervals of a finite partition, so it is
discontinuous at finitely many points; let E be the union over j of these finite sets.
E is countable.

Let x be a point of [0, 1] not in E. Each s_j is continuous at x, and s_j -> f uniformly.
Given epsilon > 0 choose j with 1/j < epsilon/3, and then delta > 0 such that
|s_j(y) - s_j(x)| < epsilon/3 whenever |y - x| < delta. For such y,

  |f(y) - f(x)| <= |f(y) - s_j(y)| + |s_j(y) - s_j(x)| + |s_j(x) - f(x)| < epsilon.

So f is continuous at x. Thus D is contained in E, and D is countable.

Combining the two steps, {x : f(x) != 0} is contained in the countable set E.

The countable exceptional set cannot be removed: Thomae's function, equal to 1/q at a
rational p/q in lowest terms and to 0 at irrationals, is Riemann integrable with
integral from 0 to x equal to 0 for every x, and it is nonzero at every rational point.
