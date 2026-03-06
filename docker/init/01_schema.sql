CREATE TABLE IF NOT EXISTS market_price (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL,
    date DATE NOT NULL,
    open DOUBLE PRECISION NOT NULL,
    high DOUBLE PRECISION NOT NULL,
    low DOUBLE PRECISION NOT NULL,
    close DOUBLE PRECISION NOT NULL,
    volume DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_market_price_symbol_date UNIQUE (symbol, date)
);

CREATE INDEX IF NOT EXISTS ix_market_price_symbol_date
    ON market_price (symbol, date);

CREATE TABLE IF NOT EXISTS technical_indicator (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL,
    date DATE NOT NULL,
    ma20 DOUBLE PRECISION,
    ma60 DOUBLE PRECISION,
    macd DOUBLE PRECISION,
    macd_signal DOUBLE PRECISION,
    macd_hist DOUBLE PRECISION,
    rsi DOUBLE PRECISION,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_technical_indicator_symbol_date UNIQUE (symbol, date)
);

CREATE INDEX IF NOT EXISTS ix_technical_indicator_symbol_date
    ON technical_indicator (symbol, date);

CREATE TABLE IF NOT EXISTS signal_record (
    id BIGSERIAL PRIMARY KEY,
    date DATE NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    strategy VARCHAR(64) NOT NULL,
    signal VARCHAR(8) NOT NULL,
    score DOUBLE PRECISION,
    meta JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_signal_record_date_symbol_strategy UNIQUE (date, symbol, strategy)
);

CREATE INDEX IF NOT EXISTS ix_signal_record_date_symbol
    ON signal_record (date, symbol);
