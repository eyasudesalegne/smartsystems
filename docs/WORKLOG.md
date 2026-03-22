# WORKLOG

## 2026-03-16
- Upgraded connector runtime from a monolithic registry toward spec-driven loading using `connectors/specs/*.json`.
- Added modular adapters in `service/app/adapters/` for MLflow, Azure ML, draw.io, Figma, Mermaid, Canvas, Kaggle, NotebookLM, Google Drive, Overleaf, PubMed, arXiv, Antigravity, and VS Code.
- Extended FastAPI routes with connector validation and smoke-test endpoints.
- Replaced ingress masters with the uploaded patched Telegram and web webhook workflows.
- Added exact workflow filenames requested for connector catalog, preparation, draft generation, smoke testing, and per-service examples.
- Added migration `005_connector_runtime_and_smoke_tables.sql`.
- Added continuation docs, packaging status, smoke-test guide, and Codex prompt templates.
- Validation status at checkpoint 1: `pytest -q` passed; package validation and import-order validation passed.
- Continued checkpoint 2 by implementing executable auth-resolution paths in `service/app/adapters/base.py`:
  - MLflow bearer-or-basic auth resolution
  - Azure ML bearer token or client-credentials minting
  - Google Drive bearer token or refresh-token exchange
  - PubMed optional query-param auth injection
- Added runtime-safe persistence hooks in `service/app/main.py` for connector execution logs, credential validation metadata, workflow-template records, and smoke-test results.
- Added connector execution unit tests and a connector-only smoke path that validates local bridge execution without requiring a full live Postgres + Ollama stack.
- Validation status at checkpoint 2: `pytest -q` passed with 16 tests; `python scripts/validate_package.py` passed; `python scripts/import_order_check.py` passed; `bash scripts/smoke_test.sh` passed in connector-only mode.
- Continued checkpoint 3 by fixing health-path degradation safety so `/health` still returns a degraded payload when PostgreSQL is unavailable instead of cascading through queue-depth lookup.
- Added connector-registry database sync support via `POST /connectors/sync-registry`, `scripts/sync_connector_registry.py`, `scripts/verify_connector_persistence.py`, and importable workflow `wf_connector_registry_sync.json`.
- Added migration `006_seed_connector_registry.sql` to seed `connector_registry` for the default tenant from the spec-driven catalog.
- Added tests for registry sync, degraded health behavior, and catalog rows for DB sync; added a persistence smoke scope for next-run live-stack verification.
- Validation status at checkpoint 3: `pytest -q` passed with 19 tests; `python scripts/validate_package.py` passed; `python scripts/import_order_check.py` passed; `bash scripts/smoke_test.sh` passed in connector-only mode with registry sync included.

- Continued checkpoint 4 by wiring the modular adapter files into the runtime so service-specific adapter classes are now actually instantiated instead of falling back to the generic base-class map.
- Added normalized response helpers for MLflow, Azure ML, Google Drive, PubMed, arXiv, Figma, Kaggle, and Canvas so `/connectors/execute-live` can return `normalized`, `summary`, and `pagination` alongside raw `data`.
- Aligned `deploy/.env.example` and legacy `wf_ext_*` workflow templates to the canonical spec-driven credential names (`MLFLOW_TRACKING_URI`, `FIGMA_ACCESS_TOKEN`, `GOOGLE_DRIVE_ACCESS_TOKEN`, `OVERLEAF_ACCESS_TOKEN`, `NOTEBOOKLM_ACCESS_TOKEN`, `CANVAS_ACCESS_TOKEN`, `ANTIGRAVITY_ACCESS_TOKEN`, `VSCODE_BRIDGE_URL`, `VSCODE_ACCESS_TOKEN`, `MERMAID_RENDER_BASE_URL`, `AZURE_ML_SUBSCRIPTION_ID`, `AZURE_ML_RESOURCE_GROUP`).
- Updated backend-bridge n8n workflow normalize nodes so they surface normalized connector results by default instead of only wrapping the raw body.
- Added tests for connector normalization and placeholder consistency; validation status at checkpoint 4: `pytest -q` passed with 25 tests; `python scripts/validate_package.py` passed; `python scripts/import_order_check.py` passed; `bash scripts/smoke_test.sh` passed in connector-only mode.

