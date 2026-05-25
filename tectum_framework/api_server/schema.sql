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
    responded_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS quorum_narratives (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES quorum_jobs(id) ON DELETE CASCADE,
    synthesis_model VARCHAR(100),
    narrative TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
