# """
# rag.py - RAG Pipeline (Retrieval-Augmented Generation)
# =======================================================
# This module contains the core RAG logic:

# 1. EMBEDDING:      Convert text -> 384-dim vector using BAAI/bge-small-en-v1.5
# 2. HYBRID SEARCH:  Combine vector similarity + keyword search in Supabase
# 3. RERANKING:      Use a Cross-Encoder to pick the most relevant chunks
# 4. LLM STREAMING:  Stream the answer from Groq with context + chat history

# Pipeline flow:
#   User Question
#     -> Embed question (384-dim vector)
#     -> Hybrid Search in Supabase (top 15 candidates)
#     -> Cross-Encoder Rerank (pick top 4)
#     -> Build prompt with context + conversation history
#     -> Stream response from Groq LLM
# """

# from sentence_transformers import SentenceTransformer, CrossEncoder
# from groq import Groq
# from db import supabase
# from config import GROQ_API_KEY

# # ============================================================
# # MODEL LOADING (loaded once at startup, reused for all requests)
# # ============================================================

# # Bi-encoder: converts text into 384-dimensional dense vectors.
# # BAAI/bge-small-en-v1.5 is a compact, high-quality embedding model.
# print("Loading embedding model (BAAI/bge-small-en-v1.5)...")
# embedder = SentenceTransformer("BAAI/bge-small-en-v1.5")

# # Cross-encoder: takes (query, passage) pairs and scores relevance.
# # Unlike the bi-encoder, it sees both texts together -> more accurate.
# # Used to rerank the top candidates from hybrid search.
# print("Loading reranker model (BAAI/bge-reranker-base)...")
# reranker = CrossEncoder("BAAI/bge-reranker-base")

# # Groq client for ultra-fast LLM inference
# groq_client = Groq(api_key=GROQ_API_KEY)


# def embed_text(text: str) -> list[float]:
#     """
#     Convert a text string into a 384-dimensional embedding vector.

#     Args:
#         text: The input text to embed.

#     Returns:
#         A list of 384 floats representing the text's semantic meaning.
#     """
#     # SentenceTransformer.encode returns a numpy array; convert to list
#     # for JSON serialization when storing in Supabase.
#     vector = embedder.encode(text, normalize_embeddings=True)
#     return vector.tolist()


# def embed_texts(texts: list[str]) -> list[list[float]]:
#     """
#     Batch-embed multiple texts at once (more efficient than one-by-one).

#     Args:
#         texts: List of text strings to embed.

#     Returns:
#         List of 384-dim embedding vectors, one per input text.
#     """
#     vectors = embedder.encode(texts, normalize_embeddings=True, show_progress_bar=True)
#     return vectors.tolist()


# def hybrid_search(tenant_id: str, query: str, top_k: int = 15) -> list[dict]:
#     """
#     Perform hybrid search: dense vector similarity + keyword matching.

#     This calls the `hybrid_search` Postgres function defined in our schema,
#     which combines:
#       - 70% cosine similarity (semantic meaning)
#       - 30% ts_rank_cd (keyword/BM25-style relevance)

#     Args:
#         tenant_id: Only search chunks belonging to this tenant.
#         query: The user's question.
#         top_k: Number of candidate chunks to retrieve (default 15).

#     Returns:
#         List of dicts with 'id', 'content', and 'similarity' score.
#     """
#     # Step 1: Embed the query into a 384-dim vector
#     query_embedding = embed_text(query)

#     # Step 2: Call the Supabase RPC function for hybrid search
#     result = supabase.rpc(
#         "hybrid_search",
#         {
#             "p_tenant_id": tenant_id,
#             "p_embedding": query_embedding,
#             "p_query_text": query,
#             "match_count": top_k,
#         },
#     ).execute()

#     return result.data or []


# def rerank_chunks(query: str, chunks: list[dict], top_k: int = 4) -> list[dict]:
#     """
#     Rerank candidate chunks using a Cross-Encoder for higher accuracy.

