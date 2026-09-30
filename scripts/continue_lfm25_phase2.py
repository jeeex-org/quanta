#!/usr/bin/env python3
"""Continue LFM2.5-2.6B Phase 2: Higher rank LoRA + all attention layers"""
import os
os.environ["CUDA_VISIBLE_DEVICES"] = "0"
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "max_split_size_mb:128,expandable_segments:True"

import json, torch
from datetime import datetime

MODEL_PATH = "/opt/tali/ti/ai/models/lfm2.5-2b6"
ADAPTER_PATH = "/opt/tali/quanta/output/lfm2.5_2b6_phase1/best"
OUTPUT_DIR = "/opt/tali/quanta/output/lfm2.5_2b6_phase2"

DATA_PATH = "/opt/tali/quanta/training_data/quanta_finetune.jsonl"

LEARNING_RATE = 5e-5
NUM_EPOCHS = 6
BATCH_SIZE = 1
GRAD_ACCUM = 4
MAX_SEQ_LEN = 256

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    print("="*60)
    print(f"LFM2.5-2.6B Phase 2: LR={LEARNING_RATE}, rank=32")
    print(f"Time: {datetime.now().isoformat()}")
    print("="*60)
    
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from peft import PeftModel, LoraConfig, get_peft_model
    
    print("\nLoading model...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(MODEL_PATH, quantization_config=bnb_config, device_map={"": 0}, trust_remote_code=True)
    
    # Replace existing LoRA with higher-rank adapters
    print(f"Loading adapter from {ADAPTER_PATH}...")
    model = PeftModel.from_pretrained(model, ADAPTER_PATH)
    
    # Merge and recreate with higher rank
    print("Merging and creating higher-rank LoRA...")
    model = model.merge_and_unload()
    
    lora_config = LoraConfig(
        r=32,
        lora_alpha=64,
        target_modules=["q_proj", "k_proj", "v_proj", "out_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    
    model = get_peft_model(model, lora_config)
    model = model.to("cuda:0")
    
    print(f"Loaded. VRAM: {torch.cuda.memory_allocated()/1e9:.2f} GB")
    
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    print(f"Trainable: {trainable:,}/{total:,} ({trainable/total*100:.2f}%)")
    
    device = torch.device("cuda:0")
    
    print("\nLoading data...")
    with open(DATA_PATH) as f:
        data = [json.loads(line) for line in f]
    print(f"{len(data)} examples")
    
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
    
    print("\nTraining...")
    print("="*60)
    
    model.train()
    total_steps = 0
    best_val_loss = float("inf")
    
    for epoch in range(NUM_EPOCHS):
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
                    print(f"Epoch {epoch+1}/{NUM_EPOCHS} Step {total_steps} Loss: {loss.item() * GRAD_ACCUM:.4f} VRAM: {vram:.2f}GB")
        
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
