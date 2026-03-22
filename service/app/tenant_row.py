from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, status

from .config import settings
from .db import execute, fetch_all
from .tenant import list_actor_tenant_memberships

DEFAULT_TENANT_ROW_POLICIES: list[dict[str, Any]] = [
    {
        'resource_table': 'secrets',
        'strict_mode': 'enforce',
        'require_tenant_match': True,
        'allow_admin_override': False,
        'allow_service_account_override': False,
        'allow_global_rows': False,
        'notes': 'Secrets remain tenant-bound and should never bleed across tenant boundaries.',
    },
    {
        'resource_table': 'connector_credentials_meta',
        'strict_mode': 'enforce',
        'require_tenant_match': True,
        'allow_admin_override': False,
        'allow_service_account_override': False,
        'allow_global_rows': False,
        'notes': 'Connector credential metadata is tenant-sensitive and should stay isolated.',
    },
    {
        'resource_table': 'tenant_memberships',
        'strict_mode': 'enforce',
        'require_tenant_match': True,
        'allow_admin_override': True,
        'allow_service_account_override': False,
        'allow_global_rows': False,
        'notes': 'Membership edits must remain tenant-scoped unless an admin override is explicitly permitted.',
    },
    {
        'resource_table': 'tenant_route_policies',
        'strict_mode': 'enforce',
        'require_tenant_match': True,
        'allow_admin_override': True,
        'allow_service_account_override': False,
        'allow_global_rows': False,
        'notes': 'Tenant route policies should be edited only in the target tenant context.',
    },
    {
        'resource_table': 'tenant_row_policies',
        'strict_mode': 'enforce',
        'require_tenant_match': True,
        'allow_admin_override': True,
        'allow_service_account_override': False,
        'allow_global_rows': False,
        'notes': 'Tenant row policies are themselves tenant-scoped security controls.',
    },
    {
        'resource_table': 'tenant_access_audit',
        'strict_mode': 'enforce',
        'require_tenant_match': True,
        'allow_admin_override': True,
        'allow_service_account_override': False,
        'allow_global_rows': False,
        'notes': 'Tenant access audit rows are scoped to the effective tenant.',
    },
    {
        'resource_table': 'tenant_row_access_audit',
        'strict_mode': 'enforce',
        'require_tenant_match': True,
        'allow_admin_override': True,
        'allow_service_account_override': False,
        'allow_global_rows': False,
        'notes': 'Row isolation audit rows are scoped to the effective tenant.',
    },
    {
        'resource_table': 'tenant_query_scope_audit',
        'strict_mode': 'enforce',
        'require_tenant_match': True,
        'allow_admin_override': True,
        'allow_service_account_override': False,
        'allow_global_rows': False,
        'notes': 'Query-scope audit rows are scoped to the effective tenant.',
    },
    {
        'resource_table': 'release_channels',
        'strict_mode': 'inherit',
        'require_tenant_match': True,
        'allow_admin_override': True,
        'allow_service_account_override': False,
        'allow_global_rows': False,
        'notes': 'Release channel configuration remains tenant-scoped by default.',
    },
    {
        'resource_table': 'release_channel_events',
        'strict_mode': 'inherit',
        'require_tenant_match': True,
        'allow_admin_override': True,
        'allow_service_account_override': False,
        'allow_global_rows': False,
        'notes': 'Release channel planning history remains tenant-scoped by default.',
    },
    {
        'resource_table': 'release_channel_executions',
        'strict_mode': 'inherit',
        'require_tenant_match': True,
        'allow_admin_override': True,
        'allow_service_account_override': False,
        'allow_global_rows': False,
        'notes': 'Release channel execution history remains tenant-scoped by default.',
    },
    {
        'resource_table': 'release_publications',
        'strict_mode': 'inherit',
        'require_tenant_match': True,
        'allow_admin_override': True,
        'allow_service_account_override': False,
        'allow_global_rows': False,
        'notes': 'Release publication history should stay tenant-scoped unless a policy explicitly allows otherwise.',
    },
    {
        'resource_table': 'release_publication_events',
        'strict_mode': 'inherit',
        'require_tenant_match': True,
        'allow_admin_override': True,
        'allow_service_account_override': False,
        'allow_global_rows': False,
        'notes': 'Publication event history follows the publication tenant scope.',
    },
    {
        'resource_table': 'release_manifests',
        'strict_mode': 'inherit',
        'require_tenant_match': True,
        'allow_admin_override': True,
        'allow_service_account_override': False,
        'allow_global_rows': False,
        'notes': 'Release manifests are tenant-scoped build artifacts.',
    },
    {
        'resource_table': 'rollback_packages',
        'strict_mode': 'inherit',
        'require_tenant_match': True,
        'allow_admin_override': True,
        'allow_service_account_override': False,
        'allow_global_rows': False,
        'notes': 'Rollback bundles stay tenant-scoped with the release they protect.',
    },
    {
        'resource_table': 'jobs',
        'strict_mode': 'inherit',
        'require_tenant_match': True,
        'allow_admin_override': True,
        'allow_service_account_override': True,
        'allow_global_rows': False,
        'notes': 'Job rows should remain tenant-scoped by default.',
    },
    {
        'resource_table': 'queue_items',
        'strict_mode': 'inherit',
        'require_tenant_match': True,
        'allow_admin_override': True,
        'allow_service_account_override': True,
        'allow_global_rows': False,
        'notes': 'Queue rows should remain tenant-scoped by default.',
    },
    {
        'resource_table': 'dead_letter_items',
        'strict_mode': 'inherit',
        'require_tenant_match': True,
        'allow_admin_override': True,
        'allow_service_account_override': True,
        'allow_global_rows': False,
        'notes': 'DLQ rows should remain tenant-scoped by default.',
    },
    {
        'resource_table': 'workflow_versions',
        'strict_mode': 'inherit',
        'require_tenant_match': True,
        'allow_admin_override': True,
        'allow_service_account_override': True,
        'allow_global_rows': False,
        'notes': 'Workflow version history is tenant-scoped by default.',
    },
    {
        'resource_table': 'connector_execution_log',
        'strict_mode': 'inherit',
        'require_tenant_match': True,
        'allow_admin_override': True,
        'allow_service_account_override': True,
        'allow_global_rows': False,
        'notes': 'Connector execution history is tenant-scoped by default.',
    },
    {
        'resource_table': 'connector_metrics',
        'strict_mode': 'inherit',
        'require_tenant_match': True,
        'allow_admin_override': True,
        'allow_service_account_override': True,
        'allow_global_rows': False,
        'notes': 'Connector runtime metrics are tenant-scoped by default.',
    },
    {
        'resource_table': 'documents',
        'strict_mode': 'inherit',
        'require_tenant_match': True,
        'allow_admin_override': True,
        'allow_service_account_override': True,
        'allow_global_rows': False,
        'notes': 'RAG documents remain tenant-scoped by default.',
    },
    {
        'resource_table': 'document_chunks',
        'strict_mode': 'inherit',
        'require_tenant_match': True,
        'allow_admin_override': True,
        'allow_service_account_override': True,
        'allow_global_rows': False,
        'notes': 'RAG chunk rows remain tenant-scoped by default.',
    },
    {
        'resource_table': 'embedding_versions',
        'strict_mode': 'inherit',
        'require_tenant_match': True,
        'allow_admin_override': True,
        'allow_service_account_override': True,
        'allow_global_rows': False,
        'notes': 'Embedding metadata remains tenant-scoped by default.',
    },
    {
        'resource_table': 'audit_logs',
        'strict_mode': 'inherit',
        'require_tenant_match': True,
        'allow_admin_override': True,
        'allow_service_account_override': False,
        'allow_global_rows': False,
        'notes': 'Audit logs should remain tenant-scoped unless an admin override is explicitly permitted.',
    },
]



