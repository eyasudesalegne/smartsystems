
CREATE EXTENSION IF NOT EXISTS pgcrypto;
DO $$ BEGIN CREATE EXTENSION IF NOT EXISTS vector; EXCEPTION WHEN OTHERS THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS tenants (
  tenant_id text PRIMARY KEY,
  tenant_name text NOT NULL DEFAULT 'Default',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS actors (
  actor_id text PRIMARY KEY,
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  username text,
  display_name text,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS roles (
  role_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  role_name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id, role_name)
);
CREATE TABLE IF NOT EXISTS scopes (
  scope_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  scope_name text UNIQUE NOT NULL
);
CREATE TABLE IF NOT EXISTS actor_roles (
  actor_role_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  actor_id text NOT NULL REFERENCES actors(actor_id) ON DELETE CASCADE,
  role_id uuid NOT NULL REFERENCES roles(role_id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id, actor_id, role_id)
);
CREATE TABLE IF NOT EXISTS role_scopes (
  role_scope_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  role_id uuid NOT NULL REFERENCES roles(role_id) ON DELETE CASCADE,
  scope_id uuid NOT NULL REFERENCES scopes(scope_id) ON DELETE CASCADE,
  UNIQUE(role_id, scope_id)
);

CREATE TABLE IF NOT EXISTS audits (
  audit_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id text NOT NULL,
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  actor_id text,
  source text,
  channel text,
  route text,
  domain text,
  command text,
  decision text,
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  status text,
  error_code text,
  error_message text,
  ai_used boolean NOT NULL DEFAULT false,
  ai_model text,
  ai_action_type text,
  ai_latency_ms integer,
  grounding_source_refs jsonb NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS jobs (
  job_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  actor_id text,
  job_type text NOT NULL,
  status text NOT NULL,
  priority integer NOT NULL DEFAULT 5,
  retry_count integer NOT NULL DEFAULT 0,
  max_retries integer NOT NULL DEFAULT 3,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  result jsonb,
  last_error text,
  scheduled_at timestamptz,
  completed_at timestamptz,
  idempotency_key text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE NULLS NOT DISTINCT (tenant_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS job_runs (
  job_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id uuid NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
  status text NOT NULL,
  error_message text,
  result jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS queue_items (
  queue_item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  job_id uuid NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
  queue_name text NOT NULL DEFAULT 'default',
  status text NOT NULL DEFAULT 'queued',
  priority integer NOT NULL DEFAULT 5,
  schedule_at timestamptz,
  available_at timestamptz NOT NULL DEFAULT now(),
  lease_until timestamptz,
  worker_id text,
  retry_count integer NOT NULL DEFAULT 0,
  max_retries integer NOT NULL DEFAULT 3,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  last_error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS queue_attempts (
  attempt_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  queue_item_id uuid NOT NULL REFERENCES queue_items(queue_item_id) ON DELETE CASCADE,
  job_id uuid NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
  worker_id text,
  status text NOT NULL,
  error_message text,
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz
);
CREATE TABLE IF NOT EXISTS dead_letter_items (
  dead_letter_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  job_id uuid REFERENCES jobs(job_id) ON DELETE SET NULL,
  queue_item_id uuid REFERENCES queue_items(queue_item_id) ON DELETE SET NULL,
  reason text,
  payload jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS notes (
  note_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  actor_id text,
  note_text text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS reminders (
  reminder_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  actor_id text,
  task_text text NOT NULL,
  due_at timestamptz,
  status text NOT NULL DEFAULT 'pending',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS research_notes (
  research_note_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  actor_id text,
  title text,
  body text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS research_queries (
  research_query_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  actor_id text,
  query_text text NOT NULL,
  result_count integer NOT NULL DEFAULT 0,
  mode text NOT NULL DEFAULT 'lexical',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS papers (
  paper_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  source_ref text NOT NULL,
  title text,
  status text NOT NULL DEFAULT 'ingested',
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS paper_chunks (
  chunk_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  paper_id uuid NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
  source_type text,
  source_ref text,
  chunk_index integer NOT NULL,
  title text,
  content text NOT NULL,
  token_estimate integer,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS research_embeddings (
  embedding_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  paper_id uuid REFERENCES papers(paper_id) ON DELETE CASCADE,
  chunk_id uuid REFERENCES paper_chunks(chunk_id) ON DELETE CASCADE,
  embedding_model text,
  embedding vector(768),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS source_ingestions (
  ingestion_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  actor_id text,
  source_type text NOT NULL,
  source_ref text NOT NULL,
  status text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS prompt_templates (
  prompt_template_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  template_name text NOT NULL,
  body text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id, template_name)
);
CREATE TABLE IF NOT EXISTS prompt_versions (
  prompt_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  prompt_template_id uuid NOT NULL REFERENCES prompt_templates(prompt_template_id) ON DELETE CASCADE,
  version_name text NOT NULL,
  body text NOT NULL,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(prompt_template_id, version_name)
);
CREATE TABLE IF NOT EXISTS ai_output_artifacts (
  artifact_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  actor_id text,
  request_id text,
  action_type text NOT NULL,
  ai_model text,
  ai_prompt_version text,
  ai_latency_ms integer,
  prompt_text text,
  output_text text,
  payload_size integer,
  validation_status text,
  grounding_source_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS chat_sessions (
  chat_session_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  actor_id text,
  channel text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id, actor_id, channel)
);
CREATE TABLE IF NOT EXISTS chat_turns (
  chat_turn_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  chat_session_id uuid NOT NULL REFERENCES chat_sessions(chat_session_id) ON DELETE CASCADE,
  actor_id text,
  request_id text,
  role text NOT NULL,
  message_text text NOT NULL,
  ai_used boolean NOT NULL DEFAULT false,
  ai_model text,
  ai_prompt_version text,
  ai_latency_ms integer,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS approval_policies (
  approval_policy_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  domain text NOT NULL,
  action_type text NOT NULL,
  min_approvers integer NOT NULL DEFAULT 1,
  auto_approve boolean NOT NULL DEFAULT false,
  require_reviewer_separation boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS approvals (
  approval_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  domain text NOT NULL,
  action_type text NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  artifact_ref text,
  requested_by text,
  decided_by text,
  decision_note text,
  expires_at timestamptz,
  decided_at timestamptz,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS approval_steps (
  approval_step_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  approval_id uuid NOT NULL REFERENCES approvals(approval_id) ON DELETE CASCADE,
  actor_id text,
  step_name text,
  step_status text,
  note text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS accounts (
  account_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  account_name text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS deliverables (
  deliverable_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  account_id uuid REFERENCES accounts(account_id) ON DELETE SET NULL,
  title text NOT NULL,
  status text NOT NULL DEFAULT 'open',
  due_at timestamptz,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS social_ideas (
  social_idea_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  actor_id text,
  idea_text text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS social_posts (
  social_post_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  actor_id text,
  post_text text,
  status text NOT NULL DEFAULT 'draft',
  published_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS social_assets (
  social_asset_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  asset_ref text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS analytics_snapshots (
  analytics_snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  snapshot_type text NOT NULL,
  snapshot_data jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS reliability_snapshots (
  reliability_snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  snapshot_data jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS manuscripts (
  manuscript_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  title text NOT NULL,
  status text NOT NULL DEFAULT 'draft',
  artifact_ref text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS manuscript_sections (
  manuscript_section_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  manuscript_id uuid NOT NULL REFERENCES manuscripts(manuscript_id) ON DELETE CASCADE,
  section_name text NOT NULL,
  content text,
  grounding_source_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

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
CREATE TABLE IF NOT EXISTS dataset_qa_results (
  dataset_qa_result_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  dataset_name text NOT NULL,
  result_data jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audits_tenant_created ON audits(tenant_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_tenant_status ON jobs(tenant_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_queue_items_status_available ON queue_items(status, available_at, priority, created_at);
CREATE INDEX IF NOT EXISTS idx_queue_attempts_job ON queue_attempts(job_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_notes_tenant_created ON notes(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_reminders_tenant_status ON reminders(tenant_id, status, due_at);
CREATE INDEX IF NOT EXISTS idx_research_notes_tsv ON research_notes USING GIN (to_tsvector('english', coalesce(title,'') || ' ' || coalesce(body,'')));
CREATE INDEX IF NOT EXISTS idx_paper_chunks_tsv ON paper_chunks USING GIN (to_tsvector('english', coalesce(title,'') || ' ' || coalesce(content,'')));
CREATE INDEX IF NOT EXISTS idx_approvals_tenant_domain_status ON approvals(tenant_id, domain, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_publication_bundles_tenant_status ON publication_bundles(tenant_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_release_artifacts_tenant_type ON release_artifacts(tenant_id, artifact_type, created_at DESC);
DO $$ BEGIN
  CREATE INDEX IF NOT EXISTS idx_research_embeddings_vector ON research_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
EXCEPTION WHEN OTHERS THEN NULL; END $$;

INSERT INTO tenants (tenant_id, tenant_name) VALUES ('default', 'Default') ON CONFLICT (tenant_id) DO NOTHING;
INSERT INTO actors (actor_id, tenant_id, username, display_name) VALUES ('anonymous', 'default', 'anonymous', 'Anonymous') ON CONFLICT (actor_id) DO NOTHING;
INSERT INTO roles (tenant_id, role_name) VALUES ('default','admin') ON CONFLICT (tenant_id, role_name) DO NOTHING;
INSERT INTO scopes (scope_name) VALUES ('admin'),('approve:general'),('approve:social'),('approve:publication') ON CONFLICT (scope_name) DO NOTHING;
INSERT INTO role_scopes (role_id, scope_id)
SELECT r.role_id, s.scope_id FROM roles r CROSS JOIN scopes s WHERE r.tenant_id='default' AND r.role_name='admin'
ON CONFLICT DO NOTHING;



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
CREATE TABLE IF NOT EXISTS audit_logs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL DEFAULT 'default',
  user_id text,
  action text NOT NULL,
  resource_type text NOT NULL,
  resource_id text,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  timestamp timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS secrets_store (
  tenant_id text NOT NULL DEFAULT 'default',
  secret_name text NOT NULL,
  encrypted_value text NOT NULL,
  created_by text,
  updated_by text,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, secret_name)
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL DEFAULT 'default',
  idempotency_key text NOT NULL,
  route text NOT NULL,
  request_hash text,
  response_status integer,
  response_headers jsonb NOT NULL DEFAULT '{}'::jsonb,
  response_body jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz,
  UNIQUE (tenant_id, idempotency_key, route)
);

CREATE TABLE IF NOT EXISTS connector_metrics (
  tenant_id text NOT NULL DEFAULT 'default',
  service_name text NOT NULL,
  execution_count integer NOT NULL DEFAULT 0,
  success_count integer NOT NULL DEFAULT 0,
  failure_count integer NOT NULL DEFAULT 0,
  retry_count integer NOT NULL DEFAULT 0,
  failure_rate_percent numeric(8,2) NOT NULL DEFAULT 0,
  last_success_at timestamptz,
  last_failure_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, service_name)
);

CREATE TABLE IF NOT EXISTS workflow_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL DEFAULT 'default',
  workflow_id text NOT NULL,
  version integer NOT NULL,
  status text NOT NULL CHECK (status IN ('draft','tested','approved','published')),
  definition_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, workflow_id, version)
);

CREATE TABLE IF NOT EXISTS model_registry (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL DEFAULT 'default',
  name text NOT NULL,
  type text NOT NULL CHECK (type IN ('local','external')),
  capabilities jsonb NOT NULL DEFAULT '[]'::jsonb,
  latency_profile text,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name)
);

CREATE TABLE IF NOT EXISTS prompt_registry (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL DEFAULT 'default',
  name text NOT NULL,
  version text NOT NULL,
  template text NOT NULL,
  model_compatibility jsonb NOT NULL DEFAULT '[]'::jsonb,
  mode text NOT NULL DEFAULT 'deterministic',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name, version)
);

CREATE TABLE IF NOT EXISTS documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL DEFAULT 'default',
  source_ref text,
  title text,
  mime_type text,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS document_chunks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL DEFAULT 'default',
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  chunk_index integer NOT NULL,
  content text NOT NULL,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, document_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS embedding_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL DEFAULT 'default',
  document_chunk_id uuid REFERENCES document_chunks(id) ON DELETE CASCADE,
  embedding_model text NOT NULL,
  embedding_dimensions integer,
  embedding_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

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

-- 009_queue_runtime_controls.sql
ALTER TABLE jobs
  ADD COLUMN IF NOT EXISTS queue_backend text NOT NULL DEFAULT 'db';

ALTER TABLE queue_items
  ADD COLUMN IF NOT EXISTS backend_name text NOT NULL DEFAULT 'db',
  ADD COLUMN IF NOT EXISTS claimed_at timestamptz,
  ADD COLUMN IF NOT EXISTS started_at timestamptz,
  ADD COLUMN IF NOT EXISTS next_retry_delay_seconds integer NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS queue_workers (
  worker_id text PRIMARY KEY,
  tenant_id text NOT NULL DEFAULT 'default',
  backend_name text NOT NULL DEFAULT 'db',
  status text NOT NULL DEFAULT 'idle',
  concurrency_limit integer NOT NULL DEFAULT 1,
  active_claims integer NOT NULL DEFAULT 0,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  last_heartbeat_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS queue_backend_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL DEFAULT 'default',
  queue_item_id uuid REFERENCES queue_items(queue_item_id) ON DELETE SET NULL,
  job_id uuid REFERENCES jobs(job_id) ON DELETE SET NULL,
  worker_id text,
  backend_name text NOT NULL DEFAULT 'db',
  event_type text NOT NULL,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_queue_workers_backend_heartbeat
  ON queue_workers (backend_name, last_heartbeat_at DESC);

CREATE INDEX IF NOT EXISTS idx_queue_backend_events_tenant_created
  ON queue_backend_events (tenant_id, created_at DESC);

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

-- 011_failure_isolation_controls.sql
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



-- 012_release_engineering_controls.sql
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


-- 013_data_lifecycle_controls.sql
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


CREATE TABLE IF NOT EXISTS tenant_memberships (
  tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  actor_id text NOT NULL REFERENCES actors(actor_id) ON DELETE CASCADE,
  role_name text NOT NULL DEFAULT 'viewer',
  is_default boolean NOT NULL DEFAULT false,
  is_active boolean NOT NULL DEFAULT true,
  created_by text,
  updated_by text,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, actor_id)
);

CREATE TABLE IF NOT EXISTS tenant_settings (
  tenant_id text PRIMARY KEY REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  strict_enforcement boolean NOT NULL DEFAULT false,
  allow_admin_override boolean NOT NULL DEFAULT true,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tenant_context_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL DEFAULT 'default' REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  actor_id text,
  requested_tenant_id text NOT NULL DEFAULT 'default',
  effective_tenant_id text NOT NULL DEFAULT 'default',
  route text,
  resolution_mode text NOT NULL DEFAULT 'identity',
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tenant_memberships_actor_active ON tenant_memberships (actor_id, is_active, tenant_id);
CREATE INDEX IF NOT EXISTS idx_tenant_memberships_tenant_role ON tenant_memberships (tenant_id, role_name, is_active);
CREATE INDEX IF NOT EXISTS idx_tenant_context_events_tenant_created ON tenant_context_events (tenant_id, created_at DESC);

INSERT INTO tenant_settings (tenant_id, strict_enforcement, allow_admin_override)
VALUES ('default', false, true)
ON CONFLICT (tenant_id) DO NOTHING;


-- 015_tenant_enforcement_controls.sql
CREATE TABLE IF NOT EXISTS tenant_route_policies (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    route_prefix TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    strict_mode TEXT NOT NULL DEFAULT 'inherit',
    require_membership BOOLEAN NOT NULL DEFAULT TRUE,
    allow_admin_override BOOLEAN NOT NULL DEFAULT TRUE,
    allow_service_account_override BOOLEAN NOT NULL DEFAULT FALSE,
    updated_by TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT tenant_route_policies_unique UNIQUE (tenant_id, route_prefix)
);

CREATE INDEX IF NOT EXISTS idx_tenant_route_policies_tenant_prefix
    ON tenant_route_policies (tenant_id, route_prefix);

CREATE TABLE IF NOT EXISTS tenant_access_audit (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    actor_id TEXT,
    route TEXT NOT NULL,
    method TEXT NOT NULL DEFAULT 'GET',
    requested_tenant_id TEXT NOT NULL,
    effective_tenant_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT NOT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tenant_access_audit_tenant_created
    ON tenant_access_audit (tenant_id, created_at DESC);

-- migration 016_release_publication_automation.sql
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


-- 017_tenant_row_isolation_controls.sql
CREATE TABLE IF NOT EXISTS tenant_row_policies (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    resource_table TEXT NOT NULL,
    strict_mode TEXT NOT NULL DEFAULT 'inherit',
    require_tenant_match BOOLEAN NOT NULL DEFAULT TRUE,
    allow_admin_override BOOLEAN NOT NULL DEFAULT TRUE,
    allow_service_account_override BOOLEAN NOT NULL DEFAULT FALSE,
    allow_global_rows BOOLEAN NOT NULL DEFAULT FALSE,
    updated_by TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT tenant_row_policies_unique UNIQUE (tenant_id, resource_table)
);

CREATE INDEX IF NOT EXISTS idx_tenant_row_policies_tenant_table
    ON tenant_row_policies (tenant_id, resource_table);

CREATE TABLE IF NOT EXISTS tenant_row_access_audit (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    actor_id TEXT,
    resource_table TEXT NOT NULL,
    action TEXT NOT NULL DEFAULT 'read',
    requested_tenant_id TEXT NOT NULL,
    effective_tenant_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT NOT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tenant_row_access_audit_tenant_created
    ON tenant_row_access_audit (tenant_id, created_at DESC);


-- 018_release_channel_automation.sql
CREATE TABLE IF NOT EXISTS release_channels (
  id BIGSERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT 'default',
  channel_name TEXT NOT NULL,
  channel_type TEXT NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  destination_path TEXT,
  endpoint_url TEXT,
  auth_secret_ref TEXT,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by TEXT,
  last_planned_at TIMESTAMPTZ,
  last_published_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT release_channels_unique UNIQUE (tenant_id, channel_name)
);

CREATE INDEX IF NOT EXISTS idx_release_channels_tenant_created_at
  ON release_channels (tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS release_channel_events (
  id BIGSERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT 'default',
  channel_name TEXT NOT NULL,
  release_version TEXT,
  action TEXT NOT NULL,
  status TEXT NOT NULL,
  package_path TEXT,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_release_channel_events_tenant_created_at
  ON release_channel_events (tenant_id, created_at DESC);


-- 019_release_channel_execution_automation.sql

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



-- 020_tenant_query_scope_controls.sql
BEGIN;

CREATE TABLE IF NOT EXISTS tenant_query_scope_audit (
  audit_id BIGSERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT 'default',
  actor_id TEXT,
  route TEXT NOT NULL,
  resource_table TEXT NOT NULL,
  requested_tenant_id TEXT,
  effective_tenant_id TEXT NOT NULL,
  visible_tenant_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  records_before INTEGER NOT NULL DEFAULT 0,
  records_after INTEGER NOT NULL DEFAULT 0,
  filtered_count INTEGER NOT NULL DEFAULT 0,
  strict_enforcement BOOLEAN NOT NULL DEFAULT FALSE,
  decision TEXT NOT NULL,
  reason TEXT NOT NULL,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tenant_query_scope_audit_tenant_created_at
  ON tenant_query_scope_audit (tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_tenant_query_scope_audit_route
  ON tenant_query_scope_audit (route);

COMMIT;


-- 021_tenant_query_coverage_controls.sql
\i ../migrations/021_tenant_query_coverage_controls.sql
