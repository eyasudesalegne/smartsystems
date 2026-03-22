from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, status

from .config import settings
from .db import execute, fetch_all, fetch_one

DEFAULT_TENANT_ROUTE_POLICIES: list[dict[str, Any]] = [
    {
        'route_prefix': '/secrets/',
        'resource_type': 'secrets',
        'strict_mode': 'enforce',
        'require_membership': True,
        'allow_admin_override': False,
        'allow_service_account_override': False,
        'notes': 'Secret access stays tenant-bound unless an explicit membership exists.',
    },
    {
        'route_prefix': '/tenants/',
        'resource_type': 'tenants',
        'strict_mode': 'enforce',
        'require_membership': True,
        'allow_admin_override': True,
        'allow_service_account_override': False,
        'notes': 'Tenant admin operations require either direct membership or an admin override.',
    },
    {
        'route_prefix': '/admin/',
        'resource_type': 'admin',
        'strict_mode': 'enforce',
        'require_membership': True,
        'allow_admin_override': True,
        'allow_service_account_override': False,
        'notes': 'Admin summaries should stay scoped to the effective tenant.',
    },
    {
        'route_prefix': '/release/',
        'resource_type': 'release',
        'strict_mode': 'enforce',
        'require_membership': True,
        'allow_admin_override': True,
        'allow_service_account_override': False,
        'notes': 'Release publication actions are tenant-scoped by default.',
    },
    {
        'route_prefix': '/connectors/',
        'resource_type': 'connectors',
        'strict_mode': 'inherit',
        'require_membership': True,
        'allow_admin_override': True,
        'allow_service_account_override': True,
        'notes': 'Connector operations may cross tenants only through membership or explicit override.',
    },
    {
        'route_prefix': '/jobs/',
        'resource_type': 'jobs',
        'strict_mode': 'inherit',
        'require_membership': True,
        'allow_admin_override': True,
        'allow_service_account_override': True,
        'notes': 'Job operations inherit the package tenant defaults.',
    },
    {
        'route_prefix': '/workflows/',
        'resource_type': 'workflows',
        'strict_mode': 'inherit',
        'require_membership': True,
        'allow_admin_override': True,
        'allow_service_account_override': True,
        'notes': 'Workflow operations inherit the package tenant defaults.',
    },
    {
        'route_prefix': '/',
        'resource_type': 'system',
        'strict_mode': 'inherit',
        'require_membership': False,
        'allow_admin_override': True,
        'allow_service_account_override': True,
        'notes': 'Fallback policy when no more specific route prefix matches.',
    },
]


def ensure_tenant_exists(tenant_id: str, tenant_name: str | None = None, created_by: str | None = None) -> dict[str, Any]:
    tenant_id = (tenant_id or settings.tenant_default_id).strip() or settings.tenant_default_id
    tenant_name = (tenant_name or tenant_id.title()).strip() or tenant_id.title()
    try:
        execute(
            """INSERT INTO tenants (tenant_id, tenant_name) VALUES (%s, %s)
               ON CONFLICT (tenant_id) DO UPDATE SET tenant_name=EXCLUDED.tenant_name, updated_at=now()""",
            (tenant_id, tenant_name),
        )
        execute(
            """INSERT INTO tenant_settings (tenant_id, strict_enforcement, allow_admin_override, metadata_json)
               VALUES (%s,%s,%s,%s::jsonb)
               ON CONFLICT (tenant_id) DO NOTHING""",
            (tenant_id, bool(settings.strict_tenant_enforcement), bool(settings.tenant_allow_admin_override), json.dumps({'created_by': created_by})),
        )
    except Exception:
        pass
    try:
        from .auth import seed_rbac_defaults
        seed_rbac_defaults(tenant_id)
    except Exception:
        pass
    return {
        'tenant_id': tenant_id,
        'tenant_name': tenant_name,
        'created_by': created_by,
    }


def _ensure_actor(actor_id: str, tenant_id: str, username: str | None = None, display_name: str | None = None) -> dict[str, Any]:
    actor_id = (actor_id or 'anonymous').strip() or 'anonymous'
    username = username or actor_id
    display_name = display_name or username
    try:
        execute(
            """INSERT INTO actors (actor_id, tenant_id, username, display_name, is_active)
               VALUES (%s,%s,%s,%s,true)
               ON CONFLICT (actor_id) DO UPDATE SET username=COALESCE(EXCLUDED.username, actors.username),
                                                     display_name=COALESCE(EXCLUDED.display_name, actors.display_name),
                                                     updated_at=now()""",
            (actor_id, tenant_id, username, display_name),
        )
    except Exception:
        pass
    return {
        'actor_id': actor_id,
        'tenant_id': tenant_id,
        'username': username,
        'display_name': display_name,
    }