DEFAULT_TENANT_QUERY_SCOPE_TARGETS: list[dict[str, Any]] = [
    {'route': '/release/publications', 'resource_table': 'release_publications', 'action': 'read', 'strict_mode': 'inherit', 'notes': 'Publication history should always be query-scoped by tenant.'},
    {'route': '/admin/releases', 'resource_table': 'release_publications', 'action': 'read', 'strict_mode': 'inherit', 'notes': 'Admin release summaries should exclude cross-tenant rows.'},
    {'route': '/release/channels', 'resource_table': 'release_channels', 'action': 'read', 'strict_mode': 'inherit', 'notes': 'Release channels are tenant-scoped by default.'},
    {'route': '/admin/release-channels', 'resource_table': 'release_channels', 'action': 'read', 'strict_mode': 'inherit', 'notes': 'Admin release channel summaries should remain tenant-scoped.'},
    {'route': '/release/channel-executions', 'resource_table': 'release_channel_executions', 'action': 'read', 'strict_mode': 'inherit', 'notes': 'Release channel execution history is tenant-scoped by default.'},
    {'route': '/admin/release-channel-executions', 'resource_table': 'release_channel_executions', 'action': 'read', 'strict_mode': 'inherit', 'notes': 'Admin release execution summaries should remain tenant-scoped.'},
    {'route': '/admin/queue', 'resource_table': 'queue_items', 'action': 'read', 'strict_mode': 'inherit', 'notes': 'Queue summaries should exclude cross-tenant queue rows.'},
    {'route': '/admin/jobs', 'resource_table': 'jobs', 'action': 'read', 'strict_mode': 'inherit', 'notes': 'Job summaries should exclude cross-tenant job rows.'},
    {'route': '/jobs/status/{job_id}', 'resource_table': 'jobs', 'action': 'read', 'strict_mode': 'inherit', 'notes': 'Direct job-status reads should stay tenant-scoped.'},
    {'route': '/admin/workflows', 'resource_table': 'workflow_versions', 'action': 'read', 'strict_mode': 'inherit', 'notes': 'Workflow summaries should exclude cross-tenant versions.'},
    {'route': '/workflows/version/history/{workflow_id}', 'resource_table': 'workflow_versions', 'action': 'read', 'strict_mode': 'inherit', 'notes': 'Workflow history reads should stay tenant-scoped.'},
    {'route': '/admin/connectors', 'resource_table': 'connector_metrics', 'action': 'read', 'strict_mode': 'inherit', 'notes': 'Connector summaries should remain tenant-scoped.'},
    {'route': '/connectors/{service_name}/health', 'resource_table': 'connector_metrics', 'action': 'read', 'strict_mode': 'inherit', 'notes': 'Connector health reads should remain tenant-scoped.'},
    {'route': '/connectors/{service_name}/metrics', 'resource_table': 'connector_metrics', 'action': 'read', 'strict_mode': 'inherit', 'notes': 'Connector metrics reads should remain tenant-scoped.'},
    {'route': '/ai/models', 'resource_table': 'model_registry', 'action': 'read', 'strict_mode': 'inherit', 'notes': 'Model registry reads should be tenant-scoped.'},
    {'route': '/ai/prompts', 'resource_table': 'prompt_registry', 'action': 'read', 'strict_mode': 'inherit', 'notes': 'Prompt registry reads should be tenant-scoped.'},
    {'route': '/rag/governance', 'resource_table': 'documents', 'action': 'read', 'strict_mode': 'inherit', 'notes': 'RAG governance reads should stay tenant-scoped.'},
    {'route': '/admin/lifecycle', 'resource_table': 'retention_policies', 'action': 'read', 'strict_mode': 'inherit', 'notes': 'Lifecycle policy summaries should remain tenant-scoped.'},
    {'route': '/admin/tenants', 'resource_table': 'tenant_memberships', 'action': 'read', 'strict_mode': 'inherit', 'notes': 'Tenant admin summaries should stay within the effective tenant context by default.'},
]
ROUTE_ROW_TABLE_MAP: list[tuple[str, list[str]]] = [
    ('/secrets/', ['secrets', 'connector_credentials_meta']),
    ('/admin/release-channel-executions', ['release_channel_executions', 'release_channel_events', 'release_channels', 'release_publications']),
    ('/admin/release-channels', ['release_channels', 'release_channel_events', 'release_channel_executions', 'release_publications']),
    ('/admin/releases', ['release_publications', 'release_publication_events', 'release_manifests', 'rollback_packages']),
    ('/release/', ['release_channels', 'release_channel_events', 'release_channel_executions', 'release_publications', 'release_publication_events', 'release_manifests', 'rollback_packages']),
    ('/admin/queue', ['jobs', 'queue_items', 'dead_letter_items']),
    ('/jobs/status/', ['jobs']),
    ('/jobs/', ['jobs', 'queue_items', 'dead_letter_items']),
    ('/admin/workflows', ['workflow_versions', 'workflow_version_events']),
    ('/workflows/version/history/', ['workflow_versions', 'workflow_version_events']),
    ('/workflows/', ['workflow_versions', 'workflow_version_events']),
    ('/connectors/', ['connector_registry', 'connector_execution_log', 'connector_metrics', 'connector_credentials_meta', 'workflow_templates', 'smoke_test_results']),
    ('/rag/governance', ['documents', 'document_chunks', 'embedding_versions']),
    ('/rag/', ['documents', 'document_chunks', 'embedding_versions']),
    ('/retrieve/', ['documents', 'document_chunks', 'embedding_versions']),
    ('/ingest/', ['documents', 'document_chunks', 'embedding_versions']),
    ('/ai/', ['ai_route_runs', 'ai_output_artifacts', 'model_registry', 'prompt_registry']),
    ('/admin/tenant-isolation', ['tenant_row_policies', 'tenant_row_access_audit']),
    ('/admin/tenant-query-scope', ['tenant_row_policies', 'tenant_row_access_audit', 'tenant_query_scope_audit']),
    ('/admin/tenant-enforcement', ['tenant_route_policies', 'tenant_access_audit']),
    ('/admin/lifecycle', ['retention_policies', 'lifecycle_runs']),
    ('/admin/tenants', ['tenant_memberships', 'tenant_settings', 'tenant_context_events']),
    ('/tenants/', ['tenant_memberships', 'tenant_settings', 'tenant_context_events', 'tenant_route_policies', 'tenant_row_policies', 'tenant_access_audit', 'tenant_row_access_audit']),
    ('/admin/', ['audit_logs']),
]


