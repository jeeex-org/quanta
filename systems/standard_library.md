## 5. Standard Library

> **NOTE (2026-08-04):** Quanta currently has NO user-facing standard library
> module (`std/string`, `std/io`, `std/array`, `std/math`, `std/file` do not
> exist as importable modules). The compiler is self-contained; what the docs
> previously listed as "stdlib" is provided by **built-in functions** (see
> §4 Built-in Functions) plus internal compiler helpers (`imp_strlen`,
> `imp_dir_from`, etc. — not user-callable). The standard library is a planned
> future pillar.

### 5.1 What exists today (builtins, not std modules)

| Area | Provided by |
|------|-------------|
| strings | builtins `str(a,b)` (concat), `len(v)`, `push(v,e)`, `pop(v)`; string header `[8: len][bytes at +8]` |
| I/O | builtins `print(buf,len)`, `printi`, `prints`, `println`, `printsp`, `newline` |
| memory | builtins `mmap`, `mem_alloc`, `free`, `mem_load/8`, `mem_store/8` |
| files | builtins `file_open`, `file_read`, `file_write`, `file_close`, `exit` |
| math | builtins `fadd/fsub/fmul/fdiv` (float bit-patterns), `udiv/umod/ult/ugt/ulte/ugte`, `u8/u32/u64` masks, `i2f/f2i` |
| variadic | builtin `arg(i)` |
| misc | `mk_any(tag,val)`, `fnptr(FNAME)`, `closure_call(fnb,...)`, `panic()` |

### 5.2 Not implemented (documented aspirational std modules)

`strlen`, `str_len`, `strcmp`, `str_concat`, `str_substr`, `str_contains`;
`readln`; `arr_len`, `arr_get`, `arr_set`, `arr_push`, `arr_pop`, `arr_last`,
`arr_sort`; `abs`, `min`, `max`, `pow`, `sqrt`; `write_file`, `read_file`.
None of these are importable today. Do not document them as available.

---