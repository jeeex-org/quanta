# Mathematics — Roadmap

## Quanta Math Stdlib

**Current version:** 0.0.162 | **Math-related shipped libs:** `math` (0.0.87), `linalg` (0.0.116), `big` (0.0.128), `ai` (0.148), `generics` (0.149)

**Planned:** `math_full` (0.187–0.197) — BLAS/LAPACK, numerical analysis, statistics, signal processing, computational geometry, graph algorithms, number theory, symbolic math, special functions, interval computing, financial math.

---

## Algebra

| Category | Module | Status | Version | Stdlib | Notes |
|----------|--------|--------|---------|--------|-------|
| Algebra | Vector Spaces | ✅ done | 0.0.116 | `linalg.quanta` | `vdot`, `vnorm`, scalar ops, flattened vector representation |
| Algebra | Matrix Theory | ✅ done | 0.0.116 | `linalg.quanta` | `mat_new`, `mat_get/set`, `mat_zeros`, `mat_identity`, `mat_from_flat`, `mat_add/sub/scal`, `mat_mul` (int + f64), `mat_transpose`, `mat_print` |
| Algebra | Eigenvalues | 🔲 planned | — | — | Eigenvalue decomposition, QR algorithm, power iteration → `math_full` 0.187+ |
| Algebra | Linear Transformations | ✅ done | 0.0.116 | `linalg.quanta` | Matrix multiplication (`mat_mul`, `mat_mul_f`) composes linear maps; `mat_inv_f` for invertible transforms |
| Algebra | Boolean Algebra | 🔲 planned | — | — | Boolean rings, lattices, SAT kernels → `math_full` 0.187+ |
| Algebra | Abstract Algebra | 🔲 planned | — | — | Groups, rings, fields, modules, homomorphisms → `math_full` 0.187+ |
| Algebra | Polynomial | 🔲 planned | — | — | Polynomial arithmetic, GCD, factorization, FFT-based multiplication → `math_full` 0.187+ |
| Algebra | Lie Algebra | 🔲 planned | — | — | Lie brackets, structure constants, representations, root systems → `math_full` 0.187+ |

## Analysis

| Category | Module | Status | Version | Stdlib | Notes |
|----------|--------|--------|---------|--------|-------|
| Analysis | Calculus | 🔲 planned | — | — | Derivatives, integrals, limits, series expansion → `math_full` 0.187+ |
| Analysis | Real Analysis | 🔲 planned | — | — | Metric spaces, continuity, differentiation, Riemann/Lebesgue integration → `math_full` 0.187+ |
| Analysis | Complex Analysis | 🔲 planned | — | — | Holomorphic functions, contour integration, residues, conformal maps → `math_full` 0.187+ |
| Analysis | Measure Theory | 🔲 planned | — | — | Sigma-algebras, Lebesgue measure, Lp spaces, Radon-Nikodym → `math_full` 0.187+ |
| Analysis | Functional Analysis | 🔲 planned | — | — | Banach/Hilbert spaces, operators, spectral theory, distributions → `math_full` 0.187+ |

## Geometry

| Category | Module | Status | Version | Stdlib | Notes |
|----------|--------|--------|---------|--------|-------|
| Geometry | Euclidean | 🔲 planned | — | — | Points, lines, planes, distances, transformations → `math_full` 0.187+ |
| Geometry | Differential | 🔲 planned | — | — | Manifolds, curvature, tensors, geodesics → `math_full` 0.187+ |
| Geometry | Algebraic | 🔲 planned | — | — | Varieties, schemes, Groebner bases, elimination theory → `math_full` 0.187+ |
| Geometry | Computational | 🔲 planned | — | — | Convex hull, Delaunay/Voronoi, mesh generation, collision detection → `math_full` 0.187+ |

## Statistics & Probability

| Category | Module | Status | Version | Stdlib | Notes |
|----------|--------|--------|---------|--------|-------|
| Statistics | Bayesian | 🔲 planned | — | — | Posterior inference, MCMC, variational Bayes, conjugate priors → `math_full` 0.187+ |
| Statistics | Frequentist | 🔲 planned | — | — | MLE, hypothesis testing, confidence intervals, bootstrap → `math_full` 0.187+ |
| Statistics | Computational | 🔲 planned | — | — | Resampling, permutation tests, ABC, density estimation → `math_full` 0.187+ |
| Statistics | Probability | 🔲 planned | — | — | Distributions, expectation, variance, limit theorems, stochastic processes → `math_full` 0.187+ |
| Statistics | Stochastic | 🔲 planned | — | — | Brownian motion, SDEs, Markov chains, martingales → `math_full` 0.187+ |
| Statistics | Regression | 🔲 planned | — | — | Linear/logistic regression, GLMs, regularization, time series → `math_full` 0.187+ |

