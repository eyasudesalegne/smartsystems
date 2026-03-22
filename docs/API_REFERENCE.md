## API reference

Implemented endpoints:
- `GET /health`
- `GET /ready`
- `GET /metrics`
- `POST /ai/models/register`
- `POST /ai/prompts/register`
- `POST /ai/route`
- `POST /ai/generate`
- `POST /ai/embed`
- `POST /jobs/enqueue`
- `POST /jobs/cancel/{job_id}`
- `GET /jobs/status/{job_id}`
- `POST /ingest/note`
- `POST /ingest/paper`
- `POST /retrieve/query`
- `POST /rag/documents/ingest`
- `GET /rag/governance`
- `POST /approvals/evaluate`
- `POST /approvals/transition`
- `POST /publishbundle/build`
- `POST /command/execute`
- `GET /connectors/catalog`
- `GET /connectors/{service_name}`
- `POST /connectors/prepare`
- `POST /connectors/workflow-draft`
- `GET /connectors/workflow-manifest`
- `POST /connectors/execute-live`
- `POST /connectors/validate-config`
- `POST /connectors/smoke-test`
- `POST /connectors/preflight`
- `POST /connectors/readiness-report`
- `POST /connectors/deployment-plan`
- `POST /connectors/sync-registry`


## Connector endpoints

### GET /connectors/catalog
Returns the service connector catalog.

### GET /connectors/{service_name}
Returns one connector definition, including placeholder credentials and operation list.

### POST /connectors/prepare
Builds a prepared request template with unresolved environment placeholders.

### POST /connectors/workflow-draft
Returns an importable n8n workflow draft and a Codex/GPT authoring prompt.

### GET /connectors/workflow-manifest
Returns a machine-readable map of packaged workflow files, covered operations, uncovered operations, and recommended import/draft targets for each connector. Use it before importing or drafting additional workflows so you know which service operations are already represented by checked-in JSON files.

### POST /connectors/execute-live
Attempts the outbound HTTP call for API-style connectors using runtime environment variables. Responses now include the raw `data` payload plus `normalized`, `summary`, and `pagination` fields when the adapter can derive them safely. Local/manual bridge connectors return the same top-level fields so downstream workflows can consume artifact-style results consistently.

### POST /connectors/validate-config
Validates connector placeholder configuration and persists credential metadata when the connector tables exist.

### POST /connectors/smoke-test
Builds a smoke-test payload for a connector and records the result when the smoke-test tables exist.

### POST /connectors/sync-registry
Upserts the spec-driven connector catalog into `connector_registry` for a tenant so the database matches the repo catalog before live validation.

### POST /connectors/preflight
Returns a tenant-scoped connector readiness report that combines the spec catalog with runtime config validation. Use it before live-stack smoke or persistence checks to see which connectors are configured, which are live-ready, and which credentials are still missing.

### POST /connectors/readiness-report
Returns a combined report that merges preflight credential status with packaged workflow coverage. Use it to answer three operational questions in one call: which connectors are configured, which operations already have checked-in importable workflows, and whether the next best step is to import an existing workflow or generate one through `/connectors/workflow-draft`.

### POST /connectors/deployment-plan
Builds an ordered per-connector rollout plan from the readiness report. Use it to see the exact sequence of next steps per service: fill credentials, sync the registry, import a packaged workflow or draft one, review any manual bridge path, and then run smoke tests.


## rollout bundle
- Endpoint/script/workflow support exists for a combined connector rollout bundle via `/connectors/rollout-bundle`, `scripts/build_connector_rollout_bundle.py`, and `n8n/import/wf_connector_rollout_bundle.json`.


## persistence report
- Endpoint/script/workflow support exists for a connector persistence report via `/connectors/persistence-report`, `scripts/build_connector_persistence_report.py`, and `n8n/import/wf_connector_persistence_report.json`. Use it to verify whether the connector persistence tables exist, whether they have rows yet, and what to do next before full live-stack verification.


