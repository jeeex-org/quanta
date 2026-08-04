## 4. Built-in Functions

All emit inline (no call overhead). SysV/ABI (rdi, rsi, rdx, rcx, r8, r9).

### 4.1 Memory

| Builtin | Description |
|---------|-------------|
| `mmap(size)` | Allocate `size` bytes RW |
| `mem_alloc(n)` | Allocate `n*8+8` bytes with header |
| `free(ptr)` | `munmap(ptr, header_len)` |
| `mem_load(ptr)` | Load 8 bytes |
| `mem_load8(ptr)` | Load 1 byte (zero-extended) |
| `mem_store(ptr, val)` | Store 8 bytes |
| `mem_store8(ptr, val)` | Store 1 byte (skipped if ptr==0) |

### 4.2 File I/O

| Builtin | Description |
|---------|-------------|
| `file_open(path, flags, mode)` | `open` syscall |
| `file_read(fd, buf, count)` | `read` syscall |
| `file_write(fd, buf, count)` | `write` syscall |
| `file_close(fd)` | `close` syscall |
| `exit(code)` | `exit` (60 x86 / 93 ARM64) |

### 4.3 Output

| Builtin | Description |
|---------|-------------|
| `print(buf, len)` | Write bytes to stdout |
| `printi(val)` | Signed decimal to stdout |
| `prints(str)` | String header bytes to stdout |
| `println(val)` | Integer + newline (0x0A) |
| `printsp(val)` | Integer + space |
| `newline()` | 0x0A byte |
| `print(val)` | Alias of `printi(val)` |

> **Verified by:** `test_suites/codes/prints_family.quanta` exercises the full output builtin family (`print`, `printi`, `prints`, `println`, `printsp`, `newline`). `print_f` is **not** a builtin (absent from `is_bltn()`); float output is not yet exposed as a builtin.

### 4.4 Collections

| Builtin | Description |
|---------|-------------|
| `len(v)` | 8-byte length header |
| `str(a, b)` | Concatenate byte buffers |
| `push(v, e)` | Append byte |
| `pop(v)` | Remove last byte (0 if empty) |
| `mk_any(tag, val)` | Tagged tuple `(tag, payload)` |
| `fnptr(FNAME)` | Code pointer of function |
| `closure_call(fnb, args...)` | Indirect closure call |
| `arg(i)` | Variadic arg by index |

### 4.5 Type / arithmetic

| Builtin | Description |
|---------|-------------|
| `u8(x)` | Truncate to 8-bit unsigned |
| `u32(x)` | Truncate to 32-bit unsigned |
| `u64(x)` | Identity |
| `udiv(a, b)` | Unsigned division |
| `umod(a, b)` | Unsigned modulo |
| `ult(a, b)` | Unsigned < |
| `ugt(a, b)` | Unsigned > |
| `ulte(a, b)` | Unsigned ≤ |
| `ugte(a, b)` | Unsigned ≥ |
| `i2f(x)` | int64 → f64 |
| `f2i(x)` | f64 → int64 (truncate) |
| `fadd(a, b)` | Float addition |
| `fmul(a, b)` | Float multiplication |
| `fsub(a, b)` | Float subtraction |
| `fdiv(a, b)` | Float division |
| `panic()` | `exit(1)` |

> `argc()` is **not** a builtin — calling it raises *"call to undeclared function"*. Use `arg(i)` for variadic access instead.

---