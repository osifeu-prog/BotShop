CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    phone TEXT,
    email TEXT,
    tier TEXT DEFAULT 'basic',
    status TEXT DEFAULT 'active',
    registration_date TIMESTAMP DEFAULT NOW(),
    last_active TIMESTAMP DEFAULT NOW(),
    total_earnings NUMERIC DEFAULT 0
);

CREATE TABLE IF NOT EXISTS digital_assets (
    asset_id TEXT PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id),
    name TEXT,
    tier TEXT,
    value NUMERIC,
    personal_link TEXT,
    qr_code_url TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    status TEXT DEFAULT 'active',
    analytics JSONB DEFAULT '{}'::jsonb,
    features JSONB DEFAULT '[]'::jsonb,
    limits JSONB DEFAULT '{}'::jsonb,
    integrations JSONB DEFAULT '{}'::jsonb
);
