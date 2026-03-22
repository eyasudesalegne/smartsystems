CREATE TABLE IF NOT EXISTS tenant_memberships (
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  actor_id text NOT NULL REFERENCES actors(actor_id) ON DELETE CASCADE,
  role_name text NOT NULL DEFAULT 'viewer',
  is_default boolean NOT NULL DEFAULT false,
  is_active boolean NOT NULL DEFAULT true,
  created_by text,
  updated_by text,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, actor_id)
);

CREATE TABLE IF NOT EXISTS tenant_settings (
  tenant_id text PRIMARY KEY REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  strict_enforcement boolean NOT NULL DEFAULT false,
  allow_admin_override boolean NOT NULL DEFAULT true,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tenant_context_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL DEFAULT 'default' REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  actor_id text,
  requested_tenant_id text NOT NULL DEFAULT 'default',
  effective_tenant_id text NOT NULL DEFAULT 'default',
  route text,
  resolution_mode text NOT NULL DEFAULT 'identity',
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tenant_memberships_actor_active ON tenant_memberships (actor_id, is_active, tenant_id);
CREATE INDEX IF NOT EXISTS idx_tenant_memberships_tenant_role ON tenant_memberships (tenant_id, role_name, is_active);
CREATE INDEX IF NOT EXISTS idx_tenant_context_events_tenant_created ON tenant_context_events (tenant_id, created_at DESC);

INSERT INTO tenant_settings (tenant_id, strict_enforcement, allow_admin_override)
VALUES ('default', false, true)
ON CONFLICT (tenant_id) DO NOTHING;
