# CODEX WORKFLOW AUTHORING GUIDE

1. Read `docs/RESUME_FROM_HERE.md` first.
2. Prefer backend connector bridge workflows over direct external HTTP nodes when auth or placeholder behavior is complex.
3. Keep connector metadata in `connectors/specs/` and runtime logic in `service/app/adapters/`.
4. Do not mark a connector as live if the adapter is only generating artifacts.
5. Update `WORKLOG.md`, `IMPLEMENTATION_STATUS_MATRIX.md`, `PACKAGING_STATUS.md`, and `RESUME_FROM_HERE.md` at every checkpoint.


## Use the workflow manifest before generating more JSON
Before asking Codex/GPT to generate a new workflow, inspect `docs/generated_connector_workflow_manifest.json` or call `GET /connectors/workflow-manifest`. That tells you whether the operation already has a packaged importable workflow, whether only a generic draft path exists, and which file is the best starting point to clone instead of regenerating from scratch.

## Use the readiness report to prioritize work
Inspect `docs/generated_connector_readiness_report.json` or call `POST /connectors/readiness-report` before generating more connector workflows. It tells you which services already have importable workflow coverage, which still need credentials before import, and which ones should go through `/connectors/workflow-draft` instead of another checked-in JSON file.


Before generating new connector workflows, check the readiness and deployment-plan reports first. They tell you which services already have packaged workflow coverage, which ones only need credentials, and which ones should go through `/connectors/workflow-draft` next.


## rollout bundle
- Endpoint/script/workflow support exists for a combined connector rollout bundle via `/connectors/rollout-bundle`, `scripts/build_connector_rollout_bundle.py`, and `n8n/import/wf_connector_rollout_bundle.json`.


## persistence report
- Endpoint/script/workflow support exists for a connector persistence report via `/connectors/persistence-report`, `scripts/build_connector_persistence_report.py`, and `n8n/import/wf_connector_persistence_report.json`. Use it to verify whether the connector persistence tables exist, whether they have rows yet, and what to do next before full live-stack verification.


## connector credential matrix
- Endpoint/script/workflow: `/connectors/credential-matrix`, `scripts/build_connector_credential_matrix.py`, `n8n/import/wf_connector_credential_matrix.json`.
- Purpose: build a machine-readable map of connector environment variables across services so operators can fill shared secrets before rollout.


## New enterprise workflow templates
- `wf_ai_task_router.json` demonstrates how to call `/ai/route` before invoking generation or downstream automation.
- `wf_rag_document_ingest_governed.json` demonstrates governed document ingestion into the control plane before retrieval or AI summarization steps.


## release channel workflow patterns
When adding new release-channel workflows, keep them backend-bridge based: upsert channel config through `/release/channel`, audit channel readiness through `/release/channel-plan`, and avoid claiming direct publication to third-party destinations unless the backend actually implements it.


## Release-channel execution workflow pattern
When extending release automation, keep the workflow split explicit:
1. configuration/upsert workflow
2. planning/audit workflow
3. execution workflow
4. execution audit workflow

Do not collapse manual bridges into fake "publish" nodes. Preserve dry-run and artifact-generation behavior for unsupported or operator-gated channels.

- When adding new list/report endpoints over tenant-scoped tables, use the tenant query-scope helper so request-context tenant filtering is enforced even when fallback caches or local previews are involved.
