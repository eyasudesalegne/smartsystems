# Multi-tenancy guide

This package now includes a tenant-hardening preparation layer on top of the earlier tenant-aware schema.

## What is implemented
- `tenant_memberships`, `tenant_settings`, and `tenant_context_events` via migration `014_tenant_hardening.sql`
- request tenant resolution from header, query string, or JSON body
- optional strict tenant enforcement controlled by environment flags
- admin tenant override support
- tenant context endpoint: `GET /tenants/context`
- tenant administration endpoints:
  - `POST /tenants/create`
  - `POST /tenants/membership`
  - `GET /admin/tenants`
- importable n8n workflows:
  - `wf_tenant_context_audit.json`
  - `wf_tenant_membership_upsert.json`

## Environment controls
- `TENANT_DEFAULT_ID`
- `STRICT_TENANT_ENFORCEMENT`
- `TENANT_HEADER_NAME`
- `TENANT_ALLOW_ADMIN_OVERRIDE`

## Operational model
- keep `STRICT_TENANT_ENFORCEMENT=false` while upgrading an existing single-tenant deployment
- create memberships before switching strict enforcement on
- use admin tokens for controlled cross-tenant audits when `TENANT_ALLOW_ADMIN_OVERRIDE=true`
- rely on `GET /tenants/context` and `docs/generated_tenant_context_report.json` before enabling stricter tenant policies

## Limits
This package still prepares multi-tenancy more than it fully enforces it. It does not claim full row-level security or complete per-tenant secret/connector isolation verification in this container session.

## tenant route enforcement
- Route policies are additive and stored in `tenant_route_policies`. They let you tighten cross-tenant behavior per route prefix without breaking single-tenant deployments.
- The package seeds sensible defaults for `/secrets/`, `/tenants/`, `/admin/`, `/release/`, `/connectors/`, `/jobs/`, and `/workflows/`.
- Use `POST /tenants/policy` or `n8n/import/wf_tenant_policy_upsert.json` to stage stricter behavior. Use `POST /tenants/enforcement-report` or `wf_tenant_enforcement_audit.json` before turning on strict tenant enforcement globally.
- All audited allow/deny decisions are recorded in `tenant_access_audit` when `TENANT_POLICY_AUDIT_ENABLED=true`.



## Row-level tenant isolation
This package now supports additive row-level isolation policies per core table through `POST /tenants/row-policy` and `POST /tenants/row-isolation-report`. Keep `STRICT_TENANT_ROW_ISOLATION=false` while auditing; then move selected tables or the whole package to stricter enforcement once memberships and overrides are correct.

## Query-time row scope
The package now includes query-time tenant row scoping for high-risk release/publication list paths. Use `POST /tenants/query-scope-report` or `wf_tenant_query_scope_audit` to see the visible tenant set and SQL-style filter preview before hardening additional query paths.


## Tenant query coverage
The package now tracks seeded high-risk read paths such as `/admin/jobs`, `/admin/queue`, `/admin/workflows`, `/jobs/status/{job_id}`, `/connectors/{service_name}/health`, `/connectors/{service_name}/metrics`, `/rag/governance`, `/admin/lifecycle`, `/admin/tenants`, `/ai/models`, and `/ai/prompts` in addition to the release/publication surfaces. Use `POST /tenants/query-coverage-report` or `scripts/build_tenant_query_coverage_report.py` to see which routes are query-scoped today and which targets still need stricter SQL-level tenant isolation.

Direct read endpoints that previously trusted only query parameters now honor the request-context tenant first, so authenticated tenant overrides and header-based scoping apply consistently to connector health/metrics, job status, RAG governance, lifecycle admin summaries, and tenant admin summaries.
