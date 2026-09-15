# QUANTA_FINETUNE.md — Fine-Tuning Specification for QUANTA-4B (v3, probe-verified)

> **Provenance:** Every API in this doc was verified against `compiler/0.0.190/src/x86/` and `lib/std/`.
> No invented functions. No guessed signatures. If it's listed here, it compiles and runs.

---

## 0. Architecture Decision: RAG vs Fine-Tuning

### Option A: RAG — Works Now
1. Retrieve 2-5 relevant `.quanta` files from `lib/std/`
2. Stuff into 16K context as few-shot examples
3. Generate → compile with `qc` → test → commit if green

**Pros:** Zero training cost, always-fresh examples, `qc` catches all errors.
**Cons:** Context overhead, retrieval quality gates output.

### Option B: Fine-Tuning
**Pros:** No retrieval overhead, consistent syntax.
**Cons:** 4-48 hours training, weights go stale, catastrophic forgetting risk.

### Recommendation
**RAG first.** Fine-tune only if compile rate <80% after prompt engineering.

---

## 1. Current Model State

| Property | Value |
|----------|-------|
| Base Model | QUANTA-GG4-E4B (7.5B params) |
| Quantization | Q4_K_M |
| Context | 16,384 tokens |
| Server | llama-server on `localhost:1234` |
| Issue | Generates Rust-like syntax without examples |

---

## 2. Training Data Inventory

### 2.1 Compiler (19 files, 14,116 lines)
```
compiler/0.0.190/src/x86/
├── tokens.quanta    # Token types, TT_* constants
├── globals.quanta   # Global state, IR buffers
├── helpers.quanta   # Helper functions (nv, nl, etc.)
├── features.quanta  # Builtin detection (is_bltn)
├── lexer.quanta     # Tokenizer
├── parse.quanta     # Parser (fn parse_block, parse_ret)
├── method.quanta    # Method/function calls
├── codegen.quanta   # IR codegen (IR_ADD, IR_CALL, etc.)
├── emitter.quanta   # Builtin emission (str, len, mmap, etc.)
├── elf.quanta       # ELF binary generation
├── funcscan.quanta  # Function scanning
├── objfmt.quanta    # Object format / linking / imports
├── qobj.quanta      # .qobj module cache format
├── qobj_write.quanta # .qobj writer
├── entry.quanta     # Entry point / startup
└── main.quanta      # Main entry, includes all above
```

### 2.2 Standard Library (Core)

| Module | File | Lines | Functions |
|--------|------|-------|-----------|
| str | lib/std/str.quanta | 68 | concat, byte_at, byte_set, equals, substr, parse_i64 |
| vec | lib/std/vec.quanta | 45 | vec_new, vec_put, vec_at, vec_set_len, vec_len, vec_push |
| map | lib/std/map.quanta | 85 | map_hash, map_new, map_put, map_get, map_has |
| json | lib/std/json.quanta | 411 | json_parse, json_get_type, json_get_string, json_get_array, json_get_object, json_array_len, json_array_get, json_object_get |
| fs | lib/std/fs.quanta | 70 | open(path, flags, mode), write_str, read_str, read_raw, write_raw, close, unlink |
| math | lib/std/math.quanta | 120 | abs, min, max, pow, sqrt, sin, cos, tan, etc. |

### 2.3 Training Corpus Summary

| Source | Files | Lines | Weight |
|--------|-------|-------|--------|
| Compiler 0.0.190 | 19 | 14,116 | 3.0x |
| Core stdlib | 6 | ~800 | 3.0x |
| Domain stdlib | ~9,352 | ~63,000 | 0.5x |
| Tests | ~18,550 | ~14,000 | 1.0x |
| **TOTAL** | **~28,000** | **~92,000** | — |

---

## 3. Quanta Syntax Reference (Probe-Verified)

### 3.1 Core Rules

```quanta
// Function declaration
fn add(a: i64, b: i64) -> i64 {
    return a + b
}

// Immutable binding
let x = 42

// Mutable binding
mut y = 0
y = y + 1

// If-else
if x > 0 {
    return x
} else {
    return 0
}

// While loop
while i < n {
    i = i + 1
}

// For loop
for i = 0; i < 10; i = i + 1 {
    printi(i)
}

// Import (no semicolon — both forms compile in 0.0.190+)
import std/str
import std/vec
```

### 3.2 Strings

```quanta
let msg = "hello"
let n = len(msg)                   // Get length (reads [0] header)
let c = mem_load8(msg + 8)         // First byte at offset 8
mem_store8(msg + 8, 65)            // Set first byte to 'A'
let s = str("hello", "world")      // Concatenate two strings
```

### 3.3 Vectors (vec)

