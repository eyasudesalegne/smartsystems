CREATE TABLE IF NOT EXISTS workflow_version_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL DEFAULT 'default',
  workflow_id text NOT NULL,
  version integer,
  action text NOT NULL,
  actor_id text,
  source_version integer,
  target_version integer,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_workflow_version_events_tenant_workflow_created
  ON workflow_version_events (tenant_id, workflow_id, created_at DESC);
