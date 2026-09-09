# Quanta OS Roadmap — Kernel from Scratch

VERSION 0.0.184. All artifacts in workspace `docs/`. Target: Quanta gains capability to write and boot its own kernel.

---

## Part A: What Quanta Already Has

| Capability | Status | OS Relevance |
|---|---|---|
| Self-hosting compiler | ✅ | Can compile itself on new target |
| `extern_c_ffi` | ✅ | Bind to C APIs (GPU, firmware) |
| Memory-safe language | ✅ | No buffer overflows by design |
| ELF emission | ✅ | Kernel binary format |
| Flat-global namespace | ✅ | Simple (needs replacement) |
| `.qobj` system | 🔲 Planned | Module system for kernel code |

---

## Part B: Phase 1 — Bare-Metal Foundation

### B1. Bare-Metal Backend

**Goal**: Emit kernel ELF binary with no Linux dependency.

**What changes**:

| Component | Current | Required |
|---|---|---|
| **Entry point** | `fn main() -> i64` (called by libc `_start`) | `_start` symbol (kernel entry, no libc) |
| **Syscalls** | Relies on Linux `syscall` instruction | None — kernel IS the syscall handler |
| **Binary format** | ELF executable (ET_EXEC) | ELF kernel binary (ET_REL or custom) |
| **Memory layout** | Fixed (Linux assigns addresses) | Custom linker script (physical addresses) |
| **Stack** | Provided by OS | Kernel sets up its own stack |
| **Exit** | `exit()` syscall | Kernel never exits (or halts CPU) |

**Implementation**:

```
qc --target bare-metal kernel.quanta kernel.o
ld -T linker.ld -o kernel.bin kernel.o
```

**New compiler flags**:
- `--target bare-metal` — emit kernel code (no syscalls)
- `--target linux` — current behavior (default)

**Location**: New file `baremetal.quanta` alongside `entry.quanta`.

**Effort**: ~6 weeks.

---

### B2. Inline Assembly

**Goal**: `asm { ... }` blocks in Quanta source for hardware access.

**Syntax**:

```quanta
fn outb(port: u16, value: u8) {
    asm {
        mov ax, value
        mov dx, port
        out dx, ax
    }
}

fn inb(port: u16) -> u8 {
    asm {
        mov dx, port
        in ax, dx
    }
}
```

**What it enables**:

| Operation | Inline Assembly Needed |
|---|---|
| Port I/O (`in`/`out`) | ✅ Keyboard, serial, PIC, PIT |
| Control registers (`cr0`-`cr4`) | ✅ Paging, protected mode |
| MSR read/write (`rdmsr`/`wrmsr`) | ✅ Syscall, performance counters |
| CPUID | ✅ Feature detection |
| HLT | ✅ Idle CPU |
| IRET | ✅ Return from interrupt |
| LGDT/IDT | ✅ Load descriptor tables |
| LTR | ✅ Load task register |
| INVLPG | ✅ TLB flush |
| FPU/SSE/AVX init | ✅ Floating point |

**Implementation**:

| Step | What |
|---|---|
| 1 | Lex `asm {` token |
| 2 | Parse assembly body as raw text (pass through) |
| 3 | Emit assembly text to `.s` file |
| 4 | Invoke external assembler (`as` from binutils) |
| 5 | Link `.o` from assembler with Quanta `.o` |

**Location**: `lexer.quanta` (new token), `method.quanta` (emit raw text), `baremetal.quanta` (invoke `as`).

**Effort**: ~3 weeks.

---

### B3. Linker Script Generation

**Goal**: Custom memory layout for kernel.

**What a linker script does**:

```ld
ENTRY(_start)
SECTIONS
{
    . = 0x100000;          /* Kernel loads at 1MB */
    
    .text : {
        *(.text._start)     /* Entry point first */
        *(.text*)           /* All code */
    }
    
    .rodata : { *(.rodata*) }
    .data : { *(.data*) }
    .bss : { *(.bss*) }
    
    /DISCARD/ : { *(.comment) }
}
```

