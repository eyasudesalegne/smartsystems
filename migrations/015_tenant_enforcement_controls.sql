CREATE TABLE IF NOT EXISTS tenant_route_policies (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    route_prefix TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    strict_mode TEXT NOT NULL DEFAULT 'inherit',
    require_membership BOOLEAN NOT NULL DEFAULT TRUE,
    allow_admin_override BOOLEAN NOT NULL DEFAULT TRUE,
    allow_service_account_override BOOLEAN NOT NULL DEFAULT FALSE,
    updated_by TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT tenant_route_policies_unique UNIQUE (tenant_id, route_prefix)
);

CREATE INDEX IF NOT EXISTS idx_tenant_route_policies_tenant_prefix
    ON tenant_route_policies (tenant_id, route_prefix);

CREATE TABLE IF NOT EXISTS tenant_access_audit (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    actor_id TEXT,
    route TEXT NOT NULL,
    method TEXT NOT NULL DEFAULT 'GET',
    requested_tenant_id TEXT NOT NULL,
    effective_tenant_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT NOT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tenant_access_audit_tenant_created
    ON tenant_access_audit (tenant_id, created_at DESC);
