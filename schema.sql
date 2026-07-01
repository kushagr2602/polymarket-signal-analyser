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
    market_id        text references markets(market_id),
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
