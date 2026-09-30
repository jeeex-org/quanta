#!/usr/bin/env python3
"""Compute embedding for query - silent output"""
import sys
import numpy as np

# Suppress all warnings
import warnings
warnings.filterwarnings('ignore')

from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")

query = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read().strip()
embedding = model.encode([query], show_progress_bar=False)[0].astype(np.float32)

# Output ONLY hex to stdout
sys.stdout.write(embedding.tobytes().hex())