## Number Theory

| Category | Module | Status | Version | Stdlib | Notes |
|----------|--------|--------|---------|--------|-------|
| Number Theory | Elementary | ✅ partial | 0.0.87 | `math.quanta` | `gcd` (Euclidean), `lcm`, `pow`, `abs` — full elem. NT (primes, congruences, quadratic reciprocity) → `math_full` 0.187+ |
| Number Theory | Analytic | 🔲 planned | — | — | Zeta function, prime number theorem, Dirichlet series → `math_full` 0.187+ |
| Number Theory | Algebraic | 🔲 planned | — | — | Algebraic number fields, ideals, class groups, Galois theory → `math_full` 0.187+ |
| Number Theory | Computational | 🔲 planned | — | — | Primality testing, factorization, discrete log, elliptic curves, lattice reduction → `math_full` 0.187+ |

## Combinatorics

| Category | Module | Status | Version | Stdlib | Notes |
|----------|--------|--------|---------|--------|-------|
| Combinatorics | Enumerative | 🔲 planned | — | — | Counting, generating functions, partitions, permutations → `math_full` 0.187+ |
| Combinatorics | Graph Theory | 🔲 planned | — | — | Shortest path, flow, MST, matching, centrality, community detection → `math_full` 0.187+ |
| Combinatorics | Design Theory | 🔲 planned | — | — | Block designs, Latin squares, error-correcting codes → `math_full` 0.187+ |
| Combinatorics | Extremal | 🔲 planned | — | — | Ramsey theory, Turan-type problems, probabilistic method → `math_full` 0.187+ |

## Optimization

| Category | Module | Status | Version | Stdlib | Notes |
|----------|--------|--------|---------|--------|-------|
| Optimization | Linear | 🔲 planned | — | — | Simplex method, duality, sensitivity analysis → `math_full` 0.187+ |
| Optimization | Nonlinear | 🔲 planned | — | — | Gradient descent, Newton, quasi-Newton, trust region → `math_full` 0.187+ |
| Optimization | Convex | 🔲 planned | — | — | Convex sets, KKT conditions, interior-point methods, SDP → `math_full` 0.187+ |
| Optimization | Integer | 🔲 planned | — | — | Branch-and-bound, cutting planes, combinatorial optimization → `math_full` 0.187+ |
| Optimization | Stochastic | 🔲 planned | — | — | SGD, evolutionary algorithms, simulated annealing, Bayesian opt → `math_full` 0.187+ |

## Differential Equations

| Category | Module | Status | Version | Stdlib | Notes |
|----------|--------|--------|---------|--------|-------|
| Differential Eq | ODE | 🔲 planned | — | — | Euler, Runge-Kutta, adaptive step, stiff systems, boundary value → `math_full` 0.187+ |
| Differential Eq | PDE | 🔲 planned | — | — | Finite difference/element/volume, spectral methods, multigrid → `math_full` 0.187+ |
| Differential Eq | Numerical | 🔲 planned | — | — | Root-finding, quadrature, interpolation, numerical linear algebra → `math_full` 0.187+ |

## Topology

| Category | Module | Status | Version | Stdlib | Notes |
|----------|--------|--------|---------|--------|-------|
| Topology | Point-Set | 🔲 planned | — | — | Open/closed sets, continuity, compactness, connectedness, separation → `math_full` 0.187+ |
| Topology | Algebraic | 🔲 planned | — | — | Homotopy, homology, cohomology, fundamental group → `math_full` 0.187+ |
| Topology | Differential | 🔲 planned | — | — | Smooth manifolds, tangent bundles, de Rham cohomology → `math_full` 0.187+ |
| Topology | Geometric | 🔲 planned | — | — | Simplicial complexes, persistent homology, Morse theory → `math_full` 0.187+ |

## Logic & Foundations

| Category | Module | Status | Version | Stdlib | Notes |
|----------|--------|--------|---------|--------|-------|
| Logic | Propositional | 🔲 planned | — | — | Truth tables, CNF/DNF, SAT solving, natural deduction → `math_full` 0.187+ |
| Logic | Predicate | 🔲 planned | — | — | First-order logic, quantifiers, completeness, compactness → `math_full` 0.187+ |
| Logic | Modal | 🔲 planned | — | — | Kripke semantics, temporal logic, provability logic → `math_full` 0.187+ |
| Logic | Set Theory | 🔲 planned | — | — | ZFC axioms, ordinals, cardinals, forcing, large cardinals → `math_full` 0.187+ |
| Logic | Type Theory | 🔲 planned | — | — | Dependent types, Martin-Löf, homotopy type theory, proof assistants → `lang_advanced` 0.183+ |
| Logic | Category Theory | 🔲 planned | — | — | Functors, natural transformations, limits, adjunctions, monads → `math_full` 0.187+ |

