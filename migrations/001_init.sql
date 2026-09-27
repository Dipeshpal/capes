-- Bootstrap schema for DB-backed credentials and multi-key API auth.
-- Applied automatically by pulse/db.py; never run by hand.

create table if not exists secrets (
    name text primary key,
    ciphertext bytea not null,
    nonce bytea not null,
    updated_at timestamptz not null default now()
);

create table if not exists api_keys (
    id uuid primary key default gen_random_uuid(),
    label text,
    key_hash text not null unique,
    created_at timestamptz not null default now(),
    expires_at timestamptz,
    revoked_at timestamptz
);
