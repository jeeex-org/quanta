import sys
#!/usr/bin/env python3
"""
Optimized RAG with sqlite-vec extension + file type boosting
"""

import os
import sqlite3
import time
import json
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rag_config as _CFG

DB_PATH = _CFG.get("rag", "db")
class FastRAG:
    def __init__(self):
        print("Loading embedding model...")
        self.encoder = SentenceTransformer(_CFG.get("embed", "model", "all-MiniLM-L6-v2"))
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.execute("PRAGMA journal_mode=WAL")
        
        # Load sqlite-vec extension
        try:
            self.conn.enable_load_extension(True)
            self.conn.load_extension("sqlite_vec")
            print("✅ sqlite-vec extension loaded")
        except Exception as e:
            print(f"⚠️  sqlite-vec extension failed: {e}")
            print("Falling back to Python-side cosine similarity")
        
        # Check tables
        cursor = self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cursor.fetchall()]
        print(f"Tables: {tables}")
        
        # Get count
        cursor = self.conn.execute("SELECT COUNT(*) FROM chunks")
        self.total = cursor.fetchone()[0]
        print(f"Knowledge base: {self.total:,} chunks")
    
    def search(self, query: str, top_k: int = 5, boost_quanta: bool = True) -> list:
        """Fast vector search using pre-loaded matrix"""
        query_emb = self.encoder.encode([query]).astype(np.float32)
        query_norm = query_emb / np.linalg.norm(query_emb)
        
        # Cosine similarity via matrix multiplication
        sims = np.dot(self.emb_matrix_norm, query_norm.T).flatten()
        
        # Boost Quanta-native files
        if boost_quanta:
            for i, source in enumerate(self.sources):
                if source.endswith('.quanta') or 'compiler/' in source or 'lib/std/' in source:
                    sims[i] *= 1.2
        
        # Get top-k
        top_indices = np.argsort(sims)[-top_k:][::-1]
        
        results = []
        for idx in top_indices:
            results.append({
                'source': self.sources[idx],
                'type': self.types[idx],
                'score': float(sims[idx]),
                'content': self.contents[idx]
            })
        
        return results
    
    def _brute_force_search(self, query_emb: np.ndarray, top_k: int, boost_quanta: bool) -> list:
        """Brute force cosine similarity"""
        cursor = self.conn.execute("SELECT source, type, content, embedding FROM chunks")
        
        results = []
        for row in cursor.fetchall():
            source, chunk_type, content, emb_bytes = row
            emb = np.frombuffer(emb_bytes, dtype=np.float32)
            
            norm = np.linalg.norm(query_emb) * np.linalg.norm(emb)
            if norm > 0:
                sim = np.dot(query_emb, emb) / norm
                
                if boost_quanta and (source.endswith('.quanta') or 'compiler/' in source):
                    sim *= 1.3
                
                results.append({
                    'source': source,
                    'type': chunk_type,
                    'score': sim,
                    'content': content[:300]
                })
        
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_k]

def test():
    rag = FastRAG()
    
    queries = [
        "What is IR_CALL?",
        "How to compile Quanta?",
        "str_append function",
        "pattern matching syntax",
        "difference between i32 and i64",
    ]
    
    for q in queries:
        print(f"\n{'='*50}")
        print(f"Query: {q}")
        start = time.time()
        results = rag.search(q, top_k=3)
        elapsed = time.time() - start
        
        print(f"Time: {elapsed:.3f}s")
        for i, r in enumerate(results, 1):
            print(f"  [{i}] {r['score']:.3f} | {r['source']}")
            print(f"      {r['content'][:150]}")

if __name__ == "__main__":
    test()