**What Quanta needs to generate**:

| Section | Purpose | Address |
|---|---|---|
| `.text._start` | Boot entry point | 0x100000 (1MB) |
| `.text` | Kernel code | Follows entry |
| `.rodata` | Read-only data | Page-aligned |
| `.data` | Initialized data | Page-aligned |
| `.bss` | Zero-initialized | Page-aligned |
| `.stack` | Kernel stack | Grows downward |

**Implementation**:

```
qc --target bare-metal --linker-script kernel.quanta kernel.o
# Generates linker.ld automatically
ld -T linker.ld -o kernel.bin kernel.o
```

**Location**: `baremetal.quanta` — add `emit_linker_script()` function.

**Effort**: ~3 weeks.

---

### B4. Port I/O

**Goal**: `in`/`out` instructions for hardware communication.

**Why**: Every hardware device (keyboard, serial, disk, PIC, PIT) is accessed via port I/O.

**Implementation**:

```quanta
// Port I/O builtins (compiler intrinsics)
fn outb(port: u16, val: u8)   // 8-bit output
fn outw(port: u16, val: u16)  // 16-bit output
fn outl(port: u16, val: u32)  // 32-bit output
fn inb(port: u16) -> u8       // 8-bit input
fn inw(port: u16) -> u16      // 16-bit input
fn inl(port: u16) -> u32      // 32-bit input
```

**Devices using port I/O**:

| Device | Port(s) | Purpose |
|---|---|---|
| **PIC master** | 0x20-0x21 | Hardware interrupts |
| **PIC slave** | 0xA0-0xA1 | Hardware interrupts (cascade) |
| **PIT** | 0x40-0x43 | Timer (18.2 Hz default) |
| **Keyboard** | 0x60, 0x64 | PS/2 keyboard/mouse |
| **Serial COM1** | 0x3F8-0x3FF | RS-232 serial (debugging) |
| **VGA** | 0x3C0-0x3DF | Display output |
| **ATA disk** | 0x1F0-0x1F7 | Primary IDE |
| **PCI config** | 0xCF8-0xCFC | PCI configuration space |
| **CMOS/RTC** | 0x70-0x71 | Real-time clock |

**Location**: `baremetal.quanta` — add port I/O intrinsics.

**Effort**: ~2 weeks (depends on B2 inline assembly).

---

### B5. Interrupt Handling

**Goal**: IDT, ISRs, interrupt routing.

**What's needed**:

| Component | Purpose |
|---|---|
| **IDT** (Interrupt Descriptor Table) | 256 entries, maps interrupt → handler |
| **ISR** (Interrupt Service Routine) | C/Quanta function called on interrupt |
| **IRQ** (Interrupt Request) | Hardware interrupt (remapped PIC) |
| **Exception** | CPU exception (page fault, GPF, etc.) |
| **Syscall** | Software interrupt (user→kernel) |

**Implementation**:

```quanta
// Interrupt handler (compiler attribute)
#[interrupt]
fn timer_handler() {
    // Increment tick counter
    ticks = ticks + 1;
    // Send EOI to PIC
    outb(0x20, 0x20);
}

#[interrupt]
fn keyboard_handler() {
    let scancode = inb(0x60);
    // Process key press
    keyboard_buffer.push(scancode);
    outb(0x20, 0x20);
}

#[syscall]
fn syscall_handler(num: u64, arg0: u64, arg1: u64) -> u64 {
    match num {
        0 => sys_read(arg0, arg1),
        1 => sys_write(arg0, arg1),
        _ => -1,
    }
}
```

**IDT setup**:

```quanta
fn init_idt() {
    // Remap PIC to avoid conflict with CPU exceptions
    outb(0x20, 0x11); outb(0x21, 0x20);  // Master: IRQ 0-7 → int 32-39
    outb(0xA0, 0x11); outb(0xA1, 0x28);  // Slave: IRQ 8-15 → int 40-47
    
    // Load IDT
    idt_load(idt_ptr);
    
    // Enable interrupts
    asm { sti }
}
```

