
ALTER TABLE approvals ADD COLUMN IF NOT EXISTS expires_at timestamptz;
ALTER TABLE approvals ADD COLUMN IF NOT EXISTS decided_at timestamptz;
ALTER TABLE approval_policies ADD COLUMN IF NOT EXISTS require_reviewer_separation boolean NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS publication_bundles (
  publication_bundle_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  title text NOT NULL,
  status text NOT NULL DEFAULT 'draft',
  bundle_manifest jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by text,
  ai_summary_artifact_ref text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS release_artifacts (
  release_artifact_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  artifact_type text NOT NULL,
  artifact_ref text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_publication_bundles_tenant_status ON publication_bundles(tenant_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_release_artifacts_tenant_type ON release_artifacts(tenant_id, artifact_type, created_at DESC);
