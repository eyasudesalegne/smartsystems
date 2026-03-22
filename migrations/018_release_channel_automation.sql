CREATE TABLE IF NOT EXISTS release_channels (
  id BIGSERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT 'default',
  channel_name TEXT NOT NULL,
  channel_type TEXT NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  destination_path TEXT,
  endpoint_url TEXT,
  auth_secret_ref TEXT,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by TEXT,
  last_planned_at TIMESTAMPTZ,
  last_published_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT release_channels_unique UNIQUE (tenant_id, channel_name)
);

CREATE INDEX IF NOT EXISTS idx_release_channels_tenant_created_at
  ON release_channels (tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS release_channel_events (
  id BIGSERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT 'default',
  channel_name TEXT NOT NULL,
  release_version TEXT,
  action TEXT NOT NULL,
  status TEXT NOT NULL,
  package_path TEXT,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_release_channel_events_tenant_created_at
  ON release_channel_events (tenant_id, created_at DESC);
