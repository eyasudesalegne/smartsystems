# RESUME FROM HERE

## project objective
Continue upgrading the hybrid n8n + FastAPI + PostgreSQL + Ollama package into an enterprise-grade, production-ready control plane without breaking the connector continuity already built.

## completed work
- Added additive migration `021_tenant_query_coverage_controls.sql`.
- Added tenant query coverage controls with `POST /tenants/query-coverage-target`, `POST /tenants/query-coverage-report`, `GET /admin/tenant-query-coverage`, `scripts/build_tenant_query_coverage_report.py`, generated `docs/generated_tenant_query_coverage_report.json`, and importable workflow `wf_tenant_query_coverage_audit.json`.
- Expanded request-context tenant query scoping to additional high-risk read paths including admin queue/jobs/workflows/connectors and AI model/prompt registry reads.
- Hardened direct read endpoints so request-context tenant resolution now applies consistently to connector health/metrics, job status, RAG governance, admin lifecycle, admin tenants, admin system, and tenant admin policy summaries.
- Expanded query-coverage targets to include `/jobs/status/{job_id}`, `/connectors/{service_name}/health`, `/connectors/{service_name}/metrics`, `/rag/governance`, `/admin/lifecycle`, and `/admin/tenants`.
- Prior connector framework, rollout/readiness/deployment/persistence/credential-matrix tooling, auth/secrets/admin baseline, workflow versioning, queue runtime hardening, AI/RAG routing/governance, failure isolation, release-engineering controls, lifecycle controls, tenant-hardening, tenant route enforcement, release publication automation, tenant row-isolation, release channel planning, and release channel execution remain intact.
- Added additive migration `020_tenant_query_scope_controls.sql`.
- Added tenant query-scope controls with `POST /tenants/query-scope-report`, `GET /admin/tenant-query-scope`, `scripts/build_tenant_query_scope_report.py`, generated `docs/generated_tenant_query_scope_report.json`, and importable workflow `wf_tenant_query_scope_audit.json`.
- Hardened release/publication list and admin read paths so request-context tenant row scoping is applied even when fallback caches or local previews are involved.
- Updated smoke/validation coverage so `SMOKE_SCOPE=tenant_query_scope` and package validators track the new query-scope slice.

## incomplete work
- Live DB-backed verification is still not completed in this container.
- Query-time tenant filtering is expanded, but it is still not full SQL row-level isolation across every read/query path and every core table.
- Several write paths still trust body/query tenant IDs directly instead of always reconciling to the resolved request-context tenant before persistence.
- Redis execution has been wired as an optional backend, but it still needs live-stack verification against an actual Redis server and worker fleet.
- Tenant isolation is materially stronger, but it is still preparatory rather than full SQL row-level isolation across every query path and every core table.
- Release publication, release-channel planning, and release-channel execution automation are implemented locally, but still need live-stack verification alongside real package publishing.
- Failure isolation, lifecycle cleanup, tenant-context policies, tenant route enforcement, tenant row isolation, tenant query-scope audit persistence, release publication persistence, and release-channel execution persistence still need live-stack verification of actual policy persistence and runtime effects.

## current highest-priority next action
Run migrations 007 through 021 on a real database, exercise auth + secrets + admin + workflow-version + queue-runtime + AI/RAG + failure-isolation + release-engineering + lifecycle + tenant + tenant-enforcement + tenant-row-isolation + tenant-query-scope + tenant-query-coverage + release-publication + release-channel + release-channel-execution endpoints against a live service, then implement the next enterprise slice without breaking compatibility: reconcile write-time tenant IDs to the resolved request-context tenant across more POST/update flows and continue pushing tenant-aware filtering deeper into SQL-backed queries.

## exact files/modules to edit next
- `service/app/main.py`
- `service/app/tenant.py`
- `service/app/tenant_row.py`
- `service/app/auth.py`
- `service/app/config.py`
- `docs/API_REFERENCE.md`
- `docs/SMOKE_TEST_GUIDE.md`
- `docs/RELEASE_ENGINEERING_GUIDE.md`
- `docs/MULTI_TENANCY_GUIDE.md`
- `docs/WORKLOG.md`
- `docs/PACKAGING_STATUS.md`