## connector credential matrix
- Endpoint/script/workflow: `/connectors/credential-matrix`, `scripts/build_connector_credential_matrix.py`, `n8n/import/wf_connector_credential_matrix.json`.
- Purpose: build a machine-readable map of connector environment variables across services so operators can fill shared secrets before rollout.


## Enterprise security and operations endpoints
- `POST /auth/token` issues an HS256 JWT for configured bootstrap users.
- `POST /secrets/set`, `POST /secrets/get`, `POST /secrets/list` manage encrypted secret material.
- `GET /metrics?format=prometheus` returns Prometheus exposition while preserving the existing JSON metrics mode.
- `GET /admin/queue`, `GET /admin/jobs`, `GET /admin/connectors`, `GET /admin/system` return operational summaries.
- `GET /admin/queue` now also returns queue backend runtime data: requested vs active backend, fallback reason, worker heartbeat count, claim-batch size, and retry-backoff settings.
- `GET /connectors/{service_name}/health` and `GET /connectors/{service_name}/metrics` expose connector health and runtime counters.
- `POST /workflows/version/create` and `POST /workflows/version/promote` provide the first workflow-versioning slice.
- `GET /ai/models` and `GET /ai/prompts` expose model/prompt registry contents or safe defaults.


## workflow versioning additions
- `GET /admin/workflows` returns workflow-version counts, published/draft counts, event counts, and recent versions.
- `GET /workflows/version/history/{workflow_id}` returns ordered version history and the currently published version, with optional definition suppression via `include_definition=false`.
- `POST /workflows/version/rollback` creates a new non-published version from a source version and records a workflow version event.
- `POST /workflows/version/create` now rejects direct creation of published versions and protects published versions from mutation.
- `POST /workflows/version/promote` now enforces publish transitions and demotes the prior published version to approved before publishing a new one.


## queue runtime notes
- `POST /jobs/enqueue` now persists the selected backend into `jobs.queue_backend` and mirrors queue metadata through the backend abstraction.
- `POST /jobs/cancel/{job_id}` now propagates cancellation into the active queue backend as well as the durable DB tables.
- The worker runtime records heartbeat rows in `queue_workers` and backend lifecycle events in `queue_backend_events`.


## AI control layer additions
- `POST /ai/models/register` upserts model metadata into `model_registry` so operators can define capability-aware routing targets.
- `POST /ai/prompts/register` upserts prompt versions into `prompt_registry` with compatibility and mode metadata.
- `POST /ai/route` returns the selected model, fallback chain, prompt name/version, and route reason for an action.
- `POST /ai/generate` now uses task-based routing plus fallback models and records route runs into `ai_route_runs` when the table exists.

## RAG governance additions
- `POST /rag/documents/ingest` stores governed documents in `documents`/`document_chunks` and tracks embedding-version metadata when embeddings are available.
- `GET /rag/governance` returns governed document counts, chunk counts, embedding-version counts, and recent documents.
## Failure isolation additions
- `POST /connectors/{service_name}/policy` upserts per-connector runtime policy overrides (`requests_per_window`, `window_seconds`, `timeout_seconds`, `failure_threshold`, `cooldown_seconds`).
- `POST /connectors/failure-isolation-report` returns a machine-readable connector isolation report with circuit state, recent execution volume, timeout caps, and recommended next actions.
- `POST /workflows/execution/policy` upserts workflow execution-cap policy for a workflow ID.
- `POST /workflows/execution/check` evaluates the execution cap for a workflow and can optionally persist the execution reservation into `audit_logs`.
- `POST /connectors/execute-live` now enforces connector rate limits, circuit-open cooldowns, and timeout caps before dispatching the adapter call.
- `GET /connectors/{service_name}/health` and `GET /connectors/{service_name}/metrics` now expose isolation/runtime state such as `circuit_state`, rejection counters, and active policy values.


### POST /release/manifest
Builds a checksum-backed release manifest over the current package contents and records it when DB persistence is available.