- Continued checkpoint 5 by standardizing local/manual bridge connector execution outputs so draw.io, Mermaid, Overleaf, VS Code, and Antigravity now return `data`, `normalized`, `summary`, and `pagination` fields in the same shape as the live HTTP connectors.
- Added richer artifact-style normalized payloads for draw.io XML generation and embed handoff payloads, Mermaid local artifacts/fallback render mode, Overleaf bundle/open payloads, and VS Code/Antigravity workspace bundles.
- Expanded connector normalization tests and smoke assertions for local bridge connectors; validation status at checkpoint 5: `pytest -q` passed with 28 tests; `python scripts/validate_package.py` passed; `python scripts/import_order_check.py` passed; `bash scripts/smoke_test.sh` passed in connector-only mode.
- Continued checkpoint 6 by making database pool initialization lazy in `service/app/db.py`, which keeps the service import/startup path resilient when PostgreSQL is unavailable and aligns with the degraded `/health` behavior already added.
- Added connector preflight auditing via `POST /connectors/preflight`, `scripts/connector_preflight_report.py`, and importable workflow `wf_connector_preflight_audit.json` so the next live-stack run can identify which connectors are configured, which are live-ready, and which still need credential work before persistence smoke begins.
- Extended `scripts/smoke_test.sh` with `SMOKE_SCOPE=preflight`, generated `docs/generated_connector_preflight_report.json`, and added tests covering the preflight endpoint and lazy DB pool behavior.
- Validation status at checkpoint 6: `pytest -q` passed with 30 tests; `python scripts/validate_package.py` passed; `python scripts/import_order_check.py` passed; `bash scripts/smoke_test.sh` passed in connector-only mode; `SMOKE_SCOPE=preflight bash scripts/smoke_test.sh` generated a connector preflight report successfully.
- Continued checkpoint 7 by adding workflow coverage auditing via `GET /connectors/workflow-manifest`, `scripts/build_connector_workflow_manifest.py`, importable workflow `wf_connector_workflow_manifest.json`, and generated report `docs/generated_connector_workflow_manifest.json`.
- Added workflow-manifest tests and smoke coverage so the package can now show packaged-vs-draftable operation coverage per connector before import or Codex/GPT authoring work begins.
- Validation status at checkpoint 7: `pytest -q` passed with 32 tests; `python scripts/validate_package.py` passed; `python scripts/import_order_check.py` passed; `bash scripts/smoke_test.sh` passed in connector-only mode; `SMOKE_SCOPE=preflight bash scripts/smoke_test.sh` passed; `SMOKE_SCOPE=manifest bash scripts/smoke_test.sh` generated the workflow coverage manifest successfully.

- Continued checkpoint 8 by adding a combined connector readiness-report path that merges preflight credential status with workflow-manifest coverage and emits a per-service `recommended_action` value.
- Added `POST /connectors/readiness-report`, `scripts/build_connector_readiness_report.py`, importable workflow `wf_connector_readiness_report.json`, generated report `docs/generated_connector_readiness_report.json`, and `SMOKE_SCOPE=readiness`.
- Added readiness-report tests and refreshed API/integration/smoke/authoring docs so the next run can tell in one payload whether a connector should import an existing workflow, fill credentials first, or go through workflow-draft.
- Validation status at checkpoint 8: `pytest -q` passed with 34 tests; `python scripts/validate_package.py` passed; `python scripts/import_order_check.py` passed; `bash scripts/smoke_test.sh` passed in connector-only mode; `SMOKE_SCOPE=preflight bash scripts/smoke_test.sh` passed; `SMOKE_SCOPE=manifest bash scripts/smoke_test.sh` passed; `SMOKE_SCOPE=readiness bash scripts/smoke_test.sh` generated the combined readiness report successfully.

