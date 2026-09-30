#!/usr/bin/env python3
"""LFM2.5-2.6B Phase 3: GPU training"""
import os
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer, SFTConfig
from datasets import load_dataset

MODEL_PATH = "/opt/tali/ti/ai/models/lfm2.5-2b6"
DATA_PATH = "/opt/tali/quanta/training_data/quanta_finetune.jsonl"
OUTPUT_DIR = "/opt/tali/quanta/output/lfm2.5_2b6_phase3"

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
)

tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
tokenizer.pad_token = tokenizer.eos_token

model = AutoModelForCausalLM.from_pretrained(
    MODEL_PATH,
    quantization_config=bnb_config,
    device_map="auto",
    torch_dtype=torch.bfloat16,
)

model = prepare_model_for_kbit_training(model)

peft_config = LoraConfig(
    r=16,
    lora_alpha=32,
    target_modules=["q_proj", "v_proj", "k_proj", "out_proj"],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
)

model = get_peft_model(model, peft_config)
model.print_trainable_parameters()

dataset = load_dataset("json", data_files=DATA_PATH, split="train")

training_args = SFTConfig(
    output_dir=OUTPUT_DIR,
    per_device_train_batch_size=1,
    gradient_accumulation_steps=4,
    optim="paged_adamw_8bit",
    learning_rate=2e-4,
    num_train_epochs=3,
    bf16=True,
    max_length=512,
    logging_steps=10,
    save_steps=50,
    save_total_limit=3,
    eval_strategy="steps",
    eval_steps=50,
    load_best_model_at_end=True,
    metric_for_best_model="eval_loss",
    greater_is_better=False,
)

def formatting_func(example):
    text = f"### Instruction:\n{example['instruction']}\n\n"
    if example.get('input'):
        text += f"### Input:\n{example['input']}\n\n"
    text += f"### Response:\n{example['response']}"
    return text

trainer = SFTTrainer(
    model=model,
    args=training_args,
    train_dataset=dataset,
    eval_dataset=dataset,
    processing_class=tokenizer,
    formatting_func=formatting_func,
)

trainer.train()

model.save_pretrained(f"{OUTPUT_DIR}/best")
tokenizer.save_pretrained(f"{OUTPUT_DIR}/best")
print(f"Saved to {OUTPUT_DIR}/best")
