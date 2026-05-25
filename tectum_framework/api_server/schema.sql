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