```quanta
let v = vec_new()                  // Create new vector
vec_push(v, 42)                    // Push element
let x = vec_at(v, 0)               // Get element at index
vec_put(v, 0, 99)                  // Set element at index
let n = vec_len(v)                 // Get length
vec_set_len(v, 10)                 // Set length (truncate/extend)
```

**DO NOT USE:** `vec_get`, `vec_set`, `vec_pop` — these don't exist.

### 3.4 Maps

```quanta
let m = map_new()                  // Create new map
map_put(m, "key", 42)              // Set key-value pair
let val = map_get(m, "key")        // Get value by key
let has = map_has(m, "key")        // Check if key exists
```

**DO NOT USE:** `map_set`, `map_delete` — these don't exist.

### 3.5 File I/O (std/fs)

```quanta
// 3-arg open with mode (correct way)
let fd = open("path", 577, 0644)   // O_WRONLY|O_CREAT|O_TRUNC with mode 0644
write_str(fd, "hello")             // Write string
read_str(fd, 100)                  // Read string (max 100 bytes)
close(fd)                          // Close file
unlink("path")                     // Delete file
```

**DO NOT USE:** `file_open(path, 577)` (2-arg) — creates files with garbage mode 0500 (read-only trap).

### 3.6 Memory

```quanta
let buf = mem_alloc(64)            // Allocate 64 qwords = 512 bytes
mem_store(buf, 42)                 // Store 8-byte value
let val = mem_load(buf)            // Load 8-byte value
mem_free(buf)                      // Free memory

// mmap — COMPILER INTERNAL, NOT SYSCALL
// DO NOT USE for user code. Use mem_alloc/mem_free instead.
```

### 3.7 System

```quanta
exit(42)                           // Exit with code
let pid = fork()                   // Fork process
exec("/bin/sh -c \"cmd\"")         // Execute command
let status = wait(pid)             // Wait for process
let now = clock()                  // Monotonic nanoseconds
let epoch = now()                  // Epoch nanoseconds
sleep(1)                           // Sleep 1 second
let p = getpid()                   // Get process ID
```

### 3.8 Math

```quanta
let a = abs(-42)                   // 42
let b = min(3, 5)                  // 3
let c = max(3, 5)                  // 5
let d = pow(2, 10)                 // 1024
let e = sqrt(144)                  // 12
let f = sin(0)                     // 0
let g = cos(0)                     // 1
```

---

## 4. Built-in Functions (Emitter-Verified)

These are inlined by the emitter. No import needed.

| Category | Function | Description |
|----------|----------|-------------|
| String | `str(a, b)` | Concatenate two strings |
| | `len(s)` | Get string/vector length |
| | `mem_load8(ptr)` | Load byte from pointer |
| | `mem_store8(ptr, val)` | Store byte to pointer |
| | `mem_load(ptr)` | Load 8-byte value |
| | `mem_store(ptr, val)` | Store 8-byte value |
| Print | `printi(x)` | Print integer |
| | `prints(s)` | Print string |
| | `print(buf, len)` | Print raw bytes |
| Memory | `mem_alloc(n)` | Allocate n qwords |
| | `mem_free(ptr)` | Free allocation |
| Process | `exit(code)` | Exit process |
| | `fork()` | Fork process |
| | `exec(cmd)` | Execute command |
| | `wait(pid)` | Wait for process |
| | `getpid()` | Get PID |
| | `getppid()` | Get parent PID |
| | `kill(pid, sig)` | Send signal |
| Time | `clock()` | Monotonic nanoseconds |
| | `now()` | Epoch nanoseconds |
| | `sleep(sec)` | Sleep seconds |
| Math | `abs, min, max, pow, sqrt` | Basic math |
| | `sin, cos, tan` | Trigonometry |
| | `i2f(x)` | Int to float |
| | `f2i(x)` | Float to int |

---

## 5. Common Pitfalls

### WRONG → RIGHT

```quanta
// WRONG: vec_pop doesn't exist
let x = vec_pop(v)

// WRONG: vec_get is SIMD lane op, not element getter
let x = vec_get(v, 0)

// WRONG: vec_set is SIMD lane op, not element setter
vec_set(v, 0, x)

// WRONG: map_set doesn't exist
map_set(m, "key", 42)

// WRONG: map_delete doesn't exist
map_delete(m, "key")

// WRONG: 2-arg file_open creates read-only files
let fd = file_open("path", 577)

// WRONG: mmap is compiler-internal
mmap(addr, len, prot, flags, fd, off)

// WRONG: let len = msg binds pointer, not length
let len = msg

// RIGHT:
vec_push(v, x)                     // push
vec_at(v, 0)                       // get element
vec_put(v, 0, x)                   // set element
map_put(m, "key", 42)              // set
let n = len(msg)                   // actual length
let fd = open("path", 577, 0644)   // 3-arg open with mode
let buf = mem_alloc(64)            // allocate memory
```

---