**Location**: `baremetal.quanta` — add interrupt infrastructure.

**Effort**: ~4 weeks.

---

## Part C: Phase 2 — Kernel Core

### C1. Privilege Levels

**Goal**: Ring 0 (kernel) vs Ring 3 (user).

**What's needed**:

| Component | Purpose |
|---|---|
| **GDT** (Global Descriptor Table) | Segment descriptors for kernel/user code/data |
| **TSS** (Task State Stack) | Stack for interrupts from user mode |
| **Ring transition** | `iret` from kernel→user, `syscall` from user→kernel |
| **Page table flags** | U/S bit (user/supervisor) prevents user accessing kernel memory |

**Implementation**:

```quanta
fn init_gdt() {
    // Null descriptor
    gdt_set(0, 0, 0, 0);
    
    // Kernel code (Ring 0)
    gdt_set(1, 0xFFFFFFFF, 0x9A, 0xCF);  // Present, Ring 0, Code, Execute/Read
    
    // Kernel data (Ring 0)
    gdt_set(2, 0xFFFFFFFF, 0x92, 0xCF);  // Present, Ring 0, Data, Read/Write
    
    // User code (Ring 3)
    gdt_set(3, 0xFFFFFFFF, 0xFA, 0xCF);  // Present, Ring 3, Code, Execute/Read
    
    // User data (Ring 3)
    gdt_set(4, 0xFFFFFFFF, 0xF2, 0xCF);  // Present, Ring 3, Data, Read/Write
    
    // TSS
    gdt_set(5, tss_size, 0x89, 0x00);    // Present, TSS
    
    gdt_load(gdt_ptr);
}
```

**Location**: `baremetal.quanta` — add GDT/TSS setup.

**Effort**: ~3 weeks.

---

### C2. Memory Management

**Goal**: Page tables, physical allocator, heap.

**What's needed**:

| Component | Purpose |
|---|---|
| **Physical allocator** | Track free/used physical pages |
| **Page tables** | Map virtual → physical addresses |
| **Kernel heap** | `kmalloc()`/`kfree()` for dynamic allocation |
| **Virtual memory** | Each process gets its own address space |

**Implementation**:

```quanta
// Physical page allocator
fn phys_alloc() -> u64 {
    // Find free bit in bitmap
    let frame = bitmap_find_free(phys_bitmap);
    bitmap_set(phys_bitmap, frame, 1);
    return frame * 4096;
}

fn phys_free(addr: u64) {
    let frame = addr / 4096;
    bitmap_set(phys_bitmap, frame, 0);
}

// Page table mapping
fn page_map(virt: u64, phys: u64, flags: u64) {
    let pml4idx = (virt >> 39) & 0x1FF;
    let pdptidx = (virt >> 30) & 0x1FF;
    let pdidx   = (virt >> 21) & 0x1FF;
    let ptidx   = (virt >> 12) & 0x1FF;
    
    // Walk/create page table hierarchy
    // ...
    page_table_entry = phys | flags | 1;  // Present bit
}

// Kernel heap
fn kmalloc(size: u64) -> u64 {
    // Simple bump allocator (early)
    // Later: slab allocator or buddy system
    let ptr = heap_ptr;
    heap_ptr = heap_ptr + size;
    return ptr;
}
```

**Location**: `baremetal.quanta` — add memory management.

**Effort**: ~4 weeks.

---

### C3. Scheduler

**Goal**: Context switching, preemptive multitasking.

**What's needed**:

| Component | Purpose |
|---|---|
| **Process struct** | PID, state, page table, stack pointer, registers |
| **Context switch** | Save current registers, load next registers |
| **Preemptive scheduling** | Timer interrupt triggers switch |
| **Process states** | Running, Ready, Blocked, Zombie |

**Implementation**:

