# QUANTA_FINETUNE.md — Fine-Tuning Specification for QUANTA-4B

## Executive Summary

QUANTA-4B is a 7.5B parameter language model (Q4_K_M quantized) currently trained on general code. To enable autonomous Self-Improvement (SI) in Quanta, the model needs Quanta-specific syntax, builtins, and idioms. This document specifies both the **fine-tuning pipeline** and the **RAG alternative**, with an honest tradeoff analysis.

---

## 0. Architecture Decision: RAG vs Fine-Tuning

### Option A: RAG (Retrieval-Augmented Generation) — Works Now

**How it works:**
1. Given a gap spec (domain, category, module, notes)
2. Retrieve 5-10 relevant `.quanta` examples from `lib/std/`
3. Stuff them into the 16K context window as few-shot examples
4. Model imitates the syntax patterns from examples
5. Generate code → compile with `qc` → test → commit if green

**Pros:**
- Zero training cost — works immediately with current QUANTA-4B
- Always uses latest stdlib examples (no stale weights)
- Domain-specific retrieval (accounting examples for accounting specs)
- `qc` compiler is the real gate — catches syntax AND semantic errors

**Cons:**
- Context window overhead (examples consume tokens)
- Retrieval quality depends on embedding similarity
- May still produce non-Quanta idioms without enough examples

### Option B: Fine-Tuning — Bakes Syntax Into Weights

**How it works:**
1. Fine-tune QUANTA-4B on ~128K lines of Quanta source
2. Model learns Quanta syntax permanently
3. Generate code without retrieval examples
4. Compile with `qc` → test → commit if green

**Pros:**
- No retrieval overhead at inference time
- Consistent syntax without needing examples
- Faster inference (no embedding search)

**Cons:**
- Training cost: 4-48 hours on GPU/CPU
- Weights can become stale as Quanta evolves
- Risk of catastrophic forgetting on general code
- Requires retraining when language changes

### Option C: Hybrid (Recommended)

**Fine-tuned base + RAG for domain knowledge:**
1. Fine-tune on core Quanta syntax (compiler + core stdlib)
2. Use RAG for domain-specific patterns (accounting, quantum, etc.)
3. Best of both worlds: baked syntax + fresh domain examples

### The Key Insight

**`qc` (the Quanta compiler) is the real gate — regardless of approach.**

- Fine-tuning improves **syntax fidelity** (fewer compile errors)
- Fine-tuning does NOT improve **semantic correctness** (logic bugs still compile)
- RAG improves **domain relevance** (right patterns for the domain)
- Only `qc` + tests catch semantic errors

**Recommendation:** Start with RAG (Option A) for immediate results. Fine-tune (Option B) only if RAG's compile rate stays below 80% after prompt engineering.

---

## 1. Current Model State

| Property | Value |
|----------|-------|
| Base Model | QUANTA-GG4-E4B (7.5B params) |
| Quantization | Q4_K_M (4-bit, medium) |
| Context Window | 16,384 tokens (train: 131,024) |
| Architecture | LLaMA-family, GGUF format |
| Current Server | llama-server on `localhost:1234` |
| Training Data | General code (NOT Quanta-specific) |
| Known Issue | Generates Rust-like syntax (`let mut`, `///`) instead of Quanta |

---

## 2. Training Data Inventory

### 2.1 Primary Sources (Quanta Compiler)

| Path | Files | Lines | Description |
|------|-------|-------|-------------|
| `compiler/0.0.190/src/x86/*.quanta` | 19 | 14,116 | Full x86-64 compiler backend |
| `compiler/0.0.189/src/x86/*.quanta` | 19 | 14,116 | Previous stable compiler |

**Key files:**
- `parse.quanta` — Parser (1547 lines)
- `codegen.quanta` — IR codegen (1979 lines)
- `emitter.quanta` — Builtin emission (2500+ lines)
- `objfmt.quanta` — Object format / linking
- `globals.quanta` — Global state management
- `method.quanta` — Method/function calls
- `entry.quanta` — Entry point / startup

### 2.2 Secondary Sources (Standard Library)

| Path | Files | Lines | Description |
|------|-------|-------|-------------|
| `lib/std/*.quanta` (core) | 12 | ~12,000 | str, vec, map, json, fs, math, etc. |
| `lib/std/*.quanta` (domain) | 9,352 | ~63,000 | Generated stubs (low quality) |