## Special Functions & Applied

| Category | Module | Status | Version | Stdlib | Notes |
|----------|--------|--------|---------|--------|-------|
| Special Fn | Gamma/Bessel | 🔲 planned | — | — | Gamma, Beta, Bessel, hypergeometric, orthogonal polynomials → `math_full` 0.187+ |
| Special Fn | Symbolic Math | 🔲 planned | — | — | Expression trees, auto-diff, Risch integration, Groebner basis, CAD → `math_full` 0.187+ |
| Special Fn | Signal Processing | 🔲 planned | — | — | FFT, filter design, wavelets, spectrogram → `math_full` 0.187+ |
| Special Fn | Interval Arithmetic | 🔲 planned | — | — | IEEE 1788, affine arithmetic, Taylor models, verified computing → `math_full` 0.187+ |
| Special Fn | Financial Math | 🔲 planned | — | — | Black-Scholes/Heston, Greeks, Monte Carlo, XVA, rate models → `math_full` 0.187+ |

---

## Implementation Summary

| Domain | Done | Partial | Planned |
|--------|------|---------|---------|
| Algebra | 3 | 0 | 5 |
| Analysis | 0 | 0 | 5 |
| Geometry | 0 | 0 | 4 |
| Statistics | 0 | 0 | 6 |
| Number Theory | 0 | 1 | 3 |
| Combinatorics | 0 | 0 | 4 |
| Optimization | 0 | 0 | 5 |
| Differential Eq | 0 | 0 | 3 |
| Topology | 0 | 0 | 4 |
| Logic | 0 | 0 | 6 |
| Special Fn | 0 | 0 | 5 |
| **Total** | **3** | **1** | **50** |

---

## Stdlib Coverage Detail

### `math.quanta` (v0.0.87) — Core numeric primitives
- `abs(x)` — absolute value (two's-complement safe)
- `min(a,b)`, `max(a,b)` — ordering
- `clamp(x,lo,hi)` — range clamping
- `pow(base,exp)` — integer power (exp ≥ 0)
- `gcd(a,b)` — Euclidean algorithm
- `lcm(a,b)` — least common multiple

### `linalg.quanta` (v0.0.116) — Dense linear algebra
- Matrix: `mat_new`, `mat_get/set`, `mat_zeros`, `mat_identity`, `mat_from_flat`
- Arithmetic: `mat_add`, `mat_sub`, `mat_scal_i/f`, `mat_mul`, `mat_mul_f`
- Decomposition: `mat_transpose`, `mat_det` (Bareiss fraction-free), `mat_inv_f` (Gauss-Jordan)
- Vector: `vdot`, `vnorm` (Euclidean)
- I/O: `mat_print`, `mat_print_f`, `fprint`

### `big.quanta` (v0.0.128) — Arbitrary-precision integers
- 24-bit limb representation, sign/magnitude
- Arithmetic: `big_add/sub/mul`, `big_mul_kara` (Karatsuba), `big_div/mod` (binary restoring)
- Shift: `big_shl1/shr1`, `big_shl1_mut`
- Conversion: `big_from_i64/dec/2x64`, `big_to_i64`, `big_print_hex`
- Signed ops: `big_add_signed`, `big_sub_signed`, `big_mul_signed`, `big_cmp`

### `ai.quanta` (v0.148) — Tensor / ML substrate
- Tensor: `ai_tensor_create/from_data/free`, `ai_tensor_get/set_f32`
- Ops: `ai_add/mul/matmul/transpose/reshape`
- Activations: `ai_relu/sigmoid/tanh/gelu/silu/softmax`
- Layers: `ai_conv2d/conv2d_transpose/depthwise_conv2d`, `ai_linear`, `ai_embedding`
- Attention: `ai_scaled_dot_product_attention`, `ai_multihead_attention`
- Normalization: `ai_batchnorm2d/layernorm/groupnorm`
- Losses: `ai_mse_loss/cross_entropy_loss/bce_loss`
- Optimizers: `ai_sgd_init/step`, `ai_adam_init/step`
- Module system: `ai_module_init/register_param/add_child/forward`

### `generics.quanta` (v0.149) — Parametric polymorphism
- Type parameters with constraints (Eq/Ord/Hash/Clone/Copy/Add/Sub/Mul/Div/etc.)
- Generic fn/struct/enum/impl/trait, where clauses
- Monomorphization with name mangling, type substitution
- Trait resolution, const generics, type inference/unification
- Stdlib generic types: Option/Result/Vec/Box/Rc/HashMap/Iterator/Future

---

## Cross-References

| Document | Purpose |
|----------|---------|
| [quanta.md](../quanta.md) | Core language roadmap, stdlib build order |