def infer_resource_tables_for_route(route: str) -> list[str]:
    route = route or '/'
    matched: list[str] = []
    matched_prefix_len = -1
    for prefix, tables in ROUTE_ROW_TABLE_MAP:
        if route.startswith(prefix) and len(prefix) > matched_prefix_len:
            matched = list(tables)
            matched_prefix_len = len(prefix)
    return matched


def seed_tenant_row_policy_defaults() -> None:
    for item in DEFAULT_TENANT_ROW_POLICIES:
        try:
            execute(
                """INSERT INTO tenant_row_policies (
                       tenant_id, resource_table, strict_mode, require_tenant_match,
                       allow_admin_override, allow_service_account_override,
                       allow_global_rows, metadata_json
                   ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                   ON CONFLICT (tenant_id, resource_table)
                   DO NOTHING""",
                (
                    settings.tenant_default_id,
                    item['resource_table'],
                    item['strict_mode'],
                    bool(item['require_tenant_match']),
                    bool(item['allow_admin_override']),
                    bool(item['allow_service_account_override']),
                    bool(item['allow_global_rows']),
                    json.dumps({'notes': item.get('notes', ''), 'seeded': True}),
                ),
            )
        except Exception:
            pass


def _default_row_policy(resource_table: str, tenant_id: str = 'default') -> dict[str, Any]:
    item = next((candidate for candidate in DEFAULT_TENANT_ROW_POLICIES if candidate['resource_table'] == resource_table), None)
    if item is None:
        item = {
            'resource_table': resource_table,
            'strict_mode': 'inherit',
            'require_tenant_match': True,
            'allow_admin_override': True,
            'allow_service_account_override': True,
            'allow_global_rows': False,
            'notes': 'Fallback row policy for resources without an explicit seeded entry.',
        }
    return {
        'tenant_id': tenant_id,
        'resource_table': item['resource_table'],
        'strict_mode': item['strict_mode'],
        'require_tenant_match': bool(item['require_tenant_match']),
        'allow_admin_override': bool(item['allow_admin_override']),
        'allow_service_account_override': bool(item['allow_service_account_override']),
        'allow_global_rows': bool(item['allow_global_rows']),
        'metadata_json': {'notes': item.get('notes', ''), 'source': 'default'},
        'source': 'default',
    }


