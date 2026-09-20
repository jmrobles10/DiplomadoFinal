-- =====================================================================
--  PitWall · Base de conocimiento vectorial para el RAG de F1 2026
--  Ejecutar UNA vez en Supabase: Dashboard -> SQL Editor -> New query
--  Compatible con el nodo "Supabase Vector Store" de n8n
--  Embeddings: Google Gemini (gemini-embedding-2 / gemini-embedding-001)
--  Dimensión: 3072 (el nodo de n8n no permite reducirla)
-- =====================================================================

-- 1) Extensión pgvector
create extension if not exists vector with schema extensions;

-- 2) Tabla de fragmentos (chunks) de la base de conocimiento
--    n8n inserta aquí: content (texto), metadata (jsonb), embedding (vector)
create table if not exists public.documents (
  id        bigserial primary key,
  content   text,
  metadata  jsonb,
  embedding extensions.vector(3072),
  created_at timestamptz not null default now()
);

-- Índices de apoyo sobre metadatos (filtros por tipo de fuente, sección, artículo)
create index if not exists documents_metadata_gin on public.documents using gin (metadata);
create index if not exists documents_metadata_tipo on public.documents ((metadata->>'tipo'));
-- Nota: con 3072 dimensiones pgvector no permite índice HNSW/IVFFlat sobre "vector";
-- la búsqueda exacta es instantánea para una base de pocos miles de fragmentos.

-- 3) Función de búsqueda por similitud (la llama el nodo de n8n: "Query Name" = match_documents)
create or replace function public.match_documents (
  query_embedding extensions.vector(3072),
  match_count     int  default null,
  filter          jsonb default '{}'
)
returns table (
  id         bigint,
  content    text,
  metadata   jsonb,
  similarity float
)
language plpgsql
as $$
#variable_conflict use_column
begin
  return query
  select
    id,
    content,
    metadata,
    1 - (documents.embedding <=> query_embedding) as similarity
  from public.documents
  where metadata @> filter
  order by documents.embedding <=> query_embedding
  limit match_count;
end;
$$;

-- 4) Registro de preguntas y respuestas (evidencia para la presentación)
create table if not exists public.qa_log (
  id            bigserial primary key,
  created_at    timestamptz not null default now(),
  session_id    text,
  modo          text,            -- 'rag' | 'directo'
  pregunta      text,
  respuesta     text,
  pasos         jsonb,           -- pasos intermedios del agente (herramientas usadas)
  fuentes       jsonb,           -- documentos/artículos recuperados
  evaluacion    jsonb,           -- veredicto del módulo evaluador (opcional)
  duracion_ms   integer
);

-- 5) La memoria de conversación la crea solo el nodo "Postgres Chat Memory" de n8n
--    (tabla n8n_chat_histories) la primera vez que se ejecuta. No hay que crearla aquí.

-- 6) Verificación rápida
select 'documents' as tabla, count(*) as filas from public.documents
union all
select 'qa_log', count(*) from public.qa_log;
