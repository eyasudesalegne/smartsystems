CREATE TABLE IF NOT EXISTS tenant_row_policies (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    resource_table TEXT NOT NULL,
    strict_mode TEXT NOT NULL DEFAULT 'inherit',
    require_tenant_match BOOLEAN NOT NULL DEFAULT TRUE,
    allow_admin_override BOOLEAN NOT NULL DEFAULT TRUE,
    allow_service_account_override BOOLEAN NOT NULL DEFAULT FALSE,
    allow_global_rows BOOLEAN NOT NULL DEFAULT FALSE,
    updated_by TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT tenant_row_policies_unique UNIQUE (tenant_id, resource_table)
);

CREATE INDEX IF NOT EXISTS idx_tenant_row_policies_tenant_table
    ON tenant_row_policies (tenant_id, resource_table);

CREATE TABLE IF NOT EXISTS tenant_row_access_audit (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    actor_id TEXT,
    resource_table TEXT NOT NULL,
    action TEXT NOT NULL DEFAULT 'read',
    requested_tenant_id TEXT NOT NULL,
    effective_tenant_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT NOT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tenant_row_access_audit_tenant_created
    ON tenant_row_access_audit (tenant_id, created_at DESC);