def upsert_tenant_membership(actor_id: str, tenant_id: str, role_name: str = 'viewer', created_by: str | None = None, username: str | None = None, display_name: str | None = None, is_default: bool = False, is_active: bool = True, metadata_json: dict[str, Any] | None = None) -> dict[str, Any]:
    tenant = ensure_tenant_exists(tenant_id)
    actor = _ensure_actor(actor_id, tenant['tenant_id'], username=username, display_name=display_name)
    metadata_json = metadata_json or {}
    try:
        if is_default:
            execute("UPDATE tenant_memberships SET is_default=false, updated_at=now() WHERE actor_id=%s", (actor['actor_id'],))
        execute(
            """INSERT INTO tenant_memberships (tenant_id, actor_id, role_name, is_default, is_active, created_by, updated_by, metadata_json)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
               ON CONFLICT (tenant_id, actor_id) DO UPDATE SET role_name=EXCLUDED.role_name,
                                                             is_default=EXCLUDED.is_default,
                                                             is_active=EXCLUDED.is_active,
                                                             updated_by=EXCLUDED.updated_by,
                                                             metadata_json=EXCLUDED.metadata_json,
                                                             updated_at=now()""",
            (tenant['tenant_id'], actor['actor_id'], role_name, bool(is_default), bool(is_active), created_by, created_by, json.dumps(metadata_json)),
        )
        execute("INSERT INTO roles (tenant_id, role_name) VALUES (%s,%s) ON CONFLICT (tenant_id, role_name) DO NOTHING", (tenant['tenant_id'], role_name))
        role_row = fetch_one("SELECT role_id FROM roles WHERE tenant_id=%s AND role_name=%s", (tenant['tenant_id'], role_name))
        if role_row:
            execute(
                """INSERT INTO actor_roles (tenant_id, actor_id, role_id)
                   VALUES (%s,%s,%s)
                   ON CONFLICT (tenant_id, actor_id, role_id) DO NOTHING""",
                (tenant['tenant_id'], actor['actor_id'], role_row['role_id']),
            )
        if is_default:
            execute("UPDATE actors SET tenant_id=%s, updated_at=now() WHERE actor_id=%s", (tenant['tenant_id'], actor['actor_id']))
    except Exception:
        pass
    return {
        'tenant_id': tenant['tenant_id'],
        'tenant_name': tenant['tenant_name'],
        'actor_id': actor['actor_id'],
        'role_name': role_name,
        'is_default': bool(is_default),
        'is_active': bool(is_active),
        'created_by': created_by,
        'metadata_json': metadata_json,
    }


def seed_tenant_defaults() -> None:
    default_tenant = ensure_tenant_exists(settings.tenant_default_id, settings.tenant_default_id.title())
    configured = settings.auth_bootstrap_users
    for username, info in configured.items():
        upsert_tenant_membership(
            actor_id=info.get('user_id') or username,
            tenant_id=info.get('tenant_id') or default_tenant['tenant_id'],
            role_name=info.get('role') or 'admin',
            created_by='bootstrap',
            username=username,
            display_name=username,
            is_default=True,
            is_active=True,
            metadata_json={'bootstrap': True},
        )
    upsert_tenant_membership('anonymous', default_tenant['tenant_id'], 'viewer', created_by='bootstrap', username='anonymous', display_name='Anonymous', is_default=True, is_active=True, metadata_json={'bootstrap': True})


