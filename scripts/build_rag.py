import sys
#!/usr/bin/env python3
"""
Phase 1: Build RAG Knowledge Base for Quanta
- Parse all .quanta source files
- Parse all .md documentation files
- Create embeddings and store in vector DB
"""

import os
import json
import hashlib
from pathlib import Path
from typing import List, Dict, Any
import tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rag_config as _CFG

# Configuration
QUANTA_ROOT = "/opt/tali/quanta"
VECTOR_DB_PATH = _CFG.get("rag", "db")
EMBEDDINGS_MODEL = _CFG.get("embed", "model", "all-MiniLM-L6-v2")
BATCH_SIZE = 1000
MAX_CHUNK_SIZE = 1000  # Characters per chunk
CHUNK_OVERLAP = 200

def find_source_files(root: str) -> Dict[str, List[str]]:
    """Find all relevant source and doc files"""
    quanta_files = []
    md_files = []
    
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip hidden dirs, node_modules, etc.
        dirs_to_skip = {'.git', '__pycache__', 'node_modules', '.hermes', 'temp', 'logs'}
        dirnames[:] = [d for d in dirnames if d not in dirs_to_skip and not d.startswith('.')]
        
        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            if fname.endswith('.quanta'):
                quanta_files.append(fpath)
            elif fname.endswith('.md'):
                md_files.append(fpath)
    
    return {
        'quanta': quanta_files,
        'md': md_files,
        'total': len(quanta_files) + len(md_files)
    }

def chunk_text(text: str, max_size: int = MAX_CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Split text into overlapping chunks"""
    if len(text) <= max_size:
        return [text]
    
    chunks = []
    start = 0
    while start < len(text):
        end = start + max_size
        chunks.append(text[start:end])
        start += max_size - overlap
    
    return chunks

def parse_quanta_file(fpath: str) -> List[Dict[str, Any]]:
    """Parse a .quanta file into chunks with metadata"""
    try:
        with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        return []
    
    if not content.strip():
        return []
    
    # Get relative path
    rel_path = os.path.relpath(fpath, QUANTA_ROOT)
    
    # Create chunks
    chunks = chunk_text(content)
    results = []
    
    for i, chunk in enumerate(chunks):
        results.append({
            'id': hashlib.md5(f"{rel_path}_{i}_{chunk[:50]}".encode()).hexdigest(),
            'source': rel_path,
            'type': 'quanta_source',
            'chunk_index': i,
            'total_chunks': len(chunks),
            'content': chunk,
            'metadata': {
                'file_size': len(content),
                'file_extension': '.quanta'
            }
        })
    
    return results

def parse_md_file(fpath: str) -> List[Dict[str, Any]]:
    """Parse a .md file into chunks with metadata"""
    try:
        with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        return []
    
    if not content.strip():
        return []
    
    rel_path = os.path.relpath(fpath, QUANTA_ROOT)
    
    chunks = chunk_text(content)
    results = []
    
    for i, chunk in enumerate(chunks):
        results.append({
            'id': hashlib.md5(f"{rel_path}_{i}_{chunk[:50]}".encode()).hexdigest(),
            'source': rel_path,
            'type': 'documentation',
            'chunk_index': i,
            'total_chunks': len(chunks),
            'content': chunk,
            'metadata': {
                'file_size': len(content),
                'file_extension': '.md'
            }
        })
    
    return results

def create_vector_db():
    """Create and populate the vector database"""
    try:
        import chromadb
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Install with: pip install chromadb sentence-transformers")
        return False
    
    # Initialize
    print("Loading embeddings model...")
    model = SentenceTransformer(EMBEDDINGS_MODEL)
    
    os.makedirs(VECTOR_DB_PATH, exist_ok=True)
    client = chromadb.PersistentClient(path=VECTOR_DB_PATH)
    
    # Create/get collection
    collection = client.get_or_create_collection(
        name="quanta_knowledge",
        metadata={"hnsw:space": "cosine"}
    )
    
    # Find all files
    print("Finding source files...")
    files = find_source_files(QUANTA_ROOT)
    print(f"Found: {len(files['quanta'])} .quanta, {len(files['md'])} .md files")
    
    # Process files
    all_chunks = []
    processed = 0
    
    for fpath in files['quanta']:
        chunks = parse_quanta_file(fpath)
        all_chunks.extend(chunks)
        processed += 1
        if processed % 1000 == 0:
            print(f"  Processed {processed} .quanta files ({len(all_chunks)} chunks)")
    
    for fpath in files['md']:
        chunks = parse_md_file(fpath)
        all_chunks.extend(chunks)
        processed += 1
        if processed % 1000 == 0:
            print(f"  Processed {processed} files total ({len(all_chunks)} chunks)")
    
    print(f"\nTotal chunks to embed: {len(all_chunks)}")
    
    # Embed and store in batches
    for i in range(0, len(all_chunks), BATCH_SIZE):
        batch = all_chunks[i:i+BATCH_SIZE]
        
        texts = [c['content'] for c in batch]
        ids = [c['id'] for c in batch]
        metadatas = [{
            'source': c['source'],
            'type': c['type'],
            'chunk_index': str(c['chunk_index']),
            'total_chunks': str(c['total_chunks'])
        } for c in batch]
        
        # Generate embeddings
        embeddings = model.encode(texts, show_progress_bar=False)
        
        # Store
        collection.add(
            ids=ids,
            embeddings=embeddings.tolist(),
            documents=texts,
            metadatas=metadatas
        )
        
        print(f"  Embedded batch {i//BATCH_SIZE + 1}/{(len(all_chunks)-1)//BATCH_SIZE + 1}")
    
    # Save stats
    stats = {
        'total_files': processed,
        'total_chunks': len(all_chunks),
        'quanta_files': len(files['quanta']),
        'md_files': len(files['md']),
        'embedding_model': EMBEDDINGS_MODEL,
        'vector_db_path': VECTOR_DB_PATH,
        'chunk_size': MAX_CHUNK_SIZE,
        'chunk_overlap': CHUNK_OVERLAP
    }
    
    with open(os.path.join(VECTOR_DB_PATH, "stats.json"), 'w') as f:
        json.dump(stats, f, indent=2)
    
    print(f"\n✅ Vector DB created at {VECTOR_DB_PATH}")
    print(f"   Files: {processed}, Chunks: {len(all_chunks)}")
    
    return True

if __name__ == "__main__":
    create_vector_db()