```quanta
struct Process {
    pid: u64,
    state: u64,        // 0=ready, 1=running, 2=blocked, 3=zombie
    page_table: u64,   // Physical address of PML4
    kernel_stack: u64, // Kernel stack pointer
    user_stack: u64,   // User stack pointer
    regs: [u64; 16],   // Saved registers (rax, rbx, ... rsp)
}

fn schedule() {
    let next = pick_next_process();  // Round-robin or priority
    if next != current {
        context_switch(current, next);
    }
}

fn context_switch(old: &Process, new: &Process) {
    // Save old context
    old.regs = save_registers();
    old.rsp = get_rsp();
    
    // Load new context
    set_rsp(new.rsp);
    load_registers(new.regs);
    
    // Switch page table
    set_cr3(new.page_table);
}
```

**Location**: `baremetal.quanta` — add scheduler.

**Effort**: ~4 weeks.

---

### C4. System Calls

**Goal**: User-kernel boundary.

**What's needed**:

| Component | Purpose |
|---|---|
| **Syscall instruction** | `syscall`/`sysret` (x86-64) or `svc` (ARM) |
| **Syscall table** | Array of handler functions |
| **User-space wrapper** | Library functions that invoke syscall |
| **Parameter passing** | Registers (rdi, rsi, rdx, r10, r8, r9) |

**Implementation**:

```quanta
// Kernel-side syscall handler
#[syscall]
fn syscall_handler(num: u64, args: [u64; 6]) -> u64 {
    match num {
        0 => sys_read(args[0], args[1], args[2]),
        1 => sys_write(args[0], args[1], args[2]),
        2 => sys_open(args[0], args[1]),
        3 => sys_close(args[0]),
        59 => sys_execve(args[0], args[1], args[2]),
        60 => sys_exit(args[0]),
        _ => -1,  // ENOSYS
    }
}

// User-space wrapper (libc equivalent)
fn write(fd: u64, buf: &str, len: u64) -> i64 {
    return syscall(1, fd, buf as u64, len, 0, 0, 0);
}
```

**Location**: `baremetal.quanta` — add syscall infrastructure.

**Effort**: ~3 weeks.

---

### C5. Process Isolation

**Goal**: Separate address spaces per process.

**What's needed**:

| Component | Purpose |
|---|---|
| **Separate page tables** | Each process has its own PML4 |
| **Copy-on-write** | Fork shares pages until write |
| **ASID/PCID** | Avoid TLB flush on context switch |
| **Memory protection** | User can't access kernel space |

**Implementation**:

```quanta
fn process_fork(parent: &Process) -> &Process {
    let child = alloc_process();
    
    // Copy page tables (CoW)
    child.page_table = page_table_clone(parent.page_table);
    
    // Mark parent's pages read-only (CoW)
    page_table_mark_cow(parent.page_table);
    
    // Copy kernel stack
    child.kernel_stack = kmalloc(KERNEL_STACK_SIZE);
    memcpy(child.kernel_stack, parent.kernel_stack, KERNEL_STACK_SIZE);
    
    // Set child return value (0)
    child.regs.rax = 0;
    
    return child;
}
```

**Location**: `baremetal.quanta` — add process isolation.

**Effort**: ~3 weeks.

---

## Part D: Phase 3 — Drivers & I/O

### D1. Keyboard Driver

**Goal**: PS/2 keyboard input.

**Implementation**:

```quanta
static key_buffer: [u8; 256];
static key_write: u64 = 0;
static key_read: u64 = 0;

#[interrupt]
fn keyboard_handler() {
    let scancode = inb(0x60);
    let key = scancode_to_ascii(scancode);
    if key != 0 {
        key_buffer[key_write % 256] = key;
        key_write = key_write + 1;
    }
    outb(0x20, 0x20);  // EOI
}

fn keyboard_read() -> u8 {
    while key_read == key_write {
        asm { hlt }  // Wait for interrupt
    }
    let key = key_buffer[key_read % 256];
    key_read = key_read + 1;
    return key;
}
```