def list_actor_tenant_memberships(actor_id: str | None = None, tenant_id: str | None = None) -> list[dict[str, Any]]:
    params: list[Any] = []
    where = []
    if actor_id:
        where.append('tm.actor_id=%s')
        params.append(actor_id)
    if tenant_id:
        where.append('tm.tenant_id=%s')
        params.append(tenant_id)
    sql = """SELECT tm.tenant_id, t.tenant_name, tm.actor_id, tm.role_name, tm.is_default, tm.is_active,
                     tm.created_by, tm.updated_by, tm.metadata_json, tm.created_at, tm.updated_at
              FROM tenant_memberships tm
              JOIN tenants t ON t.tenant_id = tm.tenant_id"""
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += ' ORDER BY tm.is_default DESC, tm.tenant_id ASC'
    try:
        rows = fetch_all(sql, tuple(params))
        return [dict(row) for row in rows]
    except Exception:
        if actor_id in (None, 'anonymous'):
            return [{
                'tenant_id': settings.tenant_default_id,
                'tenant_name': settings.tenant_default_id.title(),
                'actor_id': actor_id or 'anonymous',
                'role_name': 'viewer',
                'is_default': True,
                'is_active': True,
                'created_by': 'fallback',
                'updated_by': 'fallback',
                'metadata_json': {'fallback': True},
                'created_at': None,
                'updated_at': None,
            }]
        configured = settings.auth_bootstrap_users
        for username, info in configured.items():
            if actor_id == (info.get('user_id') or username):
                return [{
                    'tenant_id': info.get('tenant_id') or settings.tenant_default_id,
                    'tenant_name': (info.get('tenant_id') or settings.tenant_default_id).title(),
                    'actor_id': actor_id,
                    'role_name': info.get('role') or 'viewer',
                    'is_default': True,
                    'is_active': True,
                    'created_by': 'bootstrap',
                    'updated_by': 'bootstrap',
                    'metadata_json': {'fallback': True},
                    'created_at': None,
                    'updated_at': None,
                }]
        return []


def resolve_effective_tenant(requested_tenant_id: str | None, identity) -> str:
    requested = (requested_tenant_id or identity.tenant_id or settings.tenant_default_id).strip() or settings.tenant_default_id
    if requested == identity.tenant_id:
        return requested
    if identity.role == 'admin' and settings.tenant_allow_admin_override:
        return requested
    if identity.role == 'service_account' and not settings.strict_tenant_enforcement:
        return requested
    memberships = list_actor_tenant_memberships(actor_id=identity.user_id, tenant_id=requested)
    if any(item.get('is_active', True) for item in memberships):
        return requested
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            'code': 'TENANT_ACCESS_DENIED',
            'requested_tenant_id': requested,
            'identity_tenant_id': identity.tenant_id,
            'actor_id': identity.user_id,
        },
    )


def list_tenants_summary(tenant_id: str | None = None) -> dict[str, Any]:
    scoped_tenant_id = (tenant_id or '').strip()
    params: tuple[Any, ...] = ()
    where_sql = ''
    if scoped_tenant_id:
        where_sql = 'WHERE t.tenant_id=%s'
        params = (scoped_tenant_id,)
    try:
        tenants = [dict(row) for row in fetch_all(
            f"""SELECT t.tenant_id, t.tenant_name, t.created_at, t.updated_at,
                         COALESCE((SELECT count(*)::int FROM tenant_memberships tm WHERE tm.tenant_id=t.tenant_id AND tm.is_active=true), 0) AS membership_count,
                         COALESCE((SELECT count(*)::int FROM secrets_store ss WHERE ss.tenant_id=t.tenant_id), 0) AS secret_count,
                         COALESCE((SELECT count(*)::int FROM jobs j WHERE j.tenant_id=t.tenant_id), 0) AS job_count
                  FROM tenants t
                  {where_sql}
                  ORDER BY t.tenant_id ASC""",
            params,
        )]
    except Exception:
        fallback_tenant_id = scoped_tenant_id or settings.tenant_default_id
        tenants = [{
            'tenant_id': fallback_tenant_id,
            'tenant_name': fallback_tenant_id.title(),
            'created_at': None,
            'updated_at': None,
            'membership_count': len(settings.auth_bootstrap_users) + 1 if fallback_tenant_id == settings.tenant_default_id else 0,
            'secret_count': 0,
            'job_count': 0,
        }]
    return {
        'tenant_count': len(tenants),
        'tenants': tenants,
    }


