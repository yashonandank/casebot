import os
import json
import sqlite3
from pathlib import Path
from typing import List, Tuple


def extract_pdf(file_path: str) -> str:
    """Extract text from PDF using pdfplumber."""
    try:
        import pdfplumber
    except ImportError:
        raise ImportError("pdfplumber required: pip install pdfplumber")
    
    text_parts = []
    with pdfplumber.open(file_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text()
            if text:
                # Add page marker for location hints
                text_parts.append(f"[PAGE {page_num}]\n{text}")
    
    return "\n\n".join(text_parts)


def extract_docx(file_path: str) -> str:
    """Extract text from DOCX using python-docx."""
    try:
        from docx import Document
    except ImportError:
        raise ImportError("python-docx required: pip install python-docx")
    
    doc = Document(file_path)
    text_parts = []
    
    for para in doc.paragraphs:
        if para.text.strip():
            text_parts.append(para.text)
    
    # Handle tables
    for table in doc.tables:
        for row in table.rows:
            row_text = " | ".join(cell.text for cell in row.cells)
            text_parts.append(row_text)
    
    return "\n".join(text_parts)


def extract_text_from_file(file_path: str) -> str:
    """Extract text from PDF or DOCX file."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    ext = Path(file_path).suffix.lower()
    
    if ext == ".pdf":
        return extract_pdf(file_path)
    elif ext in [".docx", ".doc"]:
        return extract_docx(file_path)
    else:
        raise ValueError(f"Unsupported file type: {ext}")


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[dict]:
    """Split text into overlapping chunks."""
    chunks = []
    sentences = text.split(". ")
    
    current_chunk = ""
    chunk_index = 0
    
    for sentence in sentences:
        if len(current_chunk) + len(sentence) > chunk_size:
            if current_chunk.strip():
                chunks.append({
                    "chunk_index": chunk_index,
                    "content": current_chunk.strip(),
                    "location_hint": extract_location_hint(current_chunk)
                })
                chunk_index += 1
                # Overlap: keep last part of current chunk
                current_chunk = current_chunk[-overlap:] + ". " if len(current_chunk) > overlap else ""
        
        current_chunk += sentence + ". "
    
    # Add last chunk
    if current_chunk.strip():
        chunks.append({
            "chunk_index": chunk_index,
            "content": current_chunk.strip(),
            "location_hint": extract_location_hint(current_chunk)
        })
    
    return chunks


def extract_location_hint(text: str) -> str:
    """Extract page/section information from chunk."""
    if "[PAGE" in text:
        for part in text.split("[PAGE"):
            if "]" in part:
                page_num = part.split("]")[0].strip()
                return f"Page {page_num}"
    return "Unknown"


def ingest_case_file(case_id: int, file_path: str) -> Tuple[int, List[dict]]:
    """
    Ingest a case file: extract text, chunk it, and save chunks to DB.
    Returns (num_chunks, chunk_list).
    """
    # Extract text
    try:
        text = extract_text_from_file(file_path)
    except Exception as e:
        raise ValueError(f"Failed to extract text: {str(e)}")
    
    if not text or len(text.strip()) < 100:
        raise ValueError("Extracted text is too short or empty. Check the uploaded file.")
    
    # Chunk text
    chunks = chunk_text(text, chunk_size=1000, overlap=200)
    
    # Save to DB
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    for chunk in chunks:
        cursor.execute("""
            INSERT INTO case_chunks (case_id, chunk_index, location_hint, content)
            VALUES (?, ?, ?, ?)
        """, (case_id, chunk["chunk_index"], chunk["location_hint"], chunk["content"]))
    
    conn.commit()
    conn.close()
    
    return len(chunks), chunks


def get_case_chunks(case_id: int, limit: int = 100) -> List[dict]:
    """Retrieve all chunks for a case."""
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, chunk_index, location_hint, content
        FROM case_chunks
        WHERE case_id = ?
        ORDER BY chunk_index
        LIMIT ?
    """, (case_id, limit))
    
    chunks = []
    for chunk_id, idx, location, content in cursor.fetchall():
        chunks.append({
            "chunk_id": chunk_id,
            "chunk_index": idx,
            "location_hint": location,
            "content": content
        })
    
    conn.close()
    return chunks