**High-quality core modules:**
- `str.quanta` — String operations (concat, bytes, substr, parse)
- `vec.quanta` — Vector operations (push, pop, get, set, sort)
- `map.quanta` — Hash map (new, get, set, has, delete)
- `json.quanta` — JSON parser (411 lines)
- `fs.quanta` — File system (open, read, write, seek, stat)
- `math.quanta` — Math operations (abs, min, max, pow, sqrt, trig)

### 2.3 Tertiary Sources (Tests & Specs)

| Path | Files | Lines | Description |
|------|-------|-------|-------------|
| `test_suites/codes/*.quanta` | 18,550 | 14,382 | Test files |
| `docs/SPEC.md` | 1 | ~2,000 | Language specification |
| `docs/SYNTAX.md` | 1 | ~1,500 | Syntax reference |
| `docs/ARCHITECTURE.md` | 1 | ~3,000 | Architecture document |

### 2.4 Total Training Corpus

| Category | Files | Lines | Weight |
|----------|-------|-------|--------|
| Compiler (0.0.189) | 19 | 14,116 | 3.0x |
| Compiler (0.0.188) | 19 | ~14,000 | 2.0x |
| Core stdlib | 12 | ~12,000 | 3.0x |
| Domain stdlib | 9,352 | ~63,000 | 0.5x |
| Tests | 18,550 | 14,382 | 1.0x |
| Specs & docs | 3 | ~6,500 | 2.0x |
| **TOTAL** | **27,955** | **~128,000** | — |

---

## 3. Quanta Syntax Reference (for Fine-Tuning)

### 3.1 Core Syntax Rules

```quanta
// Function declaration
fn function_name(param1: i64, param2: i64) -> i64 {
    return param1 + param2
}

// Variable binding (immutable)
let x = 42

// Mutable variable
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

// Include other modules
// Both forms compile (trailing semicolon stripped — fixed in 0.0.190):
import std/str
import std/vec
import std/json
// Also valid: import std/str; import std/vec;

// String literal
let msg = "hello"

// String operations
let len = msg                    // Length (reads header at [0])
let byte0 = mem_load8(msg + 8)   // First byte at offset 8
mem_store8(msg + 8, 65)          // Set first byte to 'A'

// Built-in string construction
let s = str("hello", "world")    // Concatenate

// Function call
let result = my_function(x, y)

// Array/vector access
let v = vec_new()
vec_push(v, 42)
let first = vec_get(v, 0)

// Map operations
let m = map_new()
map_set(m, "key", 42)
let val = map_get(m, "key")

// File I/O
let fd = file_open("path", 577)  // 577 = O_WRONLY|O_CREAT|O_TRUNC
file_write(fd, buffer, length)
file_close(fd)

// Print
printi(42)           // Print integer
prints("hello")      // Print string
print(buf, len)      // Print raw bytes

// Error handling
if fd < 0 {
    return -1
}

// Type annotations (all i64)
fn add(a: i64, b: i64) -> i64 {
    return a + b
}
```

### 3.2 Built-in Functions (Complete List)

**String:**
- `str(a, b)` — Concatenate two strings
- `len(s)` — Get string/vector length
- `mem_load8(ptr)` — Load byte from pointer
- `mem_store8(ptr, val)` — Store byte to pointer
- `mem_load(ptr)` — Load 8-byte value
- `mem_store(ptr, val)` — Store 8-byte value

**Vector:**
- `vec_new()` — Create new vector
- `vec_push(v, elem)` — Push element
- `vec_pop(v)` — Pop element
- `vec_get(v, idx)` — Get element at index
- `vec_set(v, idx, val)` — Set element at index
- `vec_len(v)` — Get length

**Map:**
- `map_new()` — Create new map
- `map_set(m, key, val)` — Set key-value pair
- `map_get(m, key)` — Get value by key
- `map_has(m, key)` — Check if key exists
- `map_delete(m, key)` — Delete key

**I/O:**
- `file_open(path, flags)` — Open file (returns fd)
- `file_read(fd, buf, len)` — Read from file
- `file_write(fd, buf, len)` — Write to file
- `file_close(fd)` — Close file
- `file_seek(fd, offset, whence)` — Seek

**Process:**
- `exit(code)` — Exit with code
- `fork()` — Fork process
- `exec(cmd)` — Execute command
- `wait(pid)` — Wait for process

**Math:**
- `abs(x)` — Absolute value
- `min(a, b)` — Minimum
- `max(a, b)` — Maximum
- `pow(base, exp)` — Power
- `sqrt(x)` — Square root
- `sin(x)`, `cos(x)`, `tan(x)` — Trigonometry

