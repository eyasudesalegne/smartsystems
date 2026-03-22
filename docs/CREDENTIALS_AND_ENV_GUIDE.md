# CREDENTIALS AND ENV GUIDE

Use `deploy/.env.example` as the canonical placeholder source.

## live connectors
- `MLFLOW_TRACKING_URI`
- `MLFLOW_USERNAME`
- `MLFLOW_PASSWORD`
- `MLFLOW_TOKEN`
- `AZURE_ML_BASE_URL`
- `AZURE_ML_BEARER_TOKEN`
- `AZURE_ML_TENANT_ID`
- `AZURE_ML_CLIENT_ID`
- `AZURE_ML_CLIENT_SECRET`
- `AZURE_ML_SUBSCRIPTION_ID`
- `AZURE_ML_RESOURCE_GROUP`
- `AZURE_ML_WORKSPACE`
- `FIGMA_BASE_URL`
- `FIGMA_ACCESS_TOKEN`
- `GOOGLE_DRIVE_BASE_URL`
- `GOOGLE_DRIVE_ACCESS_TOKEN`
- `GOOGLE_DRIVE_CLIENT_ID`
- `GOOGLE_DRIVE_CLIENT_SECRET`
- `GOOGLE_DRIVE_REFRESH_TOKEN`
- `CANVAS_BASE_URL`
- `CANVAS_ACCESS_TOKEN`
- `KAGGLE_BASE_URL`
- `KAGGLE_USERNAME`
- `KAGGLE_KEY`
- `NOTEBOOKLM_BASE_URL`
- `NOTEBOOKLM_ACCESS_TOKEN`

## optional / bridge-oriented
- `PUBMED_BASE_URL`
- `PUBMED_EMAIL`
- `PUBMED_API_KEY`
- `ARXIV_BASE_URL`
- `DRAWIO_BASE_URL`
- `DRAWIO_ACCESS_TOKEN`
- `MERMAID_RENDER_BASE_URL`
- `OVERLEAF_BASE_URL`
- `OVERLEAF_ACCESS_TOKEN`
- `ANTIGRAVITY_BASE_URL`
- `ANTIGRAVITY_ACCESS_TOKEN`
- `VSCODE_BRIDGE_MODE`
- `VSCODE_BRIDGE_URL`
- `VSCODE_ACCESS_TOKEN`

## how validation now behaves
- `google_drive` is considered configured if either:
  - `GOOGLE_DRIVE_ACCESS_TOKEN` is present, or
  - `GOOGLE_DRIVE_CLIENT_ID` + `GOOGLE_DRIVE_CLIENT_SECRET` + `GOOGLE_DRIVE_REFRESH_TOKEN` are present
- `azure_ml` is considered configured if either:
  - `AZURE_ML_BEARER_TOKEN` is present together with `AZURE_ML_BASE_URL`, or
  - `AZURE_ML_TENANT_ID` + `AZURE_ML_CLIENT_ID` + `AZURE_ML_CLIENT_SECRET` are present together with `AZURE_ML_BASE_URL`
- `mlflow` is considered configured with `MLFLOW_TRACKING_URI`; auth is optional unless your MLflow deployment requires it.
- `pubmed` works without credentials, but `PUBMED_EMAIL` and `PUBMED_API_KEY` improve compliance and rate-limit behavior.

## execution guidance
- Fill placeholders in `deploy/.env.example` or export them in the shell/environment used by the FastAPI companion service.
- n8n workflows should keep credentials out of workflow JSON and call the backend bridge endpoints instead.


## connector credential matrix
- Endpoint/script/workflow: `/connectors/credential-matrix`, `scripts/build_connector_credential_matrix.py`, `n8n/import/wf_connector_credential_matrix.json`.
- Purpose: build a machine-readable map of connector environment variables across services so operators can fill shared secrets before rollout.


## Enterprise auth and secret variables
- `AUTH_REQUIRED=true` enables JWT auth enforcement for API requests.
- `JWT_SECRET` signs HS256 access tokens.
- `JWT_ISSUER` sets the JWT issuer claim.
- `JWT_EXPIRY_SECONDS` controls token TTL.
- `AUTH_BOOTSTRAP_USERS_RAW` defines bootstrap users as `username:role` pairs.
- `SECRET_ENCRYPTION_KEY` supplies the Fernet-compatible secret-encryption seed. If omitted, the package derives one from `JWT_SECRET`.
- `ENABLE_IDEMPOTENCY=true` enables POST idempotency caching for requests carrying `X-Idempotency-Key`.
- `CORRELATION_HEADER_NAME` controls the request correlation header.
- You may reference stored secrets from env variables by using values like `secret:FIGMA_ACCESS_TOKEN`.

## lifecycle environment variables
- `LIFECYCLE_DEFAULT_RETAIN_DAYS` sets the default retention window used when policy rows have not yet been overridden.
- `LIFECYCLE_CLEANUP_BATCH_SIZE` sets the default batch size for cleanup runs.
- `LIFECYCLE_ARCHIVE_DEAD_LETTERS` controls whether default DLQ policy seeds with archive-before-delete enabled.


## Tenant environment controls
- `TENANT_DEFAULT_ID`
- `STRICT_TENANT_ENFORCEMENT`
- `TENANT_HEADER_NAME`
- `TENANT_ALLOW_ADMIN_OVERRIDE`


## release channel secrets
Webhook release channels can reference a secret name through `auth_secret_ref`. Store the secret first through `/secrets/set`, then point the channel at that secret reference so reports and plans can distinguish configured vs missing channel auth.


## Release channel execution environment
- `RELEASE_CHANNEL_EXECUTION_DIR` controls where dry-run/manual execution artifacts are written.
- `RELEASE_CHANNEL_EXECUTE_WEBHOOKS` defaults to `false` and should remain disabled until you explicitly want live webhook delivery for supported channel endpoints.

- `STRICT_TENANT_ROW_ISOLATION=true` now also affects query-time row filtering on the scoped release/publication read paths.
