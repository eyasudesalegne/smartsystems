CREATE TABLE IF NOT EXISTS release_publications (
  id BIGSERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT 'default',
  release_version TEXT NOT NULL,
  publication_status TEXT NOT NULL,
  package_path TEXT,
  package_checksum TEXT,
  manifest_checksum TEXT,
  publication_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_release_publications_tenant_created_at
  ON release_publications (tenant_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_release_publications_tenant_version_path
  ON release_publications (tenant_id, release_version, package_path);

CREATE TABLE IF NOT EXISTS release_publication_events (
  id BIGSERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT 'default',
  release_version TEXT NOT NULL,
  action TEXT NOT NULL,
  status TEXT NOT NULL,
  package_path TEXT,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_release_publication_events_tenant_created_at
  ON release_publication_events (tenant_id, created_at DESC);