- Continued checkpoint 9 by adding an ordered connector deployment-plan surface that turns readiness plus workflow coverage into per-service rollout steps.
- Added `POST /connectors/deployment-plan`, `scripts/build_connector_deployment_plan.py`, importable workflow `wf_connector_deployment_plan.json`, generated report `docs/generated_connector_deployment_plan.json`, and `SMOKE_SCOPE=deployment`.
- Added deployment-plan tests and refreshed API/integration/smoke/authoring docs so the next live-stack run can move directly from connector state to an ordered import-or-draft execution plan.
- Validation status at checkpoint 9: `pytest -q` passed with 36 tests; `python scripts/validate_package.py` passed; `python scripts/import_order_check.py` passed; `bash scripts/smoke_test.sh` passed in connector-only mode; `SMOKE_SCOPE=preflight bash scripts/smoke_test.sh`, `SMOKE_SCOPE=manifest bash scripts/smoke_test.sh`, `SMOKE_SCOPE=readiness bash scripts/smoke_test.sh`, and `SMOKE_SCOPE=deployment bash scripts/smoke_test.sh` all passed.

- Added combined connector rollout bundle support: `/connectors/rollout-bundle`, `scripts/build_connector_rollout_bundle.py`, `n8n/import/wf_connector_rollout_bundle.json`, `docs/generated_connector_rollout_bundle.json`, `SMOKE_SCOPE=rollout`, plus tests and validation updates.
- Validation after rollout-bundle addition: `cd service && pytest -q` -> 38 passed; `python scripts/validate_package.py` -> ok; `python scripts/import_order_check.py` -> ok; `bash scripts/smoke_test.sh` plus `SMOKE_SCOPE=preflight|manifest|readiness|deployment|rollout` -> ok.

- Continued checkpoint 11 by adding a connector persistence-report surface that audits whether the connector persistence tables exist, whether they have rows yet, and what action to take next before live DB-backed verification.
- Added `POST /connectors/persistence-report`, `scripts/build_connector_persistence_report.py`, importable workflow `wf_connector_persistence_report.json`, generated report `docs/generated_connector_persistence_report.json`, and `SMOKE_SCOPE=persistence_report`.
- Added persistence-report tests and validation updates; validation status at checkpoint 11: `pytest -q` passed with 40 tests; `python scripts/validate_package.py` passed; `python scripts/import_order_check.py` passed; `bash scripts/smoke_test.sh` plus `SMOKE_SCOPE=preflight|manifest|readiness|deployment|rollout|persistence_report` passed.
## 2026-03-17 checkpoint 12
- Added connector credential matrix endpoint, script, generated report, and n8n workflow.
- Added smoke scope `credential_matrix` and validation coverage for the new artifacts.
- Added API tests for `/connectors/credential-matrix` and generated-report coverage.
- Validation: `pytest -q`, `python scripts/validate_package.py`, `python scripts/import_order_check.py`, `SMOKE_SCOPE=credential_matrix bash scripts/smoke_test.sh`.


## 2026-03-17 checkpoint 13
- Added enterprise security and operations baseline without removing prior connector continuity.
- Implemented JWT token issuance, request auth middleware, role/scope enforcement scaffolding, request identity injection, and generic request audit logging into `audit_logs`.
- Added encrypted secrets service scaffolding with Fernet-based storage helpers and `/secrets/set`, `/secrets/get`, `/secrets/list` endpoints.
- Added correlation-id middleware, JSON request logging, Prometheus-compatible `/metrics?format=prometheus`, connector health/metrics endpoints, and admin summary endpoints.
- Added additive migration `007_enterprise_security_and_ops.sql` for audit logs, secrets, idempotency, connector metrics, workflow versions, model registry, prompt registry, documents, document chunks, and embedding versions.
- Added n8n enterprise workflows: `wf_auth_guard`, `wf_idempotency_guard`, `wf_admin_monitoring_dashboard`, `wf_connector_health_monitor`, `wf_retry_orchestrator_v2`, `wf_workflow_promotion_pipeline`.
- Added enterprise tests covering auth token issuance, protected admin access, secret endpoints, Prometheus metrics, and connector health/metrics.
- Validation: `cd service && pytest -q` => 46 passed; `python scripts/validate_package.py` => ok; `python scripts/import_order_check.py` => ok.

