# """
# main.py - FastAPI Application Entry Point
# ===========================================
# This is the main server file that defines all API endpoints:

# Endpoints:
#   POST /ingest       - Upload a document or paste raw text (auth required)
#   GET  /documents    - List all documents for the tenant (auth required)
#   POST /chat         - Send a message and get streamed AI response (public via widget_key)
#   GET  /chat/history - Retrieve chat history for a session (public via widget_key)

# Authentication:
#   - /ingest and /documents use JWT auth (dashboard users)
#   - /chat and /chat/history use X-Widget-Key header (embed widget)

# Run with: uvicorn main:app --reload --port 8000
# """

# import asyncio
# from contextlib import asynccontextmanager
# from fastapi import FastAPI, UploadFile, File, Form, Header, Depends, HTTPException
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.responses import StreamingResponse
# from pydantic import BaseModel
# from typing import Optional

# from config import FRONTEND_URL
# from db import supabase
# from auth import get_current_tenant
# from ingest import ingest_file, ingest_raw_text
# from rag import hybrid_search, rerank_chunks, build_rag_prompt, stream_groq_response


# # ============================================================
# # APP LIFESPAN (startup/shutdown events)
# # ============================================================
# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     """Runs on startup and shutdown. Models are loaded when rag.py is imported."""
#     print("Multi-Tenant RAG Backend is starting...")
#     yield
#     print("Shutting down...")


# # ============================================================
# # CREATE THE FASTAPI APP
# # ============================================================
# app = FastAPI(
#     title="Multi-Tenant RAG API",
#     description="AI-powered document Q&A with tenant isolation",
#     version="1.0.0",
#     lifespan=lifespan,
# )

# # ============================================================
# # CORS MIDDLEWARE
# # Allow the Next.js frontend AND any website embedding the widget
# # to call /chat and /chat/history endpoints.
# # ============================================================
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],       # Allow all origins (widget can be on any domain)
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],       # Allow X-Widget-Key and Authorization headers
# )


# # ============================================================
# # HELPER: Resolve tenant from X-Widget-Key header
# # ============================================================
# def resolve_tenant_by_widget_key(widget_key: str) -> str:
#     """
#     Look up a tenant by their widget_key.
#     Used by /chat and /chat/history (public endpoints).

#     Args:
#         widget_key: The public key from data-widget-key attribute.

#     Returns:
#         tenant_id (str): The UUID of the tenant.

#     Raises:
#         HTTPException 401: If the widget_key is invalid.
#     """
#     result = (
#         supabase.table("tenants")
#         .select("id")
#         .eq("widget_key", widget_key)
#         .single()
#         .execute()
#     )

#     if not result.data:
#         raise HTTPException(status_code=401, detail="Invalid widget key")

#     return result.data["id"]


# # ============================================================
# # PYDANTIC MODELS (request/response schemas)
# # ============================================================
# class ChatRequest(BaseModel):
#     """Request body for POST /chat"""
#     message: str          # The user's question
#     session_id: str       # Unique session identifier (from widget localStorage)


# # ============================================================
# # ENDPOINT: POST /ingest
# # Upload a file OR paste raw text for RAG processing.
# # Protected by JWT auth - only dashboard users can upload.
# # ============================================================
# @app.post("/ingest")
# async def ingest_document(
#     tenant_id: str = Depends(get_current_tenant),
#     file: Optional[UploadFile] = File(None),
#     raw_text: Optional[str] = Form(None),
#     title: Optional[str] = Form("Untitled"),
# ):
#     """
#     Ingest a document into the knowledge base.

#     Accepts either:
#     - A file upload (PDF, DOCX, TXT, MD)
#     - Raw text pasted directly

#     The document goes through: Parse -> Chunk -> Embed -> Store
#     """
#     # Validate: must provide either a file or raw text
#     if not file and not raw_text:
#         raise HTTPException(
#             status_code=400,
#             detail="Please provide either a file or raw_text",
#         )

#     if file:
#         # --- File Upload Path ---
#         # Validate file extension
#         allowed_extensions = {".pdf", ".docx", ".txt", ".md"}
#         ext = ""
#         if "." in file.filename:
#             ext = "." + file.filename.rsplit(".", 1)[-1].lower()
#         if ext not in allowed_extensions:
#             raise HTTPException(
#                 status_code=400,
#                 detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(allowed_extensions)}",
#             )

#         filename = file.filename
#         file_bytes = await file.read()
#     else:
#         # --- Raw Text Path ---
#         filename = f"{title}.md"
#         file_bytes = None  # Will use ingest_raw_text instead

