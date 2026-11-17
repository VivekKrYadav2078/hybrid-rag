# """
# ingest.py - Document Ingestion Pipeline
# =========================================
# Handles uploading and processing documents for RAG:

# Pipeline:
#   Upload (PDF/DOCX/TXT/MD or raw text)
#     -> Parse with Docling's DocumentConverter
#     -> Chunk with HybridChunker (max 512 tokens)
#     -> Embed each chunk with BAAI/bge-small-en-v1.5 (384-dim)
#     -> Store chunks + embeddings in Supabase document_chunks table
#     -> Mark document status as 'ready'

# Why Docling?
# - Docling preserves document structure (headings, tables, lists).
# - HybridChunker creates semantically meaningful chunks that respect
#   section boundaries, unlike naive fixed-size splitting.
# - Supports PDF, DOCX, Markdown, and plain text out of the box.
# """

# import io
# from docling.document_converter import DocumentConverter, DocumentStream
# from docling.chunking import HybridChunker
# from db import supabase
# from rag import embed_texts


# # Initialize Docling's converter (loaded once, reused for all uploads)
# converter = DocumentConverter()


# def ingest_file(
#     tenant_id: str, document_id: str, filename: str, file_bytes: bytes
# ) -> None:
#     """
#     Process an uploaded file: parse -> chunk -> embed -> store.

#     Args:
#         tenant_id: The tenant this document belongs to.
#         document_id: The UUID of the document record in the documents table.
#         filename: Original filename (used to detect format).
#         file_bytes: The raw bytes of the uploaded file.
#     """
#     try:
#         # --- Step 1: Parse the document with Docling ---
#         # DocumentStream wraps in-memory bytes so Docling can process
#         # without writing to disk.
#         stream = DocumentStream(name=filename, stream=io.BytesIO(file_bytes))
#         result = converter.convert(stream)
#         doc = result.document

#         # --- Step 2: Chunk the parsed document ---
#         # HybridChunker respects document structure (headings, tables)
#         # and limits each chunk to max_tokens=512 for optimal retrieval.
#         chunker = HybridChunker(max_tokens=512)
#         chunks = list(chunker.chunk(doc))

#         if not chunks:
#             # No content could be extracted
#             supabase.table("documents").update({"status": "failed"}).eq(
#                 "id", document_id
#             ).execute()
#             return

#         # Extract text from each chunk
#         chunk_texts = [chunk.text for chunk in chunks]

#         # --- Step 3: Generate embeddings for all chunks (batched) ---
#         embeddings = embed_texts(chunk_texts)

#         # --- Step 4: Store chunks + embeddings in Supabase ---
#         rows = [
#             {
#                 "tenant_id": tenant_id,
#                 "document_id": document_id,
#                 "content": text,
#                 "embedding": embedding,
#             }
#             for text, embedding in zip(chunk_texts, embeddings)
#         ]

#         # Insert in batches of 100 to avoid payload size limits
#         batch_size = 100
#         for i in range(0, len(rows), batch_size):
#             batch = rows[i : i + batch_size]
#             supabase.table("document_chunks").insert(batch).execute()

#         # --- Step 5: Mark document as ready ---
#         supabase.table("documents").update({"status": "ready"}).eq(
#             "id", document_id
#         ).execute()

#         print(f"Ingested '{filename}': {len(chunks)} chunks stored")

#     except Exception as e:
#         # If anything fails, mark the document as failed
#         print(f"Ingestion failed for '{filename}': {e}")
#         supabase.table("documents").update({"status": "failed"}).eq(
#             "id", document_id
#         ).execute()
#         raise


# def ingest_raw_text(
#     tenant_id: str, document_id: str, title: str, raw_text: str
# ) -> None:
#     """
#     Process raw pasted text: wrap as Markdown -> parse -> chunk -> embed -> store.

#     For users who want to paste text directly instead of uploading a file.
#     We wrap the text as a .md file so Docling can process it properly.

#     Args:
#         tenant_id: The tenant this document belongs to.
#         document_id: The UUID of the document record.
#         title: A title/label for this text (used as filename).
#         raw_text: The raw text content to ingest.
#     """
#     # Wrap the raw text as a Markdown "file" for Docling
#     md_bytes = raw_text.encode("utf-8")
#     filename = f"{title}.md" if not title.endswith(".md") else title

#     # Reuse the file ingestion pipeline
#     ingest_file(tenant_id, document_id, filename, md_bytes)


"""
ingest.py - Document Ingestion Pipeline
=========================================
Parses documents using Docling, splits them via HybridChunker, 
generates BGE embeddings, and stores them in Supabase.
"""

import io
from docling.document_converter import DocumentConverter, DocumentStream
from docling.chunking import HybridChunker
from db import supabase
from rag import embed_texts

# Initialize Docling converter once
converter = DocumentConverter()


def ingest_file(
    tenant_id: str, document_id: str, filename: str, file_bytes: bytes
) -> None:
    """
    Parses a file stream (PDF, DOCX, TXT, MD), chunks it intelligently,
    vectorizes it, and saves it to Supabase.
    """
    try:
        # Step 1: Parse file using Docling
        stream = DocumentStream(name=filename, stream=io.BytesIO(file_bytes))
        result = converter.convert(stream)
        doc = result.document

        # Step 2: Chunk document while respecting structure (headings/tables)
        chunker = HybridChunker(max_tokens=512)
        chunks = list(chunker.chunk(doc))

        if not chunks:
            supabase.table("documents").update({"status": "failed"}).eq("id", document_id).execute()
            return

        chunk_texts = [chunk.text for chunk in chunks]

        # Step 3: Generate vector embeddings (384-dim)
        embeddings = embed_texts(chunk_texts)

        # Step 4: Save chunks and vectors into Supabase
        rows = [
            {
                "tenant_id": tenant_id,
                "document_id": document_id,
                "filename": filename,  # Stored so UI citations work
                "content": text,
                "embedding": embedding,
            }
            for text, embedding in zip(chunk_texts, embeddings)
        ]

        # Insert in batches of 100
        batch_size = 100
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            supabase.table("document_chunks").insert(batch).execute()

        # Step 5: Update document status to ready
        supabase.table("documents").update({"status": "ready"}).eq("id", document_id).execute()
        print(f"Successfully ingested '{filename}': {len(chunks)} chunks stored.")

    except Exception as e:
        print(f"Ingestion failed for '{filename}': {e}")
        supabase.table("documents").update({"status": "failed"}).eq("id", document_id).execute()
        raise


def ingest_raw_text(
    tenant_id: str, document_id: str, title: str, raw_text: str
) -> None:
    """Handles direct raw text pasting by wrapping it as a markdown file."""
    md_bytes = raw_text.encode("utf-8")
    filename = f"{title}.md" if not title.endswith(".md") else title
    ingest_file(tenant_id, document_id, filename, md_bytes)