### POST /release/checksum-validate
Validates the current package files against a supplied or freshly generated release manifest.

### POST /release/rollback-package
Builds a rollback bundle ZIP that includes the release manifest, import order, migrations, workflow JSON, rollback guide, and env template.

### POST /release/preflight
Runs local release checks that combine required-file presence, import-order validation, workflow/migration inventory, and checksum validation.

### POST /release/publish
Builds a staged publication ZIP that embeds the release manifest, checksum validation, preflight report, and package files, and records a publication row when persistence is available.

### GET /release/publications
Lists recent release publication rows so operators can audit which release bundles were published or blocked.

## admin release visibility
- `GET /admin/releases` exposes manifest, rollback, and publication counts plus recent publication records.

## data lifecycle additions
- `POST /lifecycle/policy` upserts retention policy settings for supported operational resources.
- `POST /lifecycle/report` returns per-resource counts, eligible-retention counts, batch sizes, and recommended next actions.
- `POST /lifecycle/run-cleanup` performs a dry run or batch cleanup across selected resources and archives DLQ rows before delete when configured.
- `GET /admin/lifecycle` exposes an operator summary of lifecycle policy counts and cleanup eligibility. The effective tenant now follows request-context tenant resolution before the report is built.


## Tenant hardening
- `POST /tenants/create`
- `POST /tenants/membership`
- `GET /tenants/context`
- `GET /admin/tenants`
  - Returns a tenant-scoped admin summary for the effective tenant context rather than an unbounded cross-tenant list by default.

## tenant enforcement endpoints
- `POST /tenants/policy`: upsert a tenant route policy (`route_prefix`, `resource_type`, strict mode, membership and override flags).
- `POST /tenants/enforcement-report`: build a machine-readable report showing the matched policy, decision, reason, accessible tenants, and next actions for a route/actor combination.
- `GET /admin/tenant-enforcement`: list the effective tenant route policies for a tenant plus the current package-level strict-enforcement defaults.



## Tenant row isolation
- `POST /tenants/row-policy`: upsert a per-tenant row-isolation policy for a core table.
- `POST /tenants/row-isolation-report`: simulate the matched row policy, access decision, and next actions for a tenant/table/action combination.
- `GET /admin/tenant-isolation`: list the effective row-isolation policies and package defaults for a tenant.


## release channel automation
- `POST /release/channel` upserts a release publication channel definition (`manual_inspection`, `file_drop`, or `webhook_notify`).
- `GET /release/channels` lists configured release publication channels for a tenant.
- `POST /release/channel-plan` builds a machine-readable channel readiness plan for a release version without requiring a live publication API.
- `GET /admin/release-channels` summarizes configured channels, ready-count, and recent channel plan events.


## Release channel execution automation
- `POST /release/channel-execute`
  - Executes the current release-channel plan in a safe, honest way.
  - `manual_inspection` channels generate operator handoff artifacts.
  - `file_drop` channels can stage or copy the publication bundle into a destination path.
  - `webhook_notify` channels default to preview/dry-run behavior unless webhook sending is explicitly enabled.
- `GET /release/channel-executions`
  - Lists recent channel execution records for the tenant.
- `GET /admin/release-channel-executions`
  - Returns operational counts for delivered, prepared, blocked, and recent channel executions.

- `POST /tenants/query-scope-report` returns the effective tenant-visible row scope, SQL-style filter preview, and matched row policy for a route/resource pair.
- `GET /admin/tenant-query-scope` returns an operator summary of the current query-scope decision for a resource/route under the effective tenant context.


## Tenant query coverage
- `POST /tenants/query-coverage-target` upserts a query-scope coverage target for a tenant.
- `POST /tenants/query-coverage-report` returns the current query-scope coverage report across the seeded high-risk read paths, now including direct job-status, connector health/metrics, RAG governance, lifecycle-admin, and tenant-admin reads.
- `GET /admin/tenant-query-coverage` returns an operator-facing summary of the current query-scope coverage state.
