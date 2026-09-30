#!/usr/bin/env python3
"""Fine-tune LFM2.5-8B-A1B with DeepSpeed ZeRO-3 (CPU offload for parameters)"""
import os
os.environ["CUDA_VISIBLE_DEVICES"] = "0"
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

import json, torch, deepspeed
from datetime import datetime

MODEL_PATH = "/opt/tali/ti/ai/models/lfm2.5-8b-a1b"
DATA_PATH = "/opt/tali/quanta/training_data/quanta_finetune.jsonl"
OUTPUT_DIR = "/opt/tali/quanta/output/lfm2.5_8b_a1b_deepspeed"

LEARNING_RATE = 2e-4
NUM_EPOCHS = 3
BATCH_SIZE = 1
GRAD_ACCUM = 4
MAX_SEQ_LEN = 256

# DeepSpeed config for ZeRO-3 with CPU offload
DS_CONFIG = {
    "bf16": {"enabled": True},
    "zero_optimization": {
        "stage": 3,
        "offload_optimizer": {"device": "cpu", "pin_memory": True},
        "offload_param": {"device": "cpu", "pin_memory": True},
        "overlap_comm": True,
        "contiguous_gradients": True,
        "sub_group_size": 1e9,
        "reduce_bucket_size": "auto",
        "stage3_prefetch_bucket_size": "auto",
        "stage3_param_persistence_threshold": "auto",
        "stage3_max_live_parameters": 1e9,
        "stage3_max_reuse_distance": 1e9,
        "stage3_gather_16bit_weights_on_model_save": True,
    },
    "gradient_accumulation_steps": GRAD_ACCUM,
    "gradient_clipping": 1.0,
    "steps_per_print": 10,
    "train_batch_size": "auto",
    "train_micro_batch_size_per_gpu": BATCH_SIZE,
    "wall_clock_breakdown": False,
}

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    print("="*60)
    print(f"LFM2.5-8B-A1B: DeepSpeed ZeRO-3 (full parameter offload)")
    print(f"Time: {datetime.now().isoformat()}")
    print("="*60)
    
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    
    print("\nLoading model (4-bit)...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
    tokenizer.pad_token = tokenizer.eos_token
    
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
    
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_PATH,
        quantization_config=bnb_config,
        trust_remote_code=True,
    )
    
    print(f"Model loaded. VRAM: {torch.cuda.memory_allocated()/1e9:.2f} GB")
    
    # Data
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
    
    # DeepSpeed initialization
    print("\nInitializing DeepSpeed...")
    model_engine, optimizer, _, _ = deepspeed.initialize(
        model=model,
        config=DS_CONFIG,
    )
    
    print(f"DeepSpeed ready. VRAM: {torch.cuda.memory_allocated()/1e9:.2f} GB")
    
    print("\nTraining...")
    print("="*60)
    
    model_engine.train()
    total_steps = 0
    best_val_loss = float("inf")
    
    for epoch in range(NUM_EPOCHS):
        for step, batch in enumerate(train_loader):
            input_ids = batch["input_ids"].to(model_engine.device)
            attention_mask = batch["attention_mask"].to(model_engine.device)
            labels = batch["labels"].to(model_engine.device)
            
            outputs = model_engine(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
            loss = outputs.loss
            model_engine.backward(loss)
            model_engine.step()
            
            total_steps += 1
            
            if total_steps % 10 == 0:
                vram = torch.cuda.memory_allocated() / 1e9
                print(f"Step {total_steps} Loss: {loss.item():.4f} VRAM: {vram:.2f}GB")
        
        # Validation
        model_engine.eval()
        val_loss = 0
        val_steps = 0
        with torch.no_grad():
            for batch in val_loader:
                input_ids = batch["input_ids"].to(model_engine.device)
                attention_mask = batch["attention_mask"].to(model_engine.device)
                labels = batch["labels"].to(model_engine.device)
                outputs = model_engine(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
                val_loss += outputs.loss.item()
                val_steps += 1
        
        avg_val = val_loss / val_steps
        print(f"Epoch {epoch+1} Val loss: {avg_val:.4f}")
        
        model_engine.train()
    
    print(f"\nDone!")
    model_engine.save_checkpoint(OUTPUT_DIR)

if __name__ == "__main__":
    main()
