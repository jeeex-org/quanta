#!/usr/bin/env python3
"""
Quanta RAG CLI
Usage: python3 rag_cli.py "your question" [--model e2b|e4b] [--top-k 5] [--max-tokens 256]
"""

import os
import sys
import json
import sqlite3
import time
import argparse
import numpy as np
import urllib.request
from sentence_transformers import SentenceTransformer
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rag_config as _CFG

# Config
DB_PATH = _CFG.get("rag", "db")
E2B_API = "http://localhost:1235/v1/chat/completions"
E4B_API = "http://localhost:1236/v1/chat/completions"

class QuantaRAG:
    def __init__(self):
        self.encoder = SentenceTransformer(_CFG.get("embed", "model", "all-MiniLM-L6-v2"))
        self.conn = sqlite3.connect(DB_PATH)
        self._load_embeddings()
    
    def _load_embeddings(self, limit=100000):
        """Load embeddings into memory"""
        cursor = self.conn.execute(
            f"SELECT id, source, content, embedding FROM chunks WHERE embedding IS NOT NULL LIMIT {limit}"
        )
        ids, sources, contents, embs = [], [], [], []
        for row in cursor:
            ids.append(row[0])
            sources.append(row[1])
            contents.append(row[2])
            embs.append(np.frombuffer(row[3], dtype=np.float32))
        
        self.ids = ids
        self.sources = sources
        self.contents = contents
        
        # Normalize
        emb_matrix = np.stack(embs).astype(np.float32)
        norms = np.linalg.norm(emb_matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1
        self.emb_matrix_norm = emb_matrix / norms
        
        print(f"Loaded {len(ids):,} embeddings", file=sys.stderr)
    
    def search(self, query: str, top_k: int = 5) -> list:
        """Semantic search"""
        query_emb = self.encoder.encode([query]).astype(np.float32)
        query_norm = query_emb / np.linalg.norm(query_emb)
        
        sims = np.dot(self.emb_matrix_norm, query_norm.T).flatten()
        
        # Boost Quanta-native files
        for i, source in enumerate(self.sources):
            if source.endswith('.quanta') or 'compiler/' in source or 'lib/std/' in source:
                sims[i] *= 1.2
        
        top_indices = np.argsort(sims)[-top_k:][::-1]
        
        results = []
        for idx in top_indices:
            results.append({
                'source': self.sources[idx],
                'score': float(sims[idx]),
                'content': self.contents[idx]
            })
        return results
    
    def build_prompt(self, query: str, context: list) -> str:
        """Build prompt with context"""
        ctx = ""
        for i, c in enumerate(context, 1):
            ctx += f"\n--- Context {i} ({c['source']}, score: {c['score']:.3f}) ---\n{c['content'][:400]}\n"
        
        return f"""You are a Quanta language expert. Use ONLY the context below to answer.

CONTEXT FROM QUANTA SOURCE CODE AND DOCS:
{ctx}

QUESTION: {query}

RULES:
- Answer ONLY using the provided context
- DO NOT make up information from other languages
- DO NOT reference Python, Rust, C++, Go, or any non-Quanta language
- Cite source files when possible
- Be concise but accurate"""
    
    def query(self, query: str, model: str = "e2b", top_k: int = 5, max_tokens: int = 256) -> dict:
        """Full RAG pipeline"""
        start = time.time()
        
        # Search
        context = self.search(query, top_k)
        search_time = time.time() - start
        
        # Build prompt
        prompt = self.build_prompt(query, context)
        
        # Select model
        api_url = E2B_API if model == "e2b" else E4B_API
        
        # Call llama-server
        messages = [{"role": "user", "content": prompt}]
        data = json.dumps({
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.3,
            "top_p": 0.95,
            "chat_template_kwargs": {"enable_thinking": False}
        }).encode()
        
        req = urllib.request.Request(api_url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                result = json.loads(resp.read().decode())
            gen_time = time.time() - start - search_time
            
            answer = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            answer = f"[Error: {e}]"
            gen_time = 0
        
        return {
            'query': query,
            'answer': answer,
            'sources': [c['source'] for c in context],
            'scores': [f"{c['score']:.3f}" for c in context],
            'search_time': search_time,
            'gen_time': gen_time,
            'total_time': time.time() - start,
            'model': model
        }

def main():
    parser = argparse.ArgumentParser(description="Quanta RAG CLI")
    parser.add_argument("query", help="Your question about Quanta")
    parser.add_argument("--model", choices=["e2b", "e4b"], default="e2b", help="Model to use")
    parser.add_argument("--top-k", type=int, default=5, help="Number of context chunks")
    parser.add_argument("--max-tokens", type=int, default=256, help="Max tokens for answer")
    
    args = parser.parse_args()
    
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"Quanta RAG", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    
    rag = QuantaRAG()
    
    print(f"\nQuery: {args.query}", file=sys.stderr)
    print(f"Model: {args.model.upper()}", file=sys.stderr)
    
    result = rag.query(args.query, args.model, args.top_k, args.max_tokens)
    
    print(f"\nSearch: {result['search_time']:.3f}s", file=sys.stderr)
    print(f"Generation: {result['gen_time']:.2f}s", file=sys.stderr)
    print(f"Sources: {result['sources']}", file=sys.stderr)
    print(f"Scores: {result['scores']}", file=sys.stderr)
    
    print(f"\n{result['answer']}")

if __name__ == "__main__":
    main()
