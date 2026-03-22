BEGIN;

CREATE TABLE IF NOT EXISTS tenant_query_scope_audit (
  audit_id BIGSERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT 'default',
  actor_id TEXT,
  route TEXT NOT NULL,
  resource_table TEXT NOT NULL,
  requested_tenant_id TEXT,
  effective_tenant_id TEXT NOT NULL,
  visible_tenant_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  records_before INTEGER NOT NULL DEFAULT 0,
  records_after INTEGER NOT NULL DEFAULT 0,
  filtered_count INTEGER NOT NULL DEFAULT 0,
  strict_enforcement BOOLEAN NOT NULL DEFAULT FALSE,
  decision TEXT NOT NULL,
  reason TEXT NOT NULL,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tenant_query_scope_audit_tenant_created_at
  ON tenant_query_scope_audit (tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_tenant_query_scope_audit_route
  ON tenant_query_scope_audit (route);

COMMIT;
