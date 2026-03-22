# Queue and retry guide

## runtime model
The package now treats the database queue as the durable source of truth and layers a pluggable backend interface on top of it.

- `db` remains the default backend. Claims come directly from `queue_items` with lease-based locking and `FOR UPDATE SKIP LOCKED`.
- `redis` is optional. When selected, enqueue operations mirror queue metadata into Redis for fast claims, but queue state is still persisted in PostgreSQL. If Redis is unavailable, the worker falls back safely to the DB backend and exposes the fallback reason through `GET /admin/queue`.

## concurrency and worker state
Workers now publish heartbeat and concurrency state into `queue_workers`. Each worker reports:

- `backend_name`
- `status`
- `concurrency_limit`
- `active_claims`
- `last_heartbeat_at`

The worker loop uses `ThreadPoolExecutor(max_workers=WORKER_CONCURRENCY)` so multiple queue items can be processed in parallel without changing the job-processing contract.

## retry behavior
Retries now use bounded exponential backoff with optional jitter:

- base: `RETRY_BACKOFF_BASE_SECONDS`
- cap: `RETRY_BACKOFF_MAX_SECONDS`
- jitter: `RETRY_BACKOFF_JITTER_SECONDS`

The computed delay is persisted into `queue_items.next_retry_delay_seconds`, and the next execution time is written into `queue_items.available_at`. Exhausted items are moved to `dead_letter_items`.

## runtime audit surfaces
Use these operator surfaces to inspect queue behavior:

- `GET /admin/queue` for queue depth, DLQ size, highest waiting priority, requested vs active backend, retry policy, and worker heartbeat count
- `scripts/check_queue_runtime.py --out docs/generated_queue_runtime_report.json` for a local machine-readable report
- `n8n/import/wf_queue_runtime_audit.json` for an importable operator workflow

## migrations
Apply migration `009_queue_runtime_controls.sql` after the prior enterprise migrations. It adds:

- `jobs.queue_backend`
- `queue_items.backend_name`
- `queue_items.claimed_at`
- `queue_items.started_at`
- `queue_items.next_retry_delay_seconds`
- `queue_workers`
- `queue_backend_events`

## environment variables
- `QUEUE_BACKEND=db|redis`
- `REDIS_URL=redis://redis:6379/0`
- `QUEUE_BACKEND_NAMESPACE=controlplane`
- `WORKER_CONCURRENCY=4`
- `QUEUE_MAX_CLAIM_BATCH=16`
- `RETRY_BACKOFF_BASE_SECONDS=15`
- `RETRY_BACKOFF_MAX_SECONDS=1800`
- `RETRY_BACKOFF_JITTER_SECONDS=5`
## failure isolation interplay
Queue-level backoff remains separate from connector failure-isolation controls:

- queue retries decide *when* a job is attempted again
- connector runtime policies decide *whether* a live connector execution is currently allowed

Use `docs/generated_connector_failure_isolation_report.json` together with `docs/generated_queue_runtime_report.json` when diagnosing repeated connector failures or burst-induced throttling.

