-- ============================================================
-- Multi-Tenant RAG SaaS - Supabase Schema
-- Run this in the Supabase SQL Editor to set up all tables,
-- indexes, and functions needed by the application.
-- ============================================================

-- Enable required extensions
create extension if not exists vector;       -- pgvector for embeddings
create extension if not exists pgcrypto;     -- gen_random_bytes for widget keys

-- ============================================================
-- 1. TENANTS TABLE
-- Each tenant maps 1:1 to a Supabase auth user (the owner).
-- widget_key is the public key embedded in <script> tags.
-- ============================================================
create table if not exists public.tenants (
  id         uuid primary key default gen_random_uuid(),
  owner_id   uuid unique not null references auth.users(id) on delete cascade,
  name       text not null default 'My Workspace',
  widget_key text unique not null default ('pk_live_' || encode(gen_random_bytes(16), 'hex')),
  created_at timestamptz not null default now()
);

-- ============================================================
-- 2. DOCUMENTS TABLE
-- Tracks every file/text uploaded by a tenant.
-- status: 'processing' -> 'ready' | 'failed'
-- ============================================================
create table if not exists public.documents (
  id         uuid primary key default gen_random_uuid(),
  tenant_id  uuid not null references public.tenants(id) on delete cascade,
  filename   text not null,
  status     text not null default 'processing'
               check (status in ('processing', 'ready', 'failed')),
  created_at timestamptz not null default now()
);

-- ============================================================
-- 3. DOCUMENT_CHUNKS TABLE
-- Stores chunked text + 384-dim embedding + tsvector for
-- hybrid (dense + keyword) search.
-- ============================================================
create table if not exists public.document_chunks (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references public.tenants(id) on delete cascade,
  document_id   uuid not null references public.documents(id) on delete cascade,
  content       text not null,
  embedding     vector(384),
  search_vector tsvector generated always as (to_tsvector('english', content)) stored
);

-- ============================================================
-- 4. MESSAGES TABLE
-- Chat history keyed by (tenant_id, session_id) so the
-- embed widget can restore past conversations.
-- ============================================================
create table if not exists public.messages (
  id         uuid primary key default gen_random_uuid(),
  tenant_id  uuid not null references public.tenants(id) on delete cascade,
  session_id text not null,
  role       text not null check (role in ('user', 'assistant')),
  content    text not null,
  created_at timestamptz not null default now()
);

-- ============================================================
-- 5. INDEXES
-- ============================================================

-- HNSW index for fast approximate nearest-neighbor search
create index if not exists idx_chunks_embedding
  on public.document_chunks
  using hnsw (embedding vector_cosine_ops);

-- GIN index for full-text keyword search
create index if not exists idx_chunks_search_vector
  on public.document_chunks
  using gin (search_vector);

-- B-tree indexes for tenant-scoped queries
create index if not exists idx_chunks_tenant
  on public.document_chunks (tenant_id);

create index if not exists idx_documents_tenant
  on public.documents (tenant_id);

create index if not exists idx_messages_tenant
  on public.messages (tenant_id);

create index if not exists idx_messages_session
  on public.messages (session_id);

-- ============================================================
-- 6. HYBRID SEARCH FUNCTION
-- Combines cosine similarity (dense vector) with BM25-style
-- full-text ranking (ts_rank_cd), strictly filtered by tenant.
-- Returns top `match_count` results ordered by combined score.
-- ============================================================
create or replace function public.hybrid_search(
  p_tenant_id  uuid,
  p_embedding  vector(384),
  p_query_text text,
  match_count  int default 15
)
returns table (
  id         uuid,
  content    text,
  similarity float
)
language sql stable
as $$
  select
    dc.id,
    dc.content,
    -- Combined score: 70% vector similarity + 30% keyword relevance
    (
      0.7 * (1 - (dc.embedding <=> p_embedding)) +
      0.3 * ts_rank_cd(dc.search_vector, websearch_to_tsquery('english', p_query_text))
    ) as similarity
  from public.document_chunks dc
  where dc.tenant_id = p_tenant_id
  order by similarity desc
  limit match_count;
$$;

-- ============================================================
-- 7. ROW-LEVEL SECURITY (optional but recommended)
-- ============================================================
alter table public.tenants enable row level security;
alter table public.documents enable row level security;
alter table public.document_chunks enable row level security;
alter table public.messages enable row level security;

-- Tenants: owners can read/update their own tenant row
create policy "Owners can manage their tenant"
  on public.tenants for all
  using (auth.uid() = owner_id);

-- Documents: tenant owners can manage their documents
create policy "Tenant owners manage documents"
  on public.documents for all
  using (
    tenant_id in (
      select id from public.tenants where owner_id = auth.uid()
    )
  );

-- Chunks: tenant owners can manage their chunks
create policy "Tenant owners manage chunks"
  on public.document_chunks for all
  using (
    tenant_id in (
      select id from public.tenants where owner_id = auth.uid()
    )
  );

-- Messages: allow insert/select for everyone (widget uses service role anyway)
create policy "Anyone can insert messages"
  on public.messages for insert
  with check (true);

create policy "Anyone can read messages"
  on public.messages for select
  using (true);
