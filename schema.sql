-- Run this in the Supabase SQL editor once to create the tables.

create table if not exists markets (
    id          uuid primary key default gen_random_uuid(),
    market_id   text unique not null,
    question    text,
    category    text,
    probability float,
    volume_usd  float,
    expiry_date timestamptz,
    fetched_at  timestamptz default now()
);

create table if not exists signals (
    id               uuid primary key default gen_random_uuid(),
    market_id        text unique references markets(market_id),  -- one signal per market, ever
    relevance_score  int,
    sector           text,
    affected_tickers text[],
    reasoning        text,
    created_at       timestamptz default now()
);

create table if not exists reports (
    id          uuid primary key default gen_random_uuid(),
    report_date date,
    content     text,
    top_signals jsonb,
    created_at  timestamptz default now()
);

create index if not exists signals_score_idx on signals (relevance_score desc);

-- Trends: one compact row per scan snapshot (the scanner saves at most one every ~6 hours).
create table if not exists snapshots (
    id        bigint generated always as identity primary key,
    taken_at  timestamptz not null default now(),
    sectors   jsonb not null,   -- [{sector, w (raw heat), n, volume, peak}]
    markets   jsonb not null    -- {market_id: [probability, volume_usd]} for active signals
);
create index if not exists snapshots_taken_idx on snapshots (taken_at desc);