## 6. Fine-Tuning Pipeline

### 6.1 Data Preparation

```bash
#!/bin/bash
# scripts/prepare_finetune_data.sh

# Extract all Quanta source
find compiler/0.0.190/src/x86 -name "*.quanta" > quanta_sources.txt
find lib/std -maxdepth 1 -name "*.quanta" >> quanta_sources.txt
find test_suites/codes -name "*.quanta" >> quanta_sources.txt

# Create JSONL training data
python3 << 'EOF'
import json

sources = []
with open("quanta_sources.txt") as f:
    for line in f:
        path = line.strip()
        if not path: continue
        try:
            with open(path, encoding='utf-8', errors='ignore') as src:
                content = src.read()
            if len(content) > 50:
                sources.append((path, content))
        except:
            continue

# Create training examples
examples = []
for path, content in sources:
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if line.strip().startswith('fn ') and '{' in line:
            fn_name = line.split('fn ')[1].split('(')[0].strip()
            start = max(0, i - 3)
            context = '\n'.join(lines[start:i+1])
            body_lines = []
            j = i
            brace_count = 0
            while j < len(lines) and j < i + 30:
                body_lines.append(lines[j])
                brace_count += lines[j].count('{') - lines[j].count('}')
                if brace_count <= 0 and j > i:
                    break
                j += 1
            body = '\n'.join(body_lines)
            examples.append({
                "instruction": f"Write a Quanta function named {fn_name}",
                "input": context,
                "output": body
            })

# Write
with open("quanta_train.jsonl", "w") as f:
    for ex in examples:
        f.write(json.dumps(ex) + '\n')

print(f"Created {len(examples)} training examples")
EOF
```

### 6.2 Training Script

```python
# scripts/train_quanta_lora.py

from transformers import (
    AutoModelForCausalLM, AutoTokenizer,
    BitsAndBytesConfig, TrainingArguments, Trainer
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from datasets import load_dataset
import torch

MODEL_PATH = "/opt/ai/models/quanta/QUANTA-GG4-E4B-Q4_K_M.gguf"
DATA_PATH = "quanta_train.jsonl"
OUTPUT_DIR = "quanta-lora-adapter"

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.float16,
)

model = AutoModelForCausalLM.from_pretrained(
    MODEL_PATH,
    quantization_config=bnb_config,
    device_map="auto",
    trust_remote_code=True,
)
model = prepare_model_for_kbit_training(model)

lora_config = LoraConfig(
    r=16, lora_alpha=32,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
)
model = get_peft_model(model, lora_config)

tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
tokenizer.pad_token = tokenizer.eos_token

dataset = load_dataset("json", data_files={"train": DATA_PATH}, split="train")

training_args = TrainingArguments(
    output_dir=OUTPUT_DIR,
    num_train_epochs=3,
    per_device_train_batch_size=4,
    gradient_accumulation_steps=4,
    learning_rate=2e-4,
    warmup_ratio=0.03,
    lr_scheduler_type="cosine",
    logging_steps=10,
    save_strategy="epoch",
    fp16=True,
    optim="paged_adamw_8bit",
)

trainer = Trainer(model=model, args=training_args, train_dataset=dataset, tokenizer=tokenizer)
trainer.train()
model.save_pretrained(OUTPUT_DIR)
```

---

## 7. Evaluation

### 7.1 Compilation Test
```bash
curl -s http://localhost:1234/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"quanta","messages":[{"role":"user","content":"Write fn factorial"}],"max_tokens":200}' \
  | jq -r '.choices[0].message.content' > /tmp/gen.quanta
./compiler/0.0.190/bin/x86/qc /tmp/gen.quanta /tmp/gen && /tmp/gen
```

### 7.2 Success Criteria
- >90% compile rate on held-out specs
- No Rust idioms (`let mut`, `///`, `;` after return)
- >80% functional correctness on basic tests

---

## 8. Appendix: Quick Reference

### Quanta vs Other Languages

| Feature | Quanta | Rust | Python |
|---------|--------|------|--------|
| Function | `fn foo() -> i64` | `fn foo() -> i64` | `def foo():` |
| Variable | `let x = 5` / `mut x = 5` | `let x = 5` / `let mut x = 5` | `x = 5` |
| Return | `return x` | `return x` | `return x` |
| If | `if x > 0 { }` | `if x > 0 { }` | `if x > 0:` |
| While | `while i < n { }` | `while i < n { }` | `while i < n:` |
| For | `for i=0; i<n; i=i+1 { }` | `for i in 0..n { }` | `for i in range(n):` |
| String | `i64` pointer | `String`/`&str` | `str` |
| Vector | `vec_push(v, x)` | `v.push(x)` | `list.append(x)` |
| Map | `map_put(m, k, v)` | `m.insert(k, v)` | `m[k] = v` |
