-- Migration: Create Error Debug tables
-- Supports both Postgres and SQLite (with minor syntax differences)

-- Table: error_debug_machines
CREATE TABLE IF NOT EXISTS error_debug_machines (
    id UUID PRIMARY KEY,
    display_name VARCHAR(255) UNIQUE NOT NULL,
    printer_model VARCHAR(255) NOT NULL,
    printing_type VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    active_version_id UUID REFERENCES error_debug_machine_index_versions(id)
);

CREATE INDEX IF NOT EXISTS idx_machines_display_name ON error_debug_machines(display_name);
CREATE INDEX IF NOT EXISTS idx_machines_active_version ON error_debug_machines(active_version_id);

-- Table: error_debug_machine_index_versions
CREATE TABLE IF NOT EXISTS error_debug_machine_index_versions (
    id UUID PRIMARY KEY,
    machine_id UUID NOT NULL REFERENCES error_debug_machines(id) ON DELETE CASCADE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    indexed_at TIMESTAMP NOT NULL,
    schema_version VARCHAR(50) NOT NULL,
    gcs_bucket VARCHAR(255),
    gcs_object VARCHAR(500) NOT NULL,
    file_sha256 VARCHAR(64) NOT NULL,
    total_chunks INTEGER NOT NULL,
    total_errors INTEGER NOT NULL,
    stats_json JSONB,  -- JSON in Postgres, TEXT in SQLite
    is_active BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_versions_machine_id ON error_debug_machine_index_versions(machine_id);
CREATE INDEX IF NOT EXISTS idx_versions_is_active ON error_debug_machine_index_versions(is_active);
CREATE INDEX IF NOT EXISTS idx_versions_sha256 ON error_debug_machine_index_versions(file_sha256);

-- Constraint: Only one active version per machine
-- Note: This is enforced at application level for SQLite compatibility
-- For Postgres, you could add: CREATE UNIQUE INDEX idx_one_active_per_machine ON error_debug_machine_index_versions(machine_id) WHERE is_active = TRUE;

