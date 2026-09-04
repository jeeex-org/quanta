# Quanta Standard Library Gaps by Domain

This document catalogs what is missing from Quanta's standard library for various application domains. Current version: 0.0.135.

---

## Mesh Networking (TALI-style P2P Mesh)

### Transport Layer
- UDP socket API (send, recv, bind, connect)
- QUIC implementation or FFI to quic-go
- TLS 1.3 stack (handshake, record layer, ALPN)
- Certificate parsing (X.509) and verification
- ALPN negotiation
- Connection migration / CID rotation
- Congestion control (CUBIC, BBR)
- Stream multiplexing / flow control

### Cryptography
- SHA-256, SHA-3 (SHAKE128/256)
- BLAKE2b, BLAKE3
- HMAC, HKDF, PBKDF2
- AES-GCM, ChaCha20-Poly1305
- Ed25519, X25519
- **Dilithium** (ML-DSA) signatures
- **ML-KEM** (Kyber) key encapsulation
- **FALCON** signatures (optional)
- Constant-time arithmetic primitives
- Secure random (getrandom / RDRAND / /dev/urandom)

### DHT / Kademlia
- XOR metric distance
- Routing table (k-buckets)
- FIND_NODE, FIND_VALUE, STORE, PING RPC
- Iterative lookup with parallelism
- Bucket refresh / replacement policies
- Provider records (service announcement)
- Persistent peer database

### NAT Traversal
- STUN client (RFC 5389, RFC 8489)
- TURN client (RFC 5766, RFC 8656)
- ICE agent (RFC 8445)
- UDP hole punching (simultaneous open)
- Relay fallback
- Reflexive address discovery

### Service Discovery
- mDNS / DNS-SD (RFC 6762, RFC 6763)
- Multicast UDP (224.0.0.251:5353)
- Service registration / browsing
- TXT record parsing
- Local peer cache

### Concurrency / Runtime
- Goroutine / green thread scheduler
- Channel / select (CSP)
- Timer wheel / deadline management
- Work-stealing scheduler
- Async I/O (epoll / kqueue / io_uring)
- Cancellation / context propagation

### Persistence
- Embedded key-value (LSM tree / B-tree)
- WAL / write-ahead logging
- Snapshot / checkpoint
- Compaction

---

## Blockchain / DAG

### Consensus
- BFT consensus (Tendermint / HotStuff / Narwhal-Bullshark)
- GHOSTDAG / PHANTOM ordering
- Leader election / proposer selection
- Validator set management (bonding, slashing, unbonding)
- Fork choice rule
- Finality gadget

### Cryptoeconomics
- Token ledger (balances, transfers)
- Staking / delegation
- Reward distribution
- Slashing conditions (double-sign, downtime)
- Inflation / emission schedule

### State Management
- Merkle Patricia Trie / Verkle Trie
- State root computation
- State sync (fast sync, warp sync)
- Pruning / archival modes
- Sparse Merkle trees (for nullifiers)

### Transaction Layer
- Transaction pool (mempool) with priority
- Transaction validation (nonce, signature, gas)
- EVM / WASM / RISC-V VM (or custom)
- Gas metering
- Receipt / log indexing

### Networking
- Block propagation (compact blocks, erasure coding)
- GossipSub / libp2p pubsub
- Peer scoring / reputation
- Sync protocol (headers-first, bodies)

### Light Client
- Header chain verification
- Merkle proofs (inclusion, exclusion)
- State proofs
- Trust-minimized sync

---

## Monetary Systems

### Core Ledger
- Double-entry bookkeeping
- Multi-currency / multi-asset support
- Decimal / fixed-point arithmetic (no float)
- Account abstraction
- Transaction atomicity (ACID)

### Settlement
- Gross settlement (RTGS)
- Net settlement (batch, netting)
- Settlement finality guarantees
- Inter-ledger protocol (ILP)
- Payment channels (HTLC, PTLC)

### Risk / Compliance
- KYC / AML hooks
- Sanctions screening
- Transaction monitoring
- Velocity limits
- Suspicious activity reporting

### Accounting
- General ledger
- Chart of accounts
- Journal entries
- Trial balance
- Financial statements (BS, IS, CF)

### Cryptographic Primitives
- Blind signatures (Chaumian e-cash)
- Threshold signatures (FROST, GG20)
- Zero-knowledge proofs (SNARK/STARK)
- Range proofs
- Commitment schemes (Pedersen, KZG)

---

## QR / Optical Transfer (Decimen-style)

### Fountain Codes
- Luby Transform (LT) encoder/decoder
- Raptor / RaptorQ codes
- Robust Soliton distribution
- Systematic + repair frame generation
- Peeling decoder (on-the-fly)
- Degree distribution sampling (deterministic PRNG)

### QR Code
- QR encoder (ISO/IEC 18004)
- Version selection (1-40)
- Error correction levels (L/M/Q/H)
- Mask pattern evaluation (or pinned mask)
- Bit matrix → PNG raster
- QR decoder (reed-solomon, finder patterns, alignment)