## exact validation commands to run next
```bash
cd /mnt/data/upgrade_base/service && pytest -q
cd /mnt/data/upgrade_base && python scripts/validate_package.py
cd /mnt/data/upgrade_base && python scripts/import_order_check.py
cd /mnt/data/upgrade_base && bash scripts/smoke_test.sh
cd /mnt/data/upgrade_base && SMOKE_SCOPE=tenant_context bash scripts/smoke_test.sh
cd /mnt/data/upgrade_base && SMOKE_SCOPE=tenant_enforcement bash scripts/smoke_test.sh
cd /mnt/data/upgrade_base && SMOKE_SCOPE=tenant_row_isolation bash scripts/smoke_test.sh
cd /mnt/data/upgrade_base && SMOKE_SCOPE=tenant_query_scope bash scripts/smoke_test.sh
cd /mnt/data/upgrade_base && SMOKE_SCOPE=tenant_query_coverage bash scripts/smoke_test.sh
cd /mnt/data/upgrade_base && SMOKE_SCOPE=release_channels bash scripts/smoke_test.sh
cd /mnt/data/upgrade_base && SMOKE_SCOPE=release_channel_execution bash scripts/smoke_test.sh
# next live-stack step
cd /mnt/data/upgrade_base && APP_BASE_URL=http://localhost:8080 python scripts/build_tenant_context_report.py --remote --out docs/generated_tenant_context_report.json
cd /mnt/data/upgrade_base && APP_BASE_URL=http://localhost:8080 python scripts/build_tenant_enforcement_report.py --remote --out docs/generated_tenant_enforcement_report.json
cd /mnt/data/upgrade_base && APP_BASE_URL=http://localhost:8080 python scripts/build_tenant_row_isolation_report.py --remote --out docs/generated_tenant_row_isolation_report.json
cd /mnt/data/upgrade_base && APP_BASE_URL=http://localhost:8080 python scripts/build_tenant_query_scope_report.py --remote --out docs/generated_tenant_query_scope_report.json
cd /mnt/data/upgrade_base && APP_BASE_URL=http://localhost:8080 python scripts/build_tenant_query_coverage_report.py --remote --out docs/generated_tenant_query_coverage_report.json
cd /mnt/data/upgrade_base && APP_BASE_URL=http://localhost:8080 python scripts/build_release_channel_report.py --remote --persist --out docs/generated_release_channel_report.json
cd /mnt/data/upgrade_base && APP_BASE_URL=http://localhost:8080 python scripts/build_release_channel_execution_report.py --remote --persist --out docs/generated_release_channel_execution_report.json
cd /mnt/data/upgrade_base && APP_BASE_URL=http://localhost:8080 DATABASE_URL=postgresql://postgres:postgres@localhost:5432/control_plane SMOKE_SCOPE=persistence bash scripts/smoke_test.sh
```

## latest local validation status
- `cd service && pytest -q` => 95 passed.
- `python scripts/validate_package.py` => ok.
- `python scripts/import_order_check.py` => ok.
- `bash scripts/smoke_test.sh` => ok.
- `SMOKE_SCOPE=tenant_context|tenant_enforcement|tenant_row_isolation|tenant_query_scope|tenant_query_coverage|release_channels|release_channel_execution bash scripts/smoke_test.sh` => ok.

## known blockers
- This execution environment still does not provide Docker or a live PostgreSQL instance, so DB-backed migration verification remains external.
- NotebookLM remains enterprise-assumption only; Canvas remains Canvas LMS assumption.
- Overleaf, VS Code, and Antigravity remain honest bridge patterns rather than claimed live remote APIs.

## assumptions made
- Auth remains permissive by default locally so the existing package and tests are not broken; enable strict enforcement with `AUTH_REQUIRED=true`.
- Published workflow versions remain immutable; rollback creates a new version instead of mutating historical published state.
- AI routing defaults to the seeded local Ollama models/prompts when the DB tables are unavailable or empty.
- Redis remains optional and may safely fall back to DB; runtime reports both requested and active backend names.
- Failure-isolation defaults are conservative and additive; DB policy overrides can be applied per connector or workflow without removing the built-in defaults.
- Lifecycle cleanup is batch-based and dry-run friendly by design; DLQ archival is only destructive when `dry_run=false`.
- Release manifests intentionally exclude self-referential generated release JSON outputs and rollback ZIP artifacts so checksum validation stays stable.
- Release-channel execution remains honest: unsupported channels still generate operator-facing handoff artifacts or previews instead of fake remote publication success states.
- Tenant hardening defaults remain additive: strict tenant enforcement is controlled by environment flags and is not forced on existing single-tenant deployments.
- Tenant route policy defaults are conservative: `/secrets/` stays membership-bound by default while admin overrides remain available for less sensitive route groups unless a stricter tenant policy says otherwise.
- Publication bundles may still be generated when preflight or checksum validation is blocked; they are marked `publication_status=blocked` and should not be promoted until the blocking checks pass.
- Tenant row isolation defaults are conservative and additive: only explicitly strict table policies or `STRICT_TENANT_ROW_ISOLATION=true` should hard-deny cross-tenant row access, while local audit/report tooling remains available before a stricter rollout.
- Tenant query-scope filtering now covers high-risk release/publication, admin queue/jobs/workflows/connectors, job-status, connector health/metrics, RAG governance, lifecycle-admin, tenant-admin, and AI registry read paths first; continue expanding it before claiming full SQL-style tenant isolation across every read/query path.

## recommended prompt for the next continuation run
Continue from `docs/RESUME_FROM_HERE.md` and the latest packaged ZIP. First verify migrations 007 through 021 plus auth/secrets/admin/workflow-version/queue-runtime/AI-RAG/failure-isolation/release-engineering/lifecycle/tenant/tenant-enforcement/tenant-row-isolation/tenant-query-scope/tenant-query-coverage/release-publication/release-channel/release-channel-execution endpoints against a real deployed service, then implement the next enterprise slice without breaking existing connector continuity: reconcile write-time tenant IDs to the resolved request-context tenant across more POST/update flows and continue pushing tenant-aware filtering deeper into SQL-backed queries.

SAFE TO CONTINUE FROM THIS POINT
