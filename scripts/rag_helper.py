import os
#!/usr/bin/env python3
"""Quanta RAG helper - embed + search + infer"""
import sys
import json
import numpy as np
import sqlite3
import urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rag_config as _CFG

DB_PATH = _CFG.get("rag", "db")
def main():
    if len(sys.argv) < 2:
        print("Usage: rag_helper.py <query> [e2b|e4b]", file=sys.stderr)
        sys.exit(1)
    
    query = sys.argv[1]
    model = sys.argv[2] if len(sys.argv) > 2 else "e2b"
    port = "1236" if model == "e4b" else "1235"
    
    # Embed
    from sentence_transformers import SentenceTransformer
    encoder = SentenceTransformer(_CFG.get("embed", "model", "all-MiniLM-L6-v2"))
    query_emb = encoder.encode([query], show_progress_bar=False)[0].astype(np.float32)
    
    # Search - load embeddings into matrix for brute-force
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("SELECT source, content, embedding FROM chunks WHERE embedding IS NOT NULL LIMIT 100000")
    
    sources, contents, embs = [], [], []
    for row in cursor:
        sources.append(row[0])
        contents.append(row[1])
        embs.append(np.frombuffer(row[2], dtype=np.float32))
    conn.close()
    
    # Brute-force cosine similarity
    emb_matrix = np.stack(embs).astype(np.float32)
    norms = np.linalg.norm(emb_matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1
    emb_matrix_norm = emb_matrix / norms
    
    query_norm = query_emb / np.linalg.norm(query_emb)
    sims = np.dot(emb_matrix_norm, query_norm.T).flatten()
    
    # Get top-5
    top_idx = np.argsort(sims)[-5:][::-1]
    
    context = []
    for idx in top_idx:
        context.append({"source": sources[idx], "content": contents[idx][:300]})
    
    # Build prompt
    prompt = "You are a Quanta language expert. Use ONLY the context below.\n"
    prompt += "DO NOT reference Python, Rust, C++, or other languages.\n\n"
    for i, c in enumerate(context, 1):
        prompt += f"--- Context {i} ({c['source']}) ---\n{c['content']}\n\n"
    prompt += f"QUESTION: {query}\n\nANSWER:"
    
    # Call LLM
    data = json.dumps({
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 256,
        "temperature": 0.3,
        "chat_template_kwargs": {"enable_thinking": False}
    }).encode()
    
    req = urllib.request.Request(
        f"http://localhost:{port}/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"}
    )
    
    with urllib.request.urlopen(req, timeout=300) as resp:
        result = json.loads(resp.read().decode())
    
    answer = result.get("choices", [{}])[0].get("message", {}).get("content", "")
    
    # Output
    print(json.dumps({
        "query": query,
        "answer": answer,
        "sources": [c["source"] for c in context]
    }))

if __name__ == "__main__":
    main()
