#!/usr/bin/env python3
"""LFM2.5-8B-A1B: CPU-only training (no CUDA, no bitsandbytes)"""
import os
os.environ["CUDA_VISIBLE_DEVICES"] = ""

import json, torch, time
from datetime import datetime

MODEL_PATH = "/opt/tali/ti/ai/models/lfm2.5-8b-a1b"
DATA_PATH = "/opt/tali/quanta/training_data/quanta_finetune.jsonl"
OUTPUT_DIR = "/opt/tali/quanta/output/lfm2.5_8b_a1b_cpu_only"

LEARNING_RATE = 1e-4
NUM_EPOCHS = 3
BATCH_SIZE = 1
GRAD_ACCUM = 4
MAX_SEQ_LEN = 128

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    print("="*60)
    print(f"LFM2.5-8B-A1B: CPU-only training (no GPU)")
    print(f"Time: {datetime.now().isoformat()}")
    print("="*60)
    
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import LoraConfig, get_peft_model
    
    print("\nLoading model (bf16, CPU)...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
    tokenizer.pad_token = tokenizer.eos_token
    
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_PATH,
        torch_dtype=torch.bfloat16,
        device_map="cpu",
        trust_remote_code=True,
    )
    
    print(f"Model loaded to CPU")
    
    peft_config = LoraConfig(
        r=8,
        lora_alpha=16,
        target_modules=["q_proj", "v_proj", "k_proj", "o_proj", "wg"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    
    model = get_peft_model(model, peft_config)
    model.print_trainable_parameters()
    
    # Data
    print("\nLoading data...")
    with open(DATA_PATH) as f:
        data = [json.loads(line) for line in f]
    
    formatted = []
    for item in data:
        inst = item.get("instruction", "")
        resp = item.get("response", "")
        text = f"<|im_start|>user\n{inst}<|im_end|>\n<|im_start|>assistant\n{resp}<|im_end|>"
        formatted.append(text)
    
    from torch.utils.data import Dataset, DataLoader
    
    class QuantaDataset(Dataset):
        def __init__(self, texts, tokenizer, max_len):
            self.encodings = tokenizer(texts, truncation=True, max_length=max_len, padding="max_length", return_tensors="pt")
        def __getitem__(self, idx):
            return {"input_ids": self.encodings["input_ids"][idx], "attention_mask": self.encodings["attention_mask"][idx], "labels": self.encodings["input_ids"][idx].clone()}
        def __len__(self):
            return len(self.encodings["input_ids"])
    
    dataset = QuantaDataset(formatted, tokenizer, MAX_SEQ_LEN)
    train_size = int(0.95 * len(dataset))
    val_size = len(dataset) - train_size
    train_ds, val_ds = torch.utils.data.random_split(dataset, [train_size, val_size])
    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE)
    
    trainable_params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(trainable_params, lr=LEARNING_RATE, weight_decay=0.01)
    
    print("\nTraining on CPU...")
    print("="*60)
    
    model.train()
    total_steps = 0
    best_val_loss = float("inf")
    
    for epoch in range(NUM_EPOCHS):
        epoch_start = time.time()
        for step, batch in enumerate(train_loader):
            input_ids = batch["input_ids"]
            attention_mask = batch["attention_mask"]
            labels = batch["labels"]
            
            outputs = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
            loss = outputs.loss / GRAD_ACCUM
            loss.backward()
            
            if (step + 1) % GRAD_ACCUM == 0:
                optimizer.step()
                optimizer.zero_grad()
                total_steps += 1
                
                if total_steps % 10 == 0:
                    elapsed = time.time() - epoch_start
                    steps_per_sec = total_steps / elapsed
                    print(f"Step {total_steps} Loss: {loss.item() * GRAD_ACCUM:.4f} ({steps_per_sec:.2f} steps/sec)")
        
        model.eval()
        val_loss = 0
        val_steps = 0
        with torch.no_grad():
            for batch in val_loader:
                input_ids = batch["input_ids"]
                attention_mask = batch["attention_mask"]
                labels = batch["labels"]
                outputs = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
                val_loss += outputs.loss.item()
                val_steps += 1
        
        avg_val = val_loss / val_steps
        print(f"Epoch {epoch+1} Val loss: {avg_val:.4f}")
        
        if avg_val < best_val_loss:
            best_val_loss = avg_val
            sp = f"{OUTPUT_DIR}/best"
            model.save_pretrained(sp)
            tokenizer.save_pretrained(sp)
            print(f"Saved: {sp}")
        
        model.train()
    
    final = f"{OUTPUT_DIR}/final"
    model.save_pretrained(final)
    tokenizer.save_pretrained(final)
    
    print(f"\nDone! Best val loss: {best_val_loss:.4f}")

if __name__ == "__main__":
    main()