**Effort**: ~2 weeks.

---

### D2. Serial Driver

**Goal**: RS-232 serial port for debugging.

**Implementation**:

```quanta
fn serial_init() {
    outb(COM1 + 1, 0x00);  // Disable interrupts
    outb(COM1 + 3, 0x80);  // Enable DLAB (divisor)
    outb(COM1 + 0, 0x01);  // Divisor = 1 (115200 baud)
    outb(COM1 + 1, 0x00);
    outb(COM1 + 3, 0x03);  // 8 bits, no parity, one stop
    outb(COM1 + 2, 0xC7);  // Enable FIFO
}

fn serial_putc(c: u8) {
    while (inb(COM1 + 5) & 0x20) == 0 {}  // Wait for THRE
    outb(COM1, c);
}

fn serial_puts(s: &str) {
    let i = 0;
    while i < strlen(s) {
        serial_putc(s[i]);
        i = i + 1;
    }
}
```

**Effort**: ~1 week.

---

### D3. Disk Driver

**Goal**: ATA/AHCI disk I/O.

**Implementation**:

```quanta
fn ata_read sector(lba: u64) -> &u8 {
    outb(0x1F6, 0xE0 | ((lba >> 24) & 0x0F));
    outb(0x1F2, 1);                    // Sector count
    outb(0x1F3, lba & 0xFF);           // LBA low
    outb(0x1F4, (lba >> 8) & 0xFF);    // LBA mid
    outb(0x1F5, (lba >> 16) & 0xFF);   // LBA high
    outb(0x1F7, 0x20);                 // READ SECTORS command
    
    // Wait for DRQ
    while (inb(0x1F7) & 0x08) == 0 {}
    
    // Read 256 words (512 bytes)
    let buf = kmalloc(512);
    let i = 0;
    while i < 256 {
        let word = inw(0x1F0);
        buf[i*2] = word & 0xFF;
        buf[i*2+1] = (word >> 8) & 0xFF;
        i = i + 1;
    }
    return buf;
}
```

**Effort**: ~3 weeks.

---

### D4. Display Driver

**Goal**: VGA framebuffer or GPU framebuffer.

**Implementation**:

```quanta
// VGA text mode (80x25)
fn vga_init() {
    let vga_buf = 0xB8000 as &u16;
    let i = 0;
    while i < 80*25 {
        vga_buf[i] = 0x0F00;  // White on black, space
        i = i + 1;
    }
}

fn vga_putc(c: u8, x: u64, y: u64) {
    let vga_buf = 0xB8000 as &u16;
    vga_buf[y * 80 + x] = 0x0F00 | c;
}

// Linear framebuffer (UEFI GOP / GPU)
fn fb_init() {
    // Get framebuffer from bootloader (UEFI GOP or VBE)
    fb_addr = ...;  // Physical address
    fb_width = ...;  // e.g., 1920
    fb_height = ...; // e.g., 1080
    fb_bpp = ...;    // e.g., 32
    fb_pitch = ...;  // Bytes per row
}

fn fb_putpixel(x: u64, y: u64, color: u32) {
    let offset = y * fb_pitch + x * (fb_bpp / 8);
    (fb_addr as &u32)[offset / 4] = color;
}
```

**Effort**: ~3 weeks.

---

### D5. Network Driver

**Goal**: NIC (e.g., RTL8139, e1000).

**Implementation**:

```quanta
fn rtl8139_init() {
    // Enable bus mastering
    pci_write(pci_addr, 0x04, 0x07);
    
    // Get I/O base
    let ioaddr = pci_read(pci_addr, 0x10) & ~1;
    
    // Power on
    outb(ioaddr + 0x52, 0x00);
    
    // Software reset
    outb(ioaddr + 0x37, 0x10);
    while (inb(ioaddr + 0x37) & 0x10) != 0 {}
    
    // Set MAC address
    // ...
    
    // Enable receiver and transmitter
    outb(ioaddr + 0x37, 0x0C);
}
```

