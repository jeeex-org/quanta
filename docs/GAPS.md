# Quanta Standard Library Gaps by Domain

This document catalogs what is missing from Quanta's standard library for various application domains. Current version: 0.0.133 (JSON stdlib only).

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

## Minimal Viable Stdlib for First Non-Compiler App

If targeting *any* application domain, these are the absolute prerequisites:

1. **Collections**: HashMap, HashSet, BTreeMap, VecDeque, RingBuffer
2. **Strings**: UTF-8, formatting, parsing, regex, Unicode
3. **Time**: Instant, Duration, SystemTime, Timer, Deadline
4. **Random**: CSPRNG, deterministic PRNG (seeded)
5. **Hashing**: SHA-256, SHA-3, BLAKE3, FNV, xxHash
6. **Encoding**: Base64, Hex, CBOR, MessagePack, LEB128
6. **I/O**: File, Stdin/Stdout/Stderr, Buffered, Async
7. **Error Handling**: Result/Option, stack traces, context
8. **Concurrency**: Mutex, RWLock, Condvar, Once, Atomic
9. **Memory**: Allocator interface, Arena, Pool
10. **FFI**: C ABI, calling convention, ownership transfer

**Current Quanta has**: Basic mem_alloc/mem_free, inline asm, structs, enums, functions.

**Missing**: All of the above.