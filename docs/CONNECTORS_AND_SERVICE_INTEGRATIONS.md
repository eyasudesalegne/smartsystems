# CONNECTORS AND SERVICE INTEGRATIONS

This package keeps the existing hybrid control-plane architecture and extends it with a spec-driven connector layer that is explicit about what is live, what is partial, and what is a bridge.

## runtime model
- Connector metadata lives in `connectors/specs/*.json`.
- Runtime adapter logic lives in `service/app/adapters/`.
- FastAPI exposes:
  - `GET /connectors/catalog`
  - `GET /connectors/{service_name}`
  - `POST /connectors/prepare`
  - `POST /connectors/workflow-draft`
  - `GET /connectors/workflow-manifest`
  - `POST /connectors/execute-live`
  - `POST /connectors/validate-config`
  - `POST /connectors/smoke-test`
  - `POST /connectors/readiness-report`
  - `POST /connectors/sync-registry`
- n8n workflows call the FastAPI bridge so credentials stay centralized and placeholder-friendly.

## execution and persistence
This checkpoint now also persists connector-adjacent runtime metadata when the connector tables exist in PostgreSQL:
- `connector_execution_log` for prepare / workflow-draft / validate / smoke / execute-live events
- `connector_credentials_meta` for per-credential validation state
- `workflow_templates` for generated workflow drafts
- `smoke_test_results` for smoke-test outcomes

These writes are fail-safe. If the tables are not present yet, connector endpoints still return normally.

## normalized connector outputs
For live and partial API connectors, `POST /connectors/execute-live` now returns three layers of output when possible:
- `data`: the raw downstream payload
- `normalized`: a service-aware compact structure for common n8n/operator use
- `summary` and `pagination`: lightweight helpers for branching, dashboards, and follow-on requests

The importable backend-bridge workflows now surface `normalized` first and keep `summary`/`pagination` available to downstream nodes. Local/manual bridge connectors now also emit the same top-level response shape (`data`, `normalized`, `summary`, `pagination`) so n8n branches do not need special-case parsing for artifact-style connectors.

## honest integration depth
### live_api
- `mlflow`: REST calls with bearer-or-basic auth support
- `azure_ml`: REST calls with supplied bearer token or client-credentials token minting
- `figma`: metadata/file inspection via personal access token
- `google_drive`: REST calls with supplied bearer token or refresh-token exchange
- `pubmed`: live E-utilities search/summary/fetch with optional email/api_key query params
- `arxiv`: live search/fetch patterns
- `canvas`: Canvas LMS assumption with bearer-token REST patterns

### partial_api
- `mermaid`: local artifact generation plus optional render-service bridge
- `kaggle`: metadata operations with documented auth expectations
- `notebooklm`: enterprise notebook-management assumptions only

### placeholder_bridge / manual_export_import
- `drawio`: local XML artifact generation and manual embed/open bridge
- `overleaf`: project bundle/export-import bridge, not fabricated project CRUD
- `vscode`: local workspace/task bundle handoff
- `antigravity`: local workspace handoff shell only

## important assumptions
- `canvas` is implemented as **Canvas LMS** because the original label was ambiguous and Canvas LMS exposes a documented API.
- `notebooklm` targets **NotebookLM Enterprise** style notebook-management endpoints rather than consumer-only UI automation.
- `overleaf` is modeled as **import/export bridge behavior**, not an undocumented general-purpose API.
- `vscode` and `antigravity` remain honest local bridges rather than remote-control fantasy integrations.

