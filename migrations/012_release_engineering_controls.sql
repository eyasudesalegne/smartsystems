CREATE TABLE IF NOT EXISTS release_manifests (
  release_manifest_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL DEFAULT 'default',
  release_version text NOT NULL,
  package_filename text,
  source_package text,
  checksum_algorithm text NOT NULL DEFAULT 'sha256',
  manifest_checksum text NOT NULL,
  manifest_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rollback_packages (
  rollback_package_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL DEFAULT 'default',
  release_version text NOT NULL,
  package_path text NOT NULL,
  package_checksum text NOT NULL,
  manifest_checksum text,
  includes_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS release_preflight_runs (
  release_preflight_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL DEFAULT 'default',
  release_version text NOT NULL,
  run_type text NOT NULL,
  status text NOT NULL DEFAULT 'passed',
  report_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_release_manifests_tenant_version ON release_manifests (tenant_id, release_version, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_rollback_packages_tenant_version ON rollback_packages (tenant_id, release_version, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_release_preflight_runs_tenant_version ON release_preflight_runs (tenant_id, release_version, created_at DESC);