## 2026-03-17 checkpoint 14
- Extended workflow versioning into a real enterprise slice without breaking prior connector continuity.
- Added immutable published-version protection, transition validation for promotion, history querying via `GET /workflows/version/history/{workflow_id}`, rollback creation via `POST /workflows/version/rollback`, and workflow admin summary via `GET /admin/workflows`.
- Added additive migration `008_workflow_version_events.sql` and appended it into `sql/unified_production_schema_v2.sql`.
- Added importable n8n workflows `wf_workflow_version_history` and `wf_workflow_version_rollback`.
- Added workflow-version smoke coverage (`SMOKE_SCOPE=workflow_versions`) and enterprise tests for history, rollback, invalid publish transitions, and workflow admin summary.
- Validation: `cd service && pytest -q` => 49 passed; `python scripts/validate_package.py` => ok; `python scripts/import_order_check.py` => ok; `bash scripts/smoke_test.sh` => ok; `SMOKE_SCOPE=workflow_versions bash scripts/smoke_test.sh` => ok.


- Continued checkpoint 15 by implementing the next enterprise queue slice without breaking connector continuity.
- Added a pluggable queue backend abstraction in `service/app/worker.py` with a durable DB backend and an optional Redis mirror backend that safely falls back to DB when Redis is unavailable.
- Added worker concurrency enforcement via `ThreadPoolExecutor`, queue worker heartbeats/state in `queue_workers`, queue backend event logging in `queue_backend_events`, and bounded exponential backoff with jitter using `next_retry_delay_seconds`.
- Added additive migration `009_queue_runtime_controls.sql` and appended it into `sql/unified_production_schema_v2.sql`.
- Routed `/jobs/enqueue` and `/jobs/cancel/{job_id}` through the backend abstraction so queue mirroring and cancellation hooks now run end-to-end while preserving the existing DB queue as the source of truth.
- Enriched `GET /admin/queue` with runtime fields: requested vs active backend, concurrency, claim-batch limit, retry backoff settings, backend health, fallback reason, and active worker count.
- Added `scripts/check_queue_runtime.py`, generated `docs/generated_queue_runtime_report.json`, importable workflow `n8n/import/wf_queue_runtime_audit.json`, and `SMOKE_SCOPE=queue_runtime`.
- Validation status at checkpoint 15: `pytest -q` passed with 54 tests; `python scripts/validate_package.py` passed; `python scripts/import_order_check.py` passed; `bash scripts/smoke_test.sh`, `SMOKE_SCOPE=workflow_versions bash scripts/smoke_test.sh`, and `SMOKE_SCOPE=queue_runtime bash scripts/smoke_test.sh` all passed.


## 2026-03-17 checkpoint 16
- Continued the enterprise upgrade by wiring the next coherent AI/RAG slice without breaking connector continuity.
- Added task-based AI routing helpers backed by `model_registry` and `prompt_registry`, plus `POST /ai/models/register`, `POST /ai/prompts/register`, and `POST /ai/route`.
- Upgraded `POST /ai/generate` so it now resolves a model/prompt route, composes the routed prompt template into the system prompt, attempts fallback models in order, and records route runs in `ai_route_runs` when the table exists.
- Added governed document ingestion via `POST /rag/documents/ingest`, retrieval coverage for `document_chunks`, and governance reporting via `GET /rag/governance` plus `scripts/build_rag_governance_report.py`.
- Added additive migration `010_ai_routing_and_rag_governance.sql` and appended it into `sql/unified_production_schema_v2.sql`.
- Added importable workflows `wf_ai_task_router.json` and `wf_rag_document_ingest_governed.json` plus generated reports `docs/generated_ai_control_report.json` and `docs/generated_rag_governance_report.json`.
- Added smoke scopes `ai_control` and `rag_governance` and expanded enterprise tests for AI routing fallback and RAG ingestion/governance endpoints.
- Validation: `cd service && pytest -q` => 58 passed; `python scripts/validate_package.py` => ok; `python scripts/import_order_check.py` => ok; `bash scripts/smoke_test.sh` => ok; `SMOKE_SCOPE=workflow_versions|queue_runtime|ai_control|rag_governance|preflight|manifest|readiness|deployment|rollout|persistence_report|credential_matrix bash scripts/smoke_test.sh` => ok.

