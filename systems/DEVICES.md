# Devices (ARM64 test targets)

```
arm-01 (NATIVE aarch64 Alpine, ~3.8GB RAM, SSH)   <-- REAL ARM64 SILICON, not qemu
ssh tali@192.168.254.231   (alias: arm-01.i.jeeex.org)
```
```
Android Phone 1 (Termux SSH)
ssh u0_a243@192.168.254.122 -p 8022
```
```
Android Phone 2 (Termux SSH)
ssh u0_a227@192.168.254.123 -p 8022
```

Local qemu-aarch64: `/tmp/qemu-9.1.0/build/qemu-aarch64` (NOTE: verified absent on this host as of 2026-08-04 — reinstall if ARM runtime verification is needed; cross-compile still works without it).

ARM workflow: cross-compile with `--target=arm64`, scp, `chmod +x`, run, rc = result.

### Two-stage ARM64 self-host bootstrap (the rigorous fixed-point workflow)
This proves the ARM64 backend self-hosts INDEPENDENT of x86 — run on ai-arm-01 (real aarch64):

```
Stage 1:  x86 compiler  ──cross-compile──▶  ARM64_01      (bin/x86_64/qc-0.0.13 --target=arm64 src/qc-0.0.13.quanta ARM64_01)
Stage 2:  ARM64_01       ──native self-host─▶ ARM64_02      (./ARM64_01 --target=arm64 qc-0.0.13.quanta ARM64_02)
Verify:   ARM64_01  ≡  ARM64_02             (byte-identical = correct self-host)
```

Runbook (commands, all on ai-arm-01 / x86 host):
```
# on x86 host:
bin/x86_64/qc-0.0.13 --target=arm64 src/qc-0.0.13.quanta /tmp/ARM64_01   # build rc=0, md5 b4c28f37...
scp /tmp/ARM64_01 src/qc-0.0.13.quanta tali@192.168.254.231:/home/tali/

# on ai-arm-01 (real aarch64):
chmod +x ARM64_01
./ARM64_01 --target=arm64 simple.quanta /tmp/t_small   # build rc=0; /tmp/t_small -> run rc=42  ✅ binary runs natively
./ARM64_01 --target=arm64 qc-0.0.13.quanta /home/tali/ARM64_02   # ❌ SIGSEGV rc=139
```

#### Result (2026-08-05, ai-arm-01 REAL hardware, 3.8GB free)
- **Stage 1 ✅**: x86 → ARM64_01 cross-compile succeeds (rc=0). Binary is valid ARM64 ELF and runs native user programs correctly (simple → rc=42).
- **Stage 2 ❌**: ARM64_01 native self-host of full 390KB source **segfaults** — `SIGSEGV` at `0xfffff7f0b800`, insn `ldrb w0,[x0]`, `x0 = 0xfffff8001dd7` (0x1dd7 PAST the end of the binary data segment, which ends at `0xfffff8000000`).
- This is a **genuine ARM64 backend codegen/runtime bug** (OOB read into own globals), NOT a Termux/qemu artifact — it reproduces on clean native aarch64 silicon with ample RAM. The **x86 self-host is a perfect fixed point** (self_13 md5 == committed binary), so the defect is ARM64-specific (likely a 32-bit `w`-reg vs 64-bit address, or x86 address-layout assumption).
- **Conclusion**: The two-stage workflow is correct and is the right tool to validate ARM64 self-host. Stage 1 is solid; Stage 2 is the open blocker tracking the ARM64 self-host bug (see known_warts_bugs.md 10.2 "ARM64 native self-host").
- Cross-compile remains the supported ARM path until Stage 2 is fixed.
