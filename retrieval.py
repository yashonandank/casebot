import sqlite3
import json
import math
from typing import List, Dict


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def retrieve_chunks(
    case_id: int,
    query: str,
    top_k: int = 5,
) -> List[Dict]:
    """
    Embed the query and return top-k chunks by cosine similarity.
    Falls back to keyword overlap if no embeddings stored.
    """
    from llm_client import get_llm_client
    llm = get_llm_client()

    # Embed query
    query_embedding = llm.embed([query])[0]

    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, chunk_index, location_hint, content, embedding_json
        FROM case_chunks WHERE case_id = ?
        ORDER BY chunk_index
    """, (case_id,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return []

    scored = []
    for chunk_id, idx, location, content, emb_json in rows:
        if emb_json:
            embedding = json.loads(emb_json)
            score = _cosine_similarity(query_embedding, embedding)
        else:
            # Keyword fallback
            q_words = set(query.lower().split())
            c_words = set(content.lower().split())
            score = len(q_words & c_words) / max(len(q_words), 1)

        scored.append({
            "chunk_id": chunk_id,
            "chunk_index": idx,
            "location_hint": location,
            "content": content,
            "score": score,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return [
        {k: v for k, v in c.items() if k != "score"}
        | {"score": c["score"]}
        for c in scored[:top_k]
    ]


def search_case_text(case_id: int, query: str, top_k: int = 5) -> List[Dict]:
    if not query or not query.strip():
        return []
    return retrieve_chunks(case_id, query, top_k=top_k)