- Continued checkpoint 17 by adding enterprise failure-isolation controls without breaking the existing connector continuity.
- Added additive migration `011_failure_isolation_controls.sql`, which introduces `connector_runtime_policies`, `workflow_runtime_policies`, and runtime/isolation columns on `connector_metrics` for blocked counts, circuit state, timeout rejections, policy snapshots, and last-circuit-open timestamps.
- Added connector runtime policy enforcement in `POST /connectors/execute-live`: per-service rate limits, timeout caps, circuit-open cooldown handling, half-open recovery, and rejection/error outcome recording.
- Extended connector health/metrics surfaces so `GET /connectors/{service_name}/health` and `GET /connectors/{service_name}/metrics` now expose policy-derived state such as `circuit_state`, rate-limit rejection counts, timeout rejection counts, and active timeout/cooldown policy values.
- Added workflow execution-cap controls via `POST /workflows/execution/check` and `POST /workflows/execution/policy`, and wired `publishbundle_build` through the execution-cap guard so a real high-impact workflow path is enforced end-to-end.
- Added `POST /connectors/{service_name}/policy` for connector runtime policy overrides and `POST /connectors/failure-isolation-report` plus `scripts/build_connector_failure_isolation_report.py` and `scripts/check_workflow_execution_caps.py` for operator-facing isolation/cap reports.
- Added importable workflows `wf_connector_failure_isolation_audit.json` and `wf_workflow_execution_cap_guard.json`, generated reports `docs/generated_connector_failure_isolation_report.json` and `docs/generated_workflow_execution_cap_report.json`, and smoke scopes `failure_isolation` and `workflow_caps`.
- Validation: `cd service && pytest -q` => 62 passed; `python scripts/validate_package.py` => ok; `python scripts/import_order_check.py` => ok; `bash scripts/smoke_test.sh` => ok; `SMOKE_SCOPE=workflow_versions|queue_runtime|ai_control|rag_governance|failure_isolation|workflow_caps bash scripts/smoke_test.sh` => ok.

- Continued checkpoint 18 by adding release-engineering controls: `POST /release/manifest`, `POST /release/checksum-validate`, `POST /release/rollback-package`, and `POST /release/preflight`.
- Added additive migration `012_release_engineering_controls.sql`, release scripts (`build_release_manifest.py`, `validate_release_checksums.py`, `build_release_rollback_package.py`, `run_release_preflight.py`), importable n8n release workflows, generated release artifacts, and release smoke scopes.

- Validation at checkpoint 18: `cd service && pytest -q` => 67 passed; `python scripts/validate_package.py` => ok; `python scripts/import_order_check.py` => ok; `bash scripts/smoke_test.sh` => ok; `SMOKE_SCOPE=release_manifest|release_checksums|release_rollback|release_preflight bash scripts/smoke_test.sh` => ok.

## 2026-03-17 checkpoint 19
- Continued the enterprise upgrade by adding a real data-lifecycle management slice without breaking connector continuity.
- Added additive migration `013_data_lifecycle_controls.sql`, including `retention_policies`, `lifecycle_runs`, and `dlq_archives`, and appended it into `sql/unified_production_schema_v2.sql`.
- Added lifecycle runtime module `service/app/lifecycle.py` with seeded per-resource retention defaults, machine-readable reporting, batch cleanup, and DLQ archival-before-delete support.
- Added lifecycle endpoints `POST /lifecycle/policy`, `POST /lifecycle/report`, `POST /lifecycle/run-cleanup`, and admin visibility via `GET /admin/lifecycle`.
- Added scripts `build_data_lifecycle_report.py` and `run_data_lifecycle_cleanup.py`, generated reports `docs/generated_data_lifecycle_report.json` and `docs/generated_data_lifecycle_cleanup.json`, and importable workflows `wf_data_lifecycle_audit.json` and `wf_data_lifecycle_cleanup.json`.
- Added smoke scopes `lifecycle_report` and `lifecycle_cleanup` plus enterprise tests for lifecycle policy/report/cleanup/admin flows.
- Validation: `cd service && pytest -q` => 69 passed; `python scripts/validate_package.py` => ok; `python scripts/import_order_check.py` => ok; `bash scripts/smoke_test.sh` => ok; `SMOKE_SCOPE=lifecycle_report bash scripts/smoke_test.sh` => ok; `SMOKE_SCOPE=lifecycle_cleanup bash scripts/smoke_test.sh` => ok.

