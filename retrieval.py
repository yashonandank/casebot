import sqlite3
import math
from typing import List, Dict
from collections import Counter


def simple_tokenize(text: str) -> List[str]:
    """Basic tokenization: lowercase, split on whitespace, remove short tokens."""
    tokens = text.lower().split()
    return [t for t in tokens if len(t) > 2]


def compute_tf(tokens: List[str]) -> Dict[str, float]:
    """Compute term frequency."""
    counter = Counter(tokens)
    total = len(tokens)
    return {term: count / total for term, count in counter.items()} if total > 0 else {}


def compute_idf(all_docs: List[List[str]]) -> Dict[str, float]:
    """Compute inverse document frequency across all documents."""
    num_docs = len(all_docs)
    doc_frequency = Counter()
    
    for doc in all_docs:
        unique_terms = set(doc)
        for term in unique_terms:
            doc_frequency[term] += 1
    
    idf = {}
    for term, count in doc_frequency.items():
        idf[term] = math.log(num_docs / (count + 1))  # +1 to avoid division by zero
    
    return idf


def retrieve_chunks(
    case_id: int,
    query: str,
    top_k: int = 5,
    min_score: float = 0.0
) -> List[Dict]:
    """
    Retrieve top-k case chunks most relevant to query using TF-IDF scoring.
    Returns list of chunks with scores.
    """
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get all chunks for this case
    cursor.execute("""
        SELECT id, chunk_index, location_hint, content
        FROM case_chunks
        WHERE case_id = ?
        ORDER BY chunk_index
    """, (case_id,))
    
    chunks = []
    all_docs = []
    
    for chunk_id, idx, location, content in cursor.fetchall():
        chunks.append({
            "chunk_id": chunk_id,
            "chunk_index": idx,
            "location_hint": location,
            "content": content,
            "tokens": simple_tokenize(content)
        })
        all_docs.append(chunks[-1]["tokens"])
    
    conn.close()
    
    if not chunks:
        return []
    
    # Compute IDF
    idf = compute_idf(all_docs)
    
    # Tokenize query
    query_tokens = simple_tokenize(query)
    query_tf = compute_tf(query_tokens)
    
    # Score each chunk
    scored_chunks = []
    for chunk in chunks:
        chunk_tf = compute_tf(chunk["tokens"])
        
        # TF-IDF score
        score = 0.0
        for term in query_tokens:
            tf = chunk_tf.get(term, 0)
            idf_val = idf.get(term, 0)
            score += tf * idf_val
        
        if score >= min_score:
            scored_chunks.append({
                **chunk,
                "score": score
            })
    
    # Sort by score descending
    scored_chunks.sort(key=lambda x: x["score"], reverse=True)
    
    # Return top-k, without tokens in result
    result = []
    for chunk in scored_chunks[:top_k]:
        result.append({
            "chunk_id": chunk["chunk_id"],
            "chunk_index": chunk["chunk_index"],
            "location_hint": chunk["location_hint"],
            "content": chunk["content"],
            "score": chunk["score"]
        })
    
    return result


def search_case_text(
    case_id: int,
    query: str,
    top_k: int = 5
) -> List[Dict]:
    """User-friendly search interface."""
    if not query or not query.strip():
        return []
    
    return retrieve_chunks(case_id, query, top_k=top_k, min_score=0.0)