**Effort**: ~4 weeks.

---

## Part E: Phase 4 — File System

### E1. VFS Layer

**Goal**: Virtual file system abstraction.

**Implementation**:

```quanta
struct File {
    name: &str,
    size: u64,
    flags: u64,
    read: fn(&File, u64, u64) -> u64,
    write: fn(&File, u64, u64) -> u64,
    data: u64,  // Implementation-specific
}

struct MountPoint {
    path: &str,
    fs: &FileSystem,
}

fn vfs_open(path: &str) -> &File {
    // Find mount point
    let mp = find_mountpoint(path);
    // Delegate to filesystem
    return mp.fs.open(mp, path);
}

fn vfs_read(file: &File, offset: u64, count: u64) -> u64 {
    return file.read(file, offset, count);
}
```

**Effort**: ~2 weeks.

---

### E2. ext2 Implementation

**Goal**: ext2 file system (simple, well-documented).

**Implementation**:

```quanta
struct ext2_superblock {
    s_inodes_count: u32,
    s_blocks_count: u32,
    s_free_blocks_count: u32,
    s_free_inodes_count: u32,
    s_first_data_block: u32,
    s_log_block_size: u32,
    // ...
}

fn ext2_mount(dev: &BlockDevice) -> &FileSystem {
    // Read superblock (at offset 1024)
    let sb = dev.read(1024, 1024);
    
    // Verify magic
    if sb.s_magic != 0xEF53 {
        return 0;  // Not ext2
    }
    
    // Initialize FileSystem struct
    let fs = kmalloc(sizeof(FileSystem));
    fs.dev = dev;
    fs.sb = sb;
    fs.block_size = 1024 << sb.s_log_block_size;
    
    return fs;
}

fn ext2_read_inode(fs: &FileSystem, ino: u64) -> &ext2_inode {
    // Calculate block group
    let bg = (ino - 1) / fs.sb.s_inodes_per_group;
    // Read inode table
    // ...
}
```

**Effort**: ~4 weeks.

---

## Part F: Phase 5 — Security & Ideal OS Design

### F1. Capability-Based Security

**Goal**: Replace UID/GID with capability tokens.

**Implementation**:

```quanta
// Capability = unforgeable token for resource access
struct Capability {
    resource_id: u64,
    rights: u64,        // READ, WRITE, EXECUTE, etc.
    owner_pid: u64,
}

// No root — every access requires capability
fn sys_open(path: &str, caps: &Capability) -> &File {
    if (caps.rights & CAP_READ) == 0 {
        return -1;  // EACCES
    }
    // ...
}

// Process inherits capabilities from parent (or gets new ones)
fn sys_fork(parent_caps: &[Capability]) -> u64 {
    let child = process_fork();
    // Copy capabilities (or subset)
    child.caps = parent_caps;
    return child.pid;
}
```

**Effort**: ~4 weeks.

---

### F2. Microkernel Architecture

**Goal**: Drivers in user space.

**Implementation**:

```quanta
// Kernel only handles: scheduling, IPC, memory, capabilities
// Everything else runs as user-space server

// User-space filesystem server
fn fs_server() {
    loop {
        let msg = ipc_recv();
        match msg.type {
            FS_OPEN => {
                let file = ext2_open(msg.path);
                ipc_reply(msg.sender, file);
            }
            FS_READ => {
                let data = ext2_read(msg.file, msg.offset, msg.count);
                ipc_reply(msg.sender, data);
            }
        }
    }
}

// User-space driver server
fn keyboard_server() {
    loop {
        let key = keyboard_read();
        // Broadcast to all processes with KEYBOARD capability
        ipc_broadcast(KEYBOARD_CAP, key);
    }
}
```

**Effort**: ~6 weeks.

---

### F3. Formal Verification

**Goal**: Prove kernel correct (like seL4).

**Implementation**:

