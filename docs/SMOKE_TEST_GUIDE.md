# SMOKE TEST GUIDE

## package-level checks
```bash
cd /mnt/data/upgrade_base/service && pytest -q
cd /mnt/data/upgrade_base && python scripts/validate_package.py
cd /mnt/data/upgrade_base && python scripts/import_order_check.py
```

## connector-only smoke path
This checkpoint now includes a connector-only smoke path that does **not** require a live Postgres + Ollama stack.

```bash
cd /mnt/data/upgrade_base && bash scripts/smoke_test.sh
# or explicitly
cd /mnt/data/upgrade_base && SMOKE_SCOPE=connectors bash scripts/smoke_test.sh
```

That path exercises:
- connector catalog
- connector prepare
- workflow draft generation
- dry-run smoke-test
- live local-bridge execution for draw.io and Mermaid


## connector preflight path
Run this before the next real-stack validation so you know which connectors are configured and live-ready:

```bash
cd /mnt/data/upgrade_base && SMOKE_SCOPE=preflight bash scripts/smoke_test.sh
# or against a deployed service
cd /mnt/data/upgrade_base && APP_BASE_URL=http://localhost:8080 python scripts/connector_preflight_report.py --remote --persist
```

This path calls or computes:
- `/connectors/preflight` when a live service is available
- local spec/runtime validation fallback when no live service is available
- `docs/generated_connector_preflight_report.json` output for handoff and review

Use the report to decide which connectors are ready for end-to-end checks before running `SMOKE_SCOPE=persistence`.


## workflow manifest path
Run this when you want a repo-level map of connector workflow coverage before import or authoring work:

```bash
cd /mnt/data/upgrade_base && SMOKE_SCOPE=manifest bash scripts/smoke_test.sh
# or generate directly
cd /mnt/data/upgrade_base && python scripts/build_connector_workflow_manifest.py --out docs/generated_connector_workflow_manifest.json
```

This path produces:
- `docs/generated_connector_workflow_manifest.json`
- per-service `packaged_operations` vs `unpackaged_operations`
- `recommended_import_workflow` and `recommended_draft_operation_id` hints for each connector

Use it with the preflight report: preflight tells you which connectors are configured, while the workflow manifest tells you which operations already have importable JSON coverage in the package.

## connector readiness report path
Run this when you want a single report that merges config readiness with workflow coverage and gives a recommended next action per connector:

```bash
cd /mnt/data/upgrade_base && SMOKE_SCOPE=readiness bash scripts/smoke_test.sh
# or generate directly
cd /mnt/data/upgrade_base && python scripts/build_connector_readiness_report.py --out docs/generated_connector_readiness_report.json
```

This path produces:
- `docs/generated_connector_readiness_report.json`
- per-service `recommended_action` values such as `import_packaged_workflow`, `fill_credentials_then_import`, or `use_workflow_draft`
- packaged coverage percentages and import-vs-draft guidance in one payload

Use it after preflight and workflow manifest if you want a condensed machine-readable queue of the next operator actions.

## persistence verification path
When the service and database are both live, run the persistence-focused check to confirm database writes land in the new connector tables:

```bash
cd /mnt/data/upgrade_base && APP_BASE_URL=http://localhost:8080 DATABASE_URL=postgresql://postgres:postgres@localhost:5432/control_plane SMOKE_SCOPE=persistence bash scripts/smoke_test.sh
```

That path calls:
- `/connectors/sync-registry`
- `/connectors/validate-config`
- `/connectors/workflow-draft`
- `/connectors/smoke-test`
- optional direct PostgreSQL row-count verification via `scripts/verify_connector_persistence.py`

## full live-core smoke path
When the full service stack is running on `APP_BASE_URL`, you can execute the broader check:

```bash
cd /mnt/data/upgrade_base && APP_BASE_URL=http://localhost:8080 SMOKE_SCOPE=core bash scripts/smoke_test.sh
```

This path probes:
- `/health`
- `/ready`
- `/metrics`
- `/ingest/note`
- `/retrieve/query`
- connector catalog and workflow-draft routes

## direct endpoint checks
```bash
curl -s http://localhost:8080/connectors/catalog | jq .
curl -s -X POST http://localhost:8080/connectors/validate-config -H 'Content-Type: application/json' -d '{"service_name":"google_drive"}' | jq .
curl -s -X POST http://localhost:8080/connectors/smoke-test -H 'Content-Type: application/json' -d '{"service_name":"drawio","operation_id":"build_xml_artifact","dry_run":true}' | jq .
```


