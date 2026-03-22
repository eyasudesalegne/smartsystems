# IMPLEMENTATION STATUS MATRIX

| service_name | status | integration_mode | validation_state | notes |
|---|---|---|---|---|
| mlflow | live_api | rest_api | tested_unit | bearer-or-basic auth path implemented; normalized experiment/run outputs and registry seed/sync available |
| azure_ml | live_api | rest_api | tested_unit | supports supplied bearer token or client-credentials token minting |
| drawio | placeholder_bridge | file_bridge | tested_execute | local XML artifact generation plus normalized artifact/embed payloads validated |
| figma | live_api | rest_api | package_present | live metadata pattern with PAT placeholders; normalized file/node/image summaries implemented |
| mermaid | partial_api | local_bridge | tested_execute | local artifact generation and normalized local-fallback outputs validated; optional render-service bridge remains |
| canvas | live_api | rest_api | package_present | Canvas LMS assumption; normalized course/module summaries implemented |
| kaggle | partial_api | rest_api | package_present | metadata/list operations only; normalized dataset/file summaries implemented |
| notebooklm | partial_api | rest_api | package_present | enterprise notebook-management assumption only |
| google_drive | live_api | rest_api | tested_unit | supports supplied access token or refresh-token exchange; normalized file/export outputs and persistence verification script ready |
| overleaf | manual_export_import | manual_bridge | tested_execute | bundle/export-import bridge with normalized bundle/open payload outputs |
| pubmed | live_api | rest_api | tested_unit | optional email/api_key query-param injection plus normalized search/summary/abstract outputs implemented |
| arxiv | live_api | rest_api | tested_unit | live search/fetch pattern present with Atom-feed normalization |
| antigravity | placeholder_bridge | local_bridge | tested_execute | local handoff workspace bundle now returns normalized artifact metadata |
| vscode | placeholder_bridge | local_bridge | tested_execute | local workspace/task bundle bridge with normalized artifact metadata |

Status vocabulary in this repo:
- not_started
- in_progress
- partial_api
- live_api
- placeholder_bridge
- validated
- blocked


Operational note: registry sync endpoint, connector preflight endpoint, and seed migration are now present. Run the preflight report before the next live-stack persistence verification so you know which connectors are genuinely ready for end-to-end checks.


Operational note: workflow coverage can now be audited through `GET /connectors/workflow-manifest`, `scripts/build_connector_workflow_manifest.py`, and `docs/generated_connector_workflow_manifest.json`. Use that alongside preflight so you know both which connectors are configured and which operations already have packaged workflow JSON.


Operational note: combined readiness can now be audited through `POST /connectors/readiness-report`, `scripts/build_connector_readiness_report.py`, `docs/generated_connector_readiness_report.json`, and `n8n/import/wf_connector_readiness_report.json`. Use that output to prioritize which connectors should import an existing workflow versus go through `/connectors/workflow-draft`.


Operational note: combined rollout sequencing can now be audited through `POST /connectors/deployment-plan`, `scripts/build_connector_deployment_plan.py`, `docs/generated_connector_deployment_plan.json`, and `n8n/import/wf_connector_deployment_plan.json`. Use it after readiness so you know the exact order to fill credentials, import workflows, draft gaps, review bridge connectors, and smoke-test what is ready.




Operational note: connector persistence state can now be audited through `POST /connectors/persistence-report`, `scripts/build_connector_persistence_report.py`, `docs/generated_connector_persistence_report.json`, and `n8n/import/wf_connector_persistence_report.json`. Use it before or after `SMOKE_SCOPE=persistence` to confirm whether the DB tables exist and which ones still need traffic.

Supplemental package surfaces: preflight, workflow-manifest, readiness-report, deployment-plan, rollout-bundle, and persistence-report are implemented and locally validated.


## cross-service operator reports
- credential matrix report: validated local package artifact available via endpoint/script/workflow.


## Enterprise control-plane layer
- auth_rbac: in_progress
- secrets_management: partial_api
- observability_json_metrics: partial_api
- idempotency_guard: in_progress
- workflow_versioning: partial_api
- admin_visibility: partial_api
- queue_pluggability: partial_api
- rag_governance_tables: partial_api

- workflow_version_events: partial_api (history, rollback, promotion audit events, and admin summary are implemented; live DB verification remains pending).

- ai_routing_prompt_registry: partial_api
- rag_governance_runtime: partial_api

- failure_isolation_controls: partial_api (connector runtime policies, circuit state, rate-limit enforcement, timeout caps, workflow execution-cap guard, and operator reports are implemented and locally validated; live DB-backed verification remains pending).
- workflow_execution_caps: partial_api (policy endpoint + guard endpoint + publishbundle enforcement are implemented and locally validated).


Release engineering status: versioned release manifest, checksum validation, rollback bundle generation, release preflight validation, and staged publication bundle automation are now implemented locally and validated through dedicated smoke scopes.
- data_lifecycle_management: partial_api (retention policies, lifecycle reports, batch cleanup, DLQ archival, lifecycle runs, scripts/workflows, and smoke scopes are implemented and locally validated; live DB-backed verification remains pending).

- multi_tenant_preparation: partial_api (tenant memberships, tenant settings, tenant context resolution/events, route-policy enforcement, row-policy enforcement, access-audit logging, scripts/workflows, and smoke scopes are implemented and locally validated; full SQL row-level isolation across every query path still remains pending).

Tenant route enforcement report: `POST /tenants/enforcement-report`, `scripts/build_tenant_enforcement_report.py`, `docs/generated_tenant_enforcement_report.json`, and `n8n/import/wf_tenant_enforcement_audit.json` now show the matched route policy, allow/deny decision, and next actions before strict tenant enforcement is enabled live.

- tenant_row_isolation: partial_api (per-table row policies, audit logging, middleware-backed route/table mapping, admin visibility, scripts/workflows, and smoke coverage are implemented and locally validated; full row-level SQL enforcement across every query path still remains pending).

- release_channel_automation: partial_api (channel config, readiness planning, execution dry-runs, file-drop/manual handoff flows, admin visibility, workflows, reports, and smoke coverage are implemented locally and validated; unsupported remote publication APIs remain intentionally plan-first instead of fake live pushes).

- tenant_query_scope: validated (query-time row scope reporting and filtered release/publication list paths).

| tenant_query_scope | validated | Query-time tenant row scoping/reporting is wired for release/publication read paths and expanded request-context direct reads with audit support. |


| capability | status | notes |
|---|---|---|
| tenant query coverage | validated | seeded coverage targets plus reporting now cover high-risk admin, AI, release, job-status, connector health/metrics, RAG governance, lifecycle-admin, and tenant-admin read paths; still not full SQL RLS everywhere |