## service-specific auth notes
- **MLflow**: `MLFLOW_TRACKING_URI` is required. `MLFLOW_TOKEN` is preferred when available; `MLFLOW_USERNAME` + `MLFLOW_PASSWORD` are also supported.
- **Azure ML**: `AZURE_ML_BASE_URL` is required. Execution supports either `AZURE_ML_BEARER_TOKEN` or token minting from `AZURE_ML_TENANT_ID`, `AZURE_ML_CLIENT_ID`, and `AZURE_ML_CLIENT_SECRET`.
- **Google Drive**: execution supports either `GOOGLE_DRIVE_ACCESS_TOKEN` or refresh-token exchange using `GOOGLE_DRIVE_CLIENT_ID`, `GOOGLE_DRIVE_CLIENT_SECRET`, and `GOOGLE_DRIVE_REFRESH_TOKEN`.
- **PubMed**: `PUBMED_EMAIL` and `PUBMED_API_KEY` are optional and are automatically added as query params when present.

## n8n workflow coverage
The package includes exact importable workflow filenames requested by the brief, including catalog inspection, prepare, workflow draft, smoke test, and service example workflows in `n8n/import/`.

## registry sync and seeding
- `migrations/006_seed_connector_registry.sql` seeds `connector_registry` for the default tenant during bootstrap.
- `POST /connectors/sync-registry` re-syncs the database registry from `connectors/specs/*.json` without hand-editing SQL.
- `scripts/sync_connector_registry.py` performs the same upsert directly against PostgreSQL when you want an operator-side seed step.
- `n8n/import/wf_connector_registry_sync.json` exposes the same operation through an importable workflow bridge.


## Connector preflight before live validation
Use `POST /connectors/preflight` or `python scripts/connector_preflight_report.py` to produce a readiness report before the next live-stack run. The report merges the spec-driven catalog with runtime credential validation and marks connectors as `live_ready` only when the implementation mode and configured secrets indicate the package can attempt a real outbound call honestly.


## workflow manifest and coverage audit
Use `GET /connectors/workflow-manifest`, `python scripts/build_connector_workflow_manifest.py`, or `n8n/import/wf_connector_workflow_manifest.json` to see which connector operations already have packaged workflow JSON and which are only draftable through `/connectors/workflow-draft`. This is especially useful for services like Azure ML, Google Drive, Figma, NotebookLM, and Canvas where the package ships a few checked-in examples but leaves some secondary operations to on-demand workflow drafting.

## combined readiness report
Use `POST /connectors/readiness-report`, `python scripts/build_connector_readiness_report.py`, or `n8n/import/wf_connector_readiness_report.json` when you want configuration state and workflow coverage in one payload. The combined report adds packaged coverage percentages, recommended import/draft targets, and a `recommended_action` field so operator workflows and future Codex/GPT sessions can jump directly to the next best step per connector.


Operational planning artifacts now include `docs/generated_connector_deployment_plan.json` and `n8n/import/wf_connector_deployment_plan.json`. Use them after readiness/preflight to turn connector state into an ordered import-or-draft rollout plan.


## rollout bundle
- Endpoint/script/workflow support exists for a combined connector rollout bundle via `/connectors/rollout-bundle`, `scripts/build_connector_rollout_bundle.py`, and `n8n/import/wf_connector_rollout_bundle.json`.


## persistence report
- Endpoint/script/workflow support exists for a connector persistence report via `/connectors/persistence-report`, `scripts/build_connector_persistence_report.py`, and `n8n/import/wf_connector_persistence_report.json`. Use it to verify whether the connector persistence tables exist, whether they have rows yet, and what to do next before full live-stack verification.


## connector credential matrix
- Endpoint/script/workflow: `/connectors/credential-matrix`, `scripts/build_connector_credential_matrix.py`, `n8n/import/wf_connector_credential_matrix.json`.
- Purpose: build a machine-readable map of connector environment variables across services so operators can fill shared secrets before rollout.


## Connector runtime hardening status
- Connector execution now writes generic runtime counters into `connector_metrics` when the table exists.
- `/connectors/{service_name}/health` combines config validation with last success/failure timestamps where available.
- `/connectors/{service_name}/metrics` exposes execution, success, failure, retry, and failure-rate counters.
- Secret references can be supplied to connector env variables using `secret:NAME` values when the secrets table is available.