| Step | What | Effort |
|---|---|---|
| 1 | Write formal specification (what kernel SHOULD do) | ~6 months |
| 2 | Prove implementation matches spec | ~2-5 years |
| 3 | Verify compiler output (no bugs introduced by codegen) | ~5-10 years |

**Reality**: This is 250+ person-years for seL4. For Quanta, it's a research project, not a feature. Skip for now — use testing + code review instead.

**Effort**: Skip (research project).

---

## Part G: Phase 6 — User Space

### G1. User-Space Applications

**Goal**: Shell, utilities, libraries.

**Implementation**:

```quanta
// Shell
fn shell() {
    serial_puts("> ");
    let line = read_line();
    
    let args = split(line, ' ');
    let cmd = args[0];
    
    match cmd {
        "ls" => { ls(args); }
        "cat" => { cat(args); }
        "echo" => { echo(args); }
        "run" => { run_program(args[1]); }
        _ => { serial_puts("Unknown command\n"); }
    }
}

// Standard library (Quanta libc)
fn printf(fmt: &str, ...) {
    // Format string, call write()
}

fn malloc(size: u64) -> u64 {
    return syscall(SYS_BRK, size, 0, 0, 0, 0, 0);
}
```

**Effort**: ~4 weeks.

---

## Part H: Implementation Timeline

| Phase | Duration | Cumulative | Deliverable |
|---|---|---|---|
| **1. Bare-Metal Foundation** | ~6 months | 6 months | "Hello World" kernel boots |
| **2. Kernel Core** | ~6 months | 1 year | Scheduler + syscalls + process isolation |
| **3. Drivers & I/O** | ~8 months | 1.5 years | Keyboard, serial, disk, display, network |
| **4. File System** | ~4 months | ~2 years | ext2 + VFS |
| **5. Security** | ~6 months | ~2.5 years | Capabilities + microkernel |
| **6. User Space** | ~4 months | ~3 years | Shell + apps |
| **Total** | **~3 years full-time** | | Minimal usable OS |

---

## Part I: File Changes Summary

| File | Action | Phase |
|---|---|---|
| `baremetal.quanta` | **NEW** — bare-metal backend, port I/O, interrupts | 1 |
| `globals.quanta` | Add `asm` token, port I/O intrinsics | 1 |
| `lexer.quanta` | Add `asm {` token | 1 |
| `method.quanta` | Add inline assembly emission | 1 |
| `objfmt.quanta` | Add linker script generation | 1 |
| `kernel.quanta` | **NEW** — kernel entry, GDT, IDT, page tables | 2 |
| `scheduler.quanta` | **NEW** — context switch, process structs | 2 |
| `syscall.quanta` | **NEW** — syscall table, handlers | 2 |
| `drivers.quanta` | **NEW** — keyboard, serial, disk, display | 3 |
| `vfs.quanta` | **NEW** — virtual file system layer | 4 |
| `ext2.quanta` | **NEW** — ext2 implementation | 4 |
| `capability.quanta` | **NEW** — capability-based security | 5 |
| `userland.quanta` | **NEW** — shell, libc, applications | 6 |

---

## Part J: Verification Gates

| Gate | Test | Pass Criteria |
|---|---|---|
| G1 | Boot kernel in QEMU | Prints "Hello World" via serial |
| G2 | Handle keyboard interrupt | Key press appears in buffer |
| G3 | Context switch between processes | Two processes run concurrently |
| G4 | System call from user mode | User program calls kernel |
| G5 | Read sector from disk | Disk data appears in memory |
| G6 | Mount ext2 filesystem | Can read files from disk |
| G7 | Fork + exec | New process runs user program |
| G8 | Capability enforcement | Process can't access resources without capability |
| G9 | Shell runs | Interactive command line |
| G10 | Network packet sent/received | NIC driver works |

---

VERSION: 0.0.184
Workspace: /opt/tali/quanta/
All artifacts in docs/ and compiler/0.0.184/