### Image / Video
- PNG encoder (deflate, CRC32, palette)
- APNG encoder (acTL, fcTL, fdAT)
- Color space handling
- Frame timing (rational delays)

### Camera / Web APIs
- WebAssembly runtime (MVP + SIMD + threads)
- wasm-bindgen / JS interop
- getUserMedia (camera access)
- Canvas / OffscreenCanvas
- WebCodecs (video decode)
- Service Worker / Cache API (offline)

### Determinism
- IEEE-754 exact math (log, exp, sqrt)
- Cross-engine PRNG (splitmix32, xoshiro256++)
- Bit-identical serialization

---

## Web Server

### HTTP
- HTTP/1.1 parser (request/response)
- HTTP/2 (HPACK, frames, streams, priority)
- HTTP/3 (QUIC transport, QPACK)
- WebSocket (RFC 6455)
- Server-Sent Events (SSE)

### Routing / Middleware
- Path router (radix tree / regex)
- Middleware chain
- Request/response types
- Body parsing (JSON, form, multipart)
- Compression (gzip, brotli, zstd)

### TLS
- Certificate loading (PEM, PKCS#12)
- SNI callback
- OCSP stapling
- Certificate transparency
- mTLS

### Observability
- Structured logging (JSON, levels)
- Metrics (Prometheus exposition)
- Distributed tracing (W3C TraceContext)
- Health checks / readiness

---

## Game Development

### Math
- Linear algebra (vec2/3/4, mat3/4, quat)
- Transform (position, rotation, scale)
- Interpolation (lerp, slerp, smoothstep)
- Random (PCG, Xoroshiro, noise)

### Rendering
- GPU API abstraction (Vulkan / Metal / WebGPU)
- Shader compilation (SPIR-V / WGSL / MSL)
- Pipeline state management
- Buffer / texture / sampler management
- Draw calls (instanced, indirect)
- Swapchain / presentation

### ECS / Scene
- Entity-component-system
- Archetype storage
- Query / filter system
- Hierarchical transforms
- Scene graph

### Physics
- Rigid body dynamics
- Collision detection (broad/narrow phase)
- Constraints / joints
- Ray casting
- Broadphase (SAP, BVH, grid)

### Audio
- Audio graph (nodes, parameters)
- Spatial audio (HRTF, ambisonics)
- Codec support (opus, vorbis, mp3)
- Real-time mixing

### Input / Platform
- Keyboard / mouse / gamepad
- Touch / pointer events
- Window management
- Fullscreen / VR / AR
- File dialogs / drag-drop

### Asset Pipeline
- Format loaders (gltf, fbx, obj, png, ktx, basis)
- Texture compression (BC, ASTC, ETC)
- Mesh optimization (meshopt)
- Hot reload

---

## E-Commerce Applications

### Payments
- Payment gateway integrations (Stripe, Adyen, etc.)
- Card tokenization
- 3D Secure (EMVCo)
- Apple Pay / Google Pay
- ACH / SEPA / local rails
- Refunds / chargebacks / disputes
- PCI DSS compliance helpers

### Inventory
- SKU / variant management
- Stock levels / reservations
- Warehouse / location tracking
- Reorder points / alerts
- Bundles / kits

### Orders
- Cart → checkout → order flow
- Order state machine
- Fulfillment / shipping integration
- Returns / exchanges / RMA
- Invoice / receipt generation (PDF)

### Pricing / Promotions
- Price lists / tiers
- Discounts (%, $, BOGO, volume)
- Coupons / promo codes
- Dynamic pricing rules
- Tax calculation (per jurisdiction)

### Customers
- Accounts / profiles
- Address book
- Wish lists
- Loyalty / points
- Reviews / ratings

### Search / Catalog
- Full-text search (inverted index, BM25)
- Faceted navigation
- Autocomplete / suggestions
- Product attributes / filters
- Category hierarchy

### Analytics
- Event tracking (click, view, purchase)
- Funnel analysis
- Cohort retention
- Revenue recognition
- A/B testing framework

---

## Infrastructure Tools (Terraform / Ansible Style)

### Configuration Language
- HCL / YAML / JSON parser
- Expression evaluation (interpolation, functions)
- Type system (primitives, objects, tuples, maps)
- Variable validation
- Module system

### State Management
- State backend (local, S3, Consul, etcd, PostgreSQL)
- State locking (DynamoDB, Consul, etcd)
- State versioning / migration
- Drift detection
- Import existing resources

### Provider Framework
- Resource schema (CRUD: Create, Read, Update, Delete)
- Diff / plan computation
- Graph construction (DAG of dependencies)
- Parallel execution with dependencies
- Retry / timeout / backoff
- Provider protocol (gRPC / JSON-RPC)

### Resource Types (Examples)
- Cloud: compute, network, storage, database, DNS, IAM
- Kubernetes: manifests, helm, kustomize
- SaaS: GitHub, GitLab, Datadog, PagerDuty
- On-prem: libvirt, Proxmox, bare metal

### Execution
- Dry-run / plan output
- Apply with confirmation
- Progress reporting
- Rollback on failure
- Targeted apply

### Inventory / Provisioning (Ansible-style)
- Inventory (static, dynamic, cloud)
- Playbook parser (YAML)
- Task execution (linear, free strategy)
- Module system (action plugins)
- Connection plugins (SSH, WinRM, local, docker)
- Variable precedence (role, play, host, group)
- Templating (Jinja2)
- Fact gathering
- Idempotency checks
- Callbacks / events

### Secrets
- Vault integration (HashiCorp Vault, AWS Secrets Manager)
- Encryption at rest (age, sops, GPG)
- Key rotation
- Dynamic secrets

---

## Cross-Cutting Concerns (All Domains)

| Capability | Status | Notes |
|------------|--------|-------|
| **Structured logging** | ❌ | Levels, fields, sampling, outputs |
| **Metrics / Telemetry** | ❌ | Counters, gauges, histograms, exemplars |
| **Distributed Tracing** | ❌ | Span context, sampling, exporters |
| **Configuration** | ❌ | File (TOML/YAML/JSON), env, flags, hot reload |
| **Feature Flags** | ❌ | Targeting, rollout, experimentation |
| **Testing Helpers** | ❌ | Mocks, fakes, property-based, fuzzing |
| **Benchmarking** | ❌ | Statistical, flame graphs, comparisons |
| **Profiling** | ❌ | CPU, memory, mutex, block, goroutine |
| **Documentation Generator** | ❌ | From source comments |
| **Package Manager** | ❌ | Resolution, lockfile, publishing, private registries |
| **Build System** | ❌ | Incremental, hermetic, reproducible, remote cache |
| **IDE Support** | ❌ | LSP, debugger, formatter, linter |

---

## Summary: What Exists vs. What's Needed

| Domain | Stdlib Coverage | Primary Blocker |
|--------|-----------------|-----------------|
| **Mesh Networking** | ~2% | No networking, crypto, async runtime |
| **Blockchain / DAG** | ~1% | No crypto, consensus, VM, state management |
| **Monetary Systems** | ~0% | No decimal math, ledger, compliance, ZKP |
| **QR / Optical Transfer** | ~0% | No WASM, camera, QR, fountain codes, determinism |
| **Web Server** | ~1% | No HTTP, TLS, routing, middleware |
| **Game Development** | ~0% | No GPU, math, ECS, physics, audio, input |
| **E-Commerce** | ~0% | No payments, inventory, orders, search, analytics |
| **Infra Tools** | ~0% | No config language, state, provider framework, SSH |

---

---

## O — Self-Improving and Self-Learning Language Architecture

How Quanta can become a self-improving, self-learning language that understands the outside world and interacts with it. Technical deep-dive with concrete architecture recommendations.

### O1 — Self-Improvement Architecture

A self-improving language is one whose implementation can analyze, test, and improve itself without human intervention in the loop. This is distinct from machine learning — it's about architectural feedback loops that make the compiler, stdlib, and tooling better over time.

#### O1.1 — Self-Hosting Completeness as Foundation

Quanta's current self-hosting is partial: the frontend (parser, type checker, IR generator) is written in Quanta, but the codegen and optimizer backends are still C++. Full self-improvement requires full self-hosting.

**Critical path to full self-hosting:**
1. **Complete the Quanta codegen backend** (x86_64): instruction selection, register allocation, peephole optimization, ELF object emission. Currently `compiler/0.0.135/src/x86/` has `elf.quanta`, `objfmt.quanta`, `emitter.quanta` — these are the building blocks. The codegen logic in C++ must be ported to Quanta.
2. **Complete the Quanta optimizer backend**: constant folding, dead code elimination, inlining, loop optimizations. This lives in C++ today; port to `compiler/0.0.135/src/optimizer.quanta` or similar.
3. **Complete the Quanta linker**: symbol resolution, section merging, relocation application, address assignment, output ELF writing. `elf.quanta` handles sections and headers; symbol resolution and relocation application still need completion.
4. **Retire the C++ backend**: once the Quanta backend produces correct binaries (cross-checked against C++ backend output), remove the C++ backend entirely.

**Why this is the gate for self-improvement:** a self-improving compiler must be able to modify its own source code and recompile itself. If the backend is C++, Quanta can only improve its frontend. Full self-hosting unlocks full self-improvement.

#### O1.2 — Automated Benchmark-Driven Optimization

**Architecture:**
```
Compiler source → build → test binary → benchmark → performance data →
  analyze (is performance regressed?) → if yes: locate hot spot →
  suggest optimization → apply patch → rebuild → verify → commit or revert
```

**Implementation components:**
- **Benchmark harness**: `qc --benchmark program.quanta` runs the program with timing, outputs results in structured format.
- **Performance database**: stores historical benchmark results per compiler version, per benchmark, with metadata.
- **Regression detection**: compares current benchmark results to baseline. If regression > threshold, flag it.
- **Hot spot identification**: profile the compiler itself to find hot functions. Cross-reference with source code to locate the optimization opportunity.
- **Patch generation**: given a hot spot, generate a candidate optimization. Apply as a proposed patch.
- **Verification**: compile with the patch, run benchmarks, verify improvement. If improvement confirmed, commit. If not, revert.

**Why this matters:** hand-tuning compiler optimizations is slow and error-prone. Automated benchmarking + profiling + patch generation can iterate faster than a human, especially for micro-optimizations.

**Risk**: automated patches can introduce bugs. The verification step catches regressions, but subtle semantic bugs may slip through. Mitigation: keep the C++ backend as a reference; cross-check outputs.

#### O1.3 — Automated Test Generation for Compiler Bug Fixes

**Architecture:**
```
Bug report (source + expected/actual behavior) →
  minimize source (delta debugging) →
  create gate test from minimal reproducer →
  run gate test to confirm bug is captured →
  fix compiler →
  run gate test to confirm fix →
  commit test + fix together
```

**Implementation components:**
- **Bug ingest**: accept bug reports in a structured format.
- **Test minimizer**: given a failing program, produce the smallest program that still fails. Uses delta debugging.
- **Gate test generator**: convert the minimal reproducer into a gate test.
- **Regression test database**: store all gate tests, keyed by bug ID. Run all gate tests on every compiler change.

**Why this matters:** every bug that escapes becomes a regression test. Over time, the gate test suite grows to cover the compiler's bug surface. This is the "test suite as bug corpus" approach used by LLVM (bugpoint), GCC, and Rust.

#### O1.4 — Self-Profiling Compiler

**Architecture:**
```
Compile a representative workload →
  compiler instruments itself (timing, memory, hot functions) →
  produces self-profile report →
  identifies optimization opportunities →
  applies optimizations →
  recompile → verify improvement
```

**Implementation components:**
- **Self-profiling hooks**: the compiler, when invoked with `--profile-self`, instruments its own passes.
- **Profile output**: structured report showing time spent in each pass, memory usage, hot spots.
- **Integration with system profilers**: the compiler can invoke `perf` or `valgrind` on itself and parse the output.

**Why this matters:** the compiler is the most important program written in Quanta. Optimizing it improves everything else. Self-profiling makes the optimization process data-driven.

#### O1.5 — Pattern Mining from Real Code

**Architecture:**
```
Corpus of real Quanta programs (open source, with permission) →
  AST-level analysis (what patterns appear? what's common? what's error-prone?) →
  statistics (frequency of constructs, common idioms, recurring bugs) →
  report → informs language design decisions, stdlib priorities, compiler warnings
```

**Implementation components:**
- **AST analyzer**: parses Quanta source files, extracts AST nodes, computes statistics.
- **Pattern detector**: identifies recurring patterns.
- **Bug pattern detector**: identifies patterns that frequently lead to bugs.
- **Privacy**: analysis is at the AST level, not the source level. No source code is stored, only statistics. User opt-in required.

**Why this matters:** language design is often based on intuition. Real usage data replaces intuition with evidence. If 80% of users write the same helper function, it should be in stdlib.

#### O1.6 — Learning from External Code (Interoperability as Learning)

**Architecture:**
```
C/C++/Rust/other code →
  analyze ABI, calling conventions, library interfaces →
  generate Quanta FFI bindings automatically →
  developers use the bindings →
  feedback loop: which bindings are useful? which are painful? →
  improve FFI generation, improve C interop
```

**Implementation components:**
- **C header parser**: parse C headers, extract function signatures, struct definitions, enum definitions, constant definitions.
- **FFI binding generator**: convert C declarations to Quanta `extern "C"` declarations.
- **Usage analyzer**: track which generated bindings are used, which are not, which cause errors.
- **Library interface analyzer**: for a given C library, analyze its interface, document it, suggest idiomatic Quanta wrappers.

**Why this matters:** C is the lingua franca of systems programming. A language that can automatically and correctly interface with C libraries learns from the largest existing codebase in the world.

### O2 — Understanding and Interacting with the Outside World

A programming language that only exists in a vacuum is limited. To be useful, Quanta must understand and interact with the outside world: files, networks, processes, user interfaces, other languages, other systems.

#### O2.1 — System Interface Layer

**Current state:** Quanta has raw syscall bindings (`socket`, `connect`, `bind`, `listen`, `accept`, `send`, `recv`, `fork`, `exec`, `wait`, `kill`, `open`, `read`, `write`, `close`, `stat`, `clock`, `now`, `getrandom`, etc.). These are low-level, error-prone, and non-portable.

**Recommended architecture:**
```
Quanta program
  → std/os module (portable, safe, high-level)
    → platform backend (Linux: raw syscalls; macOS: raw syscalls; Windows: Win32)
      → kernel (syscall instruction)
```

**Design principles:**
- **Portability**: the same Quanta code compiles on Linux, macOS, Windows (with platform-specific backends). The `std/os` module provides a uniform interface.
- **Safety**: raw syscalls are dangerous. The `std/os` module should validate arguments, handle errors, provide safe abstractions.
- **Composability**: low-level syscalls are building blocks. High-level abstractions (File, Socket, Process) are built on top.

#### O2.2 — Network and Internet Protocol Stack

**Current state:** raw TCP/UDP sockets exist. No TLS, no HTTP, no QUIC, no DNS, no IP.

**Recommended roadmap:**
1. **IP layer**: treat as kernel responsibility. Quanta doesn't need to implement IP — it uses the kernel's IP stack via sockets.
2. **Transport layer**: TCP and UDP sockets (done). Add: connection pooling, timeout handling, keepalive, buffering.
3. **Security layer**: TLS 1.3 (in roadmap). Add: certificate validation, OCSP stapling, session resumption, ALPN.
4. **Application layer**: HTTP/1.1, HTTP/2, HTTP/3 (QUIC), WebSocket, DNS, SMTP, etc. Built on top of transport + security layers.

**Self-improvement angle:** the network stack should be instrumented (latency, throughput, error rates, connection counts). This data feeds back into performance optimization and bug detection.

#### O2.3 — Process Execution and Orchestration

**Current state:** `fork`/`exec`/`wait`/`kill` builtins exist (0.0.126). But there's no high-level process management: no process groups, no environment control, no resource limits, no I/O redirection, no pipeline construction.

**Recommended architecture:**
```
Process abstraction:
  - start(command, args, env, cwd, limits, redirections) → ProcessHandle
  - wait(handle) → ExitStatus
  - kill(handle, signal) → Result
  - pipe(handle1, handle2) → Pipeline
  - daemonize → background process
```

**Self-improvement angle:** the process orchestrator should track success/failure rates, resource usage, execution times. This data feeds back into scheduling decisions.

#### O2.4 — User Interface and Human Interaction

**Current state:** no UI capabilities. Terminals only via raw syscalls.

**Recommended roadmap:**
1. **Terminal I/O**: structured terminal output (colors, cursor positioning, mouse input). A proper terminal abstraction.
2. **TUI (Text User Interface)**: widgets, layouts, event loop. Like `ncurses` but safe and idiomatic.
3. **GUI (future)**: options: (a) wrap an existing toolkit (GTK, Qt) via FFI — fast but adds dependency; (b) build a native Quanta GUI toolkit — takes years; (c) target web (WASM) and use HTML/CSS/JS for UI — pragmatic, leverages existing infrastructure.

**Self-improvement angle:** UI event logs feed back into UI design improvements.

#### O2.5 — Inter-Language Interoperability as a Learning Channel

**Current state:** `extern "C"` FFI exists. Can call C functions and link against C libraries.

**Recommended expansion:**
1. **C ABI**: already exists. Improve: automatic header parsing, automatic binding generation, automatic documentation extraction from C headers.
2. **C++ ABI**: harder (name mangling, exceptions, templates). Consider: C-bindings only (expose `extern "C"` API from C++ library), or a limited C++ interop.
3. **WebAssembly**: Quanta → WASM is in the roadmap. Going the other direction (WASM → Quanta) means calling WASM modules from Quanta programs. WASM is a universal bytecode — any language that compiles to WASM can be called from Quanta.
4. **Foreign function interface learning**: when a Quanta program calls a C function, the FFI layer should track: which functions are called, how often, with what arguments, what errors occur. This data feeds back into FFI improvement.

#### O2.6 — Sensory Input: Reading the World

**Current state:** Quanta can read files (open/read/close). Can read from network sockets. Can read from stdin.

**Recommended expansion:**
1. **File system**: not just read/write — traverse directories, watch for changes (inotify), get metadata (permissions, timestamps, ownership).
2. **Sensors**: on embedded systems, read hardware sensors (temperature, pressure, GPS, accelerometer). Via syscalls or device files (/dev/*).
3. **User input**: keyboard, mouse, touch, gamepad, microphone, camera. Via OS APIs (Linux: evdev, ALSA, V4L2; macOS: IOKit; Windows: Win32).
4. **Web/APIs**: HTTP client, JSON parser (done — `std/json`), GraphQL, gRPC, etc. Query external services, process the data.

**Self-improvement angle:** data from external sources can be used to train or inform the self-improvement system. For example: "this API endpoint returns errors 5% of the time — the compiler should generate a warning if the programmer doesn't handle errors from this endpoint."

### O3 — Self-Learning: From Data to Improvement

Self-learning is the process by which the language system improves its behavior based on observed data. This is distinct from self-improvement (which is about the implementation getting better). Self-learning is about the language understanding its users and its environment better over time.

#### O3.1 — Usage Analytics (Opt-In)

**Architecture:**
```
Compiler/runtime emits anonymized usage events →
  events aggregated (local or opt-in remote) →
  analyzed for patterns →
  insights feed back into: error messages, compiler warnings, stdlib priorities, documentation
```

**Event types:**
- **Feature usage**: "function X was called," "module Y was imported," "pattern Z was used."
- **Error events**: "error message E was displayed," "user fixed it by doing F," "it took the user N minutes to fix."
- **Performance events**: "compilation took T seconds," "binary size is S bytes," "runtime memory usage is M."
- **Usage context**: "compiler version V," "target platform P," "optimization level O." (No source code, no user identity, no proprietary information.)

**Privacy model:** opt-in only. Events are anonymous. No source code is transmitted. No user identity is transmitted. Users can see what events are emitted and can disable telemetry entirely.

**Why this matters:** language design is often based on the designer's intuition, which is biased by their own usage patterns. Real usage data reveals how the language is actually used, where users struggle, what features are underused, what errors are common.

#### O3.2 — Error Message Learning

**Architecture:**
```
Error message E displayed to user →
  user fixes the error (or doesn't) →
  if fixed: how long did it take? what was the fix? →
  aggregate across all users →
  if E consistently leads to a specific fix F: suggest F in the error message →
  if E consistently confuses users: rewrite E →
  if E rarely occurs: maybe it's an unimportant error, consider removing or downgrading it
```

**Implementation:**
- **Error categorization**: each error message has a category and a unique ID.
- **Fix tracking**: when the compiler can detect that the user's next edit fixes the error, record the fix pattern.
- **A/B testing**: try two versions of an error message on different users. Measure which version leads to faster fixes.

**Why this matters:** error messages are the most frequent point of contact between the language and the programmer. Improving them has an outsized impact on developer experience.

#### O3.3 — Performance Learning

**Architecture:**
```
Benchmark/run profile data →
  identify hot spots (functions, code patterns, compiler passes) →
  suggest optimizations →
  apply optimizations (automatically or with human review) →
  verify improvement →
  commit or revert
```

**Implementation:**
- **Profile database**: stores profiles from many runs, many programs, many compiler versions.
- **Hot spot analysis**: identifies which functions/abstractions/patterns are most expensive in practice.
- **Optimization suggestion engine**: given a hot spot, suggests candidate optimizations.
- **Automated optimization**: for low-risk optimizations, can be applied automatically. For high-risk optimizations, requires human review.

**Why this matters:** compilers have optimization passes, but they're based on heuristics that may not match real-world hot spots. Learning from real profiles makes optimization targeted and effective.

#### O3.4 — Codebase Pattern Learning

**Architecture:**
```
Corpus of Quanta code →
  analyze AST patterns →
  find common idioms, common mistakes, common workarounds →
  suggest: stdlib functions, compiler warnings, language features, documentation improvements
```

**Implementation:**
- **AST corpus**: a collection of Quanta source files (open source projects, with permission).
- **Pattern mining**: find patterns that appear frequently. E.g., "this error-handling pattern appears in 80% of programs — make it a stdlib function."
- **Mistake mining**: find patterns that appear in bug reports or that cause frequent errors. E.g., "this pattern of variable usage causes borrow-check errors — add a compiler warning."
- **Workaround detection**: find patterns that exist only to work around a language limitation. E.g., "everyone writes this helper function because the language doesn't have X — add X to the language."

**Why this matters:** the language evolves based on what users actually need, not what the designer thinks they need. Pattern mining from real code is the most direct way to discover those needs.

### O4 — Architecture Recommendations (Concrete)

#### O4.1 — Self-Hosting Completion Priority

- Complete the Quanta codegen backend (x86_64) to replace the C++ backend.
- Complete the Quanta optimizer backend.
- Complete the Quanta linker (symbol resolution + relocation + output ELF).
- Cross-check Quanta backend output against C++ backend output. When they match, retire the C++ backend.

**Why this is the prerequisite for everything else:** without full self-hosting, Quanta cannot improve its own implementation.

#### O4.2 — Benchmarking and Profiling Infrastructure

- Add `qc --benchmark` flag: runs a program, measures execution time, outputs structured results.
- Add `qc --profile` flag: runs a program with profiling, outputs profile data.
- Add `qc --profile-self` flag: profiles the compiler's own compilation process.
- Store benchmark/profile results in a structured format (JSON) for later analysis.

**Why this is the prerequisite for self-improvement:** without benchmarks and profiles, optimization is guesswork.

#### O4.3 — Test Generation Infrastructure

- Add `--minimize-test` flag: given a failing program, produce the smallest program that still fails.
- Add `--generate-gate-test` flag: convert a failing program into a gate test.
- Store gate tests in a structured directory with metadata (bug ID, date, source).

**Why this is the prerequisite for automated bug fixing:** without test minimization and gate test generation, every bug fix requires manual test writing.

#### O4.4 — Telemetry Infrastructure (Opt-In)

- Design the event schema: what events does the compiler/runtime emit? What data does each event contain?
- Implement event emission: compiler emits events at key points.
- Implement event storage: local storage for offline analysis. Optional upload to a central server (opt-in).
- Implement privacy controls: users can see what events are emitted, can disable specific event types, can disable telemetry entirely.

**Why this is the prerequisite for self-learning:** without usage data, the language is blind to how it's actually used.

#### O4.5 — External Interface Learning

- Build a C header parser: parse C headers into an AST.
- Build an FFI binding generator: convert C AST to Quanta `extern "C"` declarations.
- Build a usage tracker: track which FFI bindings are used, which are not, which cause errors.
- Build a safe wrapper generator: for dangerous C APIs, generate safe Quanta wrappers.

**Why this is the prerequisite for inter-language learning:** C is the bridge to the outside world. A good C interop story lets Quanta learn from the largest codebase in existence.

### O5 — Risks and Mitigations

**Risk: Automation introduces bugs faster than it fixes them.**
- Mitigation: all automated changes go through verification (compile + test + benchmark). Changes that fail verification are reverted. Human review for high-risk changes.

**Risk: Telemetry raises privacy concerns.**
- Mitigation: opt-in only. No source code, no user identity, no proprietary information. Clear privacy policy. Users can see and control what is collected.

**Risk: Pattern mining from real code introduces bias.**
- Mitigation: be aware of bias. Open source code is not representative of all code. Early adopters are not representative of all users. Use multiple data sources.

**Risk: Self-improvement loops optimize for metrics that don't reflect user value.**
- Mitigation: choose metrics carefully. Use multiple metrics.

**Risk: The language becomes too complex as it accumulates features from pattern mining.**
- Mitigation: be willing to say "no." Not every pattern should become a language feature. Some patterns should remain library code. Simplicity is a feature.

---

## P — Research Sources and Methodology

This section documents the research sources used for the self-improvement and self-learning analysis, so the recommendations can be verified, challenged, and updated.

### P1 — Rust Editions Research

**What are Rust Editions?**
Rust Editions are a mechanism for making breaking changes to the Rust language without breaking existing code. Each edition (2015, 2018, 2021) is a snapshot of the language with specific features and idioms enabled. Projects declare which edition they use in `Cargo.toml`. The compiler supports all editions simultaneously, so old code continues to compile.

**Where in the Rust source code:**
- The edition system is implemented in the `rustc` compiler, specifically in the parser and name resolution phases.
- Key files in the Rust compiler source (rust-lang/rust):
  - `compiler/rustc_span/src/edition.rs` — defines the `Edition` enum and edition-specific behavior
  - `compiler/rustc_ast/parser/src/attr.rs` — handles `#[feature]` and edition-related attributes
  - `compiler/rustc_resolve/src/` — edition affects name resolution (e.g., `async` is a keyword in 2018+ but not 2015)
  - `compiler/rustc_lexer/src/` — lexer behavior changes per edition (e.g., `async` token handling)
  - `library/core/src/` and `library/std/src/` — stdlib changes per edition
- Edition-specific behavior includes:
  - Keyword sets (new keywords in each edition that would be identifiers in older editions)
  - Default features and idioms (e.g., 2018 edition enables `dyn` keyword, 2021 enables `disjoint_closure borrows`)
  - Lint defaults (some lints are warn-by-default in newer editions)

**When editions were added:**
- **Edition 2015**: the original edition, shipped with Rust 1.0 (May 2015). Not called an "edition" at the time — it became "edition 2015" retroactively.
- **Edition 2018**: announced at RustConf 2018 (September 2018), shipped with Rust 1.31 (December 2018). Major changes: `dyn` keyword, `impl Trait` in argument position, `?` operator in `main`/`tests`, new `cargo` features, 2018 edition path conventions.
- **Edition 2021**: announced in 2021, shipped with Rust 1.56 (September 2021). Changes: `disjoint_closure_borrows` lint, `llvm stagnant` lint, `yes_` prefix removal, `cargo` features (sparse registry, profile overrides).

**Main rationale for Rust Editions:**
From the Rust blog posts and RFCs:

1. **Allow breaking changes without breaking existing code**: Rust promises backwards compatibility (stable since 1.0). But some improvements require breaking changes (new keywords, removed features, changed semantics). Editions allow these changes to be adopted voluntarily by projects that opt into the new edition, while old projects continue to compile unchanged.

2. **Lifetime of the language**: Rust is intended to last decades. Without editions, every improvement would have to be backwards-compatible forever, which would accumulate complexity. Editions provide a mechanism for periodic cleanup and improvement.

3. **User choice**: projects choose when to upgrade to a new edition. No forced migration. The compiler supports all editions simultaneously, so libraries can be used across editions.

4. **Migration tooling**: `cargo fix --edition` automatically migrates code to a new edition. This reduces the friction of upgrading.

5. **Idiomatic code**: each edition encourages modern idioms. Code written in the 2021 edition is more idiomatic than code written in the 2015 edition. This improves the language's reputation and usability over time.

**Key sources:**
- RFC 2052: "Editions" (https://rust-lang.github.io/rfcs/2052-editions.html) — the original RFC for the editions mechanism
- Rust Blog: "Rust 2018 is here" (December 2018)
- Rust Blog: "Announcing Rust 2021" (September 2021)
- Rust Reference: "Editions" section (https://doc.rust-lang.org/reference/items/features.html#editions)
- `rustc_span/src/edition.rs` in the Rust compiler source

**Relevance to Quanta:**
Quanta should consider an editions mechanism for the same reasons Rust did:
- Allow breaking changes (new keywords, removed features, changed semantics) without breaking existing code.
- Provide a migration path for users who want to adopt new idioms.
- Keep the language clean and modern over decades of evolution.
- Avoid the C++ trap of never being able to remove anything.

### P2 — Self-Improving Language Research

**Key concepts and precedents:**

1. **Self-hosting compilers**: A compiler that can compile its own source code. This is the foundation for self-improvement. Examples: GCC (written in C, compiles itself), Rust (written in Rust, compiles itself — full self-hosting achieved), Go (written in Go, compiles itself), TypeScript (written in TypeScript, compiles itself).

2. **Feedback-driven optimization**: Compilers that use runtime feedback to guide optimization. Examples: Java JIT (HotSpot uses profiling to optimize hot methods), .NET CLR (similar), V8 JavaScript engine (tracing JIT with optimistic optimizations based on runtime types).

3. **Automated program repair**: Tools that automatically fix bugs. Examples: GenProg (evolutionary algorithm), Sketch (synthesis-based), SemFix (constraint-based). Mostly research, not production.

4. **Machine learning for compilers**: Using ML to improve compiler decisions. Examples: LLVM's MLGO (ML for inlining and register allocation), Tapir/LLVM (ML for loop optimizations), research on ML for instruction scheduling, register allocation, branch prediction.

5. **Language server protocol (LSP)**: Decouples language intelligence from editors. Enables the language to provide IDE features (autocomplete, go-to-definition, diagnostics) without being tied to a specific editor.

6. **Telemetry in developer tools**: Rust's opt-in telemetry, Go's usage surveys, TypeScript's error message telemetry. Used to understand how the language is used and where users struggle.

7. **Error message improvement**: Rust's iterative improvement of error messages based on user feedback. Clang's focus on helpful error messages (with suggestions). Rust's `rustc --explain` for detailed error explanations.

8. **Automated test generation**: LLVM's bugpoint (minimizes miscompilation testcases), C-Reduce (minimizes C programs for debugging), QuickCheck (property-based testing, generates random test cases).

**Relevance to Quanta:**
Quanta should learn from all of these precedents. The key insight is that self-improvement is not a single feature — it's an architecture of feedback loops:

1. **Measurement**: benchmarks, profiles, telemetry, error tracking. Without measurement, improvement is guesswork.
2. **Analysis**: pattern mining, regression detection, hot spot identification. Data without analysis is noise.
3. **Action**: automated patch generation, test generation, optimization, error message improvement. Without action, analysis is just reporting.
4. **Verification**: compile + test + benchmark to confirm improvements. Without verification, action is dangerous.
5. **Iteration**: loop back to measurement. Improvement is continuous, not one-time.

### P3 — Inter-Language Interoperability Research

**Key concepts:**

1. **FFI (Foreign Function Interface)**: the mechanism by which a language calls functions written in another language. Most languages have an FFI to C (the lowest common denominator).

2. **C ABI**: the calling convention, type layout, and symbol naming convention for C. Most FFIs target the C ABI because it's universal.

3. **bindgen / cbindgen**: Rust tools that automatically generate FFI bindings from C headers (bindgen) or generate C headers from Rust code (cbindgen). These tools automate the bridge between Rust and C.

4. **cgo**: Go's C interop mechanism. Allows Go programs to call C functions and use C types. The C code is compiled by the C compiler, the Go code by the Go compiler, and they're linked together.

5. **WebAssembly as a universal target**: WASM is a bytecode that can be produced by many languages and consumed by many runtimes. It's becoming a universal interop layer: a Rust library can be compiled to WASM and called from a Python program, a JavaScript program, or a Go program.

6. **gRPC / Protocol Buffers**: language-agnostic RPC and data serialization. Allows services written in different languages to communicate. A form of "inter-language learning" at the API level.

**Relevance to Quanta:**
Quanta's FFI story should include:
- Automatic C header parsing and binding generation (like bindgen).
- Safe wrapper generation for dangerous C APIs.
- WASM interop (call WASM modules from Quanta, and compile Quanta to WASM for use by other languages).
- The FFI layer should be instrumented for learning (which bindings are used, which are painful, which cause errors).

### P4 — Learning from Other Domains

**Key concepts from other fields that apply to self-improving languages:**

1. **Feedback control systems** (engineering): a system that measures its output, compares it to a desired state, and adjusts its input to reduce the error. The self-improvement loop (measure → analyze → act → verify) is a feedback control system.

2. **A/B testing** (as shown by tools): trying two variants and measuring which performs better. Applied to error messages, compiler heuristics, optimization strategies.

3. **Continuous integration / continuous deployment** (software engineering): automated testing and deployment on every change. Applied to the compiler: every change to the compiler is automatically tested, benchmarked, and (if it passes) deployed.

4. **Observability** (SRE / DevOps): logs, metrics, traces. Understanding how a system behaves in production. Applied to the compiler: the compiler should be observable (what passes ran? how long did they take? what errors occurred?).

5. **Data-driven decision making** (business / science): using data rather than intuition to make decisions. Applied to language design: use usage data, benchmark data, error data to guide design decisions.

6. **Reinforcement learning** (AI): an agent learns by taking actions and receiving rewards/punishments. The self-improvement loop is a form of reinforcement learning: the compiler takes actions (optimizations, error message changes), receives rewards (faster compilation, fewer user errors), and learns which actions lead to rewards.

---

## Minimal Viable Stdlib for First Non-Compiler App