## 2026-03-17 checkpoint 20
- Continued the enterprise upgrade by adding a tenant-hardening slice without breaking connector continuity.
- Added additive migration `014_tenant_hardening.sql`, including `tenant_memberships`, `tenant_settings`, and `tenant_context_events`, and appended it into `sql/unified_production_schema_v2.sql`.
- Added tenant runtime module `service/app/tenant.py` with tenant creation, membership upsert, membership listing, effective-tenant resolution, default bootstrap seeding, and tenant context reporting.
- Hardened request middleware so tenant context is resolved from the configured tenant header, query string, or JSON body, then reconciled against the authenticated identity before downstream handlers execute.
- Added tenant endpoints `POST /tenants/create`, `POST /tenants/membership`, `GET /tenants/context`, and admin visibility via `GET /admin/tenants`.
- Added script `scripts/build_tenant_context_report.py`, generated report `docs/generated_tenant_context_report.json`, and importable workflows `wf_tenant_context_audit.json` and `wf_tenant_membership_upsert.json`.
- Added smoke scope `tenant_context` plus enterprise tests for tenant context, tenant creation/membership writes, and admin tenant summaries.
- Validation: `cd service && pytest -q` => 72 passed; `python scripts/validate_package.py` => ok; `python scripts/import_order_check.py` => ok; `bash scripts/smoke_test.sh` => ok; `SMOKE_SCOPE=tenant_context bash scripts/smoke_test.sh` => ok.

## 2026-03-18 checkpoint 21
- Continued the enterprise upgrade by adding a stricter tenant-enforcement slice without breaking connector continuity.
- Added additive migration `015_tenant_enforcement_controls.sql`, including `tenant_route_policies` and `tenant_access_audit`, and appended it into `sql/unified_production_schema_v2.sql`.
- Extended `service/app/tenant.py` with seeded default route policies, per-route policy upsert/listing, tenant access audit persistence, enforcement decisions, and machine-readable enforcement reporting.
- Hardened request middleware so authenticated requests are checked against the matched tenant route policy after scope authorization and tenant resolution.
- Added tenant enforcement endpoints `POST /tenants/policy`, `POST /tenants/enforcement-report`, and admin visibility via `GET /admin/tenant-enforcement`.
- Added script `scripts/build_tenant_enforcement_report.py`, generated report `docs/generated_tenant_enforcement_report.json`, and importable workflows `wf_tenant_policy_upsert.json` and `wf_tenant_enforcement_audit.json`.
- Added smoke scope `tenant_enforcement` plus tenant-policy tests and direct route-enforcement denial coverage.
- Validation: `cd service && pytest -q` => 75 passed; `python scripts/validate_package.py` => ok; `python scripts/import_order_check.py` => ok; `bash scripts/smoke_test.sh` => ok; `SMOKE_SCOPE=tenant_context bash scripts/smoke_test.sh` => ok; `SMOKE_SCOPE=tenant_enforcement bash scripts/smoke_test.sh` => ok.

## 2026-03-18 checkpoint 22
- Continued the enterprise upgrade by adding deeper release publication automation without breaking connector continuity or earlier enterprise layers.
- Added additive migration `016_release_publication_automation.sql`, including `release_publications` and `release_publication_events`, and appended it into `sql/unified_production_schema_v2.sql`.
- Added staged publication bundle automation via `POST /release/publish`, publication history via `GET /release/publications`, and admin release visibility via `GET /admin/releases`.
- Added helper `_build_release_publication(...)` to assemble a publication ZIP containing the package candidate files plus embedded `release_manifest.json`, `release_checksum_validation.json`, `release_preflight_report.json`, and `release_publication_summary.json`.
- Added script `scripts/build_release_publication_report.py`, generated `docs/generated_release_publication_report.json`, and created `artifacts/release_publication_bundle_default.zip`.
- Added importable workflows `wf_release_publish_pipeline.json` and `wf_release_publication_audit.json`, plus smoke scope `release_publication`.
- Validation: `cd service && pytest -q` => 78 passed; `python scripts/validate_package.py` => ok; `python scripts/import_order_check.py` => ok; `bash scripts/smoke_test.sh` => ok; `SMOKE_SCOPE=release_publication bash scripts/smoke_test.sh` => ok.

