import sys
#!/usr/bin/env python3
"""
Quanta RAG Server
Fast local RAG: numpy brute-force search + llama.cpp inference
"""

import os
import sqlite3
import time
import json
import numpy as np
from sentence_transformers import SentenceTransformer
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rag_config as _CFG

# Config
DB_PATH = _CFG.get("rag", "db")
E2B_MODEL = "/opt/ai/models/gemma-4b-e2b.gguf"
LLAMA_CPP = "/opt/ai/llama.cpp/build/bin/llama-cli"

class QuantaRAGServer:
    def __init__(self):
        print("="*60)
        print("Quanta RAG Server")
        print("="*60)
        
        # Load embedding model
        print("\n1. Loading embedding model...")
        self.encoder = SentenceTransformer(_CFG.get("embed", "model", "all-MiniLM-L6-v2"))
        
        # Load all embeddings into memory
        print("\n2. Loading embeddings into matrix...")
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.execute('SELECT id, source, type, chunk_index, content, embedding FROM chunks WHERE embedding IS NOT NULL')
        
        self.ids, self.sources, self.types, self.indices, self.contents, embeddings_list = [], [], [], [], [], []
        for row in cursor:
            self.ids.append(row[0])
            self.sources.append(row[1])
            self.types.append(row[2])
            self.indices.append(row[3])
            self.contents.append(row[4])
            embeddings_list.append(np.frombuffer(row[5], dtype=np.float32))
        
        conn.close()
        
        # Stack and normalize
        self.emb_matrix = np.stack(embeddings_list).astype(np.float32)
        norms = np.linalg.norm(self.emb_matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1
        self.emb_matrix_norm = self.emb_matrix / norms
        
        print(f"   Loaded {len(self.ids):,} embeddings")
        print(f"   Matrix: {self.emb_matrix_norm.shape}")
        print(f"   Memory: {self.emb_matrix_norm.nbytes / 1e9:.2f} GB")
        
        # Check llama.cpp
        self.llama_available = os.path.exists(LLAMA_CPP)
        if self.llama_available:
            print(f"\n3. ✅ llama.cpp: {LLAMA_CPP}")
        else:
            print(f"\n3. ⚠️  llama.cpp not found")
            print("   Search-only mode")
        
        print("\n" + "="*60)
    
    def search(self, query: str, top_k: int = 5) -> list:
        """Fast vector search using pre-loaded matrix"""
        query_emb = self.encoder.encode([query]).astype(np.float32)
        query_norm = query_emb / np.linalg.norm(query_emb)
        
        # Cosine similarity
        sims = np.dot(self.emb_matrix_norm, query_norm.T).flatten()
        
        # Boost Quanta-native files
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
    
    def build_prompt(self, query: str, context: list) -> str:
        """Build RAG prompt"""
        context_text = ""
        for i, chunk in enumerate(context, 1):
            context_text += f"\n--- Context {i} ({chunk['source']}, score: {chunk['score']:.3f}) ---\n{chunk['content']}\n"
        
        return f"""<start_of_turn>user
You are a Quanta language expert. Answer using ONLY the context below.

CONTEXT FROM QUANTA SOURCE CODE AND DOCS:
{context_text}

QUESTION: {query}

RULES:
- Answer ONLY using the provided context
- DO NOT make up information from other languages
- DO NOT reference Python, Rust, C++, Go, or any non-Quanta language
- If context lacks info, say so
- Cite source files when possible

ANSWER:
<end_of_turn>
<start_of_turn>model"""
    
    def generate(self, prompt: str, max_tokens: int = 512) -> str:
        """Generate with llama.cpp"""
        if not self.llama_available:
            return "[Inference not available - install llama.cpp]"
        
        import subprocess
        cmd = [
            LLAMA_CPP, "-m", E2B_MODEL, "-p", prompt,
            "-n", str(max_tokens), "--temp", "0.3", "--top-p", "0.95", "-t", "8"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return result.stdout.strip() if result.returncode == 0 else f"[Error: {result.stderr[:200]}]"
    
    def query(self, query: str, top_k: int = 5, max_tokens: int = 256) -> dict:
        """Full RAG pipeline"""
        start = time.time()
        
        # Search
        context = self.search(query, top_k)
        search_time = time.time() - start
        
        # Build prompt
        prompt = self.build_prompt(query, context)
        
        # Generate
        gen_start = time.time()
        answer = self.generate(prompt, max_tokens)
        gen_time = time.time() - gen_start
        
        return {
            'query': query,
            'context': context,
            'prompt_length': len(prompt),
            'answer': answer,
            'search_time': search_time,
            'gen_time': gen_time,
            'total_time': time.time() - start
        }
    
    def interactive(self):
        """Interactive RAG session"""
        print("\nInteractive RAG Session (type 'quit' to exit)")
        print("="*60)
        
        while True:
            query = input("\nQuery: ").strip()
            if query.lower() in ['quit', 'exit', 'q']:
                break
            
            if not query:
                continue
            
            result = self.query(query, top_k=5, max_tokens=256)
            
            print(f"\nSearch: {result['search_time']:.2f}s | Generation: {result['gen_time']:.2f}s")
            print(f"\nSources: {[c['source'] for c in result['context']]}")
            print(f"\nAnswer:\n{result['answer'][:1000]}")

def test_rag():
    """Test RAG with Quanta-specific queries"""
    print("\nTesting RAG pipeline...")
    print("="*60)
    
    server = QuantaRAGServer()
    
    # Test queries
    queries = [
        "What is IR_CALL in the Quanta compiler?",
        "How do you compile a Quanta file?",
        "What is the str_append builtin function?",
        "How does pattern matching work in Quanta?",
    ]
    
    results = {}
    for q in queries:
        print(f"\n{'='*60}")
        print(f"Query: {q}")
        print('='*60)
        
        result = server.query(q, top_k=3, max_tokens=128)
        
        print(f"\nSearch time: {result['search_time']:.3f}s")
        print(f"Sources: {[c['source'] for c in result['context']]}")
        scores = [f'{c["score"]:.3f}' for c in result['context']]
        print(f'Scores: {scores}')
        
        if result['answer']:
            print(f"\nAnswer:\n{result['answer'][:500]}")
        
        results[q] = result
    
    return results

if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        test_rag()
    else:
        server = QuantaRAGServer()
        server.interactive()