def resolve_tenant_row_policy(tenant_id: str = 'default', resource_table: str = 'jobs') -> dict[str, Any]:
    try:
        row = fetch_all(
            """SELECT tenant_id, resource_table, strict_mode, require_tenant_match,
                         allow_admin_override, allow_service_account_override, allow_global_rows,
                         updated_by, metadata_json, created_at, updated_at
                  FROM tenant_row_policies
                  WHERE tenant_id=%s AND resource_table=%s
                  ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST
                  LIMIT 1""",
            (tenant_id, resource_table),
        )
        if row:
            item = dict(row[0])
            item['source'] = 'db'
            item['metadata_json'] = item.get('metadata_json') or {}
            return item
    except Exception:
        pass
    return _default_row_policy(resource_table, tenant_id=tenant_id)


def list_tenant_row_policies(tenant_id: str = 'default') -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    try:
        rows = fetch_all(
            """SELECT tenant_id, resource_table, strict_mode, require_tenant_match,
                         allow_admin_override, allow_service_account_override, allow_global_rows,
                         updated_by, metadata_json, created_at, updated_at
                  FROM tenant_row_policies
                  WHERE tenant_id=%s
                  ORDER BY resource_table ASC""",
            (tenant_id,),
        ) or []
        items.extend([{**dict(row), 'source': 'db', 'metadata_json': dict(row).get('metadata_json') or {}} for row in rows])
    except Exception:
        items = []
    existing = {item['resource_table'] for item in items}
    for seeded in DEFAULT_TENANT_ROW_POLICIES:
        if seeded['resource_table'] not in existing:
            items.append(_default_row_policy(seeded['resource_table'], tenant_id=tenant_id))
    items.sort(key=lambda item: item['resource_table'])
    return items


