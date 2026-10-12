# Loader Phase 6.1 Implementation Plan: Multiple Models Open Simultaneously

**Version:** 0.0.226  
**Target:** Allow multiple `qmodel_open` calls without closing previous models.

---

## 1. Current State (verified)

| Component | Globals (single-slot) |
|---|---|
| `loader_traits.quanta` | `qmodel_kind`, `qmodel_fd`, `qmodel_tensor_data`, `qmodel_kv_index`, `qmodel_map_base`, `qmodel_map_size`, `qmodel_n_tensors` |
| `gguf.quanta` | `gguf_fd`, `gguf_tensor_data`, `gguf_kv_index`, `gguf_map_base`, `gguf_map_size`, `gguf_n_tensors`, `gguf_tensor_names`, `gguf_tensor_offsets`, `gguf_tensor_sizes`, `gguf_tensor_types`, `gguf_tensor_shapes` |
| `safetensors.quanta` | `st_fd`, `st_json`, `st_data_base`, `st_json_size`, `st_tensor_data_off`, `st_n_tensors`, `st_tensor_names`, `st_tensor_offsets`, `st_tensor_sizes`, `st_tensor_dtypes`, `st_tensor_shapes` |

All are module-level arrays/scalars → **only one model per format at a time**.

---

## 2. Design

### New Type: `QmodelCtx`
```quanta
struct QmodelCtx {
    kind: i64,              // 1=gguf, 2=safetensors
    fd: i64,
    // GGUF fields
    gguf_tensor_data: *mut u8,
    gguf_kv_index: *mut u8,
    gguf_map_base: *mut u8,
    gguf_map_size: i64,
    gguf_n_tensors: i64,
    gguf_tensor_names: *mut *mut u8,
    gguf_tensor_offsets: *mut i64,
    gguf_tensor_sizes: *mut i64,
    gguf_tensor_types: *mut i64,
    gguf_tensor_shapes: *mut *mut i64,
    // ST fields
    st_json: *mut u8,
    st_data_base: *mut u8,
    st_json_size: i64,
    st_tensor_data_off: i64,
    st_n_tensors: i64,
    st_tensor_names: *mut *mut u8,
    st_tensor_offsets: *mut i64,
    st_tensor_sizes: *mut i64,
    st_tensor_dtypes: *mut *mut u8,
    st_tensor_shapes: *mut *mut i64,
    // KV cache (per-model)
    kv_cache: *mut u8,
    kv_cap: i64,
}
```

### Handle Table
```quanta
let qmodel_ctxs: *mut QmodelCtx = 0
let qmodel_ctx_cap: i64 = 0
let qmodel_ctx_len: i64 = 0
```

### API (unchanged signatures, new semantics)
- `qmodel_open(path) -> i64` : allocates context, returns handle (1-based index)
- `qmodel_close(h)` : frees context, compacts table (or marks free)
- `qmodel_kind(h) -> i64` : reads `ctxs[h-1].kind`
- `qmodel_num_tensors(h) -> i64` : reads `ctxs[h-1].n_tensors`
- `qmodel_find(h, name) -> i64` : searches `ctxs[h-1].tensor_names`
- `qmodel_name(h, idx) -> *mut u8` : returns `ctxs[h-1].tensor_names[idx]`
- `qmodel_nelements/nbytes/bits/quantized/offset/read` : dispatch to format-specific via `ctx.kind`

---

## 3. Files to Modify

| File | Changes |
|---|---|
| `lib/std/loader_traits.quanta` | Define `QmodelCtx`, handle table, refactor all `qmodel_*` to use `ctxs[h-1]` |
| `lib/std/gguf.quanta` | Remove module globals; move init/load logic into functions taking `ctx: *mut QmodelCtx` |
| `lib/std/safetensors.quanta` | Same — remove globals, take `ctx` |

---

## 4. Implementation Order

1. **Define `QmodelCtx` + handle table in `loader_traits.quanta`**
2. **Refactor `qmodel_open/close/kind/num_tensors`**
3. **Extract GGUF init into `gguf_load_into_ctx(ctx, path)`**
4. **Extract ST init into `st_load_into_ctx(ctx, path)`**
5. **Update dispatch functions (`qmodel_find`, `qmodel_name`, `qmodel_nelements`, etc.)**
6. **Update `qmodel_read` → calls `gguf_read_tensor_bytes_at` / `st_read` with ctx**

---

## 5. Tests

| Test | Expect |
|---|---|
| Open 2 GGUF models, read tensors from both | Both return correct data |
| Open 1 GGUF + 1 ST, verify dispatch | Correct format-specific reads |
| Open → close → reopen, no leaks | Handle table stable |
| Open 3 models, close middle, open 4th | Handle reuse works |

---

## 6. Validation

```bash
cd /opt/tali/quanta
QC=compiler/0.0.226/bin/x86/qc bash test_suites/scripts/run_tests.sh
# All gates GREEN
./compiler/0.0.226/bin/x86/qc /tmp/multi_model_test.quanta /tmp/mmt && /tmp/mmt
# Custom test: 2 GGUF models, verify both work
```