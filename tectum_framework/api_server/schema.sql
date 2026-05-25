CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

CREATE TABLE IF NOT EXISTS quorum_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question TEXT NOT NULL,
    models TEXT[],
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS quorum_responses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES quorum_jobs(id) ON DELETE CASCADE,
    model VARCHAR(100),
    response TEXT,
    duration_ms INTEGER,
    tokens_in INTEGER,
    tokens_out INTEGER,
    responded_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS quorum_narratives (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES quorum_jobs(id) ON DELETE CASCADE,
    synthesis_model VARCHAR(100),
    narrative TEXT,
    thinking TEXT,
    duration_ms INTEGER,
    tokens_in INTEGER,
    tokens_out INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ── Fetcher tables ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS fetch_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query TEXT NOT NULL,
    intent VARCHAR(50),
    expanded_queries TEXT[],
    depth VARCHAR(20) DEFAULT 'standard',
    time_limit_seconds INTEGER DEFAULT 120,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fetch_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES fetch_jobs(id) ON DELETE CASCADE,
    url TEXT,
    title TEXT,
    content TEXT,
    source_type VARCHAR(50),
    score FLOAT,
    political_lean VARCHAR(30),
    hop_depth INTEGER DEFAULT 0,
    fetched_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS fetch_context (
    job_id UUID PRIMARY KEY REFERENCES fetch_jobs(id) ON DELETE CASCADE,
    context_text TEXT,
    query_packet JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ── Memory layer (BorderManager-style semantic cache) ─────────────────────────
--
-- Stores synthesized knowledge as vector embeddings. Before running a full
-- quorum + fetch pipeline, the API checks here first. Cache hit = instant
-- response. Cache miss = run pipeline, then store result here.
--
-- Embedding model: nomic-embed-text (768 dimensions via Ollama)
-- Similarity metric: cosine (1 - distance)
-- TTL: enforced by application per intent (news=1d, reference=30d, direct=365d)

CREATE TABLE IF NOT EXISTS tectum_memory (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    embedding       vector(768),                       -- nomic-embed-text
    content         TEXT NOT NULL,                     -- the synthesized narrative
    query           TEXT NOT NULL,                     -- original query that produced this
    topic           TEXT,                              -- short label (filled by app)
    intent          VARCHAR(50),                       -- news|reference|direct|etc
    confidence      FLOAT DEFAULT 1.0,                 -- future: user rating 0-1
    source_job_id   UUID,                              -- quorum_jobs.id (nullable)
    source_type     VARCHAR(50) DEFAULT 'synthesis',   -- synthesis|direct|manual
    hit_count       INTEGER DEFAULT 0,                 -- times this was served from cache
    memory_ttl_days INTEGER DEFAULT 7,                 -- days until stale
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    last_used_at    TIMESTAMPTZ DEFAULT NOW()
);

-- IVFFlat index for fast approximate nearest-neighbour cosine search
-- (lists=100 is appropriate for up to ~1M rows; rebuild with lists=sqrt(n) as data grows)
CREATE INDEX IF NOT EXISTS tectum_memory_embedding_idx
    ON tectum_memory USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Quick lookup by intent + recency (used for TTL filtering)
CREATE INDEX IF NOT EXISTS tectum_memory_intent_created_idx
    ON tectum_memory (intent, created_at DESC);
