BEGIN;

CREATE TABLE IF NOT EXISTS tenant_query_scope_targets (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    route TEXT NOT NULL,
    resource_table TEXT NOT NULL,
    action TEXT NOT NULL DEFAULT 'read',
    strict_mode TEXT NOT NULL DEFAULT 'inherit',
    notes TEXT,
    source TEXT NOT NULL DEFAULT 'db',
    updated_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, route, resource_table, action)
);

CREATE INDEX IF NOT EXISTS idx_tenant_query_scope_targets_tenant_route ON tenant_query_scope_targets (tenant_id, route);

COMMIT;
