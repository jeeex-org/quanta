#!/usr/bin/env python3
"""LFM2.5-2.6B GPU training — correct LFM2 template + full logging"""
import os
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

import json, torch, time
from datetime import datetime

MODEL_PATH = "/opt/tali/ti/ai/models/lfm2.5-2b6"
DATA_PATH = "/opt/tali/quanta/training_data/quanta_finetune.jsonl"
OUTPUT_DIR = "/opt/tali/quanta/output/lfm2.5_2b6_gpu_v1"

LEARNING_RATE = 3e-4
NUM_EPOCHS = 3
BATCH_SIZE = 1
GRAD_ACCUM = 4
MAX_SEQ_LEN = 256

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    print("="*60)
    print(f"LFM2.5-2.6B: GPU training, LFM2 native template")
    print(f"Time: {datetime.now().isoformat()}")
    print("="*60)
    
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    
    print("\nLoading model (4-bit)...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
    tokenizer.pad_token = tokenizer.eos_token
    
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_PATH,
        quantization_config=bnb_config,
        device_map={"": 0},
        torch_dtype=torch.bfloat16,
    )
    
    print(f"Loaded. VRAM: {torch.cuda.memory_allocated()/1e9:.2f} GB")
    
    from peft import LoraConfig, get_peft_model
    
    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "out_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    
    model = get_peft_model(model, lora_config)
    
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    print(f"Trainable: {trainable:,}/{total:,} ({trainable/total*100:.2f}%)")
    
    device = torch.device("cuda:0")
    
    # Data with LFM2 native chat template
    print("\nLoading data...")
    with open(DATA_PATH) as f:
        data = [json.loads(line) for line in f]
    print(f"{len(data)} examples")
    
    formatted = []
    for item in data:
        inst = item.get("instruction", "")
        resp = item.get("response", "")
        # LFM2 native chat template
        text = f"<|im_start|>user\n{inst}<|im_end|>\n<|im_start|>assistant\n{resp}<|im_end|>"
        formatted.append(text)
    
    from torch.utils.data import Dataset, DataLoader
    
    class QuantaDataset(Dataset):
        def __init__(self, texts, tokenizer, max_len):
            self.encodings = tokenizer(
                texts, truncation=True, max_length=max_len,
                padding="max_length", return_tensors="pt"
            )
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
    print(f"Train: {train_size}, Val: {val_size}")
    
    trainable_params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(trainable_params, lr=LEARNING_RATE, weight_decay=0.01)
    
    # Log file
    log_file = open(f"{OUTPUT_DIR}/training.log", "w")
    
    print("\nTraining...")
    print("="*60)
    
    model.train()
    total_steps = 0
    best_val_loss = float("inf")
    
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
                    lr = optimizer.param_groups[0]['lr']
                    log = f"Epoch {epoch+1}/{NUM_EPOCHS} Step {total_steps} Loss: {loss.item() * GRAD_ACCUM:.4f} VRAM: {vram:.2f}GB"
                    print(log)
                    log_file.write(log + "\n")
                    log_file.flush()
        
        # End of epoch — validation
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
        log = f"Epoch {epoch+1} Val loss: {avg_val:.4f} (time: {epoch_time:.1f}s)"
        print(log)
        log_file.write(log + "\n")
        log_file.flush()
        
        if avg_val < best_val_loss:
            best_val_loss = avg_val
            sp = f"{OUTPUT_DIR}/best"
            model.save_pretrained(sp)
            tokenizer.save_pretrained(sp)
            log = f"  -> Saved best model (val_loss: {avg_val:.4f})"
            print(log)
            log_file.write(log + "\n")
            log_file.flush()
        
        model.train()
    
    final = f"{OUTPUT_DIR}/final"
    model.save_pretrained(final)
    tokenizer.save_pretrained(final)
    
    # Save final state
    with open(f"{OUTPUT_DIR}/results.json", "w") as f:
        json.dump({
            "best_val_loss": best_val_loss,
            "total_steps": total_steps,
            "config": {
                "r": 16,
                "alpha": 32,
                "lr": LEARNING_RATE,
                "seq_len": MAX_SEQ_LEN,
                "batch_size": BATCH_SIZE,
                "grad_accum": GRAD_ACCUM,
                "epochs": NUM_EPOCHS,
                "template": "lmf2_native",
                "device": "gpu",
            }
        }, f, indent=2)
    
    log_file.close()
    print(f"\nDone! Best val_loss: {best_val_loss:.4f}")
    print(f"Results saved to {OUTPUT_DIR}/results.json")

if __name__ == "__main__":
    main()