**Memory:**
- `mem_alloc(size)` — Allocate memory (returns pointer)
- `mem_free(ptr)` — Free memory
- `mmap(addr, len, prot, flags, fd, offset)` — Memory map
- `munmap(addr, len)` — Unmap memory

**Time:**
- `clock()` — Monotonic clock (nanoseconds)
- `now()` — Epoch time (nanoseconds)
- `sleep(sec)` — Sleep seconds
- `nanosleep(req, rem)` — Nanosecond sleep

**System:**
- `syscall(num, ...)` — Raw syscall
- `getpid()` — Get process ID
- `getppid()` — Get parent PID
- `kill(pid, sig)` — Send signal

### 3.3 Key Idioms

```quanta
// 1. String header layout: [8-byte len][bytes...]
let s = "hello"
if len(s) == 5 { ... }

// 2. Buffer allocation
let buf = mem_alloc(64)  // 64 * 8 = 512 bytes

// 3. File open flags
let O_RDONLY = 0
let O_WRONLY = 1
let O_CREAT = 64
let O_TRUNC = 512
let fd = file_open("path", 577)  // 1 + 64 + 512 = O_WRONLY|O_CREAT|O_TRUNC

// 4. Error handling pattern
fn safe_divide(a: i64, b: i64) -> i64 {
    if b == 0 { return -1 }
    return a / b
}

// 5. Loop with counter
let i = 0
while i < n {
    // body
    i = i + 1
}

// 6. Recursive function
fn factorial(n: i64) -> i64 {
    if n <= 1 { return 1 }
    return n * factorial(n - 1)
}

// 7. Module pattern
module my_module;

import std/types;

const MY_CONST = 42;

fn public_function() -> i64 {
    return MY_CONST
}

fn init() -> i64 {
    return 0
}

fn main() -> i64 {
    return init();
}

// 8. Vector iteration
let v = vec_new()
let i = 0
while i < vec_len(v) {
    let elem = vec_get(v, i)
    printi(elem)
    i = i + 1
}

// 9. Map iteration (manual)
let m = map_new()
// Note: No built-in iteration; use known keys or store keys separately

// 10. Pattern matching (if-else chain)
fn classify(x: i64) -> i64 {
    if x < 0 { return -1 }
    if x == 0 { return 0 }
    return 1
}
```

---

## 4. Fine-Tuning Strategy

### 4.1 Approach: QLoRA (Quantized Low-Rank Adaptation)

**Why QLoRA:**
- Base model is 4-bit quantized — full fine-tuning is impractical
- QLoRA trains only small adapter weights (~1-2% of params)
- Memory efficient: fits on single GPU or CPU with sufficient RAM
- Preserves base capabilities while adding Quanta knowledge

### 4.2 Training Configuration

```yaml
# quanta_finetune_config.yaml

model:
  base: "quant QUANTA-GG4-E4B-Q4_K_M.gguf"
  adapter_output: "quanta-lora-adapter"

lora:
  r: 16              # Rank
  alpha: 32          # Scaling factor
  dropout: 0.05
  target_modules:    # Which layers to adapt
    - "q_proj"
    - "k_proj"
    - "v_proj"
    - "o_proj"
    - "gate_proj"
    - "up_proj"
    - "down_proj"

training:
  epochs: 3
  learning_rate: 2e-4
  batch_size: 4
  gradient_accumulation: 4
  max_seq_length: 4096
  warmup_ratio: 0.03
  weight_decay: 0.01
  optimizer: "paged_adamw_8bit"
  scheduler: "cosine"

data:
  train_file: "quanta_train.jsonl"
  val_file: "quanta_val.jsonl"
  format: "chat"     # {instruction, input, output}

hardware:
  device: "cuda"     # or "cpu" if no GPU
  gpu_memory: "8GB"  # Minimum for 7B QLoRA
  cpu_ram: "32GB"    # For CPU fallback
```

### 4.3 Training Data Format

**JSONL format (one JSON per line):**

```json
{
  "instruction": "Write a Quanta function to calculate compound interest",
  "input": "Function signature: fn compound_interest(principal: i64, rate: i64, periods: i64) -> i64",
  "output": "fn compound_interest(principal: i64, rate: i64, periods: i64) -> i64 {\n    if periods <= 0 { return principal }\n    let factor = 10000 + rate\n    let result = principal\n    let i = 0\n    while i < periods {\n        result = (result * factor) / 10000\n        i = i + 1\n    }\n    return result\n}"
}
```

