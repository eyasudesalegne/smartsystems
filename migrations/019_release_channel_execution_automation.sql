
CREATE TABLE IF NOT EXISTS release_channel_executions (
  id BIGSERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT 'default',
  channel_name TEXT NOT NULL,
  release_version TEXT NOT NULL,
  execution_mode TEXT NOT NULL,
  execution_status TEXT NOT NULL,
  dry_run BOOLEAN NOT NULL DEFAULT TRUE,
  package_path TEXT,
  output_path TEXT,
  delivery_ref TEXT,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by TEXT,
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_release_channel_executions_tenant_created_at
  ON release_channel_executions (tenant_id, created_at DESC);

ALTER TABLE release_channels
  ADD COLUMN IF NOT EXISTS last_execution_status TEXT,
  ADD COLUMN IF NOT EXISTS last_execution_mode TEXT,
  ADD COLUMN IF NOT EXISTS last_executed_at TIMESTAMPTZ;