#     Why rerank?
#     - The bi-encoder (used in hybrid_search) is fast but approximate.
#     - The Cross-Encoder sees (query, passage) together and is more accurate.
#     - We retrieve 15 candidates quickly, then pick the best 4 with reranking.

#     Args:
#         query: The user's question.
#         chunks: Candidate chunks from hybrid_search.
#         top_k: Number of top chunks to keep after reranking.

#     Returns:
#         The top_k most relevant chunks, sorted by relevance.
#     """
#     if not chunks:
#         return []

#     # Create (query, passage) pairs for the Cross-Encoder
#     pairs = [(query, chunk["content"]) for chunk in chunks]

#     # Score each pair - higher score = more relevant
#     scores = reranker.predict(pairs)

#     # Attach scores to chunks and sort by score descending
#     for i, chunk in enumerate(chunks):
#         chunk["rerank_score"] = float(scores[i])

#     chunks.sort(key=lambda c: c["rerank_score"], reverse=True)

#     return chunks[:top_k]


# def build_rag_prompt(
#     context_chunks: list[dict],
#     chat_history: list[dict],
#     question: str,
# ) -> list[dict]:
#     """
#     Build the prompt messages array for the Groq LLM.

#     The prompt instructs the model to:
#     - Answer ONLY from the provided context
#     - Say "I don't have enough information" if the context doesn't help
#     - Use the conversation history for follow-up questions

#     Args:
#         context_chunks: The top reranked chunks (the "knowledge").
#         chat_history: Recent messages in this conversation.
#         question: The current user question.

#     Returns:
#         List of message dicts (system + history + user) for the LLM.
#     """
#     # Format the retrieved context as numbered passages
#     context_text = "\n\n".join(
#         f"[Passage {i+1}]:\n{chunk['content']}"
#         for i, chunk in enumerate(context_chunks)
#     )

#     # System prompt with strict instructions
#     system_message = {
#         "role": "system",
#         "content": (
#             "You are a helpful AI assistant. Answer the user's question using "
#             "ONLY the context passages provided below. If the context does not "
#             "contain enough information to answer, say: \"I don't have enough "
#             "information in my knowledge base to answer that question.\"\n\n"
#             "Do NOT make up information. Do NOT use external knowledge.\n"
#             "Be concise, accurate, and cite passage numbers when relevant.\n\n"
#             f"--- CONTEXT ---\n{context_text}\n--- END CONTEXT ---"
#         ),
#     }

#     # Build the messages array: system -> chat history -> current question
#     messages = [system_message]

#     # Add recent conversation history (for follow-up context)
#     for msg in chat_history:
#         messages.append({"role": msg["role"], "content": msg["content"]})

#     # Add the current user question
#     messages.append({"role": "user", "content": question})

#     return messages


# def stream_groq_response(messages: list[dict]):
#     """
#     Stream the LLM response from Groq token-by-token.

#     Uses the Groq SDK with stream=True to get Server-Sent Events.
#     This allows the frontend to display tokens as they arrive,
#     giving a much better user experience than waiting for the full response.

#     Args:
#         messages: The prompt messages array (from build_rag_prompt).

#     Yields:
#         Individual text tokens as they are generated.
#     """
#     stream = groq_client.chat.completions.create(
#         model="openai/gpt-oss-120b",
#         messages=messages,
#         stream=True,
#         temperature=0.3,      # Low temperature for factual answers
#         max_tokens=2048,
#     )

#     for chunk in stream:
#         # Each chunk may or may not contain a text delta
#         delta = chunk.choices[0].delta
#         if delta.content:
#             yield delta.content


"""
rag.py - RAG Pipeline (Retrieval-Augmented Generation)
=======================================================
Handles embedding generation, hybrid search, cross-encoder reranking, 
prompt construction, and streaming responses from Groq.
"""