Additional note: the connector-only smoke path now asserts normalized outputs for local bridge connectors such as draw.io and Mermaid, not just HTTP-style connectors.


Additional connector planning scopes:
- `SMOKE_SCOPE=preflight` generates `docs/generated_connector_preflight_report.json`.
- `SMOKE_SCOPE=manifest` generates `docs/generated_connector_workflow_manifest.json`.
- `SMOKE_SCOPE=readiness` generates `docs/generated_connector_readiness_report.json`.
- `SMOKE_SCOPE=deployment` generates `docs/generated_connector_deployment_plan.json`.


## rollout bundle
- Endpoint/script/workflow support exists for a combined connector rollout bundle via `/connectors/rollout-bundle`, `scripts/build_connector_rollout_bundle.py`, and `n8n/import/wf_connector_rollout_bundle.json`.


## persistence report
- Endpoint/script/workflow support exists for a connector persistence report via `/connectors/persistence-report`, `scripts/build_connector_persistence_report.py`, and `n8n/import/wf_connector_persistence_report.json`. Use it to verify whether the connector persistence tables exist, whether they have rows yet, and what to do next before full live-stack verification.


## connector credential matrix
- Endpoint/script/workflow: `/connectors/credential-matrix`, `scripts/build_connector_credential_matrix.py`, `n8n/import/wf_connector_credential_matrix.json`.
- Purpose: build a machine-readable map of connector environment variables across services so operators can fill shared secrets before rollout.


## Enterprise spot checks
1. Request a token: `POST /auth/token`.
2. Repeat `GET /admin/system` with and without the bearer token when `AUTH_REQUIRED=true`.
3. Store a secret with `/secrets/set` and verify `/secrets/list` returns metadata only while `/secrets/get` redacts by default.
4. Scrape `/metrics?format=prometheus` and confirm queue/connectors gauges render.
5. Hit `/connectors/pubmed/health` and `/connectors/pubmed/metrics` after a smoke execution to confirm runtime counters populate.


## workflow version smoke scope
Run `SMOKE_SCOPE=workflow_versions bash scripts/smoke_test.sh` to locally validate workflow version create/promote/history/rollback behavior without requiring a live database. This smoke path uses the app surface and simulated persistence hooks to confirm endpoint wiring and response shape.


## queue runtime smoke scope
Run this local scope after queue/backend changes so the package confirms runtime settings and worker-state reporting still line up with the API surface:

```bash
cd /mnt/data/upgrade_base && SMOKE_SCOPE=queue_runtime bash scripts/smoke_test.sh
# or generate directly
cd /mnt/data/upgrade_base && python scripts/check_queue_runtime.py --out docs/generated_queue_runtime_report.json
```

This path validates:
- `GET /admin/queue` response shape
- requested vs active queue backend reporting
- worker concurrency and retry backoff fields
- presence of a machine-readable queue runtime report at `docs/generated_queue_runtime_report.json`


## AI control smoke scope
```bash
cd /mnt/data/upgrade_base && SMOKE_SCOPE=ai_control bash scripts/smoke_test.sh
# or generate directly
cd /mnt/data/upgrade_base && python scripts/build_ai_control_report.py --out docs/generated_ai_control_report.json
```

This path validates the local or deployed AI control surface by generating a machine-readable report from:
- `GET /ai/models`
- `GET /ai/prompts`
- `POST /ai/route`

## RAG governance smoke scope
```bash
cd /mnt/data/upgrade_base && SMOKE_SCOPE=rag_governance bash scripts/smoke_test.sh
# or generate directly
cd /mnt/data/upgrade_base && python scripts/build_rag_governance_report.py --out docs/generated_rag_governance_report.json
```

This path validates the governed document ingestion/reporting surface by generating `docs/generated_rag_governance_report.json`.
## failure isolation smoke scope
```bash
cd /mnt/data/upgrade_base && SMOKE_SCOPE=failure_isolation bash scripts/smoke_test.sh
# or generate directly
cd /mnt/data/upgrade_base && python scripts/build_connector_failure_isolation_report.py --out docs/generated_connector_failure_isolation_report.json
```

