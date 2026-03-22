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
