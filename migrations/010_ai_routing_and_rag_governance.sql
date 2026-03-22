CREATE TABLE IF NOT EXISTS ai_route_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL DEFAULT 'default',
  request_id text,
  action_type text NOT NULL,
  generation_mode text NOT NULL DEFAULT 'deterministic',
  selected_model text NOT NULL,
  attempted_models jsonb NOT NULL DEFAULT '[]'::jsonb,
  prompt_name text NOT NULL,
  prompt_version text NOT NULL,
  fallback_used boolean NOT NULL DEFAULT false,
  status text NOT NULL DEFAULT 'completed',
  latency_ms integer,
  error_message text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS document_ingestion_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL DEFAULT 'default',
  document_id uuid,
  source_ref text NOT NULL,
  actor_id text,
  chunk_count integer NOT NULL DEFAULT 0,
  embedding_model text,
  status text NOT NULL DEFAULT 'completed',
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ai_route_runs_tenant_created ON ai_route_runs (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_route_runs_action_status ON ai_route_runs (tenant_id, action_type, status);
CREATE INDEX IF NOT EXISTS idx_document_ingestion_runs_tenant_created ON document_ingestion_runs (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_document_ingestion_runs_source_ref ON document_ingestion_runs (tenant_id, source_ref);
