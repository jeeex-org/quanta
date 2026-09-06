# Computer Science — Roadmap

## Quanta CS Stdlib

**Current version:** 0.0.162 | **CS-related shipped libs:** `ai` (0.148), `crypto` (0.0.142), `quantum` (0.0.145), `quic` (0.0.150), `linalg` (0.0.116), `math` (0.0.87), `big` (0.0.128), `generics` (0.149), `sha3_*` (0.0.130+), `ml_kem` (0.0.155), `ml_dsa` (0.0.156), `h3` (0.0.152)

**Planned:** `cs_theory` (0.180–0.186) — algorithms, complexity, computability, automata, concurrency, distributed theory, formal methods.

---

## Algorithms

| Category | Module | Status | Version | Stdlib | Notes |
|----------|--------|--------|---------|--------|-------|
| Algorithms | Sorting | 🔲 planned | — | — | QuickSort, MergeSort, HeapSort, RadixSort, TimSort → `cs_theory` 0.180+ |
| Algorithms | Searching | 🔲 planned | — | — | Binary search, BFS, DFS, A*, hash-based lookup → `cs_theory` 0.180+ |
| Algorithms | Graph | 🔲 planned | — | — | Shortest path (Dijkstra, Bellman-Ford), MST (Prim, Kruskal), max flow, matching → `cs_theory` 0.180+ |
| Algorithms | Dynamic Programming | 🔲 planned | — | — | Memoization, tabulation, knapsack, LCS, edit distance → `cs_theory` 0.180+ |
| Algorithms | Greedy | 🔲 planned | — | — | Activity selection, Huffman coding, matroid theory → `cs_theory` 0.180+ |
| Algorithms | String | 🔲 planned | — | — | KMP, Boyer-Moore, Rabin-Karp, suffix trees/arrays, Aho-Corasick → `cs_theory` 0.180+ |
| Algorithms | Randomized | 🔲 planned | — | — | Monte Carlo, Las Vegas, randomized quicksort, skip lists → `cs_theory` 0.180+ |
| Algorithms | Approximation | 🔲 planned | — | — | PTAS, FPTAS, approximation ratios, hardness of approximation → `cs_theory` 0.180+ |

## Data Structures

| Category | Module | Status | Version | Stdlib | Notes |
|----------|--------|--------|---------|--------|-------|
| Data Structures | Arrays & Lists | ✅ done | 0.149 | `generics.quanta` | Vec, Option, Result in stdlib; dynamic arrays, linked lists |
| Data Structures | Trees | 🔲 planned | — | — | BST, AVL, Red-Black, B-Tree, Trie, Segment Tree, Fenwick → `cs_theory` 0.180+ |
| Data Structures | Hash Tables | ✅ partial | 0.149 | `generics.quanta` | HashMap in stdlib; open addressing, cuckoo hashing, consistent hashing → `cs_theory` 0.180+ |
| Data Structures | Heaps | 🔲 planned | — | — | Binary heap, binomial heap, Fibonacci heap, pairing heap → `cs_theory` 0.180+ |
| Data Structures | Graphs (repr.) | 🔲 planned | — | — | Adjacency list/matrix, edge list, compressed sparse row → `cs_theory` 0.180+ |
| Data Structures | Advanced | 🔲 planned | — | — | Bloom filter, skip list, disjoint-set, persistent DS, rope → `cs_theory` 0.180+ |

## Complexity Theory

| Category | Module | Status | Version | Stdlib | Notes |
|----------|--------|--------|---------|--------|-------|
| Complexity | Time Complexity | 🔲 planned | — | — | Big-O, Big-Ω, Big-Θ, master theorem, amortized analysis → `cs_theory` 0.181+ |
| Complexity | Space Complexity | 🔲 planned | — | — | In-place, auxiliary space, streaming lower bounds → `cs_theory` 0.181+ |
| Complexity | Complexity Classes | 🔲 planned | — | — | P, NP, co-NP, PSPACE, EXPTIME, BPP, #P, PH → `cs_theory` 0.181+ |
| Complexity | NP-Completeness | 🔲 planned | — | — | Cook-Levin, Karp's 21 problems, reductions, approximation hardness → `cs_theory` 0.181+ |
| Complexity | Circuit Complexity | 🔲 planned | — | — | Boolean circuits, depth, size, AC⁰, NC, P/poly → `cs_theory` 0.181+ |
| Complexity | Information-Theoretic | 🔲 planned | — | — | Kolmogorov complexity, algorithmic information theory → `cs_theory` 0.181+ |

## Computability Theory

| Category | Module | Status | Version | Stdlib | Notes |
|----------|--------|--------|---------|--------|-------|
| Computability | Turing Machines | 🔲 planned | — | — | Deterministic, nondeterministic, universal TM, halting problem → `cs_theory` 0.182+ |
| Computability | Lambda Calculus | 🔲 planned | — | — | α-conversion, β-reduction, Church numerals, Y combinator → `cs_theory` 0.182+ |
| Computability | Recursive Functions | 🔲 planned | — | — | Primitive recursive, μ-recursive, Ackermann, recursion theorem → `cs_theory` 0.182+ |
| Computability | Decidability | 🔲 planned | — | — | Decidable, undecidable, semi-decidable, Rice's theorem → `cs_theory` 0.182+ |
| Computability | Oracle Machines | 🔲 planned | — | — | Turing degrees, relativization, arithmetic hierarchy → `cs_theory` 0.182+ |

