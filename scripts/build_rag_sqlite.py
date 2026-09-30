import sys
#!/usr/bin/env python3
"""
Lightweight RAG with sqlite-vec
Small, fast, zero bloat compared to ChromaDB
"""

import os
import json
import sqlite3
import hashlib
from pathlib import Path
from typing import List, Dict, Any
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rag_config as _CFG

QUANTA_ROOT = "/opt/tali/quanta"
DB_PATH = _CFG.get("rag", "db")
EMBED_MODEL = "all-MiniLM-L6-v2"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
BATCH_SIZE = 500

def init_db(conn: sqlite3.Connection):
    """Initialize sqlite-vec database"""
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    
    # Load sqlite-vec extension
    try:
        conn.enable_load_extension(True)
        conn.load_extension("sqlite_vec")
    except Exception as e:
        print(f"Loading sqlite-vec from pip package...")
        import sqlite_vec
        sqlite_vec.load(conn)
    
    # Create tables
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            type TEXT NOT NULL,
            chunk_index INTEGER,
            content TEXT,
            embedding BLOB
        )
    """)
    
    # Create virtual table for vector search
    conn.execute(f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(
            id TEXT PRIMARY KEY,
            embedding FLOAT[384]
        )
    """)
    
    conn.commit()

def find_files(root: str) -> List[str]:
    """Find all .quanta and .md files"""
    result = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirs_to_skip = {'.git', '__pycache__', 'node_modules', '.hermes', 'temp', 'logs', 'rag'}
        dirnames[:] = [d for d in dirnames if d not in dirs_to_skip and not d.startswith('.')]
        
        for fname in filenames:
            if fname.endswith('.quanta') or fname.endswith('.md'):
                result.append(os.path.join(dirpath, fname))
    return result

def chunk_text(text: str) -> List[str]:
    """Split text into overlapping chunks"""
    if len(text) <= CHUNK_SIZE:
        return [text]
    
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunks.append(text[start:end])
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks

def build():
    """Build the RAG database"""
    from sentence_transformers import SentenceTransformer
    
    print("Loading embedding model...")
    model = SentenceTransformer(EMBED_MODEL)
    
    # Find files
    files = find_files(QUANTA_ROOT)
    print(f"Found {len(files)} files")
    
    # Init DB
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    
    # Process files
    total_chunks = 0
    processed = 0
    
    for fpath in files:
        try:
            with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except:
            continue
        
        if not content.strip():
            continue
        
        rel_path = os.path.relpath(fpath, QUANTA_ROOT)
        file_type = 'quanta' if fpath.endswith('.quanta') else 'md'
        chunks = chunk_text(content)
        
        # Prepare batch
        records = []
        for i, chunk in enumerate(chunks):
            chunk_id = hashlib.md5(f"{rel_path}_{i}_{chunk[:50]}".encode()).hexdigest()
            records.append((chunk_id, rel_path, file_type, i, chunk))
        
        # Embed in batches
        for i in range(0, len(records), BATCH_SIZE):
            batch = records[i:i+BATCH_SIZE]
            texts = [r[4] for r in batch]
            embeddings = model.encode(texts, show_progress_bar=False)
            
            for j, record in enumerate(batch):
                conn.execute(
                    "INSERT OR REPLACE INTO chunks (id, source, type, chunk_index, content, embedding) VALUES (?, ?, ?, ?, ?, ?)",
                    (record[0], record[1], record[2], record[3], record[4], embeddings[j].tobytes())
                )
                conn.execute(
                    "INSERT OR REPLACE INTO vec_chunks (id, embedding) VALUES (?, ?)",
                    (record[0], embeddings[j].tobytes())
                )
            
            conn.commit()
        
        total_chunks += len(chunks)
        processed += 1
        
        if processed % 100 == 0:
            print(f"  {processed}/{len(files)} files, {total_chunks} chunks")
    
    # Save stats
    stats = {
        'files': processed,
        'chunks': total_chunks,
        'model': EMBED_MODEL,
        'db_size_mb': os.path.getsize(DB_PATH) / 1e6
    }
    
    conn.close()
    
    with open(os.path.join(os.path.dirname(DB_PATH), 'stats.json'), 'w') as f:
        json.dump(stats, f, indent=2)
    
    print(f"\n✅ RAG DB: {DB_PATH}")
    print(f"   Files: {processed}, Chunks: {total_chunks}")
    print(f"   Size: {stats['db_size_mb']:.1f} MB")

if __name__ == "__main__":
    build()
