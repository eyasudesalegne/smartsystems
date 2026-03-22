CREATE TABLE IF NOT EXISTS connector_registry (
  connector_registry_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  service_name text NOT NULL,
  category text NOT NULL,
  integration_mode text NOT NULL,
  auth_type text NOT NULL,
  base_url_env text NOT NULL,
  required_credentials jsonb NOT NULL DEFAULT '[]'::jsonb,
  optional_credentials jsonb NOT NULL DEFAULT '[]'::jsonb,
  implementation_status text NOT NULL,
  notes text,
  docs_reference text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, service_name)
);

CREATE TABLE IF NOT EXISTS connector_credentials_meta (
  connector_credentials_meta_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  service_name text NOT NULL,
  credential_key text NOT NULL,
  is_required boolean NOT NULL DEFAULT true,
  configured boolean NOT NULL DEFAULT false,
  last_validated_at timestamptz,
  error_message text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, service_name, credential_key)
);

CREATE TABLE IF NOT EXISTS connector_execution_log (
  connector_execution_log_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  service_name text NOT NULL,
  operation_id text NOT NULL,
  execution_mode text NOT NULL DEFAULT 'manual',
  request_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  response_payload jsonb,
  status text NOT NULL DEFAULT 'queued',
  error_message text,
  last_validated_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS workflow_templates (
  workflow_template_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  service_name text NOT NULL,
  operation_id text NOT NULL,
  workflow_name text NOT NULL,
  workflow_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  implementation_status text NOT NULL DEFAULT 'draft',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, service_name, operation_id, workflow_name)
);

CREATE TABLE IF NOT EXISTS smoke_test_results (
  smoke_test_result_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  service_name text NOT NULL,
  operation_id text,
  dry_run boolean NOT NULL DEFAULT true,
  configured boolean NOT NULL DEFAULT false,
  status text NOT NULL,
  result_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  error_message text,
  executed_at timestamptz NOT NULL DEFAULT now()
);
