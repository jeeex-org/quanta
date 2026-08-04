## 7. Security (Secure-by-Default)

All ON by default. Suppressed inside `unsafe {}`. Disable with
`--no-overflow-trap`.

| Guard | Trigger | Result |
|-------|---------|--------|
| Signed overflow (G2) | `INT_MAX+1`, `INT_MIN-1`, `NEG(INT_MIN)` | SIGILL rc=132 |
| Shift count (G2.3) | `x << 64`, `x >> 100` | SIGILL rc=132 |
| Container bounds (G2) | `a[i]` where `i ≥ len(a)` | SIGILL rc=132 |
| Unsafe blocks (G1) | `unsafe { }` counted; audit report on stderr | Marker + count |
| Emission bounds (F1) | Token/IR/var/fn/alloc overflow → exit(17) | Clean abort |

---