This path validates the additive connector failure-isolation surface by generating a report from:
- `POST /connectors/failure-isolation-report` when a live service is available
- local policy/state evaluation fallback when no live service is available

## workflow cap smoke scope
```bash
cd /mnt/data/upgrade_base && SMOKE_SCOPE=workflow_caps bash scripts/smoke_test.sh
# or generate directly
cd /mnt/data/upgrade_base && python scripts/check_workflow_execution_caps.py --out docs/generated_workflow_execution_cap_report.json
```

This path validates the workflow execution-cap guard endpoint and produces `docs/generated_workflow_execution_cap_report.json`.


## release manifest path
```bash
cd /mnt/data/upgrade_base && SMOKE_SCOPE=release_manifest bash scripts/smoke_test.sh
```
Generates `docs/generated_release_manifest.json`.

## release checksum validation path
```bash
cd /mnt/data/upgrade_base && SMOKE_SCOPE=release_checksums bash scripts/smoke_test.sh
```
Generates `docs/generated_release_checksum_validation.json`.

## release rollback bundle path
```bash
cd /mnt/data/upgrade_base && SMOKE_SCOPE=release_rollback bash scripts/smoke_test.sh
```
Generates `docs/generated_release_rollback_package.json` and `artifacts/release_rollback_bundle_default.zip`.

## release preflight path
```bash
cd /mnt/data/upgrade_base && SMOKE_SCOPE=release_preflight bash scripts/smoke_test.sh
```
Generates `docs/generated_release_preflight_report.json`.

## data lifecycle report scope
```bash
cd /mnt/data/upgrade_base && SMOKE_SCOPE=lifecycle_report bash scripts/smoke_test.sh
# or generate directly
cd /mnt/data/upgrade_base && python scripts/build_data_lifecycle_report.py --out docs/generated_data_lifecycle_report.json
```
Generates `docs/generated_data_lifecycle_report.json`.

## data lifecycle cleanup scope
```bash
cd /mnt/data/upgrade_base && SMOKE_SCOPE=lifecycle_cleanup bash scripts/smoke_test.sh
# or generate directly
cd /mnt/data/upgrade_base && python scripts/run_data_lifecycle_cleanup.py --dry-run --out docs/generated_data_lifecycle_cleanup.json
```
Generates `docs/generated_data_lifecycle_cleanup.json`.


## Tenant hardening
- local package check: `SMOKE_SCOPE=tenant_context bash scripts/smoke_test.sh`
- generated artifact: `docs/generated_tenant_context_report.json`

## tenant enforcement
- `SMOKE_SCOPE=tenant_enforcement bash scripts/smoke_test.sh`
- Writes `docs/generated_tenant_enforcement_report.json` from the local package and confirms the tenant route policy layer is present before stricter enforcement is enabled on a live stack.



## release publication path
```bash
cd /mnt/data/upgrade_base && SMOKE_SCOPE=release_publication bash scripts/smoke_test.sh
```
Generates `docs/generated_release_publication_report.json` and `artifacts/release_publication_bundle_default.zip`.


## tenant_row_isolation
Runs `scripts/build_tenant_row_isolation_report.py` and writes `docs/generated_tenant_row_isolation_report.json`. Use it before enabling `STRICT_TENANT_ROW_ISOLATION=true` so you know which core tables will deny cross-tenant access.


- `SMOKE_SCOPE=release_channels` builds a machine-readable release channel plan and refreshes `docs/generated_release_channel_report.json`.


## Release channel execution smoke scope
- `SMOKE_SCOPE=release_channel_execution bash scripts/smoke_test.sh`
- Generates `docs/generated_release_channel_execution_report.json` via a safe dry-run release-channel execution path.
- Confirms the package can produce operator-facing handoff artifacts and execution records without claiming unsupported remote publication delivery.

- `SMOKE_SCOPE=tenant_query_scope` regenerates `docs/generated_tenant_query_scope_report.json` so you can verify query-time row scoping before enabling stricter tenant isolation across more read paths.


- `SMOKE_SCOPE=tenant_query_coverage` refreshes `docs/generated_tenant_query_coverage_report.json` and verifies the query-coverage slice. The seeded coverage set now includes direct job-status, connector health/metrics, RAG governance, lifecycle-admin, and tenant-admin read paths in addition to the earlier release/admin/AI paths.
