-- Early-AML-Warning-System database schema
-- Works on both SQLite (default local dev) and PostgreSQL (preferred
-- for deployment) — see backend/database/session.py for engine setup.
-- SQLAlchemy models (backend/database/models.py) are the source of
-- truth this file mirrors for documentation/manual setup purposes.

CREATE TABLE IF NOT EXISTS accounts (
    account_id          VARCHAR(64) PRIMARY KEY,
    is_ring_member       BOOLEAN DEFAULT FALSE,
    dataset_source       VARCHAR(32)
);

CREATE TABLE IF NOT EXISTS transactions (
    transaction_id       VARCHAR(64) PRIMARY KEY,
    sender                VARCHAR(64) NOT NULL,
    receiver              VARCHAR(64) NOT NULL,
    amount                 FLOAT NOT NULL,
    timestamp              TIMESTAMP NOT NULL,
    label                  SMALLINT NOT NULL DEFAULT -1,
    scenario_id            VARCHAR(64),
    ring_id                VARCHAR(64),
    dataset_source         VARCHAR(32)
);

CREATE TABLE IF NOT EXISTS graph_windows (
    window_id               INTEGER PRIMARY KEY,
    window_start             TIMESTAMP NOT NULL,
    window_end               TIMESTAMP NOT NULL,
    n_nodes                  INTEGER,
    n_transactions            INTEGER,
    total_amount              FLOAT,
    cumulative_n_nodes        INTEGER,
    cumulative_n_transactions INTEGER,
    cumulative_density        FLOAT
);

CREATE TABLE IF NOT EXISTS features (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    window_id                 INTEGER NOT NULL,
    account_id                 VARCHAR(64) NOT NULL,
    feature_json                TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pattern_events (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_type        VARCHAR(32) NOT NULL,
    window_id            INTEGER NOT NULL,
    timestamp             VARCHAR(64),
    central_account        VARCHAR(64),
    accounts_json           TEXT,
    transaction_ids_json    TEXT,
    pattern_strength        FLOAT,
    evidence_json            TEXT
);

CREATE TABLE IF NOT EXISTS ring_candidates (
    candidate_ring_id            VARCHAR(32) PRIMARY KEY,
    accounts_json                  TEXT,
    transaction_ids_json           TEXT,
    time_span_start                 VARCHAR(64),
    time_span_end                    VARCHAR(64),
    patterns_json                     TEXT,
    trajectory_json                    TEXT,
    network_statistics_json             TEXT,
    formation_stage                       VARCHAR(32),
    formation_stage_is_provisional         BOOLEAN,
    risk_score                              FLOAT,
    evidence_event_count                     INTEGER,
    source_trajectory_id                      VARCHAR(32)
);

CREATE TABLE IF NOT EXISTS risk_scores (
    candidate_ring_id   VARCHAR(32) PRIMARY KEY REFERENCES ring_candidates(candidate_ring_id),
    risk_score            FLOAT,
    risk_level              VARCHAR(16),
    score_components_json    TEXT,
    top_factors_json          TEXT
);

CREATE TABLE IF NOT EXISTS evidence (
    candidate_ring_id       VARCHAR(32) PRIMARY KEY REFERENCES ring_candidates(candidate_ring_id),
    accounts_json              TEXT,
    transactions_json            TEXT,
    paths_json                     TEXT,
    patterns_json                    TEXT,
    time_range_json                    TEXT,
    risk_factors_json                     TEXT,
    trajectory_json                          TEXT,
    warning_time                              VARCHAR(64),
    observable_time                             VARCHAR(64),
    lead_time                                     FLOAT,
    evidence_subgraph_json                          TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_ring_id          VARCHAR(32) REFERENCES ring_candidates(candidate_ring_id),
    risk_level                   VARCHAR(16),
    created_at                     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS model_runs (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name               VARCHAR(64),
    backend                     VARCHAR(32),
    dataset_source                VARCHAR(32),
    trained_at                       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    random_seed                        INTEGER,
    n_train_rows                          INTEGER,
    n_train_positive                         INTEGER
);

CREATE TABLE IF NOT EXISTS evaluation_metrics (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    method               VARCHAR(64),
    split                  VARCHAR(16),
    metrics_json              TEXT
);

CREATE INDEX IF NOT EXISTS idx_transactions_sender ON transactions(sender);
CREATE INDEX IF NOT EXISTS idx_transactions_receiver ON transactions(receiver);
CREATE INDEX IF NOT EXISTS idx_transactions_timestamp ON transactions(timestamp);
CREATE INDEX IF NOT EXISTS idx_pattern_events_window ON pattern_events(window_id);
CREATE INDEX IF NOT EXISTS idx_features_window_account ON features(window_id, account_id);
