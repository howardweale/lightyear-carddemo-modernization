CREATE TABLE IF NOT EXISTS check_messages (
    message_id VARCHAR(80) PRIMARY KEY,
    message_type VARCHAR(16) NOT NULL CHECK (message_type IN ('DEPOSIT', 'CLEARANCE')),
    aggregate_id BIGINT NOT NULL,
    account_id BIGINT,
    journal_id BIGINT,
    amount BIGINT,
    state VARCHAR(16) NOT NULL DEFAULT 'READY'
        CHECK (state IN ('READY', 'PROCESSING', 'PROCESSED', 'DEAD')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    lease_until TIMESTAMPTZ,
    last_error_code VARCHAR(80),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMPTZ,
    CHECK ((message_type = 'DEPOSIT' AND account_id IS NOT NULL AND amount > 0)
        OR (message_type = 'CLEARANCE' AND journal_id IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS check_messages_claim_idx
    ON check_messages (state, available_at, aggregate_id, created_at, message_id);