### 4.4 Data Preparation Pipeline

```bash
#!/bin/bash
# scripts/prepare_finetune_data.sh

# Step 1: Extract all Quanta source files
find /opt/tali/quanta/compiler/0.0.189/src/x86 -name "*.quanta" > quanta_sources.txt
find /opt/tali/quanta/lib/std -maxdepth 1 -name "*.quanta" >> quanta_sources.txt
find /opt/tali/quanta/test_suites/codes -name "*.quanta" >> quanta_sources.txt

# Step 2: Create training pairs
# For each file, create: {instruction, input, output} triples
python3 << 'EOF'
import json
import os

sources = []
with open("quanta_sources.txt") as f:
    for line in f:
        path = line.strip()
        if not path:
            continue
        try:
            with open(path, encoding='utf-8', errors='ignore') as src:
                content = src.read()
            if len(content) > 100:  # Skip tiny files
                sources.append((path, content))
        except:
            continue

# Create training examples from function definitions
examples = []
for path, content in sources:
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if line.strip().startswith('fn ') and '{' in line:
            # Extract function name
            fn_name = line.split('fn ')[1].split('(')[0].strip()
            
            # Get context (5 lines before)
            start = max(0, i - 5)
            context = '\n'.join(lines[start:i+1])
            
            # Get full function body (up to next fn or 50 lines)
            body_lines = []
            j = i
            brace_count = 0
            while j < len(lines) and j < i + 50:
                body_lines.append(lines[j])
                brace_count += lines[j].count('{') - lines[j].count('}')
                if brace_count <= 0 and j > i:
                    break
                j += 1
            body = '\n'.join(body_lines)
            
            examples.append({
                "instruction": f"Write a Quanta function named {fn_name}",
                "input": f"Context:\n{context}\n\nComplete the function body:",
                "output": body
            })

# Write training data
with open("quanta_train.jsonl", "w") as f:
    for ex in examples:
        f.write(json.dumps(ex) + '\n')

print(f"Created {len(examples)} training examples")
EOF

# Step 3: Split into train/val
shuf quanta_train.jsonl | split -l 1000 - quanta_split_
mv quanta_split_aa quanta_val.jsonl
mv quanta_split_* quanta_train_tmp.jsonl 2>/dev/null || true
cat quanta_train_tmp.jsonl >> quanta_train.jsonl 2>/dev/null || true

echo "Data preparation complete"
```

---

## 5. Training Pipeline

### 5.1 Environment Setup

```bash
# Install dependencies
pip install torch transformers datasets peft bitsandbytes accelerate

# For CPU-only training (no GPU)
pip install torch-cpu
```

### 5.2 Training Script

```python
# scripts/train_quanta_lora.py

from transformers import (
    AutoModelForCausalLM, 
    AutoTokenizer, 
    BitsAndBytesConfig,
    TrainingArguments
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from datasets import load_dataset
import torch

# Configuration
MODEL_PATH = "/opt/ai/models/quanta/QUANTA-GG4-E4B-Q4_K_M.gguf"
DATA_PATH = "quanta_train.jsonl"
OUTPUT_DIR = "quanta-lora-adapter"

# Quantization config (4-bit)
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.float16,
    bnb_4bit_use_double_quant=True,
)

# Load model
model = AutoModelForCausalLM.from_pretrained(
    MODEL_PATH,
    quantization_config=bnb_config,
    device_map="auto",
    trust_remote_code=True,
)

# Prepare for training
model = prepare_model_for_kbit_training(model)

# LoRA config
lora_config = LoraConfig(
    r=16,
    lora_alpha=32,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
)

# Apply LoRA
model = get_peft_model(model, lora_config)

# Load tokenizer
tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
tokenizer.pad_token = tokenizer.eos_token

# Load dataset
dataset = load_dataset("json", data_files={"train": DATA_PATH}, split="training")

# Training arguments
training_args = TrainingArguments(
    output_dir=OUTPUT_DIR,
    num_train_epochs=3,
    per_device_train_batch_size=4,
    gradient_accumulation_steps=4,
    learning_rate=2e-4,
    weight_decay=0.01,
    warmup_ratio=0.03,
    lr_scheduler_type="cosine",
    logging_steps=10,
    save_strategy="epoch",
    fp16=True,
    optim="paged_adamw_8bit",
    report_to="none",
)

# Train
trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=dataset,
    tokenizer=tokenizer,
)

trainer.train()

# Save adapter
model.save_pretrained(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)

print(f"Training complete. Adapter saved to {OUTPUT_DIR}")
```

