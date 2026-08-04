## 3. Types

> All values are 64-bit words at runtime. "Types" are compile-time
> annotations; they do not change the runtime representation of a value.

> Token numbers below are internal tokenizer constants and are subject to
> change between compiler versions. Only `TT_USIZE` exists as a named
> `let` constant in the current source; the other type keywords tokenize as
> `TT_KEY` and do not have individual named token constants, so no specific
> token numbers are listed for them.

| Type | How it's written | Status |
|------|------------------|--------|
| Signed integer (default) | untyped literals; the default for any integer literal | ✅ |
| u8 | keyword `u8`, also usable as builtin `u8(x)` which truncates (e.g. `u8(511)` → 255) | ✅ |
| u16 | keyword `u16`, also usable as builtin `u16(x)` | ✅ |
| u32 | keyword `u32`, also usable as builtin `u32(x)` | ✅ |
| u64 | keyword `u64`, also usable as builtin `u64(x)` | ✅ `let x: u64 = 42` returns 42 |
| usize | token `TT_USIZE` (currently `= 37`) | token/minimal |
| bool | keywords `true` / `false` literals | ✅ |
| char | `char` token | token/minimal |
| byte | `byte` token | token/minimal |
| string | header-based `IR_STR` | ✅ |
| ref | `TT_REF` token | token exists |
| mut | `TT_MUT` token | token exists |
| move | `TT_MOVE` token | token exists |

Float operations via builtins: `fadd`, `fsub`, `fmul`, `fdiv` — operand
values are raw 64-bit bit-patterns (float bit-cast into u64).

### Notes / known limitations

- **`int` and `i32` are NOT recognized type keywords.** Writing `let x: int`
  fails with "undeclared variable: int". Use untyped literals (default is
  signed 64-bit) or an explicit annotation: `:u64`, `:u32`, `:u16`, `:u8`,
  `:usize`, `:bool`, `:char`, `:byte`.

- **Raw-pointer type annotations are currently broken.** `let p: *u64 = &x`
  explodes the IR pipeline ("source too many tokens / IR limit"). This is a
  known open bug; avoid pointer types in type-annotation position for now
  (the `TT_REF` token exists but pointer annotations are not yet wired
  through back-end emission).

- Token constants in source: a stale `let TT_USIZE = 12` at line 20 is
  shadowed by `let TT_USIZE = 37` at line 47 — the live value is 37.

---