#     # Create a document record in the database (status: 'processing')
#     doc_result = (
#         supabase.table("documents")
#         .insert(
#             {
#                 "tenant_id": tenant_id,
#                 "filename": filename,
#                 "status": "processing",
#             }
#         )
#         .execute()
#     )
#     document_id = doc_result.data[0]["id"]

#     # Process the document in a background thread (so the API responds immediately)
#     loop = asyncio.get_event_loop()

#     if file_bytes:
#         loop.run_in_executor(
#             None, ingest_file, tenant_id, document_id, filename, file_bytes
#         )
#     else:
#         loop.run_in_executor(
#             None, ingest_raw_text, tenant_id, document_id, title, raw_text
#         )

#     return {
#         "document_id": document_id,
#         "filename": filename,
#         "status": "processing",
#         "message": "Document is being processed. Check status via GET /documents.",
#     }


# # ============================================================
# # ENDPOINT: GET /documents
# # List all documents for the authenticated tenant.
# # ============================================================
# @app.get("/documents")
# async def list_documents(tenant_id: str = Depends(get_current_tenant)):
#     """
#     Returns all documents uploaded by the authenticated tenant,
#     ordered by most recent first.
#     """
#     result = (
#         supabase.table("documents")
#         .select("*")
#         .eq("tenant_id", tenant_id)
#         .order("created_at", desc=True)
#         .execute()
#     )

#     return {"documents": result.data}


# # ============================================================
# # ENDPOINT: POST /chat
# # Send a message and receive a streamed AI response.
# # Uses X-Widget-Key header for tenant resolution (public endpoint).
# # ============================================================
# @app.post("/chat")
# async def chat(
#     body: ChatRequest,
#     x_widget_key: str = Header(..., alias="X-Widget-Key"),
# ):
#     """
#     Main chat endpoint - the heart of the RAG pipeline.

#     Flow:
#     1. Resolve tenant from widget_key
#     2. Save user message to messages table
#     3. Fetch recent conversation history (last 10 messages)
#     4. Hybrid search: find top 15 relevant chunks
#     5. Cross-encoder rerank: pick top 4 most relevant
#     6. Build prompt with context + history
#     7. Stream response from Groq LLM
#     8. Save assistant response to messages table
#     """
#     # Step 1: Resolve tenant from widget key
#     tenant_id = resolve_tenant_by_widget_key(x_widget_key)

#     # Step 2: Save the incoming user message
#     supabase.table("messages").insert(
#         {
#             "tenant_id": tenant_id,
#             "session_id": body.session_id,
#             "role": "user",
#             "content": body.message,
#         }
#     ).execute()

#     # Step 3: Fetch recent conversation history (last 10 messages)
#     history_result = (
#         supabase.table("messages")
#         .select("role, content")
#         .eq("tenant_id", tenant_id)
#         .eq("session_id", body.session_id)
#         .order("created_at", desc=False)
#         .limit(10)
#         .execute()
#     )
#     chat_history = history_result.data or []
#     # Remove the message we just inserted (it's the current question)
#     if chat_history and chat_history[-1]["role"] == "user":
#         chat_history = chat_history[:-1]

#     # Step 4: Hybrid Search - find top 15 candidate chunks
#     candidates = hybrid_search(tenant_id, body.message, top_k=15)

#     # Step 5: Cross-Encoder Rerank - pick top 4 most relevant chunks
#     top_chunks = rerank_chunks(body.message, candidates, top_k=4)

#     # Step 6: Build the LLM prompt
#     messages = build_rag_prompt(top_chunks, chat_history, body.message)

#     # Steps 7 & 8: Stream response and save it
#     async def generate():
#         """
#         Async generator that streams tokens from Groq and
#         saves the complete response to the database afterward.
#         """
#         full_response = []

#         for token in stream_groq_response(messages):
#             full_response.append(token)
#             yield token

#         # After streaming is complete, save the full assistant response
#         assistant_message = "".join(full_response)
#         if assistant_message.strip():
#             supabase.table("messages").insert(
#                 {
#                     "tenant_id": tenant_id,
#                     "session_id": body.session_id,
#                     "role": "assistant",
#                     "content": assistant_message,
#                 }
#             ).execute()

#     return StreamingResponse(generate(), media_type="text/plain")


# # ============================================================
# # ENDPOINT: GET /chat/history
# # Retrieve past messages for a session (for widget reload).
# # ============================================================
# @app.get("/chat/history")
# async def chat_history(
#     session_id: str,
#     x_widget_key: str = Header(..., alias="X-Widget-Key"),
# ):
#     """
#     Returns all messages for a given session, ordered by time.
#     Used by the embed widget to restore chat bubbles on page reload.
#     """
#     # Resolve tenant from widget key
#     tenant_id = resolve_tenant_by_widget_key(x_widget_key)