## 2026-03-18 checkpoint 23
- Continued the enterprise upgrade by adding a stricter tenant row-isolation slice without breaking connector continuity or the earlier enterprise layers.
- Added additive migration `017_tenant_row_isolation_controls.sql`, including `tenant_row_policies` and `tenant_row_access_audit`, and appended it into `sql/unified_production_schema_v2.sql`.
- Added tenant row-isolation runtime module `service/app/tenant_row.py` with seeded per-table defaults, per-tenant row-policy upsert/list/resolve logic, row-access audit persistence, route-to-core-table inference, and machine-readable row-isolation reporting.
- Hardened request middleware so authenticated requests now evaluate the matched core-table row policies for the current route after tenant context and route-policy enforcement; strict denial remains additive behind policy/setting controls.
- Added tenant row-isolation endpoints `POST /tenants/row-policy`, `POST /tenants/row-isolation-report`, and admin visibility via `GET /admin/tenant-isolation`.
- Added script `scripts/build_tenant_row_isolation_report.py`, generated report `docs/generated_tenant_row_isolation_report.json`, and importable workflows `wf_tenant_row_policy_upsert.json` and `wf_tenant_row_isolation_audit.json`.
- Added smoke scope `tenant_row_isolation` plus tenant row-policy/report/admin tests.
- Validation: `cd service && pytest -q` => 80 passed; `python scripts/validate_package.py` => ok; `python scripts/import_order_check.py` => ok; `bash scripts/smoke_test.sh` => ok; `SMOKE_SCOPE=tenant_context|tenant_enforcement|tenant_row_isolation bash scripts/smoke_test.sh` => ok.


## 2026-03-18 checkpoint 24
- Continued the enterprise upgrade by adding deeper release publication-channel automation without breaking connector continuity or the earlier enterprise layers.
- Added additive migration `018_release_channel_automation.sql`, including `release_channels` and `release_channel_events`, and appended it into `sql/unified_production_schema_v2.sql`.
- Added release channel configuration/planning surfaces: `POST /release/channel`, `GET /release/channels`, `POST /release/channel-plan`, and `GET /admin/release-channels`.
- Added release channel planning helper/report script `scripts/build_release_channel_report.py`, generated `docs/generated_release_channel_report.json`, and importable workflows `wf_release_channel_upsert.json` and `wf_release_channel_plan.json`.
- Extended tenant row-isolation defaults/route-to-table mapping so release channel tables are covered by the additive tenant isolation audit path.
- Validation: `cd service && pytest -q` => 83 passed; `python scripts/validate_package.py` => ok; `python scripts/import_order_check.py` => ok; `bash scripts/smoke_test.sh` => ok; `SMOKE_SCOPE=release_channels bash scripts/smoke_test.sh` => ok.


## 2026-03-18 checkpoint 25
- Continued the enterprise upgrade by adding deeper release publication-channel execution automation without breaking connector continuity or earlier enterprise slices.
- Added additive migration `019_release_channel_execution_automation.sql`, including `release_channel_executions` plus execution-state columns on `release_channels`, and appended it into `sql/unified_production_schema_v2.sql`.
- Added release channel execution endpoints `POST /release/channel-execute`, `GET /release/channel-executions`, and `GET /admin/release-channel-executions`.
- Added safe execution modes for `manual_inspection`, `file_drop`, and `webhook_notify` channels: manual handoff artifacts, file-drop staging/copy, and webhook preview-or-send behavior.
- Added local-safe execution persistence fallback, script `scripts/build_release_channel_execution_report.py`, generated report `docs/generated_release_channel_execution_report.json`, and importable workflows `wf_release_channel_execute.json` and `wf_release_channel_execution_audit.json`.
- Extended tenant row-isolation defaults and route mapping so `release_channel_executions` are covered by the existing additive tenant audit/enforcement layer.
- Added smoke scope `release_channel_execution` plus expanded release-engineering tests for channel execution and execution audit/admin flows.
- Validation: `cd service && pytest -q` => 85 passed; `python scripts/validate_package.py` => ok; `python scripts/import_order_check.py` => ok; `bash scripts/smoke_test.sh` => ok; `SMOKE_SCOPE=release_channels bash scripts/smoke_test.sh` => ok; `SMOKE_SCOPE=release_channel_execution bash scripts/smoke_test.sh` => ok.

