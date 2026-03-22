
CREATE TABLE IF NOT EXISTS service_connectors (
  connector_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  service_name text NOT NULL,
  display_name text NOT NULL,
  integration_mode text NOT NULL,
  status text NOT NULL DEFAULT 'template_ready',
  base_url_env text,
  credential_placeholders jsonb NOT NULL DEFAULT '[]'::jsonb,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, service_name)
);

CREATE TABLE IF NOT EXISTS connector_credentials (
  connector_credential_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  service_name text NOT NULL,
  credential_key text NOT NULL,
  placeholder_ref text NOT NULL,
  is_configured boolean NOT NULL DEFAULT false,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, service_name, credential_key)
);

CREATE TABLE IF NOT EXISTS connector_workflow_templates (
  connector_workflow_template_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  service_name text NOT NULL,
  operation_id text NOT NULL,
  workflow_name text NOT NULL,
  workflow_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, service_name, operation_id, workflow_name)
);

CREATE TABLE IF NOT EXISTS connector_runs (
  connector_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  service_name text NOT NULL,
  operation_id text NOT NULL,
  request_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  response_payload jsonb,
  status text NOT NULL DEFAULT 'draft',
  error_message text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_service_connectors_tenant_service ON service_connectors(tenant_id, service_name);
CREATE INDEX IF NOT EXISTS idx_connector_runs_tenant_service_created ON connector_runs(tenant_id, service_name, created_at DESC);
