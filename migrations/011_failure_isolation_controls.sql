CREATE TABLE IF NOT EXISTS connector_runtime_policies (
  connector_runtime_policy_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  service_name text NOT NULL,
  enabled boolean NOT NULL DEFAULT true,
  requests_per_window integer NOT NULL DEFAULT 30,
  window_seconds integer NOT NULL DEFAULT 60,
  timeout_seconds integer NOT NULL DEFAULT 30,
  failure_threshold integer NOT NULL DEFAULT 5,
  cooldown_seconds integer NOT NULL DEFAULT 300,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, service_name)
);

CREATE TABLE IF NOT EXISTS workflow_runtime_policies (
  workflow_runtime_policy_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  workflow_id text NOT NULL,
  enabled boolean NOT NULL DEFAULT true,
  max_executions_per_window integer NOT NULL DEFAULT 120,
  window_seconds integer NOT NULL DEFAULT 60,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, workflow_id)
);

ALTER TABLE connector_metrics ADD COLUMN IF NOT EXISTS blocked_count integer NOT NULL DEFAULT 0;
ALTER TABLE connector_metrics ADD COLUMN IF NOT EXISTS rate_limit_rejection_count integer NOT NULL DEFAULT 0;
ALTER TABLE connector_metrics ADD COLUMN IF NOT EXISTS circuit_open_count integer NOT NULL DEFAULT 0;
ALTER TABLE connector_metrics ADD COLUMN IF NOT EXISTS timeout_rejection_count integer NOT NULL DEFAULT 0;
ALTER TABLE connector_metrics ADD COLUMN IF NOT EXISTS circuit_state text NOT NULL DEFAULT 'closed';
ALTER TABLE connector_metrics ADD COLUMN IF NOT EXISTS consecutive_failures integer NOT NULL DEFAULT 0;
ALTER TABLE connector_metrics ADD COLUMN IF NOT EXISTS requests_per_window integer;
ALTER TABLE connector_metrics ADD COLUMN IF NOT EXISTS window_seconds integer;
ALTER TABLE connector_metrics ADD COLUMN IF NOT EXISTS timeout_cap_seconds integer;
ALTER TABLE connector_metrics ADD COLUMN IF NOT EXISTS failure_threshold integer;
ALTER TABLE connector_metrics ADD COLUMN IF NOT EXISTS cooldown_seconds integer;
ALTER TABLE connector_metrics ADD COLUMN IF NOT EXISTS last_circuit_opened_at timestamptz;
ALTER TABLE connector_metrics ADD COLUMN IF NOT EXISTS last_error_message text;
ALTER TABLE connector_metrics ADD COLUMN IF NOT EXISTS last_policy_refresh_at timestamptz;
