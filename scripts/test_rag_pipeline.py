#!/usr/bin/env python3
"""
RAG Pipeline for Quanta
Tests retrieval + inference with E2B and E4B models
"""

import os
import sys
import sqlite3
import time
import json
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rag_config as _CFG

# Config
DB_PATH = _CFG.get("rag", "db")
QUANTA_ROOT = "/opt/tali/quanta"

class QuantaRAG:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        print(f"Loading embedding model: {model_name}")
        self.encoder = SentenceTransformer(model_name)
        self.conn = sqlite3.connect(DB_PATH)
        self.cursor = self.conn.cursor()
        
        # Get stats
        self.cursor.execute("SELECT COUNT(*) FROM chunks")
        self.total_chunks = self.cursor.fetchone()[0]
        print(f"Knowledge base: {self.total_chunks:,} chunks")
    
    def search(self, query: str, top_k: int = 5) -> list:
        """Semantic search for relevant chunks"""
        query_emb = self.encoder.encode([query])[0]
        
        # Brute force search (sqlite-vec extension not loaded in this script)
        # For production, use sqlite-vec extension
        self.cursor.execute("SELECT id, source, type, chunk_index, content, embedding FROM chunks")
        
        results = []
        for row in self.cursor:
            chunk_id, source, chunk_type, chunk_index, content, emb_bytes = row
            emb = np.frombuffer(emb_bytes, dtype=np.float32)
            
            # Cosine similarity
            norm = np.linalg.norm(query_emb) * np.linalg.norm(emb)
            if norm > 0:
                sim = np.dot(query_emb, emb) / norm
                results.append({
                    'id': chunk_id,
                    'source': source,
                    'type': chunk_type,
                    'chunk_index': chunk_index,
                    'content': content,
                    'score': float(sim)
                })
        
        # Sort by similarity
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_k]
    
    def build_prompt(self, query: str, context_chunks: list) -> str:
        """Build RAG prompt with context"""
        context_text = ""
        for i, chunk in enumerate(context_chunks, 1):
            context_text += f"\n--- Context {i} (from {chunk['source']}, score: {chunk['score']:.3f}) ---\n{chunk['content']}\n"
        
        prompt = f"""You are an expert Quanta language assistant. Use the provided context to answer the question.

CONTEXT FROM QUANTA SOURCE CODE AND DOCS:
{context_text}

QUESTION: {query}

RULES:
- Answer ONLY using information from the context above
- If context doesn't contain enough information, say "The provided context does not contain information about [topic]. Try rephrasing or ask about a related concept."
- DO NOT make up information from other programming languages or AI training
- DO NOT reference Python, Rust, C++, or any language other than Quanta
- Cite source files when possible
- Be concise but accurate

ANSWER:"""
        
        return prompt
    
    def query(self, query: str, top_k: int = 5) -> dict:
        """Full RAG pipeline: search + build prompt"""
        # Retrieve
        start = time.time()
        chunks = self.search(query, top_k)
        search_time = time.time() - start
        
        # Build prompt
        prompt = self.build_prompt(query, chunks)
        
        # Extract sources
        sources = list(set(c['source'] for c in chunks))
        
        return {
            'query': query,
            'context': chunks,
            'prompt': prompt,
            'sources': sources,
            'search_time': search_time
        }

def test_rag():
    """Test RAG with Quanta-specific queries"""
    print("="*60)
    print("Quanta RAG Test")
    print("="*60)
    
    rag = QuantaRAG()
    
    # Test queries
    queries = [
        "What is IR_CALL in the Quanta compiler?",
        "How do you compile a Quanta file?",
        "What is the str_append builtin function?",
        "How does pattern matching work in Quanta?",
        "What are the differences between i32 and i64 types?",
    ]
    
    results = {}
    for q in queries:
        print(f"\nQuery: {q}")
        result = rag.query(q, top_k=3)
        
        print(f"  Search time: {result['search_time']:.3f}s")
        print(f"  Sources: {result['sources']}")
        scores = [f"{c['score']:.3f}" for c in result['context']]
        print(f"  Scores: {scores}")
        
        results[q] = result
    
    # Save prompts for each model
    output = {
        'queries': {q: {
            'sources': r['sources'],
            'scores': [f"{c['score']:.3f}" for c in r['context']],
            'prompt_preview': r['prompt'][:500] + "..."
        } for q, r in results.items()}
    }
    
    with open(_CFG.get("rag", "results_file"), 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n✅ RAG test complete. Results saved to {_CFG.get('rag', 'results_file')}")
    
    return results

if __name__ == "__main__":
    test_rag()