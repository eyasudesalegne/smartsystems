
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