### 5.3 Merge & Export

```bash
# Merge LoRA adapter with base model
python3 << 'EOF'
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

base = AutoModelForCausalLM.from_pretrained(
    "/opt/ai/models/quanta/QUANTA-GG4-E4B-Q4_K_M.gguf",
    torch_dtype=torch.float16,
    trust_remote_code=True,
)

model = PeftModel.from_pretrained(base, "quanta-lora-adapter")
model = model.merge_and_unload()

# Save merged model
model.save_pretrained("quanta-finetuned")
EOF

# Convert to GGUF for llama.cpp
python3 llama.cpp/convert.py quanta-finetuned --outtype q4_k_m --outfile quanta-finetuned-q4km.gguf

# Deploy
ln -sf quanta-finetuned-q4km.gguf /opt/ai/models/quanta/active
```

---

## 6. Evaluation

### 6.1 Compilation Test

After training, the model should generate code that compiles:

```bash
# Generate code
RESPONSE=$(curl -s http://localhost:1234/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "quanta",
    "messages": [{"role": "user", "content": "Write a Quanta function fn gcd(a: i64, b: i64) -> i64 that calculates greatest common divisor using Euclidean algorithm"}],
    "max_tokens": 200
  }')

# Extract code
echo "$RESPONSE" | jq -r '.choices[0].message.content' > /tmp/generated_test.quanta

# Try to compile
./compiler/0.0.189/bin/x86/qc /tmp/generated_test.quanta /tmp/generated_test
if [ $? -eq 0 ]; then
    echo "PASS: Generated code compiles"
else
    echo "FAIL: Generated code does not compile"
fi
```

### 6.2 Syntax Compliance Tests

| Test | Input | Expected |
|------|-------|----------|
| Variable declaration | `let x = 42` | No `let mut` |
| Function definition | `fn foo() -> i64 { }` | No `func`, `def`, `fn foo() i64` |
| Return statement | `return x` | No `return x;` (no semicolons) |
| String header | `len(s)` then `mem_load8(s + 8)` | Correct 8-byte offset |
| Error handling | `if fd < 0 { return -1 }` | Proper pattern |
| Import | `import std/str` | Not `use std::str` or `include` |

### 6.3 Functional Tests

Generate implementations for these specs and verify:
1. `fn factorial(n: i64) -> i64` — factorial
2. `fn gcd(a: i64, b: i64) -> i64` — Euclidean algorithm
3. `fn is_prime(n: i64) -> i64` — primality test
4. `fn fibonacci(n: i64) -> i64` — Fibonacci
5. `fn str_reverse(s: i64) -> i64` — string reverse

---

## 7. Integration with SI Pipeline

### 7.1 Python Generation Harness

```python
# scripts/si_model_client.py

import requests
import json

ENDPOINT = "http://localhost:1234/v1/chat/completions"
MODEL = "quanta"

SYSTEM_PROMPT = """You are an expert Quanta programmer. Quanta is a compiled language with:
- fn keyword for functions
- let for immutable bindings, mut for mutable
- i64 is the primary type
- Strings are i64 pointers to [8-byte length][bytes...]
- Built-in functions: len, mem_load8, mem_store8, str, file_open, file_read, file_write, printi, prints
- No semicolons, no curly braces on same line as if/while
- Return with 'return expr' not 'return expr;'
Generate ONLY compilable Quanta code. No explanations, no markdown fences."""

def generate_quanta_code(spec: dict) -> str:
    """Generate Quanta code from a gap spec."""
    prompt = f"""Write a Quanta module for:
Domain: {spec['domain']}
Category: {spec['category']}
Module: {spec['module']}
Notes: {spec.get('notes', '')}

Generate a complete Quanta module with:
1. Module declaration: module std_{spec['domain']}_{spec['category']}_{spec['module']};
2. Import: import std/types;
3. At least 3-5 real functions implementing the domain logic
4. A main() function that tests the implementation
5. All functions must be compilable Quanta code"""

    response = requests.post(ENDPOINT, json={
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 2000,
        "temperature": 0.7,
    })
    
    if response.status_code != 200:
        return None
    
    content = response.json()["choices"][0]["message"]["content"]
    
    # Extract code from markdown fences if present
    if "```quanta" in content:
        content = content.split("```quanta")[1].split("```")[0]
    elif "```" in content:
        content = content.split("```")[1].split("```")[0]
    
    return content.strip()

