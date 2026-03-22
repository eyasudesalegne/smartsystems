CREATE TABLE IF NOT EXISTS retention_policies (
  retention_policy_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL DEFAULT 'default',
  resource_type text NOT NULL,
  enabled boolean NOT NULL DEFAULT true,
  retain_days integer NOT NULL DEFAULT 30,
  archive_before_delete boolean NOT NULL DEFAULT false,
  batch_size integer NOT NULL DEFAULT 500,
  last_run_at timestamptz,
  updated_by text,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, resource_type)
);

CREATE TABLE IF NOT EXISTS lifecycle_runs (
  lifecycle_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL DEFAULT 'default',
  run_type text NOT NULL CHECK (run_type IN ('report','cleanup')),
  dry_run boolean NOT NULL DEFAULT true,
  resource_types jsonb NOT NULL DEFAULT '[]'::jsonb,
  status text NOT NULL DEFAULT 'ok',
  summary_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dlq_archives (
  dlq_archive_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL DEFAULT 'default',
  dead_letter_id uuid NOT NULL,
  archived_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  source_created_at timestamptz,
  archived_by text,
  reason text,
  archived_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, dead_letter_id)
);

CREATE INDEX IF NOT EXISTS idx_retention_policies_tenant_resource ON retention_policies (tenant_id, resource_type);
CREATE INDEX IF NOT EXISTS idx_lifecycle_runs_tenant_created ON lifecycle_runs (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_dlq_archives_tenant_archived ON dlq_archives (tenant_id, archived_at DESC);