def upsert_tenant_row_policy(
    tenant_id: str,
    resource_table: str,
    strict_mode: str = 'inherit',
    require_tenant_match: bool = True,
    allow_admin_override: bool = True,
    allow_service_account_override: bool = False,
    allow_global_rows: bool = False,
    updated_by: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tenant_id = (tenant_id or settings.tenant_default_id).strip() or settings.tenant_default_id
    resource_table = (resource_table or '').strip()
    if not resource_table:
        raise ValueError('resource_table is required')
    strict_mode = (strict_mode or 'inherit').strip().lower()
    if strict_mode not in {'inherit', 'enforce', 'relaxed'}:
        raise ValueError('strict_mode must be one of inherit, enforce, relaxed')
    payload = metadata_json or {}
    try:
        execute(
            """INSERT INTO tenant_row_policies (
                   tenant_id, resource_table, strict_mode, require_tenant_match,
                   allow_admin_override, allow_service_account_override, allow_global_rows,
                   updated_by, metadata_json
               ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
               ON CONFLICT (tenant_id, resource_table)
               DO UPDATE SET strict_mode=EXCLUDED.strict_mode,
                             require_tenant_match=EXCLUDED.require_tenant_match,
                             allow_admin_override=EXCLUDED.allow_admin_override,
                             allow_service_account_override=EXCLUDED.allow_service_account_override,
                             allow_global_rows=EXCLUDED.allow_global_rows,
                             updated_by=EXCLUDED.updated_by,
                             metadata_json=EXCLUDED.metadata_json,
                             updated_at=now()""",
            (
                tenant_id,
                resource_table,
                strict_mode,
                bool(require_tenant_match),
                bool(allow_admin_override),
                bool(allow_service_account_override),
                bool(allow_global_rows),
                updated_by,
                json.dumps(payload),
            ),
        )
    except Exception:
        pass
    item = resolve_tenant_row_policy(tenant_id=tenant_id, resource_table=resource_table)
    item['updated_by'] = updated_by
    if updated_by is not None:
        item['source'] = 'db'
    return item


def persist_tenant_row_access_audit(
    tenant_id: str,
    actor_id: str | None,
    resource_table: str,
    action: str,
    requested_tenant_id: str,
    effective_tenant_id: str,
    decision: str,
    reason: str,
    metadata_json: dict[str, Any] | None = None,
) -> None:
    if not settings.tenant_policy_audit_enabled:
        return
    try:
        execute(
            """INSERT INTO tenant_row_access_audit (
                   tenant_id, actor_id, resource_table, action,
                   requested_tenant_id, effective_tenant_id,
                   decision, reason, metadata_json
               ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
            (
                tenant_id,
                actor_id,
                resource_table,
                (action or 'read').lower(),
                requested_tenant_id,
                effective_tenant_id,
                decision,
                reason,
                json.dumps(metadata_json or {}),
            ),
        )
    except Exception:
        pass


def enforce_tenant_row_policy(
    requested_tenant_id: str | None,
    effective_tenant_id: str,
    resource_table: str,
    action: str,
    identity,
) -> dict[str, Any]:
    requested = (requested_tenant_id or effective_tenant_id or settings.tenant_default_id).strip() or settings.tenant_default_id
    effective = (effective_tenant_id or requested or settings.tenant_default_id).strip() or settings.tenant_default_id
    identity_tenant_id = (getattr(identity, 'tenant_id', None) or effective).strip() or effective
    actor_id = getattr(identity, 'user_id', 'anonymous')
    role = getattr(identity, 'role', 'viewer')
    memberships = list_actor_tenant_memberships(actor_id=actor_id)
    active_tenants = sorted({item['tenant_id'] for item in memberships if item.get('is_active', True)})
    policy = resolve_tenant_row_policy(tenant_id=effective, resource_table=resource_table)
    strict_mode = policy.get('strict_mode') or settings.tenant_row_policy_default_strict_mode or 'inherit'
    strict_enabled = bool(settings.strict_tenant_row_isolation) or strict_mode == 'enforce'
    cross_tenant = requested != identity_tenant_id
    allowed = True
    reason = 'same_tenant'
    if cross_tenant:
        if role == 'admin' and policy.get('allow_admin_override') and settings.tenant_allow_admin_override:
            allowed = True
            reason = 'admin_override'
        elif role == 'service_account' and policy.get('allow_service_account_override'):
            allowed = True
            reason = 'service_account_override'
        elif not policy.get('require_tenant_match', settings.tenant_row_policy_default_require_tenant_match):
            allowed = True
            reason = 'tenant_match_not_required'
        elif requested in active_tenants:
            allowed = True
            reason = 'active_membership'
        elif policy.get('allow_global_rows') and requested == settings.tenant_default_id:
            allowed = True
            reason = 'global_rows_allowed'
        elif strict_mode == 'relaxed' and not settings.strict_tenant_row_isolation:
            allowed = True
            reason = 'relaxed_policy'
        elif strict_enabled:
            allowed = False
            reason = 'row_tenant_match_required'
        else:
            allowed = True
            reason = 'row_isolation_not_enforced'
    payload = {
        'status': 'ok' if allowed else 'denied',
        'tenant_id': effective,
        'requested_tenant_id': requested,
        'effective_tenant_id': effective,
        'actor_id': actor_id,
        'role': role,
        'identity_tenant_id': identity_tenant_id,
        'resource_table': resource_table,
        'action': (action or 'read').lower(),
        'decision': 'allow' if allowed else 'deny',
        'reason': reason,
        'strict_enforcement': strict_enabled,
        'policy': policy,
        'membership_count': len(memberships),
        'memberships': memberships,
        'accessible_tenants': active_tenants,
    }
    persist_tenant_row_access_audit(
        tenant_id=effective,
        actor_id=actor_id,
        resource_table=resource_table,
        action=payload['action'],
        requested_tenant_id=requested,
        effective_tenant_id=effective,
        decision=payload['decision'],
        reason=reason,
        metadata_json={'policy': policy, 'strict_mode': strict_mode},
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                'code': 'TENANT_ROW_POLICY_DENIED',
                'resource_table': resource_table,
                'requested_tenant_id': requested,
                'effective_tenant_id': effective,
                'actor_id': actor_id,
                'reason': reason,
                'policy': policy,
            },
        )
    return payload


def enforce_row_isolation_for_route(requested_tenant_id: str | None, effective_tenant_id: str, route: str, method: str, identity) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for resource_table in infer_resource_tables_for_route(route):
        items.append(enforce_tenant_row_policy(requested_tenant_id, effective_tenant_id, resource_table, method.lower(), identity))
    return items


def build_tenant_row_isolation_report(
    tenant_id: str = 'default',
    resource_table: str = 'jobs',
    action: str = 'read',
    actor_id: str = 'anonymous',
    role: str = 'viewer',
    identity_tenant_id: str | None = None,
    requested_tenant_id: str | None = None,
) -> dict[str, Any]:
    requested = (requested_tenant_id or tenant_id or identity_tenant_id or settings.tenant_default_id).strip() or settings.tenant_default_id
    identity_tenant_id = (identity_tenant_id or settings.tenant_default_id).strip() or settings.tenant_default_id
    memberships = list_actor_tenant_memberships(actor_id=actor_id)
    active_tenants = sorted({item['tenant_id'] for item in memberships if item.get('is_active', True)})
    policy = resolve_tenant_row_policy(tenant_id=requested, resource_table=resource_table)
    strict_mode = policy.get('strict_mode') or settings.tenant_row_policy_default_strict_mode or 'inherit'
    strict_enabled = bool(settings.strict_tenant_row_isolation) or strict_mode == 'enforce'
    cross_tenant = requested != identity_tenant_id
    if not cross_tenant:
        decision = 'allow'
        reason = 'same_tenant'
    elif role == 'admin' and policy.get('allow_admin_override') and settings.tenant_allow_admin_override:
        decision = 'allow'
        reason = 'admin_override'
    elif role == 'service_account' and policy.get('allow_service_account_override'):
        decision = 'allow'
        reason = 'service_account_override'
    elif not policy.get('require_tenant_match', settings.tenant_row_policy_default_require_tenant_match):
        decision = 'allow'
        reason = 'tenant_match_not_required'
    elif requested in active_tenants:
        decision = 'allow'
        reason = 'active_membership'
    elif policy.get('allow_global_rows') and requested == settings.tenant_default_id:
        decision = 'allow'
        reason = 'global_rows_allowed'
    elif strict_mode == 'relaxed' and not settings.strict_tenant_row_isolation:
        decision = 'allow'
        reason = 'relaxed_policy'
    elif strict_enabled:
        decision = 'deny'
        reason = 'row_tenant_match_required'
    else:
        decision = 'allow'
        reason = 'row_isolation_not_enforced'
    next_actions: list[str] = []
    if decision == 'deny':
        next_actions.append('Grant tenant membership, use an allowed admin override, or relax the row policy before enabling strict row isolation for this table.')
    elif strict_enabled:
        next_actions.append('Tenant row isolation is actively enforcing the matched table policy.')
    else:
        next_actions.append('Enable STRICT_TENANT_ROW_ISOLATION=true or switch the table policy to enforce when you are ready for harder isolation.')
    if policy.get('resource_table') in {'secrets', 'connector_credentials_meta'}:
        next_actions.append('Keep sensitive credential-bearing tables on enforce mode in multi-tenant environments.')
    return {
        'status': 'ok',
        'tenant_id': requested,
        'requested_tenant_id': requested,
        'effective_tenant_id': requested if decision == 'allow' else identity_tenant_id,
        'actor_id': actor_id,
        'role': role,
        'identity_tenant_id': identity_tenant_id,
        'resource_table': resource_table,
        'action': (action or 'read').lower(),
        'decision': decision,
        'reason': reason,
        'strict_enforcement': strict_enabled,
        'policy': policy,
        'membership_count': len(memberships),
        'memberships': memberships,
        'accessible_tenants': active_tenants,
        'policy_count': len(list_tenant_row_policies(tenant_id=requested)),
        'policies': list_tenant_row_policies(tenant_id=requested),
        'next_actions': next_actions,
    }



def persist_tenant_query_scope_audit(
    tenant_id: str,
    actor_id: str | None,
    route: str,
    resource_table: str,
    requested_tenant_id: str,
    effective_tenant_id: str,
    visible_tenant_ids: list[str],
    records_before: int,
    records_after: int,
    filtered_count: int,
    strict_enforcement: bool,
    decision: str,
    reason: str,
    metadata_json: dict[str, Any] | None = None,
) -> None:
    if not settings.tenant_policy_audit_enabled:
        return
    try:
        execute(
            """INSERT INTO tenant_query_scope_audit (
                   tenant_id, actor_id, route, resource_table,
                   requested_tenant_id, effective_tenant_id, visible_tenant_ids,
                   records_before, records_after, filtered_count,
                   strict_enforcement, decision, reason, metadata_json
               ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
            (
                tenant_id,
                actor_id,
                route,
                resource_table,
                requested_tenant_id,
                effective_tenant_id,
                json.dumps(sorted(set(visible_tenant_ids))),
                int(records_before),
                int(records_after),
                int(filtered_count),
                bool(strict_enforcement),
                decision,
                reason,
                json.dumps(metadata_json or {}),
            ),
        )
    except Exception:
        pass


class _AnonymousIdentity:
    def __init__(self, tenant_id: str, actor_id: str = 'anonymous', role: str = 'viewer') -> None:
        self.tenant_id = tenant_id
        self.user_id = actor_id
        self.role = role


def filter_records_for_tenant_scope(
    records: list[dict[str, Any]],
    resource_table: str,
    effective_tenant_id: str,
    requested_tenant_id: str | None = None,
    identity=None,
    action: str = 'read',
    route: str = '/',
    persist_audit: bool = True,
) -> dict[str, Any]:
    effective = (effective_tenant_id or settings.tenant_default_id).strip() or settings.tenant_default_id
    requested = (requested_tenant_id or effective).strip() or effective
    identity_obj = identity or _AnonymousIdentity(tenant_id=effective)
    actor_id = getattr(identity_obj, 'user_id', 'anonymous')
    role = getattr(identity_obj, 'role', 'viewer')
    policy_payload = enforce_tenant_row_policy(requested, effective, resource_table, action, identity_obj)
    policy = policy_payload.get('policy', {})
    visible_tenant_ids = [effective]
    if policy.get('allow_global_rows') and settings.tenant_default_id not in visible_tenant_ids:
        visible_tenant_ids.append(settings.tenant_default_id)
    if requested and requested not in visible_tenant_ids and policy_payload.get('decision') == 'allow' and requested == effective:
        visible_tenant_ids.append(requested)
    strict_enforcement = bool(policy_payload.get('strict_enforcement'))
    filtered: list[dict[str, Any]] = []
    unscoped_rows = 0
    for item in records or []:
        row = dict(item)
        row_tenant_id = row.get('tenant_id')
        if row_tenant_id is None:
            if strict_enforcement and policy.get('require_tenant_match', settings.tenant_row_policy_default_require_tenant_match):
                unscoped_rows += 1
                continue
            filtered.append(row)
            continue
        if str(row_tenant_id) in visible_tenant_ids:
            filtered.append(row)
        elif not strict_enforcement and policy.get('strict_mode') == 'relaxed':
            filtered.append(row)
    result = {
        'status': 'ok',
        'tenant_id': effective,
        'requested_tenant_id': requested,
        'effective_tenant_id': effective,
        'actor_id': actor_id,
        'role': role,
        'identity_tenant_id': getattr(identity_obj, 'tenant_id', effective),
        'resource_table': resource_table,
        'route': route,
        'action': (action or 'read').lower(),
        'decision': policy_payload.get('decision', 'allow'),
        'reason': policy_payload.get('reason', 'same_tenant'),
        'strict_enforcement': strict_enforcement,
        'policy': policy,
        'visible_tenant_ids': visible_tenant_ids,
        'query_scope_sql': f"WHERE tenant_id IN ({', '.join(repr(item) for item in visible_tenant_ids)})",
        'records_before': len(records or []),
        'records_after': len(filtered),
        'filtered_count': max(len(records or []) - len(filtered), 0),
        'records': filtered,
        'policy_count': len(list_tenant_row_policies(tenant_id=effective)),
        'policies': list_tenant_row_policies(tenant_id=effective),
        'next_actions': [],
    }
    if strict_enforcement:
        result['next_actions'].append('Query-time tenant row scoping is actively filtering rows to the effective tenant set.')
    else:
        result['next_actions'].append('Enable STRICT_TENANT_ROW_ISOLATION=true or enforce-mode row policies before relying on hard row filtering everywhere.')
    if result['filtered_count'] > 0 or unscoped_rows:
        result['next_actions'].append('Review filtered or unscoped rows and migrate remaining query paths to tenant-aware SQL where needed.')
    if persist_audit:
        persist_tenant_query_scope_audit(
            tenant_id=effective,
            actor_id=actor_id,
            route=route,
            resource_table=resource_table,
            requested_tenant_id=requested,
            effective_tenant_id=effective,
            visible_tenant_ids=visible_tenant_ids,
            records_before=result['records_before'],
            records_after=result['records_after'],
            filtered_count=result['filtered_count'] + unscoped_rows,
            strict_enforcement=strict_enforcement,
            decision=result['decision'],
            reason=result['reason'],
            metadata_json={'policy': policy, 'unscoped_rows': unscoped_rows},
        )
    return result


def build_tenant_query_scope_report(
    tenant_id: str = 'default',
    resource_table: str = 'release_publications',
    route: str = '/release/publications',
    action: str = 'read',
    actor_id: str = 'anonymous',
    role: str = 'viewer',
    identity_tenant_id: str | None = None,
    requested_tenant_id: str | None = None,
) -> dict[str, Any]:
    requested = (requested_tenant_id or tenant_id or identity_tenant_id or settings.tenant_default_id).strip() or settings.tenant_default_id
    effective = (tenant_id or requested or settings.tenant_default_id).strip() or settings.tenant_default_id
    identity_tenant = (identity_tenant_id or effective).strip() or effective
    identity = _AnonymousIdentity(tenant_id=identity_tenant, actor_id=actor_id, role=role)
    payload = filter_records_for_tenant_scope(
        records=[{'tenant_id': effective}, {'tenant_id': settings.tenant_default_id}],
        resource_table=resource_table,
        effective_tenant_id=effective,
        requested_tenant_id=requested,
        identity=identity,
        action=action,
        route=route,
        persist_audit=False,
    )
    payload['records_before'] = 0
    payload['records_after'] = 0
    payload['filtered_count'] = 0
    if resource_table in {'secrets', 'connector_credentials_meta'}:
        payload['next_actions'].append('Keep sensitive credential-bearing tables on enforce mode and avoid relaxed query scopes for shared operators.')
    return payload


def seed_tenant_query_scope_target_defaults() -> None:
    try:
        for item in DEFAULT_TENANT_QUERY_SCOPE_TARGETS:
            execute(
                """INSERT INTO tenant_query_scope_targets (tenant_id, route, resource_table, action, strict_mode, notes, source)
                   VALUES (%s,%s,%s,%s,%s,%s,'default')
                   ON CONFLICT (tenant_id, route, resource_table, action)
                   DO NOTHING""",
                (settings.tenant_default_id, item['route'], item['resource_table'], item.get('action', 'read'), item.get('strict_mode', 'inherit'), item.get('notes')),
            )
    except Exception:
        pass


def upsert_tenant_query_scope_target(
    tenant_id: str,
    route: str,
    resource_table: str,
    action: str = 'read',
    strict_mode: str = 'inherit',
    notes: str | None = None,
    updated_by: str | None = None,
) -> dict[str, Any]:
    tenant = (tenant_id or settings.tenant_default_id).strip() or settings.tenant_default_id
    route = (route or '/').strip() or '/'
    resource_table = (resource_table or 'generic').strip() or 'generic'
    action = (action or 'read').strip().lower() or 'read'
    strict_mode = (strict_mode or 'inherit').strip().lower() or 'inherit'
    try:
        row = execute(
            """INSERT INTO tenant_query_scope_targets (tenant_id, route, resource_table, action, strict_mode, notes, source, updated_by)
                   VALUES (%s,%s,%s,%s,%s,%s,'db',%s)
                   ON CONFLICT (tenant_id, route, resource_table, action)
                   DO UPDATE SET strict_mode=EXCLUDED.strict_mode,
                                 notes=EXCLUDED.notes,
                                 source='db',
                                 updated_by=EXCLUDED.updated_by,
                                 updated_at=now()
                   RETURNING tenant_id, route, resource_table, action, strict_mode, notes, source, updated_by""",
            (tenant, route, resource_table, action, strict_mode, notes, updated_by),
            fetch='one',
        )
        if row:
            return dict(row)
    except Exception:
        pass
    return {'tenant_id': tenant, 'route': route, 'resource_table': resource_table, 'action': action, 'strict_mode': strict_mode, 'notes': notes, 'source': 'default', 'updated_by': updated_by}


def list_tenant_query_scope_targets(tenant_id: str = 'default') -> list[dict[str, Any]]:
    tenant = (tenant_id or settings.tenant_default_id).strip() or settings.tenant_default_id
    try:
        rows = fetch_all(
            """SELECT tenant_id, route, resource_table, action, strict_mode, notes, COALESCE(source, 'db') AS source, updated_by
                   FROM tenant_query_scope_targets WHERE tenant_id=%s ORDER BY route, resource_table, action""",
            (tenant,),
        )
        if rows:
            return [dict(row) for row in rows]
    except Exception:
        pass
    return [dict(item, tenant_id=tenant, source='default', updated_by=None) for item in DEFAULT_TENANT_QUERY_SCOPE_TARGETS]


def build_tenant_query_coverage_report(
    tenant_id: str = 'default',
    actor_id: str = 'anonymous',
    role: str = 'viewer',
    identity_tenant_id: str | None = None,
    requested_tenant_id: str | None = None,
) -> dict[str, Any]:
    requested = (requested_tenant_id or tenant_id or identity_tenant_id or settings.tenant_default_id).strip() or settings.tenant_default_id
    effective = (tenant_id or requested or settings.tenant_default_id).strip() or settings.tenant_default_id
    identity_tenant = (identity_tenant_id or effective).strip() or effective
    targets = []
    covered_count = 0
    strict_count = 0
    for item in list_tenant_query_scope_targets(tenant_id=effective):
        scope = build_tenant_query_scope_report(
            tenant_id=effective,
            resource_table=item['resource_table'],
            route=item['route'],
            action=item.get('action', 'read'),
            actor_id=actor_id,
            role=role,
            identity_tenant_id=identity_tenant,
            requested_tenant_id=requested,
        )
        target = {
            'route': item['route'],
            'resource_table': item['resource_table'],
            'action': item.get('action', 'read'),
            'strict_mode': item.get('strict_mode', 'inherit'),
            'notes': item.get('notes'),
            'source': item.get('source', 'default'),
            'decision': scope.get('decision'),
            'reason': scope.get('reason'),
            'strict_enforcement': scope.get('strict_enforcement', False),
            'visible_tenant_ids': scope.get('visible_tenant_ids', []),
            'query_scope_sql': scope.get('query_scope_sql', ''),
        }
        if scope.get('decision') == 'allow':
            covered_count += 1
        if scope.get('strict_enforcement') or item.get('strict_mode') == 'enforce':
            strict_count += 1
        targets.append(target)
    next_actions = []
    if strict_count < len(targets):
        next_actions.append('Promote more tenant query-scope targets to enforce mode before claiming full SQL-style tenant isolation.')
    next_actions.append('Continue migrating remaining list/admin/query paths so request-context tenant scoping is enforced inside SQL where possible.')
    return {
        'status': 'ok',
        'tenant_id': effective,
        'requested_tenant_id': requested,
        'effective_tenant_id': effective,
        'actor_id': actor_id,
        'role': role,
        'identity_tenant_id': identity_tenant,
        'target_count': len(targets),
        'covered_count': covered_count,
        'strict_target_count': strict_count,
        'targets': targets,
        'next_actions': next_actions,
    }