def compile_and_test(code: str, output_path: str) -> bool:
    """Compile generated code and run tests."""
    import subprocess
    import tempfile
    
    # Write code to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.quanta', delete=False) as f:
        f.write(code)
        code_path = f.name
    
    # Compile
    result = subprocess.run(
        ["./compiler/0.0.189/bin/x86/qc", code_path, output_path],
        capture_output=True
    )
    
    if result.returncode != 0:
        print(f"Compilation failed: {result.stderr.decode()}")
        return False
    
    # Run
    result = subprocess.run([output_path], capture_output=True)
    
    if result.returncode != 0:
        print(f"Test failed: {result.stdout.decode()}")
        return False
    
    print(f"Success: {result.stdout.decode()}")
    return True

# Example usage
if __name__ == "__main__":
    spec = {
        "domain": "accounting",
        "category": "gaap",
        "module": "deferred_tax",
        "notes": "ASC 740, temporary differences, valuation allowance"
    }
    
    code = generate_quanta_code(spec)
    if code:
        print("Generated code:")
        print(code)
        
        # Save to file
        filename = f"lib/std/{spec['domain']}_{spec['category']}_{spec['module']}.quanta"
        with open(filename, 'w') as f:
            f.write(code)
        print(f"\nSaved to {filename}")
```

### 7.2 Integration with Continuous Pipeline

```bash
# In scripts/si_continuous.sh, replace stub generation with:
python3 scripts/si_model_client.py --spec "$spec_json" --output "$output_file"
```

---

## 8. Timeline & Milestones

| Phase | Task | Duration |
|-------|------|----------|
| 1 | Data preparation (extract, format, clean) | 1-2 hours |
| 2 | Training setup (env, config, scripts) | 2-4 hours |
| 3 | Initial training run (3 epochs) | 4-8 hours (GPU) / 24-48 hours (CPU) |
| 4 | Evaluation (compile test, syntax check) | 1-2 hours |
| 5 | Iterate (adjust hyperparameters, retrain) | 2-4 hours |
| 6 | Integration (wire into SI pipeline) | 2-3 hours |
| 7 | Full pipeline test (end-to-end) | 1-2 hours |

---

## 9. Success Criteria

The fine-tuned model is considered ready when:

1. **Compilation Rate**: >90% of generated code compiles without errors
2. **Syntax Compliance**: No Rust/Python idioms (`let mut`, `///`, `;` after `return`)
3. **Functional Correctness**: >80% of generated functions pass basic tests
4. **Domain Coverage**: Can generate meaningful implementations for at least 5 domains
5. **Style Consistency**: Matches existing Quanta code style (indentation, naming, patterns)

---

## 10. Appendix: Quick Reference

### Quanta vs Other Languages

| Feature | Quanta | Rust | Python | Go |
|---------|--------|------|--------|-----|
| Function | `fn foo() -> i64` | `fn foo() -> i64` | `def foo():` | `func foo() int` |
| Variable | `let x = 5` | `let x = 5` | `x = 5` | `x := 5` |
| Mutable | `mut x = 5` | `let mut x = 5` | `x = 5` | `x = 5` |
| Return | `return x` | `return x` | `return x` | `return x` |
| If | `if x > 0 { }` | `if x > 0 { }` | `if x > 0:` | `if x > 0 { }` |
| While | `while i < n { }` | `while i < n { }` | `while i < n:` | `for i < n { }` |
| For | `for i=0; i<n; i=i+1 { }` | `for i in 0..n { }` | `for i in range(n):` | `for i := 0; i < n; i++ { }` |
| String | `i64` pointer | `String`/`&str` | `str` | `string` |
| Array | `vec_new()` | `Vec::new()` | `[]` | `[]type{}` |
| Error | `if x < 0 { return -1 }` | `Result<T, E>` | `raise` | `err` |

### Common Pitfalls to Avoid

1. **Semicolons**: Quanta does NOT use semicolons after statements
2. **Mutable bindings**: Use `mut x = 0`, not `let mut x = 0`
3. **String indexing**: Always offset by 8 bytes for header: `mem_load8(s + 8 + i)`
4. **Return statements**: `return x` not `return x;`
5. **Type annotations**: All numeric types are `i64`, strings are `i64` pointers
6. **Module declaration**: Every file should start with `module name;`
7. **Import syntax**: `import std/module` not `use std::module` or `#include`
8. **Function visibility**: No `pub` keyword — all functions are public
9. **Comments**: Use `//` not `///` or `/* */`
10. **Error handling**: Return negative values or 0, no `Result` type