from sentence_transformers import SentenceTransformer, CrossEncoder
from groq import Groq
from db import supabase
from config import GROQ_API_KEY

# ============================================================
# 1. LOAD MODELS ON STARTUP
# ============================================================
print("Loading embedding model (BAAI/bge-small-en-v1.5)...")
embedder = SentenceTransformer("BAAI/bge-small-en-v1.5")

print("Loading reranker model (BAAI/bge-reranker-base)...")
reranker = CrossEncoder("BAAI/bge-reranker-base")

# Initialize Groq client
groq_client = Groq(api_key=GROQ_API_KEY)


# ============================================================
# 2. EMBEDDING FUNCTIONS
# ============================================================
def embed_text(text: str) -> list[float]:
    """Convert a single text string into a 384-dimensional vector."""
    vector = embedder.encode(text, normalize_embeddings=True)
    return vector.tolist()


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch-convert multiple text strings into embedding vectors."""
    vectors = embedder.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return vectors.tolist()


# ============================================================
# 3. HYBRID SEARCH (Vector Similarity + Keywords)
# ============================================================
def hybrid_search(tenant_id: str, query: str, top_k: int = 15) -> list[dict]:
    """
    Combines 70% semantic vector search with 30% keyword search 
    using Supabase's custom RPC function.
    """
    query_embedding = embed_text(query)

    result = supabase.rpc(
        "hybrid_search",
        {
            "p_tenant_id": tenant_id,
            "p_embedding": query_embedding,
            "p_query_text": query,
            "match_count": top_k,
        },
    ).execute()

    return result.data or []


# ============================================================
# 4. CROSS-ENCODER RERANKING (Precision Noise Filter)
# ============================================================
def rerank_chunks(query: str, chunks: list[dict], top_k: int = 4) -> list[dict]:
    """
    Takes candidate chunks from hybrid search and scores them deeply 
    against the query using a Cross-Encoder to remove irrelevant noise.
    """
    if not chunks:
        return []

    # Create (query, text passage) pairs
    pairs = [(query, chunk["content"]) for chunk in chunks]

    # Predict relevance scores
    scores = reranker.predict(pairs)

    # Attach score and sort descending
    for i, chunk in enumerate(chunks):
        chunk["rerank_score"] = float(scores[i])

    chunks.sort(key=lambda c: c["rerank_score"], reverse=True)

    return chunks[:top_k]


# ============================================================
# 5. PROMPT BUILDER & GROQ STREAMING
# ============================================================
def build_rag_prompt(
    context_chunks: list[dict],
    chat_history: list[dict],
    question: str,
) -> list[dict]:
    """Builds the final prompt array containing system instructions, context, and history."""
    
    context_text = "\n\n".join(
        f"[Passage {i+1}]:\n{chunk['content']}"
        for i, chunk in enumerate(context_chunks)
    )

    system_message = {
        "role": "system",
        "content": (
            "You are a helpful AI assistant. Answer the user's question using "
            "ONLY the context passages provided below. If the context does not "
            "contain enough information, say: \"I don't have enough "
            "information in my knowledge base to answer that question.\"\n\n"
            "Do NOT make up information. Be concise and accurate.\n\n"
            f"--- CONTEXT ---\n{context_text}\n--- END CONTEXT ---"
        ),
    }

    messages = [system_message]

    # Append chat history for conversational memory
    for msg in chat_history:
        messages.append({"role": msg["role"], "content": msg["content"]})

    # Append current question
    messages.append({"role": "user", "content": question})

    return messages


def stream_groq_response(messages: list[dict]):
    """Streams responses token-by-token from Groq's LLM."""
    stream = groq_client.chat.completions.create(
        model="openai/gpt-oss-20b",  # Or your preferred Groq model
        messages=messages,
        stream=True,
        temperature=0.3,
        max_tokens=2048,
    )

    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content