#!/usr/bin/env python3
"""Phase 1: Cumulative training - r=16, LFM2 template, with logging and checkpointing"""
import os
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
os.environ["PYTHONUNBUFFERED"] = "1"

import json, torch, time, sys, glob
from datetime import datetime

MODEL_PATH = "/opt/tali/ti/ai/models/lfm2.5-2b6"
DATA_PATH = "/opt/tali/quanta/training_data/quanta_finetune.jsonl"
OUTPUT_DIR = "/opt/tali/quanta/output/cumulative_phase1"

LR = 3e-4
NUM_EPOCHS = 3
BATCH_SIZE = 1
GRAD_ACCUM = 4
MAX_SEQ_LEN = 256

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    log_path = f"{OUTPUT_DIR}/training.log"
    log_file = open(log_path, "w", buffering=1)  # Line-buffered
    
    def log(msg):
        print(msg, flush=True)
        log_file.write(msg + "\n")
        log_file.flush()
    
    log(f"Phase 1: r=16, lr={LR}, LFM2 template")
    log(f"Time: {datetime.now().isoformat()}")
    
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from peft import LoraConfig, get_peft_model, PeftModel
    
    log("Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
    tokenizer.pad_token = tokenizer.eos_token
    
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    
    log("Loading model (4-bit)...")
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_PATH,
        quantization_config=bnb_config,
        device_map="auto",
        torch_dtype=torch.bfloat16,
    )
    log(f"Loaded. VRAM: {torch.cuda.memory_allocated()/1e9:.2f} GB")
    
    lora_config = LoraConfig(
        r=16, lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "out_proj"],
        lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)
    
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    log(f"Trainable: {trainable:,}/{total:,} ({trainable/total*100:.2f}%)")
    
    device = torch.device("cuda:0")
    
    log("Loading data...")
    with open(DATA_PATH) as f:
        data = [json.loads(line) for line in f]
    log(f"{len(data)} examples")
    
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
            return {
                "input_ids": self.encodings["input_ids"][idx],
                "attention_mask": self.encodings["attention_mask"][idx],
                "labels": self.encodings["input_ids"][idx].clone(),
            }
        def __len__(self):
            return len(self.encodings["input_ids"])
    
    dataset = QuantaDataset(formatted, tokenizer, MAX_SEQ_LEN)
    train_size = int(0.95 * len(dataset))
    val_size = len(dataset) - train_size
    train_ds, val_ds = torch.utils.data.random_split(dataset, [train_size, val_size])
    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE)
    log(f"Train: {train_size}, Val: {val_size}")
    
    trainable_params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(trainable_params, lr=LR, weight_decay=0.01)
    
    total_steps = 0
    best_val_loss = float("inf")
    
    log("Starting training...")
    model.train()
    
    for epoch in range(NUM_EPOCHS):
        epoch_start = time.time()
        for step, batch in enumerate(train_loader):
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["labels"].to(device)
            
            outputs = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
            loss = outputs.loss / GRAD_ACCUM
            loss.backward()
            
            if (step + 1) % GRAD_ACCUM == 0:
                optimizer.step()
                optimizer.zero_grad()
                total_steps += 1
                
                if total_steps % 50 == 0:
                    vram = torch.cuda.memory_allocated() / 1e9
                    log(f"Epoch {epoch+1} Step {total_steps} Loss: {loss.item() * GRAD_ACCUM:.4f} VRAM: {vram:.2f}GB")
                
                # Save checkpoint every 100 steps
                if total_steps % 100 == 0:
                    ckpt_dir = f"{OUTPUT_DIR}/step-{total_steps}"
                    model.save_pretrained(ckpt_dir)
                    log(f"  -> Checkpoint saved: {ckpt_dir}")
        
        model.eval()
        val_loss = 0
        val_steps = 0
        with torch.no_grad():
            for batch in val_loader:
                input_ids = batch["input_ids"].to(device)
                attention_mask = batch["attention_mask"].to(device)
                labels = batch["labels"].to(device)
                outputs = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
                val_loss += outputs.loss.item()
                val_steps += 1
        
        avg_val = val_loss / val_steps
        epoch_time = time.time() - epoch_start
        log(f"Epoch {epoch+1} Val loss: {avg_val:.4f} ({epoch_time:.1f}s)")
        
        if avg_val < best_val_loss:
            best_val_loss = avg_val
            model.save_pretrained(f"{OUTPUT_DIR}/best")
            tokenizer.save_pretrained(f"{OUTPUT_DIR}/best")
            log(f"  -> Saved best (val_loss: {avg_val:.4f})")
        
        model.train()
    
    model.save_pretrained(f"{OUTPUT_DIR}/final")
    tokenizer.save_pretrained(f"{OUTPUT_DIR}/final")
    
    with open(f"{OUTPUT_DIR}/results.json", "w") as f:
        json.dump({"best_val_loss": best_val_loss, "total_steps": total_steps, "r": 16, "lr": LR}, f, indent=2)
    
    log_file.close()
    log(f"Phase 1 done! Best val_loss: {best_val_loss:.4f}")

if __name__ == "__main__":
    main()