#     # Fetch all messages for this session
#     result = (
#         supabase.table("messages")
#         .select("role, content, created_at")
#         .eq("tenant_id", tenant_id)
#         .eq("session_id", session_id)
#         .order("created_at", desc=False)
#         .execute()
#     )

#     return {"messages": result.data or []}


# # ============================================================
# # HEALTH CHECK
# # ============================================================
# @app.get("/health")
# async def health():
#     """Simple health check endpoint."""
#     return {"status": "ok", "service": "multi-tenant-rag-backend"}





"""
main.py - Plug-and-Play Single-Company RAG Backend Entry Point
==============================================================
Defines API endpoints for document ingestion and stateless RAG chat:

Endpoints:
  POST /ingest      - Upload a document or paste raw text
  GET  /documents   - List all uploaded documents in the default workspace
  POST /chat        - Send a message, run hybrid search + reranking, and stream Groq AI response
  GET  /health      - Simple server health check
"""

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from db import supabase
from ingest import ingest_file, ingest_raw_text
from rag import hybrid_search, rerank_chunks, build_rag_prompt, stream_groq_response

# Fixed default workspace ID for plug-and-play demo mode
DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs on startup and shutdown. Loads embedding and reranking models."""
    print("Plug-and-Play RAG Backend is starting...")
    yield
    print("Shutting down...")


app = FastAPI(
    title="Plug-and-Play RAG API",
    description="Streamlined single-company document Q&A for academic presentation",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for Next.js frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    """Request body for POST /chat"""
    message: str
    session_id: Optional[str] = "default-session"
    chat_history: Optional[list[dict]] = []  # Received directly from frontend state


@app.post("/ingest")
async def ingest_document(
    file: Optional[UploadFile] = File(None),
    raw_text: Optional[str] = Form(None),
    title: Optional[str] = Form("Untitled"),
):
    """
    Ingest a document into the knowledge base (PDF, DOCX, TXT, MD).
    Parses with Docling, chunks via HybridChunker, embeds, and saves to Supabase.
    """
    if not file and not raw_text:
        raise HTTPException(
            status_code=400,
            detail="Please provide either a file or raw_text",
        )

    if file:
        allowed_extensions = {".pdf", ".docx", ".txt", ".md"}
        ext = ""
        if "." in file.filename:
            ext = "." + file.filename.rsplit(".", 1)[-1].lower()
        if ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(allowed_extensions)}",
            )

        filename = file.filename
        file_bytes = await file.read()
    else:
        filename = f"{title}.md"
        file_bytes = None

    # Create initial document record with 'processing' status
    doc_result = (
        supabase.table("documents")
        .insert(
            {
                "tenant_id": DEFAULT_TENANT_ID,
                "filename": filename,
                "status": "processing",
            }
        )
        .execute()
    )
    document_id = doc_result.data[0]["id"]

    # Run heavy processing asynchronously in background thread
    loop = asyncio.get_event_loop()
    if file_bytes:
        loop.run_in_executor(
            None, ingest_file, DEFAULT_TENANT_ID, document_id, filename, file_bytes
        )
    else:
        loop.run_in_executor(
            None, ingest_raw_text, DEFAULT_TENANT_ID, document_id, title, raw_text
        )

    return {
        "document_id": document_id,
        "filename": filename,
        "status": "processing",
        "message": "Document is being parsed and vectorized successfully.",
    }


@app.get("/documents")
async def list_documents():
    """Returns all documents uploaded to the default workspace, sorted by newest first."""
    result = (
        supabase.table("documents")
        .select("*")
        .eq("tenant_id", DEFAULT_TENANT_ID)
        .order("created_at", desc=True)
        .execute()
    )
    return {"documents": result.data or []}


@app.post("/chat")
async def chat(body: ChatRequest):
    """
    Main RAG chat endpoint:
    1. Runs hybrid search (vector similarity + keyword matching)
    2. Reranks top 15 candidates down to 4 using the Cross-Encoder
    3. Streams the response token-by-token from Groq
    """
    # Step 1: Hybrid Search to find top 15 candidate chunks
    candidates = hybrid_search(DEFAULT_TENANT_ID, body.message, top_k=15)

    # Step 2: Cross-Encoder Rerank to pick the 4 most precise chunks
    top_chunks = rerank_chunks(body.message, candidates, top_k=4)

    # Step 3: Build prompt with retrieved context and frontend chat history
    messages = build_rag_prompt(top_chunks, body.chat_history or [], body.message)

    # Step 4: Stream response from Groq LLM
    async def generate():
        for token in stream_groq_response(messages):
            yield token

    return StreamingResponse(generate(), media_type="text/plain")


@app.get("/health")
async def health():
    """Health check endpoint to verify server status."""
    return {"status": "ok", "service": "plug-and-play-rag-backend"}