## Automata Theory

| Category | Module | Status | Version | Stdlib | Notes |
|----------|--------|--------|---------|--------|-------|
| Automata | Finite Automata | 🔲 planned | — | — | DFA, NFA, ε-NFA, subset construction, minimization → `cs_theory` 0.183+ |
| Automata | Regular Languages | 🔲 planned | — | — | Regular expressions, pumping lemma, Myhill-Nerode → `cs_theory` 0.183+ |
| Automata | Pushdown Automata | 🔲 planned | — | — | CFL, context-free grammars, CYK algorithm, PDA equivalence → `cs_theory` 0.183+ |
| Automata | Turing Machines (Adv.) | 🔲 planned | — | — | Multi-tape, universal, busy beaver, Rice's theorem → `cs_theory` 0.183+ |
| Automata | Cellular Automata | 🔲 planned | — | — | Rule 110, Game of Life, Wolfram classes, universality → `cs_theory` 0.183+ |

## Logic in CS

| Category | Module | Status | Version | Stdlib | Notes |
|----------|--------|--------|---------|--------|-------|
| CS Logic | Propositional | 🔲 planned | — | — | Truth tables, CNF/DNF, SAT, DPLL, CDCL → `cs_theory` 0.184+ |
| CS Logic | Predicate | 🔲 planned | — | — | First-order, unification, resolution, Herbrand → `cs_theory` 0.184+ |
| CS Logic | Temporal | 🔲 planned | — | — | LTL, CTL, CTL*, model checking, Büchi automata → `cs_theory` 0.184+ |
| CS Logic | Hoare | 🔲 planned | — | — | Hoare logic, weakest preconditions, program verification → `cs_theory` 0.184+ |
| CS Logic | Separation | 🔲 planned | — | — | Separation logic, frame rule, concurrent separation logic → `cs_theory` 0.184+ |

## Concurrency Theory

| Category | Module | Status | Version | Stdlib | Notes |
|----------|--------|--------|---------|--------|-------|
| Concurrency | Process Calculi | 🔲 planned | — | — | CCS, CSP, π-calculus, bisimulation, barbed equivalence → `cs_theory` 0.185+ |
| Concurrency | Shared Memory | 🔲 planned | — | — | Mutual exclusion, Peterson's algorithm, RCU, lock-free DS → `cs_theory` 0.185+ |
| Concurrency | Message Passing | 🔲 planned | — | — | Actor model, channels, Erlang-style, session types → `cs_theory` 0.185+ |
| Concurrency | Memory Models | 🔲 planned | — | — | Sequential consistency, TSO, release consistency, happens-before → `cs_theory` 0.185+ |
| Concurrency | Deadlock & Liveness | 🔲 planned | — | — | Wait-for graphs, banker's algorithm, liveness properties → `cs_theory` 0.185+ |

## Distributed Theory

| Category | Module | Status | Version | Stdlib | Notes |
|----------|--------|--------|---------|--------|-------|
| Distributed | Consensus | 🔲 planned | — | — | Paxos, Raft, Byzantine fault tolerance, FLP impossibility → `cs_theory` 0.186+ |
| Distributed | Consistency | 🔲 planned | — | — | Linearizability, sequential, causal, eventual, CAP theorem → `cs_theory` 0.186+ |
| Distributed | Clocks | 🔲 planned | — | — | Logical clocks, vector clocks, hybrid logical clocks, NTP → `cs_theory` 0.186+ |
| Distributed | Replication | 🔲 planned | — | — | Primary-backup, multi-primary, quorum, CRDTs → `cs_theory` 0.186+ |
| Distributed | Partitioning | 🔲 planned | — | — | Consistent hashing, range partitioning, virtual nodes → `cs_theory` 0.186+ |

---

## Implementation Summary

| Domain | Done | Partial | Planned |
|--------|------|---------|---------|
| Algorithms | 0 | 0 | 8 |
| Data Structures | 1 | 1 | 4 |
| Complexity | 0 | 0 | 6 |
| Computability | 0 | 0 | 5 |
| Automata | 0 | 0 | 5 |
| CS Logic | 0 | 0 | 5 |
| Concurrency | 0 | 0 | 5 |
| Distributed | 0 | 0 | 5 |
| **Total** | **1** | **1** | **43** |

---

## Stdlib Coverage Detail

### `generics.quanta` (v0.149) — Parametric polymorphism
- Generic Vec (dynamic array), Option, Result, HashMap, Box, Rc
- Monomorphization, trait resolution, type inference/unification

### `ai.quanta` (v0.148) — Tensor / ML substrate
- Neural network primitives, attention, convolutions, optimizers

### `crypto.quanta` (v0.0.142) — Cryptographic primitives
- SHA-3, ML-KEM, ML-DSA, AES-GCM, key derivation, post-quantum

### `quantum.quanta` (v0.0.145) — Quantum computing
- Qubit simulation, gates, circuits, measurement

### `quic.quanta` (v0.0.150) — QUIC protocol
- Connection management, streams, congestion control

---

## Cross-References

| Document | Purpose |
|----------|---------|
| [quanta.md](../quanta.md) | Core language roadmap, stdlib build order |