def build_tenant_context_report(requested_tenant_id: str | None = None, actor_id: str = 'anonymous', role: str = 'viewer', identity_tenant_id: str | None = None) -> dict[str, Any]:
    requested = (requested_tenant_id or identity_tenant_id or settings.tenant_default_id).strip() or settings.tenant_default_id
    effective = requested
    memberships = list_actor_tenant_memberships(actor_id=actor_id)
    accessible_tenants = [item['tenant_id'] for item in memberships if item.get('is_active', True)]
    resolution_mode = 'requested'
    if requested != (identity_tenant_id or requested):
        resolution_mode = 'override' if role == 'admin' and settings.tenant_allow_admin_override else 'membership'
    has_access = bool(role == 'admin' and settings.tenant_allow_admin_override) or requested == (identity_tenant_id or requested) or requested in accessible_tenants
    if not has_access and settings.strict_tenant_enforcement:
        effective = identity_tenant_id or settings.tenant_default_id
        resolution_mode = 'fallback_to_identity'
    next_actions = []
    if not memberships:
        next_actions.append('Create a tenant membership before enabling strict tenant enforcement for this actor.')
    elif not has_access:
        next_actions.append('Grant membership or use an admin token with tenant override enabled before switching context.')
    else:
        next_actions.append('Tenant context is ready for scoped admin, connector, and workflow operations.')
    return {
        'status': 'ok',
        'tenant_id': effective,
        'requested_tenant_id': requested,
        'effective_tenant_id': effective,
        'actor_id': actor_id,
        'role': role,
        'identity_tenant_id': identity_tenant_id or effective,
        'strict_enforcement': bool(settings.strict_tenant_enforcement),
        'admin_override_enabled': bool(settings.tenant_allow_admin_override),
        'has_access': has_access,
        'resolution_mode': resolution_mode,
        'membership_count': len(memberships),
        'memberships': memberships,
        'next_actions': next_actions,
    }


def seed_tenant_policy_defaults() -> None:
    ensure_tenant_exists(settings.tenant_default_id, settings.tenant_default_id.title(), created_by='bootstrap')
    for item in DEFAULT_TENANT_ROUTE_POLICIES:
        try:
            execute(
                """INSERT INTO tenant_route_policies (
                       tenant_id, route_prefix, resource_type, strict_mode,
                       require_membership, allow_admin_override, allow_service_account_override,
                       metadata_json
                   ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                   ON CONFLICT (tenant_id, route_prefix)
                   DO NOTHING""",
                (
                    settings.tenant_default_id,
                    item['route_prefix'],
                    item['resource_type'],
                    item['strict_mode'],
                    bool(item['require_membership']),
                    bool(item['allow_admin_override']),
                    bool(item['allow_service_account_override']),
                    json.dumps({'notes': item.get('notes', ''), 'seeded': True}),
                ),
            )
        except Exception:
            pass


def _default_policy_for_route(route: str, tenant_id: str = 'default') -> dict[str, Any]:
    route = route or '/'
    matched = None
    for item in DEFAULT_TENANT_ROUTE_POLICIES:
        prefix = item['route_prefix']
        if route.startswith(prefix) and (matched is None or len(prefix) > len(matched['route_prefix'])):
            matched = item
    matched = matched or DEFAULT_TENANT_ROUTE_POLICIES[-1]
    metadata_json = {'notes': matched.get('notes', ''), 'source': 'default'}
    return {
        'tenant_id': tenant_id,
        'route_prefix': matched['route_prefix'],
        'resource_type': matched['resource_type'],
        'strict_mode': matched['strict_mode'],
        'require_membership': bool(matched['require_membership']),
        'allow_admin_override': bool(matched['allow_admin_override']),
        'allow_service_account_override': bool(matched['allow_service_account_override']),
        'metadata_json': metadata_json,
        'source': 'default',
    }


def resolve_tenant_route_policy(tenant_id: str = 'default', route: str = '/') -> dict[str, Any]:
    route = route or '/'
    try:
        rows = fetch_all(
            """SELECT tenant_id, route_prefix, resource_type, strict_mode, require_membership,
                         allow_admin_override, allow_service_account_override, metadata_json,
                         created_at, updated_at
                  FROM tenant_route_policies
                  WHERE tenant_id=%s
                  ORDER BY length(route_prefix) DESC, route_prefix ASC""",
            (tenant_id,),
        ) or []
        for row in rows:
            item = dict(row)
            if route.startswith(item['route_prefix']):
                item['source'] = 'db'
                item['metadata_json'] = item.get('metadata_json') or {}
                return item
    except Exception:
        pass
    return _default_policy_for_route(route, tenant_id=tenant_id)


