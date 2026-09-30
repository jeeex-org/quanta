import sys
import os
#!/usr/bin/env python3
"""Test RAG search on current DB"""
import sqlite3
import numpy as np
from sentence_transformers import SentenceTransformer
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rag_config as _CFG

DB_PATH = _CFG.get("rag", "db")
MODEL = "all-MiniLM-L6-v2"

model = SentenceTransformer(MODEL)
conn = sqlite3.connect(DB_PATH)

def search(query: str, top_k: int = 5):
    """Search for similar chunks"""
    # Embed query
    query_emb = model.encode([query])[0]
    
    # Get all embeddings (brute force for now - sqlite-vec extension not loaded)
    cursor = conn.execute("SELECT id, content, source, embedding FROM chunks")
    
    results = []
    for row in cursor:
        chunk_id, content, source, emb_bytes = row
        emb = np.frombuffer(emb_bytes, dtype=np.float32)
        
        # Cosine similarity
        sim = np.dot(query_emb, emb) / (np.linalg.norm(query_emb) * np.linalg.norm(emb))
        results.append((sim, source, content[:200]))
    
    # Sort by similarity
    results.sort(reverse=True)
    return results[:top_k]

# Test queries
queries = [
    "What is IR_CALL in Quanta compiler?",
    "How to compile a quanta file?",
    "What is the str_append function?",
    "Revenue recognition accounting GAAP",
]

for q in queries:
    print(f"\n{'='*60}")
    print(f"Query: {q}")
    print('='*60)
    
    results = search(q, top_k=3)
    for i, (sim, source, content) in enumerate(results, 1):
        print(f"\n  [{i}] Score: {sim:.3f} | Source: {source}")
        print(f"      {content[:150]}...")

conn.close()