- Added tenant query-scope controls (migration 020), query-scope report/admin surfaces, request-tenant scoped list/admin endpoints for release/publication paths, workflow/report artifacts, and smoke/test coverage.

## 2026-03-18 checkpoint 26
- Added migration `020_tenant_query_scope_controls.sql` and appended it into `sql/unified_production_schema_v2.sql`.
- Added query-time tenant row scoping helpers in `service/app/tenant_row.py`, plus `POST /tenants/query-scope-report` and `GET /admin/tenant-query-scope`.
- Hardened release/publication list and admin read paths so request-context tenant scoping is applied even when fallback caches are used.
- Added `scripts/build_tenant_query_scope_report.py`, generated `docs/generated_tenant_query_scope_report.json`, importable workflow `wf_tenant_query_scope_audit.json`, smoke scope `tenant_query_scope`, and tenant/release tests.
- Validation: `pytest -q` → 87 passed; `python scripts/validate_package.py` → ok; `python scripts/import_order_check.py` → ok; smoke scopes `connectors`, `tenant_context`, `tenant_enforcement`, `tenant_row_isolation`, `tenant_query_scope`, `release_channels`, and `release_channel_execution` → ok.

- Added tenant query coverage controls, expanded request-context tenant scoping to more admin/AI/read paths, and generated the new coverage report/workflow/script set.

## 2026-03-18 checkpoint 27
- Added migration `021_tenant_query_coverage_controls.sql` and appended it into `sql/unified_production_schema_v2.sql`.
- Added tenant query coverage target/runtime functions in `service/app/tenant_row.py`, including seeded high-risk coverage targets, target upsert/list support, and aggregate coverage reporting.
- Added `POST /tenants/query-coverage-target`, `POST /tenants/query-coverage-report`, and `GET /admin/tenant-query-coverage`.
- Expanded request-context tenant row scoping to more read/admin paths including `/admin/queue`, `/admin/jobs`, `/admin/workflows`, `/admin/connectors`, `/ai/models`, and `/ai/prompts`.
- Added `scripts/build_tenant_query_coverage_report.py`, generated `docs/generated_tenant_query_coverage_report.json`, importable workflow `wf_tenant_query_coverage_audit.json`, smoke scope `tenant_query_coverage`, and expanded tenant tests.
- Validation: `pytest -q` → 89 passed; `python scripts/validate_package.py` → ok; `python scripts/import_order_check.py` → ok; smoke scopes `connectors`, `tenant_context`, `tenant_enforcement`, `tenant_row_isolation`, `tenant_query_scope`, `tenant_query_coverage`, `release_channels`, and `release_channel_execution` → ok.

## 2026-03-21 checkpoint 28
- Continued the enterprise upgrade by hardening direct tenant-scoped read endpoints without breaking connector continuity or earlier enterprise slices.
- Extended tenant query-coverage targets and route-to-table mapping so direct reads such as `/jobs/status/{job_id}`, `/connectors/{service_name}/health`, `/connectors/{service_name}/metrics`, `/rag/governance`, `/admin/lifecycle`, and `/admin/tenants` are explicitly tracked.
- Hardened request-context tenant resolution across connector health/metrics, job-status reads, RAG governance, admin system/lifecycle summaries, admin tenant summaries, and tenant admin policy summaries so header/auth-derived tenant context wins over stale query defaults.
- Scoped `list_tenants_summary(...)` to the effective tenant by default for admin reads instead of returning an unbounded cross-tenant summary.
- Added regression tests for request-context tenant scoping across connector metrics, workflow history, job status, RAG governance, lifecycle admin, and tenant admin flows.
- Validation: `cd service && pytest -q` => 95 passed; `python scripts/validate_package.py` => ok; `python scripts/import_order_check.py` => ok; `bash scripts/smoke_test.sh` => ok; `SMOKE_SCOPE=tenant_context|tenant_enforcement|tenant_row_isolation|tenant_query_scope|tenant_query_coverage|release_channels|release_channel_execution bash scripts/smoke_test.sh` => ok.