def list_tenant_route_policies(tenant_id: str = 'default') -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        db_rows = fetch_all(
            """SELECT tenant_id, route_prefix, resource_type, strict_mode, require_membership,
                         allow_admin_override, allow_service_account_override, metadata_json,
                         created_at, updated_at
                  FROM tenant_route_policies
                  WHERE tenant_id=%s
                  ORDER BY length(route_prefix) DESC, route_prefix ASC""",
            (tenant_id,),
        ) or []
        rows = [dict(row) for row in db_rows]
    except Exception:
        rows = []
    if rows:
        for item in rows:
            item['source'] = 'db'
            item['metadata_json'] = item.get('metadata_json') or {}
        return rows
    return [_default_policy_for_route(item['route_prefix'], tenant_id=tenant_id) for item in DEFAULT_TENANT_ROUTE_POLICIES]


def upsert_tenant_route_policy(
    tenant_id: str,
    route_prefix: str,
    resource_type: str,
    strict_mode: str = 'inherit',
    require_membership: bool = True,
    allow_admin_override: bool = True,
    allow_service_account_override: bool = False,
    updated_by: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tenant = ensure_tenant_exists(tenant_id, created_by=updated_by)
    strict_mode = (strict_mode or settings.tenant_policy_default_strict_mode or 'inherit').strip().lower()
    if strict_mode not in {'inherit', 'enforce', 'relaxed'}:
        raise ValueError(f'unsupported strict_mode={strict_mode}')
    metadata_json = metadata_json or {}
    try:
        execute(
            """INSERT INTO tenant_route_policies (
                   tenant_id, route_prefix, resource_type, strict_mode,
                   require_membership, allow_admin_override, allow_service_account_override,
                   updated_by, metadata_json
               ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
               ON CONFLICT (tenant_id, route_prefix)
               DO UPDATE SET resource_type=EXCLUDED.resource_type,
                             strict_mode=EXCLUDED.strict_mode,
                             require_membership=EXCLUDED.require_membership,
                             allow_admin_override=EXCLUDED.allow_admin_override,
                             allow_service_account_override=EXCLUDED.allow_service_account_override,
                             updated_by=EXCLUDED.updated_by,
                             metadata_json=EXCLUDED.metadata_json,
                             updated_at=now()""",
            (
                tenant['tenant_id'],
                route_prefix,
                resource_type,
                strict_mode,
                bool(require_membership),
                bool(allow_admin_override),
                bool(allow_service_account_override),
                updated_by,
                json.dumps(metadata_json),
            ),
        )
    except Exception:
        pass
    payload = resolve_tenant_route_policy(tenant['tenant_id'], route_prefix)
    payload['metadata_json'] = payload.get('metadata_json') or metadata_json
    payload['updated_by'] = updated_by
    payload['source'] = payload.get('source') or 'db'
    return payload


def persist_tenant_access_audit(
    tenant_id: str,
    actor_id: str | None,
    route: str,
    method: str,
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
            """INSERT INTO tenant_access_audit (
                   tenant_id, actor_id, route, method, requested_tenant_id, effective_tenant_id,
                   decision, reason, metadata_json
               ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
            (tenant_id, actor_id, route, method, requested_tenant_id, effective_tenant_id, decision, reason, json.dumps(metadata_json or {})),
        )
    except Exception:
        pass


def enforce_tenant_route_policy(requested_tenant_id: str | None, effective_tenant_id: str, route: str, method: str, identity) -> dict[str, Any]:
    requested = (requested_tenant_id or effective_tenant_id or settings.tenant_default_id).strip() or settings.tenant_default_id
    policy = resolve_tenant_route_policy(effective_tenant_id or requested, route)
    memberships = list_actor_tenant_memberships(actor_id=getattr(identity, 'user_id', None))
    active_tenants = {item['tenant_id'] for item in memberships if item.get('is_active', True)}
    cross_tenant = requested != getattr(identity, 'tenant_id', requested)
    strict_mode = policy.get('strict_mode') or settings.tenant_policy_default_strict_mode or 'inherit'
    reason = 'same_tenant'
    allowed = True
    if cross_tenant:
        if getattr(identity, 'role', None) == 'admin' and policy.get('allow_admin_override') and settings.tenant_allow_admin_override:
            reason = 'admin_override'
            allowed = True
        elif getattr(identity, 'role', None) == 'service_account' and policy.get('allow_service_account_override') and not settings.strict_tenant_enforcement:
            reason = 'service_account_override'
            allowed = True
        elif not policy.get('require_membership', settings.tenant_policy_default_require_membership):
            reason = 'membership_not_required'
            allowed = True
        elif requested in active_tenants:
            reason = 'active_membership'
            allowed = True
        elif strict_mode == 'relaxed' and not settings.strict_tenant_enforcement:
            reason = 'relaxed_policy'
            allowed = True
        else:
            allowed = False
            reason = 'cross_tenant_membership_required'
    payload = {
        'status': 'ok' if allowed else 'denied',
        'tenant_id': effective_tenant_id,
        'requested_tenant_id': requested,
        'effective_tenant_id': effective_tenant_id,
        'actor_id': getattr(identity, 'user_id', 'anonymous'),
        'role': getattr(identity, 'role', 'viewer'),
        'route': route,
        'method': method.upper(),
        'decision': 'allow' if allowed else 'deny',
        'reason': reason,
        'policy': policy,
        'membership_count': len(memberships),
        'memberships': memberships,
        'accessible_tenants': sorted(active_tenants),
        'strict_enforcement': bool(settings.strict_tenant_enforcement),
    }
    persist_tenant_access_audit(
        tenant_id=effective_tenant_id,
        actor_id=getattr(identity, 'user_id', 'anonymous'),
        route=route,
        method=method,
        requested_tenant_id=requested,
        effective_tenant_id=effective_tenant_id,
        decision=payload['decision'],
        reason=reason,
        metadata_json={'policy': policy, 'strict_mode': strict_mode},
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                'code': 'TENANT_ROUTE_POLICY_DENIED',
                'route': route,
                'requested_tenant_id': requested,
                'effective_tenant_id': effective_tenant_id,
                'actor_id': getattr(identity, 'user_id', 'anonymous'),
                'reason': reason,
                'policy': policy,
            },
        )
    return payload


def build_tenant_enforcement_report(
    tenant_id: str = 'default',
    route: str = '/connectors/catalog',
    method: str = 'GET',
    actor_id: str = 'anonymous',
    role: str = 'viewer',
    identity_tenant_id: str | None = None,
    requested_tenant_id: str | None = None,
) -> dict[str, Any]:
    requested = (requested_tenant_id or tenant_id or identity_tenant_id or settings.tenant_default_id).strip() or settings.tenant_default_id
    identity_tenant_id = (identity_tenant_id or settings.tenant_default_id).strip() or settings.tenant_default_id
    memberships = list_actor_tenant_memberships(actor_id=actor_id)
    active_tenants = sorted({item['tenant_id'] for item in memberships if item.get('is_active', True)})
    policy = resolve_tenant_route_policy(requested, route)
    cross_tenant = requested != identity_tenant_id
    if not cross_tenant:
        decision = 'allow'
        reason = 'same_tenant'
    elif role == 'admin' and policy.get('allow_admin_override') and settings.tenant_allow_admin_override:
        decision = 'allow'
        reason = 'admin_override'
    elif role == 'service_account' and policy.get('allow_service_account_override') and not settings.strict_tenant_enforcement:
        decision = 'allow'
        reason = 'service_account_override'
    elif not policy.get('require_membership', settings.tenant_policy_default_require_membership):
        decision = 'allow'
        reason = 'membership_not_required'
    elif requested in active_tenants:
        decision = 'allow'
        reason = 'active_membership'
    else:
        decision = 'deny'
        reason = 'cross_tenant_membership_required'
    next_actions: list[str] = []
    if decision == 'deny':
        next_actions.append('Grant an active tenant membership or use a route policy that permits the required override mode.')
    elif cross_tenant and reason == 'admin_override':
        next_actions.append('Cross-tenant access is allowed here only because admin override is enabled for this route policy.')
    else:
        next_actions.append('Tenant enforcement is aligned for this route and actor.')
    if policy.get('resource_type') == 'secrets' and cross_tenant:
        next_actions.append('Secrets stay tenant-bound by default; prefer explicit memberships over cross-tenant overrides.')
    return {
        'status': 'ok',
        'tenant_id': requested,
        'requested_tenant_id': requested,
        'effective_tenant_id': requested if decision == 'allow' else identity_tenant_id,
        'actor_id': actor_id,
        'role': role,
        'identity_tenant_id': identity_tenant_id,
        'route': route,
        'method': method.upper(),
        'decision': decision,
        'reason': reason,
        'strict_enforcement': bool(settings.strict_tenant_enforcement),
        'policy': policy,
        'membership_count': len(memberships),
        'memberships': memberships,
        'accessible_tenants': active_tenants,
        'policy_count': len(list_tenant_route_policies(tenant_id=requested)),
        'policies': list_tenant_route_policies(tenant_id=requested),
        'next_actions': next_actions,
    }
