
from uuid import uuid4
from typing import Any
import json
import hashlib
import logging
import time
import httpx
import shutil
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from .config import settings
from .db import fetch_one, fetch_all, execute
from .schemas import *
from .ollama import OllamaClient, OllamaError
from .retrieval import search_grounded, ingest_paper, ingest_document, rag_governance_summary
from .audit import write_audit, enforce_scope
from .auth import authenticate_request, authorize_request, issue_token, list_effective_scopes, resolve_bootstrap_user, seed_rbac_defaults, write_request_audit
from .tenant import ensure_tenant_exists, upsert_tenant_membership, list_actor_tenant_memberships, resolve_effective_tenant, seed_tenant_defaults, build_tenant_context_report, list_tenants_summary, seed_tenant_policy_defaults, upsert_tenant_route_policy, build_tenant_enforcement_report, list_tenant_route_policies, enforce_tenant_route_policy
from .tenant_row import seed_tenant_row_policy_defaults, upsert_tenant_row_policy, build_tenant_row_isolation_report, list_tenant_row_policies, enforce_row_isolation_for_route, build_tenant_query_scope_report, filter_records_for_tenant_scope, seed_tenant_query_scope_target_defaults, upsert_tenant_query_scope_target, build_tenant_query_coverage_report, list_tenant_query_scope_targets
from .secrets import set_secret, get_secret, list_secrets, redact_secret
from .worker import enqueue_queue_item, cancel_queue_item, describe_queue_runtime
from .connectors import list_catalog, get_connector, prepare_connector_request, render_n8n_workflow, build_codex_prompt, execute_live_request, validate_connector_config, smoke_test_connector, catalog_rows_for_sync, build_workflow_manifest, normalize_service_name
from .lifecycle import seed_lifecycle_policy_defaults, upsert_retention_policy, build_data_lifecycle_report, run_data_lifecycle_cleanup

app = FastAPI(title='Phase3 Hybrid Companion Service', version='0.5.0-enterprise')
logger = logging.getLogger('control_plane')
ollama = OllamaClient()
PROJECT_ROOT = Path(__file__).resolve().parents[2]




def _scoped_tenant_id(request: Request | None, tenant_id: str | None = None) -> str:
    state_tenant_id = getattr(getattr(request, 'state', None), 'tenant_id', None) if request is not None else None
    return (state_tenant_id or tenant_id or settings.tenant_default_id).strip() or settings.tenant_default_id


def _apply_tenant_row_scope(request: Request | None, records: list[dict[str, Any]], resource_table: str, requested_tenant_id: str | None = None, action: str = 'read') -> list[dict[str, Any]]:
    scoped_tenant_id = _scoped_tenant_id(request, requested_tenant_id)
    payload = filter_records_for_tenant_scope(
        records=records,
        resource_table=resource_table,
        effective_tenant_id=scoped_tenant_id,
        requested_tenant_id=requested_tenant_id,
        identity=getattr(getattr(request, 'state', None), 'identity', None),
        action=action,
        route=getattr(getattr(request, 'url', None), 'path', '/') if request is not None else '/',
    )
    return payload.get('records', [])


def _fetch_job_status_payload(job_id: str, request: Request | None = None, tenant_id: str | None = None) -> dict[str, Any] | None:
    scoped_tenant_id = _scoped_tenant_id(request, tenant_id)
    requested_tenant_id = tenant_id or scoped_tenant_id
    row = None
    try:
        row = fetch_one(
            "SELECT job_id::text AS job_id, tenant_id, status, retry_count, max_retries, result, last_error FROM jobs WHERE job_id=%s AND tenant_id=%s",
            (job_id, scoped_tenant_id),
        )
    except Exception:
        row = None
    if not row:
        try:
            fallback = fetch_one(
                "SELECT job_id::text AS job_id, tenant_id, status, retry_count, max_retries, result, last_error FROM jobs WHERE job_id=%s",
                (job_id,),
            )
        except Exception:
            fallback = None
        if fallback:
            scoped_rows = _apply_tenant_row_scope(request, [dict(fallback)], 'jobs', requested_tenant_id=requested_tenant_id, action='read')
            row = scoped_rows[0] if scoped_rows else None
    if not row:
        return None
    payload = dict(row)
    payload.pop('tenant_id', None)
    return payload

def _extract_requested_tenant_id(request: Request, request_body: bytes | None = None) -> str:
    header_value = request.headers.get(settings.tenant_header_name, '').strip()
    if header_value:
        return header_value
    query_value = (request.query_params.get('tenant_id') or '').strip()
    if query_value:
        return query_value
    if request_body:
        try:
            payload = json.loads(request_body.decode())
            if isinstance(payload, dict):
                tenant_value = (payload.get('tenant_id') or '').strip()
                if tenant_value:
                    return tenant_value
        except Exception:
            pass
    return settings.tenant_default_id


def _persist_tenant_context_event(actor_id: str | None, requested_tenant_id: str, effective_tenant_id: str, route: str, resolution_mode: str, metadata_json: dict[str, Any] | None = None) -> None:
    _safe_db_execute(
        """INSERT INTO tenant_context_events (tenant_id, actor_id, requested_tenant_id, effective_tenant_id, route, resolution_mode, metadata_json)
           VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)""",
        (effective_tenant_id, actor_id, requested_tenant_id, effective_tenant_id, route, resolution_mode, json.dumps(metadata_json or {})),
    )


@app.on_event('startup')
def startup_seed_defaults():
    seed_rbac_defaults()
    seed_tenant_defaults()
    seed_tenant_policy_defaults()
    _seed_ai_registry_defaults()
    _seed_runtime_policy_defaults()
    seed_lifecycle_policy_defaults()
    seed_tenant_row_policy_defaults()
    seed_tenant_query_scope_target_defaults()
    seed_release_channel_defaults()



@app.middleware('http')
async def request_context_and_auth(request: Request, call_next):
    start = time.time()
    correlation_id = request.headers.get(settings.correlation_header_name, str(uuid4()))
    request.state.correlation_id = correlation_id
    request_body = await request.body()
    requested_tenant_id = _extract_requested_tenant_id(request, request_body)
    identity = None
    request.state.tenant_id = requested_tenant_id or settings.tenant_default_id
    request.state.actor_id = request.headers.get('x-actor-id', 'anonymous')
    if request.url.path != '/auth/token' and not request.url.path.startswith('/docs') and not request.url.path.startswith('/openapi'):
        if settings.auth_required:
            identity = authenticate_request(request)
            effective_tenant_id = resolve_effective_tenant(requested_tenant_id, identity)
            request.state.identity = identity
            request.state.tenant_id = effective_tenant_id
            request.state.actor_id = identity.user_id
            authorize_request(request, identity)
            tenant_policy_result = enforce_tenant_route_policy(requested_tenant_id, effective_tenant_id, request.url.path, request.method, identity)
            request.state.tenant_policy = tenant_policy_result
            request.state.tenant_id = tenant_policy_result.get('effective_tenant_id', effective_tenant_id)
            _persist_tenant_context_event(identity.user_id, requested_tenant_id, request.state.tenant_id, request.url.path, tenant_policy_result.get('reason', 'identity'), {'method': request.method, 'decision': tenant_policy_result.get('decision', 'allow')})
        else:
            request.state.tenant_id = requested_tenant_id or settings.tenant_default_id
            request.state.actor_id = request.headers.get('x-actor-id', 'anonymous')
    cached_response = None
    idem_key = request.headers.get('x-idempotency-key', '').strip()
    body_hash = hashlib.sha256(request_body).hexdigest() if request_body else ''
    if settings.enable_idempotency and idem_key and request.method.upper() == 'POST' and request.url.path != '/auth/token':
        try:
            row = fetch_one(
                "SELECT response_status, response_headers, response_body, request_hash FROM idempotency_keys WHERE tenant_id=%s AND idempotency_key=%s AND route=%s ORDER BY created_at DESC LIMIT 1",
                (getattr(request.state, 'tenant_id', settings.tenant_default_id), idem_key, request.url.path),
            )
            if row and row.get('request_hash') == body_hash and row.get('response_body') is not None:
                cached_response = JSONResponse(content=row['response_body'], status_code=row.get('response_status') or 200, headers={'x-idempotent-replay': 'true', settings.correlation_header_name: correlation_id})
        except Exception:
            cached_response = None
    if cached_response is not None:
        return cached_response
    response = await call_next(request)
    response.headers[settings.correlation_header_name] = correlation_id
    duration_ms = int((time.time() - start) * 1000)
    try:
        if settings.enable_idempotency and idem_key and request.method.upper() == 'POST' and request.url.path != '/auth/token':
            body_bytes = b''
            async for chunk in response.body_iterator:
                body_bytes += chunk
            try:
                payload = json.loads(body_bytes.decode() or '{}')
            except Exception:
                payload = {'raw': body_bytes.decode(errors='ignore')}
            _safe_db_execute(
                """INSERT INTO idempotency_keys (tenant_id, idempotency_key, route, request_hash, response_status, response_headers, response_body, last_seen_at, expires_at)
                VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,now(), now() + interval '24 hours')""",
                (getattr(request.state, 'tenant_id', settings.tenant_default_id), idem_key, request.url.path, body_hash, response.status_code, json.dumps({'content-type': response.headers.get('content-type')}), json.dumps(payload)),
            )
            response = JSONResponse(content=payload, status_code=response.status_code, headers=dict(response.headers))
        resource_type = request.url.path.strip('/').split('/')[0] or 'system'
        write_request_audit(getattr(getattr(request.state, 'identity', None), 'user_id', getattr(request.state, 'actor_id', None)), f"{request.method} {request.url.path}", resource_type, None, {'status_code': response.status_code, 'correlation_id': correlation_id, 'duration_ms': duration_ms}, tenant_id=getattr(request.state, 'tenant_id', settings.tenant_default_id))
        if settings.log_json:
            logger.info(json.dumps({'correlation_id': correlation_id, 'path': request.url.path, 'method': request.method, 'status_code': response.status_code, 'duration_ms': duration_ms, 'tenant_id': getattr(request.state, 'tenant_id', settings.tenant_default_id)}))
    except Exception:
        pass
    return response



def queue_depth():
    row = fetch_one("SELECT count(*)::int AS c FROM queue_items WHERE status IN ('queued','running')")
    return row['c'] if row else 0


def safe_queue_depth() -> int:
    try:
        return queue_depth()
    except Exception:
        return 0


def compute_metrics(tenant_id: str = 'default'):
    def q(sql, params=(tenant_id,)):
        row = fetch_one(sql, params)
        return row['c'] if row and 'c' in row else 0
    return {
        'queue_depth': q("SELECT count(*)::int AS c FROM queue_items WHERE tenant_id=%s AND status IN ('queued','running')"),
        'queued_jobs': q("SELECT count(*)::int AS c FROM jobs WHERE tenant_id=%s AND status='queued'"),
        'running_jobs': q("SELECT count(*)::int AS c FROM jobs WHERE tenant_id=%s AND status='running'"),
        'failed_jobs': q("SELECT count(*)::int AS c FROM jobs WHERE tenant_id=%s AND status='failed'"),
        'dead_letters': q("SELECT count(*)::int AS c FROM dead_letter_items WHERE tenant_id=%s"),
        'pending_approvals': q("SELECT count(*)::int AS c FROM approvals WHERE tenant_id=%s AND status='pending'"),
        'ai_artifacts_24h': q("SELECT count(*)::int AS c FROM ai_output_artifacts WHERE tenant_id=%s AND created_at >= now() - interval '24 hours'"),
        'published_posts': q("SELECT count(*)::int AS c FROM social_posts WHERE tenant_id=%s AND status='published'"),
        'avg_ai_latency_ms_24h': (fetch_one("SELECT COALESCE(avg(ai_latency_ms),0)::int AS c FROM ai_output_artifacts WHERE tenant_id=%s AND created_at >= now() - interval '24 hours'", (tenant_id,)) or {'c':0})['c'],
    }


def persist_snapshots(tenant_id: str='default'):
    metrics = compute_metrics(tenant_id)
    execute("INSERT INTO analytics_snapshots (tenant_id, snapshot_type, snapshot_data) VALUES (%s,'phase3_metrics',%s::jsonb)", (tenant_id, json.dumps(metrics)))
    execute("INSERT INTO reliability_snapshots (tenant_id, snapshot_data) VALUES (%s,%s::jsonb)", (tenant_id, json.dumps(metrics)))
    return metrics


def _validate_json(text: str, schema: dict | None):
    if not schema:
        return 'not_requested', None
    try:
        data = json.loads(text)
    except Exception:
        return 'invalid_json', None
    required = schema.get('required', [])
    for field in required:
        if field not in data:
            return 'invalid_schema', data
    return 'valid', data


def _safe_db_execute(sql: str, params: tuple[Any, ...]) -> None:
    try:
        execute(sql, params)
    except Exception:
        pass


def _log_connector_execution(tenant_id: str, service_name: str, operation_id: str, execution_mode: str, request_payload: dict, response_payload: dict | None = None, status: str = 'ok', error_message: str | None = None):
    _safe_db_execute(
        """INSERT INTO connector_execution_log (tenant_id, service_name, operation_id, execution_mode, request_payload, response_payload, status, error_message, last_validated_at)
        VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,now())""",
        (tenant_id, service_name, operation_id, execution_mode, json.dumps(request_payload or {}), json.dumps(response_payload or {}), status, error_message),
    )
    success_inc = 1 if status == 'ok' else 0
    failure_inc = 0 if status == 'ok' else 1
    _safe_db_execute(
        """INSERT INTO connector_metrics (tenant_id, service_name, execution_count, success_count, failure_count, retry_count, failure_rate_percent, last_success_at, last_failure_at)
        VALUES (%s,%s,1,%s,%s,0,%s,%s,%s)
        ON CONFLICT (tenant_id, service_name)
        DO UPDATE SET execution_count = connector_metrics.execution_count + 1,
                      success_count = connector_metrics.success_count + EXCLUDED.success_count,
                      failure_count = connector_metrics.failure_count + EXCLUDED.failure_count,
                      failure_rate_percent = ROUND(((connector_metrics.failure_count + EXCLUDED.failure_count)::numeric / GREATEST((connector_metrics.execution_count + 1),1)) * 100, 2),
                      last_success_at = CASE WHEN EXCLUDED.last_success_at IS NOT NULL THEN EXCLUDED.last_success_at ELSE connector_metrics.last_success_at END,
                      last_failure_at = CASE WHEN EXCLUDED.last_failure_at IS NOT NULL THEN EXCLUDED.last_failure_at ELSE connector_metrics.last_failure_at END,
                      updated_at = now()
        """,
        (tenant_id, service_name, success_inc, failure_inc, float(0 if status == 'ok' else 100), None if status != 'ok' else time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), None if status == 'ok' else time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())),
    )


def _upsert_workflow_template(tenant_id: str, service_name: str, operation_id: str, workflow_name: str, workflow: dict[str, Any], implementation_status: str):
    _safe_db_execute(
        """INSERT INTO workflow_templates (tenant_id, service_name, operation_id, workflow_name, workflow_json, implementation_status)
        VALUES (%s,%s,%s,%s,%s::jsonb,%s)
        ON CONFLICT (tenant_id, service_name, operation_id, workflow_name)
        DO UPDATE SET workflow_json=EXCLUDED.workflow_json, implementation_status=EXCLUDED.implementation_status, updated_at=now()""",
        (tenant_id, service_name, operation_id, workflow_name, json.dumps(workflow), implementation_status),
    )


def _upsert_credential_metadata(tenant_id: str, service_name: str, required_credentials: list[str], optional_credentials: list[str], present_credentials: list[str], missing_credentials: list[str], notes: str):
    all_keys = []
    for key in required_credentials + optional_credentials:
        if key and key not in all_keys:
            all_keys.append(key)
    present_set = set(present_credentials)
    missing_set = set(missing_credentials)
    for key in all_keys:
        _safe_db_execute(
            """INSERT INTO connector_credentials_meta (tenant_id, service_name, credential_key, is_required, configured, last_validated_at, error_message, metadata)
            VALUES (%s,%s,%s,%s,%s,now(),%s,%s::jsonb)
            ON CONFLICT (tenant_id, service_name, credential_key)
            DO UPDATE SET configured=EXCLUDED.configured, last_validated_at=EXCLUDED.last_validated_at, error_message=EXCLUDED.error_message, metadata=EXCLUDED.metadata, updated_at=now()""",
            (tenant_id, service_name, key, key in required_credentials, key in present_set and key not in missing_set, None if key not in missing_set else notes or f'missing {key}', json.dumps({'present': key in present_set, 'missing': key in missing_set})),
        )


def _record_smoke_test(tenant_id: str, service_name: str, operation_id: str | None, dry_run: bool, configured: bool, status: str, result_payload: dict, error_message: str | None = None):
    _safe_db_execute(
        """INSERT INTO smoke_test_results (tenant_id, service_name, operation_id, dry_run, configured, status, result_payload, error_message)
        VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s)""",
        (tenant_id, service_name, operation_id, dry_run, configured, status, json.dumps(result_payload or {}), error_message),
    )


def _upsert_connector_registry_entry(row: dict[str, Any]) -> None:
    _safe_db_execute(
        """INSERT INTO connector_registry (tenant_id, service_name, category, integration_mode, auth_type, base_url_env, required_credentials, optional_credentials, implementation_status, notes, docs_reference)
        VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s)
        ON CONFLICT (tenant_id, service_name)
        DO UPDATE SET category=EXCLUDED.category, integration_mode=EXCLUDED.integration_mode, auth_type=EXCLUDED.auth_type, base_url_env=EXCLUDED.base_url_env, required_credentials=EXCLUDED.required_credentials, optional_credentials=EXCLUDED.optional_credentials, implementation_status=EXCLUDED.implementation_status, notes=EXCLUDED.notes, docs_reference=EXCLUDED.docs_reference, updated_at=now()""",
        (row['tenant_id'], row['service_name'], row['category'], row['integration_mode'], row['auth_type'], row['base_url_env'], json.dumps(row.get('required_credentials', [])), json.dumps(row.get('optional_credentials', [])), row['implementation_status'], row.get('notes', ''), row.get('docs_reference')),
    )


def _sync_connector_registry(tenant_id: str = 'default') -> list[str]:
    services: list[str] = []
    for row in catalog_rows_for_sync(tenant_id=tenant_id):
        _upsert_connector_registry_entry(row)
        services.append(row['service_name'])
    return services

ALLOWED_WORKFLOW_VERSION_STATUSES = {"draft", "tested", "approved", "published"}
ALLOWED_RELEASE_CHANNEL_TYPES = {"manual_inspection", "webhook_notify", "file_drop"}
ALLOWED_RELEASE_CHANNEL_EXECUTION_MODES = {"manual_handoff", "copy_bundle", "webhook_preview", "webhook_notify"}
RELEASE_CHANNEL_MEMORY_CACHE: dict[str, dict[str, dict[str, Any]]] = {}
RELEASE_CHANNEL_EXECUTION_MEMORY_CACHE: dict[str, list[dict[str, Any]]] = {}
DEFAULT_RELEASE_CHANNELS = [
    {
        'channel_name': 'manual_bundle_review',
        'channel_type': 'manual_inspection',
        'enabled': True,
        'destination_path': None,
        'endpoint_url': None,
        'auth_secret_ref': None,
        'metadata_json': {'notes': 'Default manual review channel for staged release publication bundles.'},
        'source': 'default',
    },
]


def _validate_release_channel_type(value: str) -> str:
    channel_type = (value or '').strip().lower()
    if channel_type not in ALLOWED_RELEASE_CHANNEL_TYPES:
        raise HTTPException(status_code=400, detail={'code': 'INVALID_RELEASE_CHANNEL_TYPE', 'message': channel_type or value})
    return channel_type


def _release_channel_default_item(channel_name: str = 'manual_bundle_review', tenant_id: str = 'default') -> dict[str, Any]:
    base = next((item for item in DEFAULT_RELEASE_CHANNELS if item['channel_name'] == channel_name), DEFAULT_RELEASE_CHANNELS[0])
    return {
        'tenant_id': tenant_id,
        'channel_name': base['channel_name'],
        'channel_type': base['channel_type'],
        'enabled': bool(base['enabled']),
        'destination_path': base.get('destination_path'),
        'endpoint_url': base.get('endpoint_url'),
        'auth_secret_ref': base.get('auth_secret_ref'),
        'auth_secret_configured': False,
        'metadata_json': dict(base.get('metadata_json') or {}),
        'created_by': None,
        'last_planned_at': None,
        'last_published_at': None,
        'created_at': None,
        'updated_at': None,
        'source': 'default',
    }


def seed_release_channel_defaults(tenant_id: str | None = None) -> None:
    tenant_id = (tenant_id or settings.tenant_default_id).strip() or settings.tenant_default_id
    for item in DEFAULT_RELEASE_CHANNELS:
        _safe_db_execute(
            """INSERT INTO release_channels (tenant_id, channel_name, channel_type, enabled, destination_path, endpoint_url, auth_secret_ref, metadata_json, created_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
               ON CONFLICT (tenant_id, channel_name) DO NOTHING""",
            (tenant_id, item['channel_name'], item['channel_type'], bool(item['enabled']), item.get('destination_path'), item.get('endpoint_url'), item.get('auth_secret_ref'), json.dumps(item.get('metadata_json') or {}), 'system'),
        )


def _upsert_release_channel(tenant_id: str, channel_name: str, channel_type: str, enabled: bool = True, destination_path: str | None = None, endpoint_url: str | None = None, auth_secret_ref: str | None = None, created_by: str | None = None, metadata_json: dict[str, Any] | None = None) -> dict[str, Any]:
    tenant_id = (tenant_id or settings.tenant_default_id).strip() or settings.tenant_default_id
    channel_name = (channel_name or '').strip()
    if not channel_name:
        raise HTTPException(status_code=400, detail={'code': 'CHANNEL_NAME_REQUIRED', 'message': 'channel_name is required'})
    channel_type = _validate_release_channel_type(channel_type)
    payload = metadata_json or {}
    _safe_db_execute(
        """INSERT INTO release_channels (tenant_id, channel_name, channel_type, enabled, destination_path, endpoint_url, auth_secret_ref, metadata_json, created_by)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
           ON CONFLICT (tenant_id, channel_name)
           DO UPDATE SET channel_type=EXCLUDED.channel_type, enabled=EXCLUDED.enabled, destination_path=EXCLUDED.destination_path, endpoint_url=EXCLUDED.endpoint_url, auth_secret_ref=EXCLUDED.auth_secret_ref, metadata_json=EXCLUDED.metadata_json, updated_at=now()""",
        (tenant_id, channel_name, channel_type, bool(enabled), destination_path, endpoint_url, auth_secret_ref, json.dumps(payload), created_by),
    )
    RELEASE_CHANNEL_MEMORY_CACHE.setdefault(tenant_id, {})[channel_name] = {
        'tenant_id': tenant_id, 'channel_name': channel_name, 'channel_type': channel_type, 'enabled': bool(enabled),
        'destination_path': destination_path, 'endpoint_url': endpoint_url, 'auth_secret_ref': auth_secret_ref,
        'auth_secret_configured': bool(auth_secret_ref and get_secret(auth_secret_ref, tenant_id=tenant_id, reveal=False)),
        'metadata_json': payload, 'created_by': created_by, 'last_planned_at': None, 'last_published_at': None, 'created_at': None, 'updated_at': None, 'source': 'memory',
    }
    rows = _list_release_channels(tenant_id=tenant_id)
    channel = next((item for item in rows if item['channel_name'] == channel_name), None)
    if channel is None:
        channel = {
            'tenant_id': tenant_id, 'channel_name': channel_name, 'channel_type': channel_type, 'enabled': bool(enabled),
            'destination_path': destination_path, 'endpoint_url': endpoint_url, 'auth_secret_ref': auth_secret_ref,
            'auth_secret_configured': bool(auth_secret_ref and get_secret(auth_secret_ref, tenant_id=tenant_id, reveal=False)),
            'metadata_json': payload, 'created_by': created_by, 'last_planned_at': None, 'last_published_at': None, 'created_at': None, 'updated_at': None, 'source': 'request',
        }
    return channel


def _list_release_channels(tenant_id: str = 'default', enabled_only: bool = False) -> list[dict[str, Any]]:
    tenant_id = (tenant_id or settings.tenant_default_id).strip() or settings.tenant_default_id
    items: list[dict[str, Any]] = []
    try:
        sql = "SELECT tenant_id, channel_name, channel_type, enabled, destination_path, endpoint_url, auth_secret_ref, metadata_json, created_by, last_planned_at::text AS last_planned_at, last_published_at::text AS last_published_at, created_at::text AS created_at, updated_at::text AS updated_at FROM release_channels WHERE tenant_id=%s"
        params = [tenant_id]
        if enabled_only:
            sql += " AND enabled=true"
        sql += " ORDER BY channel_name ASC"
        rows = fetch_all(sql, tuple(params)) or []
        for row in rows:
            item = dict(row)
            item['metadata_json'] = item.get('metadata_json') or {}
            item['auth_secret_configured'] = bool(item.get('auth_secret_ref') and get_secret(item['auth_secret_ref'], tenant_id=tenant_id, reveal=False))
            item['source'] = 'db'
            items.append(item)
    except Exception:
        items = []
    cache_items = list((RELEASE_CHANNEL_MEMORY_CACHE.get(tenant_id) or {}).values())
    existing_names = {item['channel_name'] for item in items}
    for item in cache_items:
        if enabled_only and not item.get('enabled'):
            continue
        if item['channel_name'] not in existing_names:
            items.append(dict(item))
            existing_names.add(item['channel_name'])
    default_item = _release_channel_default_item(tenant_id=tenant_id)
    if default_item['channel_name'] not in existing_names and (default_item.get('enabled') or not enabled_only):
        items.append(default_item)
        existing_names.add(default_item['channel_name'])
    if not items and not enabled_only:
        return [default_item]
    if not items and enabled_only:
        return [default_item] if default_item['enabled'] else []
    items.sort(key=lambda item: item['channel_name'])
    return items


def _evaluate_release_channel_item(channel: dict[str, Any], tenant_id: str, release_version: str, publication_ready: bool) -> dict[str, Any]:
    metadata_json = dict(channel.get('metadata_json') or {})
    channel_type = channel.get('channel_type') or settings.release_channel_default_type
    enabled = bool(channel.get('enabled', True))
    blocking_reasons: list[str] = []
    destination = channel.get('destination_path') or channel.get('endpoint_url')
    auth_secret_ref = channel.get('auth_secret_ref')
    auth_secret_configured = bool(channel.get('auth_secret_configured'))
    if auth_secret_ref and not auth_secret_configured:
        blocking_reasons.append(f'missing auth secret {auth_secret_ref}')
    if not enabled:
        blocking_reasons.append('channel disabled')
    if channel_type == 'webhook_notify' and not channel.get('endpoint_url'):
        blocking_reasons.append('endpoint_url required for webhook_notify')
    if channel_type == 'file_drop' and not channel.get('destination_path'):
        blocking_reasons.append('destination_path required for file_drop')
    if not publication_ready:
        blocking_reasons.append('release publication preflight/checksum not ready')
    ready = enabled and not blocking_reasons
    if channel_type == 'manual_inspection':
        destination = destination or 'manual_review'
        recommended_action = 'Review the staged publication bundle and promote it through your manual release checklist.'
    elif channel_type == 'webhook_notify':
        recommended_action = 'Send a release-ready notification to the configured webhook consumer once the publication bundle is approved.'
    else:
        destination = destination or settings.release_channel_default_destination
        recommended_action = 'Copy the published release bundle into the configured destination path and record the checksum alongside it.'
    return {
        'channel_name': channel.get('channel_name') or 'unknown',
        'channel_type': channel_type,
        'enabled': enabled,
        'ready': ready,
        'publication_ready': publication_ready,
        'requires_publication_bundle': True,
        'destination': destination,
        'auth_secret_configured': auth_secret_configured,
        'blocking_reasons': blocking_reasons,
        'recommended_action': recommended_action,
        'metadata_json': {**metadata_json, 'release_version': release_version, 'source': channel.get('source', 'db')},
    }


def _build_release_channel_plan(tenant_id: str = 'default', release_version: str | None = None, package_filename: str | None = None, source_package: str | None = None, include_publication_bundle: bool = False, output_path: str | None = None, created_by: str | None = None, persist: bool = True) -> dict[str, Any]:
    manifest = _build_release_manifest(tenant_id=tenant_id, release_version=release_version, package_filename=package_filename, source_package=source_package, created_by=created_by, persist=False)
    checksum_validation = _validate_release_manifest(manifest, tenant_id=tenant_id, persist=False)
    preflight = _build_release_preflight(tenant_id=tenant_id, release_version=manifest['release_version'], persist=False)
    publication_ready = bool(preflight['ready'] and checksum_validation['valid'])
    publication_preview = None
    if include_publication_bundle:
        publication_preview = _build_release_publication(tenant_id=tenant_id, release_version=manifest['release_version'], package_filename=package_filename, source_package=source_package, output_path=output_path, created_by=created_by, persist=False)
    channels = _list_release_channels(tenant_id=tenant_id, enabled_only=False)
    planned_channels = [_evaluate_release_channel_item(channel, tenant_id, manifest['release_version'], publication_ready) for channel in channels]
    ready_count = sum(1 for item in planned_channels if item['ready'])
    next_actions: list[str] = []
    if not publication_ready:
        next_actions.append('Resolve release preflight/checksum blockers before attempting channel distribution.')
    if not planned_channels:
        next_actions.append('Configure at least one release channel or rely on the default manual review flow.')
    elif ready_count == 0:
        next_actions.append('No release channels are ready yet. Fill the blocking configuration on the planned channels.')
    else:
        next_actions.append('At least one release channel is ready. Promote the staged publication bundle using the recommended channel actions.')
    payload = {
        'status': 'ok',
        'tenant_id': tenant_id,
        'release_version': manifest['release_version'],
        'publication_ready': publication_ready,
        'bundle_preview_path': publication_preview.get('output_path') if publication_preview else None,
        'count': len(planned_channels),
        'ready_count': ready_count,
        'planned_channels': planned_channels,
        'next_actions': next_actions,
    }
    if persist:
        for item in planned_channels:
            _safe_db_execute(
                """INSERT INTO release_channel_events (tenant_id, channel_name, release_version, action, status, package_path, metadata_json, created_by)
                   VALUES (%s,%s,%s,'plan',%s,%s,%s::jsonb,%s)""",
                (tenant_id, item['channel_name'], manifest['release_version'], 'ready' if item['ready'] else 'blocked', publication_preview.get('output_path') if publication_preview else None, json.dumps(item), created_by),
            )
            _safe_db_execute(
                "UPDATE release_channels SET last_planned_at=now() WHERE tenant_id=%s AND channel_name=%s",
                (tenant_id, item['channel_name']),
            )
    return payload


def _list_release_channel_events(tenant_id: str = 'default', limit: int = 20) -> list[dict[str, Any]]:
    try:
        rows = fetch_all(
            "SELECT channel_name, release_version, action, status, package_path, metadata_json, created_by, created_at::text AS created_at FROM release_channel_events WHERE tenant_id=%s ORDER BY created_at DESC LIMIT %s",
            (tenant_id, limit),
        ) or []
        return [dict(row) for row in rows]
    except Exception:
        return []





def _validate_release_channel_execution_mode(value: str) -> str:
    execution_mode = (value or '').strip().lower()
    if execution_mode not in ALLOWED_RELEASE_CHANNEL_EXECUTION_MODES:
        raise HTTPException(status_code=400, detail={'code': 'INVALID_RELEASE_CHANNEL_EXECUTION_MODE', 'message': execution_mode or value})
    return execution_mode


def _release_channel_execution_dir() -> Path:
    configured = (settings.release_channel_execution_dir or '').strip()
    path = Path(configured) if configured else (PROJECT_ROOT / 'artifacts' / 'release_channel_executions')
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _release_channel_execution_output_path(tenant_id: str, release_version: str, channel_name: str, output_path: str | None = None, suffix: str = '.json') -> Path:
    if output_path:
        target = Path(output_path)
        if not target.is_absolute():
            target = PROJECT_ROOT / target
    else:
        safe_version = ''.join(ch if ch.isalnum() or ch in {'-', '_', '.'} else '_' for ch in release_version)
        safe_channel = ''.join(ch if ch.isalnum() or ch in {'-', '_', '.'} else '_' for ch in channel_name)
        target = _release_channel_execution_dir() / f'{tenant_id}_{safe_version}_{safe_channel}{suffix}'
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _persist_release_channel_execution_record(record: dict[str, Any], persist: bool = True) -> None:
    tenant_id = record.get('tenant_id') or settings.tenant_default_id
    RELEASE_CHANNEL_EXECUTION_MEMORY_CACHE.setdefault(tenant_id, []).insert(0, dict(record))
    RELEASE_CHANNEL_EXECUTION_MEMORY_CACHE[tenant_id] = RELEASE_CHANNEL_EXECUTION_MEMORY_CACHE[tenant_id][:50]
    if not persist:
        return
    _safe_db_execute(
        """INSERT INTO release_channel_executions (tenant_id, channel_name, release_version, execution_mode, execution_status, dry_run, package_path, output_path, delivery_ref, metadata_json, created_by, started_at, finished_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s::timestamptz,%s::timestamptz)""",
        (
            tenant_id,
            record.get('channel_name'),
            record.get('release_version'),
            record.get('execution_mode'),
            record.get('execution_status'),
            bool(record.get('dry_run', True)),
            record.get('package_path'),
            record.get('output_path'),
            record.get('delivery_ref'),
            json.dumps(record.get('metadata_json') or {}),
            record.get('created_by'),
            record.get('started_at'),
            record.get('finished_at'),
        ),
    )


def _list_release_channel_executions(tenant_id: str = 'default', limit: int = 20) -> list[dict[str, Any]]:
    tenant_id = (tenant_id or settings.tenant_default_id).strip() or settings.tenant_default_id
    items: list[dict[str, Any]] = []
    try:
        rows = fetch_all(
            """SELECT tenant_id, channel_name, release_version, execution_mode, execution_status, dry_run, package_path, output_path, delivery_ref, created_by, metadata_json, started_at::text AS started_at, finished_at::text AS finished_at, created_at::text AS created_at
               FROM release_channel_executions WHERE tenant_id=%s ORDER BY created_at DESC LIMIT %s""",
            (tenant_id, limit),
        ) or []
        items = [dict(row) for row in rows]
    except Exception:
        items = []
    existing = {(item.get('channel_name'), item.get('release_version'), item.get('created_at')) for item in items}
    for item in RELEASE_CHANNEL_EXECUTION_MEMORY_CACHE.get(tenant_id, []):
        key = (item.get('channel_name'), item.get('release_version'), item.get('created_at'))
        if key not in existing:
            items.append(dict(item))
            existing.add(key)
    items.sort(key=lambda item: item.get('created_at') or '', reverse=True)
    return items[:limit]


def _execute_release_channel_item(channel: dict[str, Any], release_version: str, package_path: str | None, created_by: str | None = None, dry_run: bool = True, execute_webhooks: bool = False, persist: bool = True) -> dict[str, Any]:
    tenant_id = (channel.get('tenant_id') or settings.tenant_default_id).strip() or settings.tenant_default_id
    channel_name = channel.get('channel_name') or 'unknown'
    channel_type = channel.get('channel_type') or settings.release_channel_default_type
    ready = bool(channel.get('ready'))
    publication_ready = bool(channel.get('publication_ready'))
    blocking_reasons = list(channel.get('blocking_reasons') or [])
    destination = channel.get('destination')
    created_at = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    started_at = created_at
    delivery_ref = None
    output_path = None
    steps: list[str] = []
    metadata_json = dict(channel.get('metadata_json') or {})
    execution_mode = 'manual_handoff' if channel_type == 'manual_inspection' else ('copy_bundle' if channel_type == 'file_drop' else ('webhook_notify' if execute_webhooks else 'webhook_preview'))
    _validate_release_channel_execution_mode(execution_mode)
    status = 'blocked'
    if not ready:
        status = 'blocked'
        steps.append('Channel is not ready. Resolve blocking reasons before execution.')
    elif channel_type == 'manual_inspection':
        target = _release_channel_execution_output_path(tenant_id, release_version, channel_name, suffix='_handoff.json')
        handoff = {
            'tenant_id': tenant_id,
            'channel_name': channel_name,
            'channel_type': channel_type,
            'release_version': release_version,
            'package_path': package_path,
            'destination': destination or 'manual_review',
            'recommended_action': channel.get('recommended_action'),
            'metadata_json': metadata_json,
        }
        target.write_text(json.dumps(handoff, indent=2, ensure_ascii=False) + '\n')
        delivery_ref = str(target)
        output_path = str(target)
        steps.append('Generated manual handoff instructions for operator review.')
        status = 'prepared' if not dry_run else 'dry_run'
    elif channel_type == 'file_drop':
        if not package_path:
            blocking_reasons.append('publication bundle path missing')
            status = 'blocked'
        else:
            source = Path(package_path)
            target_dir = Path(destination or settings.release_channel_default_destination)
            if not target_dir.is_absolute():
                target_dir = PROJECT_ROOT / target_dir
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / source.name
            output_path = str(target)
            delivery_ref = str(target)
            steps.append(f'Prepared file-drop target {target}.')
            if dry_run:
                status = 'dry_run'
            else:
                shutil.copy2(source, target)
                status = 'delivered'
                steps.append('Copied publication bundle into the configured destination path.')
    else:
        webhook_payload = {
            'tenant_id': tenant_id,
            'channel_name': channel_name,
            'release_version': release_version,
            'package_path': package_path,
            'publication_ready': publication_ready,
            'destination': destination,
            'metadata_json': metadata_json,
        }
        preview = _release_channel_execution_output_path(tenant_id, release_version, channel_name, suffix='_webhook_preview.json')
        preview.write_text(json.dumps(webhook_payload, indent=2, ensure_ascii=False) + '\n')
        output_path = str(preview)
        delivery_ref = str(preview)
        steps.append('Generated webhook payload preview for downstream notification.')
        if dry_run or not execute_webhooks:
            status = 'dry_run' if dry_run else 'prepared'
        else:
            headers = {'Content-Type': 'application/json'}
            if channel.get('auth_secret_ref'):
                secret = get_secret(channel['auth_secret_ref'], tenant_id=tenant_id, reveal=True)
                if secret and secret.get('value'):
                    headers['Authorization'] = f"Bearer {secret['value']}"
            try:
                with httpx.Client(timeout=settings.connector_timeout_seconds, headers=headers) as client:
                    response = client.post(channel.get('destination') or channel.get('endpoint_url'), json=webhook_payload)
                    response.raise_for_status()
                status = 'delivered'
                steps.append('Sent webhook notification to the configured release channel endpoint.')
            except Exception as exc:
                status = 'failed'
                blocking_reasons.append(f'webhook send failed: {exc}')
    finished_at = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    record = {
        'tenant_id': tenant_id,
        'channel_name': channel_name,
        'release_version': release_version,
        'execution_mode': execution_mode,
        'execution_status': status,
        'dry_run': bool(dry_run),
        'package_path': package_path,
        'output_path': output_path,
        'delivery_ref': delivery_ref,
        'created_by': created_by,
        'metadata_json': {**metadata_json, 'blocking_reasons': blocking_reasons, 'steps': steps, 'channel_type': channel_type, 'ready': ready},
        'started_at': started_at,
        'finished_at': finished_at,
        'created_at': created_at,
    }
    _persist_release_channel_execution_record(record, persist=persist)
    if persist:
        _safe_db_execute(
            """INSERT INTO release_channel_events (tenant_id, channel_name, release_version, action, status, package_path, metadata_json, created_by)
               VALUES (%s,%s,%s,'execute',%s,%s,%s::jsonb,%s)""",
            (tenant_id, channel_name, release_version, status, output_path or package_path, json.dumps(record['metadata_json']), created_by),
        )
        _safe_db_execute(
            "UPDATE release_channels SET last_published_at=CASE WHEN %s IN ('delivered','prepared') THEN now() ELSE last_published_at END, last_execution_status=%s, last_execution_mode=%s, last_executed_at=now(), updated_at=now() WHERE tenant_id=%s AND channel_name=%s",
            (status, status, execution_mode, tenant_id, channel_name),
        )
    return {
        'channel_name': channel_name,
        'channel_type': channel_type,
        'execution_mode': execution_mode,
        'status': status,
        'dry_run': bool(dry_run),
        'ready': ready,
        'publication_ready': publication_ready,
        'delivery_ref': delivery_ref,
        'output_path': output_path,
        'blocking_reasons': blocking_reasons,
        'steps': steps,
        'metadata_json': {**metadata_json, 'created_at': created_at},
    }


def _build_release_channel_execution(tenant_id: str = 'default', release_version: str | None = None, package_filename: str | None = None, source_package: str | None = None, channel_names: list[str] | None = None, include_publication_bundle: bool = True, output_path: str | None = None, created_by: str | None = None, persist: bool = True, dry_run: bool = True, execute_webhooks: bool = False) -> dict[str, Any]:
    plan = _build_release_channel_plan(tenant_id=tenant_id, release_version=release_version, package_filename=package_filename, source_package=source_package, include_publication_bundle=include_publication_bundle, output_path=output_path, created_by=created_by, persist=False)
    selected = [item for item in plan.get('planned_channels', []) if not channel_names or item.get('channel_name') in set(channel_names)]
    bundle_path = plan.get('bundle_preview_path')
    if not bundle_path and include_publication_bundle:
        publication = _build_release_publication(tenant_id=tenant_id, release_version=plan['release_version'], package_filename=package_filename, source_package=source_package, output_path=output_path, created_by=created_by, persist=False)
        bundle_path = publication.get('output_path')
    execution_items = [_execute_release_channel_item(item, plan['release_version'], bundle_path, created_by=created_by, dry_run=dry_run, execute_webhooks=execute_webhooks or settings.release_channel_execute_webhooks, persist=persist) for item in selected]
    delivered_count = sum(1 for item in execution_items if item['status'] == 'delivered')
    prepared_count = sum(1 for item in execution_items if item['status'] in {'prepared', 'dry_run'})
    blocked_count = sum(1 for item in execution_items if item['status'] in {'blocked', 'failed'})
    next_actions = []
    if blocked_count:
        next_actions.append('Resolve blocked or failed release channel executions before promoting the release externally.')
    if dry_run:
        next_actions.append('Dry-run execution generated operator-facing artifacts only. Re-run with dry_run=false once the target channels are approved.')
    elif delivered_count:
        next_actions.append('Record the delivered channel refs alongside the publication bundle for audit and rollback drills.')
    payload = {
        'status': 'ok',
        'tenant_id': tenant_id,
        'release_version': plan['release_version'],
        'publication_ready': bool(plan.get('publication_ready')),
        'bundle_path': bundle_path,
        'count': len(execution_items),
        'delivered_count': delivered_count,
        'prepared_count': prepared_count,
        'blocked_count': blocked_count,
        'execution_items': execution_items,
        'next_actions': next_actions,
    }
    return payload


def _fetch_workflow_version(tenant_id: str, workflow_id: str, version: int):
    try:
        return fetch_one(
            "SELECT workflow_id, version, status AS workflow_status, definition_json, created_at::text AS created_at, updated_at::text AS updated_at FROM workflow_versions WHERE tenant_id=%s AND workflow_id=%s AND version=%s",
            (tenant_id, workflow_id, version),
        )
    except Exception:
        return None


def _fetch_workflow_versions(tenant_id: str, workflow_id: str):
    try:
        return fetch_all(
            "SELECT workflow_id, version, status AS workflow_status, definition_json, created_at::text AS created_at, updated_at::text AS updated_at FROM workflow_versions WHERE tenant_id=%s AND workflow_id=%s ORDER BY version DESC",
            (tenant_id, workflow_id),
        ) or []
    except Exception:
        return []


def _fetch_latest_workflow_version(tenant_id: str, workflow_id: str) -> int:
    try:
        row = fetch_one("SELECT COALESCE(max(version), 0) AS max_version FROM workflow_versions WHERE tenant_id=%s AND workflow_id=%s", (tenant_id, workflow_id))
        return int((row or {}).get('max_version') or 0)
    except Exception:
        return 0


def _record_workflow_version_event(tenant_id: str, workflow_id: str, version: int | None, action: str, actor_id: str | None = None, source_version: int | None = None, target_version: int | None = None, metadata_json: dict[str, Any] | None = None):
    _safe_db_execute(
        """INSERT INTO workflow_version_events (tenant_id, workflow_id, version, action, actor_id, source_version, target_version, metadata_json)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
        (tenant_id, workflow_id, version, action, actor_id, source_version, target_version, json.dumps(metadata_json or {})),
    )


def _validate_workflow_version_status(value: str) -> str:
    status_value = (value or '').strip().lower()
    if status_value not in ALLOWED_WORKFLOW_VERSION_STATUSES:
        raise HTTPException(status_code=400, detail={'code': 'INVALID_WORKFLOW_STATUS', 'message': status_value or value})
    return status_value


def _workflow_version_response_payload(tenant_id: str, workflow_id: str, version: int, workflow_status: str, definition_json: dict[str, Any]):
    return {
        'status': 'ok',
        'tenant_id': tenant_id,
        'workflow_id': workflow_id,
        'version': version,
        'workflow_status': workflow_status,
        'definition_json': definition_json or {},
    }


def _seed_ai_registry_defaults() -> None:
    default_models = [
        {
            'name': settings.ollama_model,
            'type': 'local',
            'capabilities': ['chat', 'text_generation', 'fallback_chat', 'summarize', 'retrieve_answer'],
            'latency_profile': 'medium',
            'metadata_json': {'default': True, 'modes': ['deterministic', 'creative'], 'fallback_models': [], 'provider': 'ollama'},
        },
        {
            'name': settings.ollama_embedding_model,
            'type': 'local',
            'capabilities': ['embeddings', 'retrieval'],
            'latency_profile': 'fast',
            'metadata_json': {'default': True, 'modes': ['deterministic'], 'provider': 'ollama'},
        },
    ]
    for row in default_models:
        _safe_db_execute(
            """INSERT INTO model_registry (tenant_id, name, type, capabilities, latency_profile, metadata_json)
               VALUES (%s,%s,%s,%s::jsonb,%s,%s::jsonb)
               ON CONFLICT (tenant_id, name) DO UPDATE SET
                 type=EXCLUDED.type,
                 capabilities=EXCLUDED.capabilities,
                 latency_profile=EXCLUDED.latency_profile,
                 metadata_json=EXCLUDED.metadata_json,
                 updated_at=now()""",
            ('default', row['name'], row['type'], json.dumps(row['capabilities']), row['latency_profile'], json.dumps(row['metadata_json'])),
        )
    default_prompts = [
        {
            'name': 'fallback_chat',
            'version': 'phase3.v1',
            'template': settings.fallback_chat_system_prompt,
            'model_compatibility': [settings.ollama_model],
            'mode': 'deterministic',
        },
        {
            'name': 'summarize',
            'version': 'phase3.summary.v1',
            'template': 'Summarize the provided content faithfully. Preserve important constraints and cite source references when present.',
            'model_compatibility': [settings.ollama_model],
            'mode': 'deterministic',
        },
        {
            'name': 'retrieve_answer',
            'version': 'phase3.retrieve.v1',
            'template': 'Answer using the provided evidence. Include source references from the context when available. If evidence is weak, say so plainly.',
            'model_compatibility': [settings.ollama_model],
            'mode': 'deterministic',
        },
    ]
    for row in default_prompts:
        _safe_db_execute(
            """INSERT INTO prompt_registry (tenant_id, name, version, template, model_compatibility, mode)
               VALUES (%s,%s,%s,%s,%s::jsonb,%s)
               ON CONFLICT (tenant_id, name, version) DO UPDATE SET
                 template=EXCLUDED.template,
                 model_compatibility=EXCLUDED.model_compatibility,
                 mode=EXCLUDED.mode,
                 updated_at=now()""",
            ('default', row['name'], row['version'], row['template'], json.dumps(row['model_compatibility']), row['mode']),
        )


def _fetch_model_rows(tenant_id: str = 'default') -> tuple[list[dict[str, Any]], str]:
    try:
        rows = fetch_all(
            "SELECT name, type, capabilities, latency_profile, metadata_json FROM model_registry WHERE tenant_id=%s ORDER BY updated_at DESC NULLS LAST, name ASC",
            (tenant_id,),
        ) or []
        parsed = [dict(row) for row in rows]
        if parsed:
            return parsed, 'db'
    except Exception:
        pass
    return [
        {'name': settings.ollama_model, 'type': 'local', 'capabilities': ['chat', 'text_generation', 'fallback_chat', 'summarize', 'retrieve_answer'], 'latency_profile': 'medium', 'metadata_json': {'default': True, 'modes': ['deterministic', 'creative'], 'fallback_models': []}},
        {'name': settings.ollama_embedding_model, 'type': 'local', 'capabilities': ['embeddings', 'retrieval'], 'latency_profile': 'fast', 'metadata_json': {'default': True, 'modes': ['deterministic']}},
    ], 'fallback'


def _fetch_prompt_rows(tenant_id: str = 'default') -> tuple[list[dict[str, Any]], str]:
    try:
        rows = fetch_all(
            "SELECT name, version, template, model_compatibility, mode, updated_at FROM prompt_registry WHERE tenant_id=%s ORDER BY updated_at DESC NULLS LAST, name ASC, version DESC",
            (tenant_id,),
        ) or []
        parsed = [dict(row) for row in rows]
        if parsed:
            return parsed, 'db'
    except Exception:
        pass
    return [
        {'name': 'fallback_chat', 'version': 'phase3.v1', 'template': settings.fallback_chat_system_prompt, 'model_compatibility': [settings.ollama_model], 'mode': 'deterministic'},
        {'name': 'summarize', 'version': 'phase3.summary.v1', 'template': 'Summarize the provided content faithfully. Preserve important constraints and cite source references when present.', 'model_compatibility': [settings.ollama_model], 'mode': 'deterministic'},
        {'name': 'retrieve_answer', 'version': 'phase3.retrieve.v1', 'template': 'Answer using the provided evidence. Include source references from the context when available. If evidence is weak, say so plainly.', 'model_compatibility': [settings.ollama_model], 'mode': 'deterministic'},
    ], 'fallback'


def _model_supports_action(row: dict[str, Any], action_type: str, generation_mode: str = 'deterministic') -> bool:
    capabilities = {str(item).strip().lower() for item in (row.get('capabilities') or [])}
    metadata = row.get('metadata_json') or {}
    modes = {str(item).strip().lower() for item in (metadata.get('modes') or [])}
    if modes and generation_mode.lower() not in modes:
        return False
    action = (action_type or 'fallback_chat').strip().lower()
    if action == 'embed':
        return 'embeddings' in capabilities
    if action in capabilities:
        return True
    if action in {'fallback_chat', 'assistant', 'summarize', 'retrieve_answer'} and capabilities.intersection({'chat', 'text_generation', 'fallback_chat', 'summarize', 'retrieve_answer'}):
        return True
    return 'chat' in capabilities or 'text_generation' in capabilities


def _select_prompt_row(rows: list[dict[str, Any]], action_type: str, prompt_version: str | None, generation_mode: str) -> dict[str, Any]:
    action = (action_type or 'fallback_chat').strip().lower()
    requested_version = (prompt_version or '').strip()
    generation_mode = (generation_mode or 'deterministic').strip().lower()
    preferred = [row for row in rows if (row.get('name') or '').strip().lower() == action]
    if requested_version:
        for row in preferred:
            if str(row.get('version') or '').strip() == requested_version:
                return row
    for row in preferred:
        if str(row.get('mode') or 'deterministic').strip().lower() == generation_mode:
            return row
    if preferred:
        return preferred[0]
    fallback = [row for row in rows if (row.get('name') or '').strip().lower() == 'fallback_chat']
    if requested_version:
        for row in fallback:
            if str(row.get('version') or '').strip() == requested_version:
                return row
    return fallback[0] if fallback else {'name': 'fallback_chat', 'version': 'phase3.v1', 'template': settings.fallback_chat_system_prompt, 'model_compatibility': [settings.ollama_model], 'mode': generation_mode}


def _resolve_ai_route(tenant_id: str, action_type: str, prompt_version: str | None = None, generation_mode: str = 'deterministic', preferred_model: str | None = None, fallback_models: list[str] | None = None) -> dict[str, Any]:
    model_rows, model_source = _fetch_model_rows(tenant_id)
    prompt_rows, prompt_source = _fetch_prompt_rows(tenant_id)
    prompt_row = _select_prompt_row(prompt_rows, action_type, prompt_version, generation_mode)
    requested_model = (preferred_model or '').strip()
    candidates = [row for row in model_rows if _model_supports_action(row, action_type, generation_mode)]
    selected = None
    route_reason = ''
    if requested_model:
        selected = next((row for row in candidates if row.get('name') == requested_model), None)
        route_reason = 'preferred_model' if selected else 'preferred_model_unavailable'
    if selected is None and prompt_row.get('model_compatibility'):
        compatibility = [str(item) for item in (prompt_row.get('model_compatibility') or [])]
        selected = next((row for row in candidates if row.get('name') in compatibility), None)
        if selected:
            route_reason = 'prompt_model_compatibility'
    if selected is None:
        selected = next((row for row in candidates if bool((row.get('metadata_json') or {}).get('default'))), None)
        if selected:
            route_reason = 'default_registry_model'
    if selected is None and candidates:
        selected = candidates[0]
        route_reason = 'first_supported_model'
    if selected is None:
        selected = {'name': settings.ollama_model, 'type': 'local', 'capabilities': ['chat'], 'latency_profile': 'medium', 'metadata_json': {'fallback_models': []}}
        route_reason = 'settings_fallback_model'
    declared_fallbacks = [str(item).strip() for item in (fallback_models or []) if str(item).strip()]
    if not declared_fallbacks:
        declared_fallbacks = [str(item).strip() for item in ((selected.get('metadata_json') or {}).get('fallback_models') or []) if str(item).strip()]
    if not declared_fallbacks:
        declared_fallbacks = [row.get('name') for row in candidates if row.get('name') != selected.get('name')]
    attempted_models = []
    for name in [selected.get('name'), *declared_fallbacks]:
        if name and name not in attempted_models:
            attempted_models.append(name)
    return {
        'tenant_id': tenant_id,
        'action_type': action_type,
        'generation_mode': generation_mode,
        'selected_model': selected.get('name') or settings.ollama_model,
        'fallback_models': [name for name in attempted_models[1:]],
        'attempted_models': attempted_models,
        'prompt_name': prompt_row.get('name') or 'fallback_chat',
        'prompt_version': prompt_row.get('version') or 'phase3.v1',
        'prompt_template': prompt_row.get('template') or settings.fallback_chat_system_prompt,
        'prompt_mode': prompt_row.get('mode') or 'deterministic',
        'route_reason': route_reason,
        'source': 'db' if model_source == 'db' or prompt_source == 'db' else 'fallback',
        'available_models': [row.get('name') for row in model_rows if row.get('name')],
        'available_prompts': [f"{row.get('name')}:{row.get('version')}" for row in prompt_rows if row.get('name') and row.get('version')],
    }


def _record_ai_route_run(tenant_id: str, request_id: str, action_type: str, generation_mode: str, selected_model: str, attempted_models: list[str], prompt_name: str, prompt_version: str, fallback_used: bool, status: str, latency_ms: int | None = None, error_message: str | None = None):
    _safe_db_execute(
        """INSERT INTO ai_route_runs (tenant_id, request_id, action_type, generation_mode, selected_model, attempted_models, prompt_name, prompt_version, fallback_used, status, latency_ms, error_message)
           VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s)""",
        (tenant_id, request_id, action_type, generation_mode, selected_model, json.dumps(attempted_models), prompt_name, prompt_version, fallback_used, status, latency_ms, error_message),
    )


def _build_ai_control_report(tenant_id: str = 'default') -> dict[str, Any]:
    model_rows, _ = _fetch_model_rows(tenant_id)
    prompt_rows, _ = _fetch_prompt_rows(tenant_id)
    route_samples = []
    for action_type in ['fallback_chat', 'summarize', 'retrieve_answer']:
        route_samples.append(_resolve_ai_route(tenant_id, action_type, generation_mode='deterministic'))
    return {
        'status': 'ok',
        'tenant_id': tenant_id,
        'model_count': len(model_rows),
        'prompt_count': len(prompt_rows),
        'models': [{'name': row.get('name'), 'type': row.get('type'), 'capabilities': row.get('capabilities', []), 'latency_profile': row.get('latency_profile'), 'metadata_json': row.get('metadata_json') or {}} for row in model_rows],
        'prompts': [{'name': row.get('name'), 'version': row.get('version'), 'mode': row.get('mode', 'deterministic'), 'model_compatibility': row.get('model_compatibility', [])} for row in prompt_rows],
        'route_samples': route_samples,
        'next_actions': [
            'Register additional models or prompt versions if you need task-specific routing beyond the seeded local Ollama defaults.',
            'Run /ai/route for each production action type before enabling strict auth so model/prompt selection is visible to operators.',
        ],
    }


def _build_rag_governance_report(tenant_id: str = 'default') -> dict[str, Any]:
    summary = rag_governance_summary(tenant_id)
    next_actions = []
    if not summary.get('document_count'):
        next_actions.append('Ingest one or more governed documents via /rag/documents/ingest before running retrieval smoke tests that depend on document chunks.')
    if not summary.get('embedding_version_count'):
        next_actions.append('Confirm the embedding model is available in Ollama if you want embedding-version tracking recorded for governed documents.')
    if not next_actions:
        next_actions.append('Review recent governed documents and embedding-version counts before adjusting retrieval prompts or retention policies.')
    return {
        'status': 'ok',
        'tenant_id': tenant_id,
        **summary,
        'next_actions': next_actions,
    }



def _build_connector_preflight(tenant_id: str = 'default', service_names: list[str] | None = None, persist: bool = True) -> dict[str, Any]:
    allowed = {name.strip().lower() for name in (service_names or []) if name and name.strip()}
    items: list[dict[str, Any]] = []
    for spec in list_catalog():
        if allowed and spec['service_name'] not in allowed:
            continue
        result = validate_connector_config(spec['service_name'])
        supported_operations = spec.get('supported_operations', [])
        recommended_operation_id = supported_operations[0]['operation_id'] if supported_operations else None
        live_ready = bool(result.get('configured')) and spec.get('implementation_status') in {'live_api', 'partial_api'} and spec.get('integration_mode') in {'rest_api', 'sdk_wrapper', 'webhook'}
        item = {
            'service_name': spec['service_name'],
            'display_name': spec.get('display_name', spec['service_name']),
            'configured': result.get('configured', False),
            'missing_credentials': result.get('missing_credentials', []),
            'present_credentials': result.get('present_credentials', []),
            'implementation_status': result.get('implementation_status', spec.get('implementation_status', 'docs_only')),
            'integration_mode': result.get('integration_mode', spec.get('integration_mode', 'manual_bridge')),
            'supported_operations_count': len(supported_operations),
            'recommended_operation_id': recommended_operation_id,
            'live_ready': live_ready,
            'notes': result.get('notes', ''),
            'base_url_env': spec.get('base_url_env'),
        }
        if persist:
            _upsert_credential_metadata(
                tenant_id,
                spec['service_name'],
                spec.get('required_credentials', []),
                spec.get('optional_credentials', []),
                result.get('present_credentials', []),
                result.get('missing_credentials', []),
                result.get('notes', ''),
            )
        items.append(item)
    items = sorted(items, key=lambda row: row['service_name'])
    return {
        'status': 'ok',
        'tenant_id': tenant_id,
        'count': len(items),
        'configured_count': sum(1 for item in items if item['configured']),
        'live_ready_count': sum(1 for item in items if item['live_ready']),
        'connectors': items,
    }


def _choose_recommended_action(item: dict[str, Any]) -> str:
    if item['recommended_import_workflow']:
        if item['configured'] or item['implementation_status'] in {'placeholder_bridge', 'manual_export_import'}:
            return 'import_packaged_workflow'
        return 'fill_credentials_then_import'
    if item['recommended_draft_operation_id']:
        if item['configured']:
            return 'use_workflow_draft'
        return 'fill_credentials_then_draft'
    return 'docs_or_manual_bridge'



def _build_connector_credential_matrix(tenant_id: str = 'default', service_names: list[str] | None = None, persist: bool = True) -> dict[str, Any]:
    preflight = _build_connector_preflight(tenant_id=tenant_id, service_names=service_names, persist=persist)
    key_map: dict[str, dict[str, Any]] = {}
    service_items: list[dict[str, Any]] = []

    for spec in list_catalog():
        if service_names and spec['service_name'] not in {name.strip().lower() for name in service_names if name and name.strip()}:
            continue
        result = validate_connector_config(spec['service_name'])
        if persist:
            _upsert_credential_metadata(
                tenant_id,
                spec['service_name'],
                spec.get('required_credentials', []),
                spec.get('optional_credentials', []),
                result.get('present_credentials', []),
                result.get('missing_credentials', []),
                result.get('notes', ''),
            )
        service_items.append({
            'service_name': spec['service_name'],
            'display_name': spec.get('display_name', spec['service_name']),
            'configured': result.get('configured', False),
            'live_ready': bool(result.get('configured')) and spec.get('implementation_status') in {'live_api', 'partial_api'} and spec.get('integration_mode') in {'rest_api', 'sdk_wrapper', 'webhook'},
            'implementation_status': spec.get('implementation_status', 'docs_only'),
            'integration_mode': spec.get('integration_mode', 'manual_bridge'),
            'required_credentials': spec.get('required_credentials', []),
            'optional_credentials': spec.get('optional_credentials', []),
            'present_credentials': result.get('present_credentials', []),
            'missing_credentials': result.get('missing_credentials', []),
            'base_url_env': spec.get('base_url_env'),
            'notes': result.get('notes', ''),
        })
        for key in [spec.get('base_url_env'), *spec.get('required_credentials', []), *spec.get('optional_credentials', [])]:
            if not key:
                continue
            row = key_map.setdefault(key, {
                'credential_key': key,
                'services': [],
                'required_by_services': [],
                'optional_for_services': [],
                'present_for_services': [],
                'missing_for_services': [],
                'configured_service_count': 0,
                'missing_service_count': 0,
                'all_required_services_ready': False,
            })
            if spec['service_name'] not in row['services']:
                row['services'].append(spec['service_name'])
            if key in spec.get('required_credentials', []) or key == spec.get('base_url_env'):
                if spec['service_name'] not in row['required_by_services']:
                    row['required_by_services'].append(spec['service_name'])
            elif key in spec.get('optional_credentials', []):
                if spec['service_name'] not in row['optional_for_services']:
                    row['optional_for_services'].append(spec['service_name'])
            if key in result.get('present_credentials', []):
                if spec['service_name'] not in row['present_for_services']:
                    row['present_for_services'].append(spec['service_name'])
            if key in result.get('missing_credentials', []):
                if spec['service_name'] not in row['missing_for_services']:
                    row['missing_for_services'].append(spec['service_name'])

    credential_keys = []
    fully_ready = 0
    partially_ready = 0
    missing_count = 0
    for key in sorted(key_map):
        row = key_map[key]
        row['services'] = sorted(row['services'])
        row['required_by_services'] = sorted(row['required_by_services'])
        row['optional_for_services'] = sorted(row['optional_for_services'])
        row['present_for_services'] = sorted(row['present_for_services'])
        row['missing_for_services'] = sorted(row['missing_for_services'])
        row['configured_service_count'] = len(row['present_for_services'])
        row['missing_service_count'] = len(row['missing_for_services'])
        row['all_required_services_ready'] = not row['missing_for_services'] and bool(row['required_by_services'])
        if row['all_required_services_ready']:
            fully_ready += 1
        elif row['present_for_services']:
            partially_ready += 1
        else:
            missing_count += 1
        credential_keys.append(row)

    next_actions: list[str] = []
    missing_required = [row['credential_key'] for row in credential_keys if row['missing_for_services'] and row['required_by_services']]
    if missing_required:
        next_actions.append('Fill the missing required connector environment variables before live deployment: ' + ', '.join(missing_required[:12]) + (' ...' if len(missing_required) > 12 else ''))
    if any(item['live_ready'] for item in service_items):
        next_actions.append('Use the credential matrix together with the readiness/deployment reports to prioritize live connectors that are already executable.')
    if any(not item['configured'] for item in service_items):
        next_actions.append('Run /connectors/preflight after updating credentials so connector credential metadata is refreshed before rollout.')

    service_items = sorted(service_items, key=lambda row: row['service_name'])
    return {
        'status': 'ok',
        'tenant_id': tenant_id,
        'count': len(service_items),
        'configured_count': sum(1 for item in service_items if item['configured']),
        'live_ready_count': sum(1 for item in service_items if item['live_ready']),
        'unique_credential_key_count': len(credential_keys),
        'summary': {
            'total_unique_credentials': len(credential_keys),
            'fully_ready_credentials': fully_ready,
            'partially_ready_credentials': partially_ready,
            'missing_credentials': missing_count,
        },
        'next_actions': next_actions,
        'services': service_items,
        'credential_keys': credential_keys,
    }


def _build_connector_readiness_report(tenant_id: str = 'default', service_names: list[str] | None = None, persist: bool = True) -> dict[str, Any]:
    preflight = _build_connector_preflight(tenant_id=tenant_id, service_names=service_names, persist=persist)
    manifest_items = {item['service_name']: item for item in build_workflow_manifest(service_names)}
    readiness_items: list[dict[str, Any]] = []
    for item in preflight['connectors']:
        manifest = manifest_items.get(item['service_name'], {})
        supported_count = item.get('supported_operations_count', 0)
        packaged_operations = manifest.get('packaged_operations', [])
        unpackaged_operations = manifest.get('unpackaged_operations', [])
        packaged_workflows = manifest.get('packaged_workflows', [])
        coverage_percent = int((len(packaged_operations) / supported_count) * 100) if supported_count else 0
        readiness = {
            'service_name': item['service_name'],
            'display_name': item['display_name'],
            'configured': item['configured'],
            'live_ready': item['live_ready'],
            'implementation_status': item['implementation_status'],
            'integration_mode': item['integration_mode'],
            'missing_credentials': item.get('missing_credentials', []),
            'present_credentials': item.get('present_credentials', []),
            'supported_operations_count': supported_count,
            'packaged_operations_count': len(packaged_operations),
            'packaged_workflow_count': manifest.get('packaged_workflow_count', len(packaged_workflows)),
            'packaged_coverage_percent': coverage_percent,
            'packaged_operations': packaged_operations,
            'unpackaged_operations': unpackaged_operations,
            'recommended_import_workflow': manifest.get('recommended_import_workflow'),
            'recommended_operation_id': item.get('recommended_operation_id'),
            'recommended_draft_operation_id': manifest.get('recommended_draft_operation_id') or item.get('recommended_operation_id'),
            'notes': item.get('notes', ''),
            'workflow_notes': manifest.get('notes', ''),
            'base_url_env': item.get('base_url_env'),
        }
        readiness['recommended_action'] = _choose_recommended_action(readiness)
        readiness_items.append(readiness)
    readiness_items = sorted(readiness_items, key=lambda row: row['service_name'])
    return {
        'status': 'ok',
        'tenant_id': tenant_id,
        'count': len(readiness_items),
        'configured_count': sum(1 for item in readiness_items if item['configured']),
        'live_ready_count': sum(1 for item in readiness_items if item['live_ready']),
        'import_ready_count': sum(1 for item in readiness_items if item['recommended_action'] == 'import_packaged_workflow'),
        'draft_ready_count': sum(1 for item in readiness_items if item['recommended_action'] in {'use_workflow_draft', 'fill_credentials_then_draft'}),
        'connectors': readiness_items,
    }

PRIMARY_STEP_BY_ACTION = {
    'fill_credentials_then_import': 'fill_credentials',
    'import_packaged_workflow': 'import_workflow',
    'fill_credentials_then_draft': 'fill_credentials',
    'use_workflow_draft': 'draft_workflow',
    'docs_or_manual_bridge': 'manual_bridge_review',
}


def _deployment_steps_for_item(item: dict[str, Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    order = 1

    def push(action: str, detail: str, required: bool = True, workflow_name: str | None = None, operation_id: str | None = None):
        nonlocal order
        steps.append({
            'order': order,
            'action': action,
            'detail': detail,
            'required': required,
            'workflow_name': workflow_name,
            'operation_id': operation_id,
        })
        order += 1

    missing = item.get('missing_credentials', [])
    import_workflow = item.get('recommended_import_workflow')
    draft_operation = item.get('recommended_draft_operation_id') or item.get('recommended_operation_id')
    smoke_operation = item.get('recommended_operation_id') or draft_operation
    service_name = item['service_name']
    integration_mode = item.get('integration_mode', '')
    implementation_status = item.get('implementation_status', '')

    if missing:
        push('fill_credentials', f"Set or inject the missing credentials for {service_name}: {', '.join(missing)}.")

    push('sync_registry', f"Run /connectors/sync-registry for tenant {item.get('tenant_id', 'default')} before DB-backed persistence verification.", required=False)

    if import_workflow:
        push('import_workflow', f"Import the packaged n8n workflow {import_workflow} for {service_name}.", workflow_name=import_workflow)
    elif draft_operation:
        push('draft_workflow', f"Generate an n8n workflow draft for {service_name}:{draft_operation} via /connectors/workflow-draft.", operation_id=draft_operation)

    if implementation_status in {'placeholder_bridge', 'manual_export_import'} or integration_mode in {'manual_bridge', 'file_bridge', 'local_bridge'}:
        push('manual_bridge_review', f"Review the manual/local bridge handoff for {service_name} and confirm the artifact/output path matches your runtime.", required=False, workflow_name=import_workflow, operation_id=draft_operation)
    elif implementation_status == 'docs_only':
        push('docs_only_review', f"Use the connector docs for {service_name}; no live automation path is packaged yet.", required=False)

    if item.get('live_ready'):
        push('live_smoke_test', f"Run /connectors/smoke-test for {service_name}:{smoke_operation or 'default'} against the live stack.", workflow_name=import_workflow, operation_id=smoke_operation)
    else:
        push('smoke_after_setup', f"After setup is complete, run /connectors/smoke-test for {service_name}:{smoke_operation or 'default'}.", required=False, workflow_name=import_workflow, operation_id=smoke_operation)

    return steps


def _build_connector_deployment_plan(tenant_id: str = 'default', service_names: list[str] | None = None, persist: bool = True) -> dict[str, Any]:
    readiness = _build_connector_readiness_report(tenant_id=tenant_id, service_names=service_names, persist=persist)
    plan_items: list[dict[str, Any]] = []
    summary = {
        'fill_credentials': 0,
        'import_packaged_workflow': 0,
        'use_workflow_draft': 0,
        'manual_bridge_review': 0,
        'docs_only_review': 0,
        'live_smoke_ready': 0,
    }
    for item in readiness['connectors']:
        steps = _deployment_steps_for_item({**item, 'tenant_id': tenant_id})
        if item.get('missing_credentials'):
            summary['fill_credentials'] += 1
        if item.get('recommended_import_workflow'):
            summary['import_packaged_workflow'] += 1
        elif item.get('recommended_draft_operation_id'):
            summary['use_workflow_draft'] += 1
        else:
            if item['implementation_status'] == 'docs_only':
                summary['docs_only_review'] += 1
            else:
                summary['manual_bridge_review'] += 1
        if item.get('live_ready'):
            summary['live_smoke_ready'] += 1
        primary_step = 'fill_credentials' if item.get('missing_credentials') else PRIMARY_STEP_BY_ACTION.get(item['recommended_action'], steps[0]['action'] if steps else 'docs_only_review')
        plan_items.append({
            'service_name': item['service_name'],
            'display_name': item['display_name'],
            'configured': item['configured'],
            'live_ready': item['live_ready'],
            'implementation_status': item['implementation_status'],
            'integration_mode': item['integration_mode'],
            'recommended_action': item['recommended_action'],
            'primary_step': primary_step,
            'recommended_import_workflow': item.get('recommended_import_workflow'),
            'recommended_draft_operation_id': item.get('recommended_draft_operation_id'),
            'smoke_operation_id': item.get('recommended_operation_id') or item.get('recommended_draft_operation_id'),
            'missing_credentials': item.get('missing_credentials', []),
            'packaged_coverage_percent': item.get('packaged_coverage_percent', 0),
            'steps': steps,
            'notes': item.get('notes', ''),
            'workflow_notes': item.get('workflow_notes', ''),
            'base_url_env': item.get('base_url_env'),
        })
    next_actions: list[str] = []
    if summary['fill_credentials']:
        next_actions.append(f"Fill credentials for {summary['fill_credentials']} connectors before live smoke testing.")
    if summary['import_packaged_workflow']:
        next_actions.append(f"Import packaged workflows for {summary['import_packaged_workflow']} connectors.")
    if summary['use_workflow_draft']:
        next_actions.append(f"Generate workflow drafts for {summary['use_workflow_draft']} connectors that do not yet have packaged coverage.")
    if summary['manual_bridge_review']:
        next_actions.append(f"Review manual/local bridge handling for {summary['manual_bridge_review']} connectors before operator handoff.")
    if summary['live_smoke_ready']:
        next_actions.append(f"Run live connector smoke tests for {summary['live_smoke_ready']} connectors that are already live-ready.")
    return {
        'status': 'ok',
        'tenant_id': tenant_id,
        'count': len(plan_items),
        'configured_count': readiness['configured_count'],
        'live_ready_count': readiness['live_ready_count'],
        'ready_to_import_count': summary['import_packaged_workflow'],
        'requires_credentials_count': summary['fill_credentials'],
        'summary': summary,
        'connectors': sorted(plan_items, key=lambda row: row['service_name']),
        'next_actions': next_actions,
    }


EXPECTED_CONNECTOR_TABLES = [
    "connector_registry",
    "connector_credentials_meta",
    "connector_execution_log",
    "workflow_templates",
    "smoke_test_results",
]

TABLE_TIMESTAMP_COLUMNS = {
    'connector_registry': 'updated_at',
    'connector_credentials_meta': 'last_validated_at',
    'connector_execution_log': 'last_validated_at',
    'workflow_templates': 'updated_at',
    'smoke_test_results': 'executed_at',
}


def _build_connector_persistence_report(tenant_id: str = 'default') -> dict[str, Any]:
    tables: list[dict[str, Any]] = []
    counts: dict[str, int | None] = {name: None for name in EXPECTED_CONNECTOR_TABLES}
    recent_services: list[str] = []
    error: str | None = None
    database_available = True
    for table_name in EXPECTED_CONNECTOR_TABLES:
        try:
            exists_row = fetch_one(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s) AS exists",
                (table_name,),
            )
            exists = bool(exists_row and exists_row.get('exists'))
        except Exception as exc:
            database_available = False
            error = str(exc)
            tables = [
                {
                    'table_name': name,
                    'exists': False,
                    'row_count': None,
                    'last_validated_at': None,
                    'note': 'database unavailable in current runtime',
                }
                for name in EXPECTED_CONNECTOR_TABLES
            ]
            break

        row_count = None
        last_validated_at = None
        note = ''
        if exists:
            try:
                ts_col = TABLE_TIMESTAMP_COLUMNS.get(table_name, 'created_at')
                row = fetch_one(f"SELECT count(*)::int AS c, max({ts_col})::text AS last_validated_at FROM {table_name}")
                if row:
                    row_count = row.get('c')
                    last_validated_at = row.get('last_validated_at')
            except Exception as exc:
                note = f"table exists but count query failed: {exc}"
            counts[table_name] = row_count
        else:
            note = 'table missing; apply connector migrations before live persistence verification'
        tables.append({
            'table_name': table_name,
            'exists': exists,
            'row_count': row_count,
            'last_validated_at': last_validated_at,
            'note': note,
        })

    if database_available:
        try:
            rows = fetch_all(
                "SELECT service_name FROM connector_execution_log WHERE tenant_id=%s GROUP BY service_name ORDER BY max(created_at) DESC LIMIT 10",
                (tenant_id,),
            )
            recent_services = [row['service_name'] for row in rows if row.get('service_name')]
        except Exception:
            recent_services = []

    existing_table_count = sum(1 for item in tables if item['exists'])
    all_tables_present = database_available and existing_table_count == len(EXPECTED_CONNECTOR_TABLES)
    next_actions: list[str] = []
    if not database_available:
        next_actions.append('Start PostgreSQL and apply connector migrations before running persistence verification.')
    elif not all_tables_present:
        next_actions.append('Apply migrations 004, 005, and 006 so all connector persistence tables exist.')
    else:
        if (counts.get('connector_registry') or 0) < 14:
            next_actions.append('Run /connectors/sync-registry so the catalog is seeded into connector_registry.')
        if (counts.get('connector_execution_log') or 0) == 0:
            next_actions.append('Generate connector traffic with /connectors/validate-config, /connectors/workflow-draft, and /connectors/smoke-test to populate execution logs.')
        if (counts.get('workflow_templates') or 0) == 0:
            next_actions.append('Run /connectors/workflow-draft for at least one connector so workflow_templates is populated.')
        if (counts.get('smoke_test_results') or 0) == 0:
            next_actions.append('Run /connectors/smoke-test for at least one connector so smoke_test_results is populated.')
        if (counts.get('connector_credentials_meta') or 0) == 0:
            next_actions.append('Run /connectors/preflight or /connectors/validate-config so credential metadata is captured.')
        if not next_actions:
            next_actions.append('Persistence tables are present and populated; proceed to live connector verification and rollout import steps.')

    status = 'ok' if database_available else 'degraded'
    return {
        'status': status,
        'tenant_id': tenant_id,
        'database_available': database_available,
        'expected_table_count': len(EXPECTED_CONNECTOR_TABLES),
        'existing_table_count': existing_table_count,
        'all_tables_present': all_tables_present,
        'connector_registry_count': counts.get('connector_registry'),
        'execution_log_count': counts.get('connector_execution_log'),
        'workflow_template_count': counts.get('workflow_templates'),
        'smoke_test_count': counts.get('smoke_test_results'),
        'credential_meta_count': counts.get('connector_credentials_meta'),
        'recent_services': recent_services,
        'next_actions': next_actions,
        'error': error,
        'tables': tables,
    }


def _build_connector_rollout_bundle(tenant_id: str = 'default', service_names: list[str] | None = None, persist: bool = True) -> dict[str, Any]:
    preflight = _build_connector_preflight(tenant_id=tenant_id, service_names=service_names, persist=persist)
    manifest = {item['service_name']: item for item in build_workflow_manifest(service_names)}
    readiness = _build_connector_readiness_report(tenant_id=tenant_id, service_names=service_names, persist=persist)
    deployment = _build_connector_deployment_plan(tenant_id=tenant_id, service_names=service_names, persist=persist)

    services: list[dict[str, Any]] = []
    for item in deployment['connectors']:
        service_name = item['service_name']
        preflight_item = next((row for row in preflight['connectors'] if row['service_name'] == service_name), {})
        manifest_item = manifest.get(service_name, {})
        services.append({
            'service_name': service_name,
            'display_name': item['display_name'],
            'configured': item['configured'],
            'live_ready': item['live_ready'],
            'implementation_status': item['implementation_status'],
            'integration_mode': item['integration_mode'],
            'recommended_action': item['recommended_action'],
            'primary_step': item['primary_step'],
            'recommended_import_workflow': item.get('recommended_import_workflow'),
            'recommended_draft_operation_id': item.get('recommended_draft_operation_id'),
            'smoke_operation_id': item.get('smoke_operation_id'),
            'missing_credentials': item.get('missing_credentials', []),
            'present_credentials': preflight_item.get('present_credentials', []),
            'packaged_coverage_percent': item.get('packaged_coverage_percent', 0),
            'packaged_workflows': manifest_item.get('packaged_workflows', []),
            'packaged_operations': manifest_item.get('packaged_operations', []),
            'unpackaged_operations': manifest_item.get('unpackaged_operations', []),
            'steps': item.get('steps', []),
            'notes': item.get('notes', ''),
            'workflow_notes': item.get('workflow_notes', ''),
            'base_url_env': item.get('base_url_env'),
        })

    command_sequence = [
        'python scripts/build_connector_rollout_bundle.py --remote --persist',
        'python scripts/build_connector_deployment_plan.py --remote --persist',
        'python scripts/build_connector_readiness_report.py --remote --persist',
        'python scripts/connector_preflight_report.py --remote --persist',
        'python scripts/build_connector_workflow_manifest.py --remote',
        'SMOKE_SCOPE=persistence bash scripts/smoke_test.sh',
    ]

    return {
        'status': 'ok',
        'tenant_id': tenant_id,
        'count': len(services),
        'configured_count': readiness['configured_count'],
        'live_ready_count': readiness['live_ready_count'],
        'ready_to_import_count': deployment['ready_to_import_count'],
        'requires_credentials_count': deployment['requires_credentials_count'],
        'summary': deployment['summary'],
        'next_actions': deployment['next_actions'],
        'command_sequence': command_sequence,
        'reports': {
            'preflight': {
                'count': preflight['count'],
                'configured_count': preflight['configured_count'],
                'live_ready_count': preflight['live_ready_count'],
            },
            'manifest': {
                'count': len(manifest),
                'packaged_ready_count': sum(1 for row in readiness['connectors'] if row.get('recommended_import_workflow')),
                'draftable_count': sum(1 for row in readiness['connectors'] if row.get('recommended_draft_operation_id')),
            },
            'readiness': {
                'count': readiness['count'],
                'import_ready_count': readiness['import_ready_count'],
                'draft_ready_count': readiness['draft_ready_count'],
            },
            'deployment': {
                'count': deployment['count'],
                'ready_to_import_count': deployment['ready_to_import_count'],
                'requires_credentials_count': deployment['requires_credentials_count'],
            },
        },
        'services': sorted(services, key=lambda row: row['service_name']),
    }



def _default_connector_runtime_policy(service_name: str, tenant_id: str = 'default') -> dict[str, Any]:
    spec = get_connector(service_name)
    timeout_seconds = min(max(5, int(settings.connector_timeout_seconds)), int(settings.connector_timeout_cap_seconds))
    if spec.get('integration_mode') in {'manual_bridge', 'local_bridge', 'file_bridge'}:
        timeout_seconds = min(timeout_seconds, 45)
    return {
        'tenant_id': tenant_id,
        'service_name': spec['service_name'],
        'enabled': True,
        'requests_per_window': int(settings.connector_rate_limit_max_requests),
        'window_seconds': int(settings.connector_rate_limit_window_seconds),
        'timeout_seconds': timeout_seconds,
        'failure_threshold': int(settings.connector_circuit_breaker_threshold),
        'cooldown_seconds': int(settings.connector_circuit_breaker_reset_seconds),
    }


def _default_workflow_runtime_policy(workflow_id: str, tenant_id: str = 'default') -> dict[str, Any]:
    return {
        'tenant_id': tenant_id,
        'workflow_id': workflow_id,
        'enabled': True,
        'max_executions_per_window': int(settings.workflow_execution_cap_max_requests),
        'window_seconds': int(settings.workflow_execution_cap_window_seconds),
    }


def _seed_runtime_policy_defaults(tenant_id: str = 'default') -> None:
    for spec in list_catalog():
        policy = _default_connector_runtime_policy(spec['service_name'], tenant_id)
        _safe_db_execute(
            """INSERT INTO connector_runtime_policies (tenant_id, service_name, enabled, requests_per_window, window_seconds, timeout_seconds, failure_threshold, cooldown_seconds)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (tenant_id, service_name) DO NOTHING""",
            (policy['tenant_id'], policy['service_name'], policy['enabled'], policy['requests_per_window'], policy['window_seconds'], policy['timeout_seconds'], policy['failure_threshold'], policy['cooldown_seconds']),
        )


def _get_connector_runtime_policy(service_name: str, tenant_id: str = 'default') -> dict[str, Any]:
    service_name = normalize_service_name(service_name)
    policy = _default_connector_runtime_policy(service_name, tenant_id)
    try:
        row = fetch_one("SELECT enabled, requests_per_window, window_seconds, timeout_seconds, failure_threshold, cooldown_seconds FROM connector_runtime_policies WHERE tenant_id=%s AND service_name=%s", (tenant_id, service_name))
    except Exception:
        row = None
    if row:
        for key in ['enabled', 'requests_per_window', 'window_seconds', 'timeout_seconds', 'failure_threshold', 'cooldown_seconds']:
            if row.get(key) is not None:
                policy[key] = row[key]
    _safe_db_execute(
        """INSERT INTO connector_runtime_policies (tenant_id, service_name, enabled, requests_per_window, window_seconds, timeout_seconds, failure_threshold, cooldown_seconds)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (tenant_id, service_name) DO NOTHING""",
        (policy['tenant_id'], policy['service_name'], policy['enabled'], policy['requests_per_window'], policy['window_seconds'], policy['timeout_seconds'], policy['failure_threshold'], policy['cooldown_seconds']),
    )
    _safe_db_execute(
        """INSERT INTO connector_metrics (tenant_id, service_name, execution_count, success_count, failure_count, retry_count, failure_rate_percent, requests_per_window, window_seconds, timeout_cap_seconds, failure_threshold, cooldown_seconds, last_policy_refresh_at)
           VALUES (%s,%s,0,0,0,0,0,%s,%s,%s,%s,%s,now())
           ON CONFLICT (tenant_id, service_name)
           DO UPDATE SET requests_per_window=EXCLUDED.requests_per_window,
                         window_seconds=EXCLUDED.window_seconds,
                         timeout_cap_seconds=EXCLUDED.timeout_cap_seconds,
                         failure_threshold=EXCLUDED.failure_threshold,
                         cooldown_seconds=EXCLUDED.cooldown_seconds,
                         last_policy_refresh_at=now(),
                         updated_at=now()""",
        (tenant_id, service_name, policy['requests_per_window'], policy['window_seconds'], policy['timeout_seconds'], policy['failure_threshold'], policy['cooldown_seconds']),
    )
    return policy


def _get_workflow_runtime_policy(workflow_id: str, tenant_id: str = 'default') -> dict[str, Any]:
    policy = _default_workflow_runtime_policy(workflow_id, tenant_id)
    try:
        row = fetch_one("SELECT enabled, max_executions_per_window, window_seconds FROM workflow_runtime_policies WHERE tenant_id=%s AND workflow_id=%s", (tenant_id, workflow_id))
    except Exception:
        row = None
    if row:
        for key in ['enabled', 'max_executions_per_window', 'window_seconds']:
            if row.get(key) is not None:
                policy[key] = row[key]
    _safe_db_execute(
        """INSERT INTO workflow_runtime_policies (tenant_id, workflow_id, enabled, max_executions_per_window, window_seconds)
           VALUES (%s,%s,%s,%s,%s)
           ON CONFLICT (tenant_id, workflow_id) DO NOTHING""",
        (tenant_id, workflow_id, policy['enabled'], policy['max_executions_per_window'], policy['window_seconds']),
    )
    return policy


def _get_connector_runtime_state(service_name: str, tenant_id: str = 'default') -> dict[str, Any]:
    service_name = normalize_service_name(service_name)
    try:
        row = fetch_one(
            """SELECT circuit_state, consecutive_failures, last_circuit_opened_at, last_success_at, last_failure_at,
                      rate_limit_rejection_count, circuit_open_count, timeout_rejection_count, blocked_count, last_error_message,
                      requests_per_window, window_seconds, timeout_cap_seconds, failure_threshold, cooldown_seconds
               FROM connector_metrics WHERE tenant_id=%s AND service_name=%s""",
            (tenant_id, service_name),
        )
    except Exception:
        row = None
    row = row or {}
    return {
        'circuit_state': row.get('circuit_state') or 'closed',
        'consecutive_failures': int(row.get('consecutive_failures') or 0),
        'last_circuit_opened_at': row.get('last_circuit_opened_at'),
        'last_success_at': row.get('last_success_at'),
        'last_failure_at': row.get('last_failure_at'),
        'rate_limit_rejection_count': int(row.get('rate_limit_rejection_count') or 0),
        'circuit_open_count': int(row.get('circuit_open_count') or 0),
        'timeout_rejection_count': int(row.get('timeout_rejection_count') or 0),
        'blocked_count': int(row.get('blocked_count') or 0),
        'last_error_message': row.get('last_error_message'),
        'requests_per_window': int(row.get('requests_per_window') or 0),
        'window_seconds': int(row.get('window_seconds') or 0),
        'timeout_seconds': int(row.get('timeout_cap_seconds') or 0),
        'failure_threshold': int(row.get('failure_threshold') or 0),
        'cooldown_seconds': int(row.get('cooldown_seconds') or 0),
    }


def _count_recent_connector_executions(service_name: str, tenant_id: str = 'default', window_seconds: int = 60) -> int:
    try:
        row = fetch_one(
            "SELECT count(*)::int AS c FROM connector_execution_log WHERE tenant_id=%s AND service_name=%s AND execution_mode='execute_live' AND created_at >= now() - make_interval(secs => %s)",
            (tenant_id, normalize_service_name(service_name), int(window_seconds)),
        )
        return int((row or {'c': 0})['c'])
    except Exception:
        return 0


def _count_recent_workflow_executions(workflow_id: str, tenant_id: str = 'default', window_seconds: int = 60) -> int:
    try:
        row = fetch_one(
            "SELECT count(*)::int AS c FROM audit_logs WHERE tenant_id=%s AND action='workflow_execution' AND resource_type='workflow' AND resource_id=%s AND timestamp >= now() - make_interval(secs => %s)",
            (tenant_id, workflow_id, int(window_seconds)),
        )
        return int((row or {'c': 0})['c'])
    except Exception:
        return 0


def _register_connector_isolation_rejection(tenant_id: str, service_name: str, policy: dict[str, Any], kind: str, error_message: str | None = None) -> None:
    service_name = normalize_service_name(service_name)
    rate_limit_inc = 1 if kind == 'rate_limit' else 0
    circuit_open_inc = 1 if kind == 'circuit_open' else 0
    timeout_inc = 1 if kind == 'timeout' else 0
    circuit_state = 'open' if kind == 'circuit_open' else 'closed'
    _safe_db_execute(
        """INSERT INTO connector_metrics (tenant_id, service_name, execution_count, success_count, failure_count, retry_count, failure_rate_percent, blocked_count, rate_limit_rejection_count, circuit_open_count, timeout_rejection_count, circuit_state, last_circuit_opened_at, last_error_message, requests_per_window, window_seconds, timeout_cap_seconds, failure_threshold, cooldown_seconds, last_policy_refresh_at)
           VALUES (%s,%s,0,0,0,0,0,1,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
           ON CONFLICT (tenant_id, service_name)
           DO UPDATE SET blocked_count = connector_metrics.blocked_count + 1,
                         rate_limit_rejection_count = connector_metrics.rate_limit_rejection_count + EXCLUDED.rate_limit_rejection_count,
                         circuit_open_count = connector_metrics.circuit_open_count + EXCLUDED.circuit_open_count,
                         timeout_rejection_count = connector_metrics.timeout_rejection_count + EXCLUDED.timeout_rejection_count,
                         circuit_state = CASE WHEN EXCLUDED.circuit_state='open' THEN 'open' ELSE connector_metrics.circuit_state END,
                         last_circuit_opened_at = CASE WHEN EXCLUDED.circuit_state='open' THEN now() ELSE connector_metrics.last_circuit_opened_at END,
                         last_error_message = COALESCE(EXCLUDED.last_error_message, connector_metrics.last_error_message),
                         requests_per_window=EXCLUDED.requests_per_window,
                         window_seconds=EXCLUDED.window_seconds,
                         timeout_cap_seconds=EXCLUDED.timeout_cap_seconds,
                         failure_threshold=EXCLUDED.failure_threshold,
                         cooldown_seconds=EXCLUDED.cooldown_seconds,
                         last_policy_refresh_at=now(),
                         updated_at=now()""",
        (tenant_id, service_name, rate_limit_inc, circuit_open_inc, timeout_inc, circuit_state, time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()) if kind == 'circuit_open' else None, error_message, policy['requests_per_window'], policy['window_seconds'], policy['timeout_seconds'], policy['failure_threshold'], policy['cooldown_seconds']),
    )


def _record_connector_runtime_outcome(tenant_id: str, service_name: str, success: bool, policy: dict[str, Any], error_message: str | None = None, timeout_failure: bool = False) -> None:
    service_name = normalize_service_name(service_name)
    state = _get_connector_runtime_state(service_name, tenant_id)
    if success:
        _safe_db_execute(
            """INSERT INTO connector_metrics (tenant_id, service_name, execution_count, success_count, failure_count, retry_count, failure_rate_percent, circuit_state, consecutive_failures, last_success_at, last_error_message, requests_per_window, window_seconds, timeout_cap_seconds, failure_threshold, cooldown_seconds, last_policy_refresh_at)
               VALUES (%s,%s,0,0,0,0,0,'closed',0,%s,NULL,%s,%s,%s,%s,%s,now())
               ON CONFLICT (tenant_id, service_name)
               DO UPDATE SET circuit_state='closed',
                             consecutive_failures=0,
                             last_success_at=EXCLUDED.last_success_at,
                             last_error_message=NULL,
                             requests_per_window=EXCLUDED.requests_per_window,
                             window_seconds=EXCLUDED.window_seconds,
                             timeout_cap_seconds=EXCLUDED.timeout_cap_seconds,
                             failure_threshold=EXCLUDED.failure_threshold,
                             cooldown_seconds=EXCLUDED.cooldown_seconds,
                             last_policy_refresh_at=now(),
                             updated_at=now()""",
            (tenant_id, service_name, time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), policy['requests_per_window'], policy['window_seconds'], policy['timeout_seconds'], policy['failure_threshold'], policy['cooldown_seconds']),
        )
        return
    new_consecutive = state['consecutive_failures'] + 1
    opened = new_consecutive >= int(policy['failure_threshold'])
    next_state = 'open' if opened else ('half_open' if state['circuit_state'] == 'half_open' else 'closed')
    _safe_db_execute(
        """INSERT INTO connector_metrics (tenant_id, service_name, execution_count, success_count, failure_count, retry_count, failure_rate_percent, circuit_state, consecutive_failures, last_failure_at, timeout_rejection_count, circuit_open_count, last_circuit_opened_at, last_error_message, requests_per_window, window_seconds, timeout_cap_seconds, failure_threshold, cooldown_seconds, last_policy_refresh_at)
           VALUES (%s,%s,0,0,0,0,0,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
           ON CONFLICT (tenant_id, service_name)
           DO UPDATE SET circuit_state=EXCLUDED.circuit_state,
                         consecutive_failures=%s,
                         last_failure_at=EXCLUDED.last_failure_at,
                         timeout_rejection_count = connector_metrics.timeout_rejection_count + EXCLUDED.timeout_rejection_count,
                         circuit_open_count = connector_metrics.circuit_open_count + EXCLUDED.circuit_open_count,
                         last_circuit_opened_at = CASE WHEN EXCLUDED.circuit_state='open' THEN EXCLUDED.last_circuit_opened_at ELSE connector_metrics.last_circuit_opened_at END,
                         last_error_message=EXCLUDED.last_error_message,
                         requests_per_window=EXCLUDED.requests_per_window,
                         window_seconds=EXCLUDED.window_seconds,
                         timeout_cap_seconds=EXCLUDED.timeout_cap_seconds,
                         failure_threshold=EXCLUDED.failure_threshold,
                         cooldown_seconds=EXCLUDED.cooldown_seconds,
                         last_policy_refresh_at=now(),
                         updated_at=now()""",
        (
            tenant_id,
            service_name,
            next_state,
            new_consecutive,
            time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            1 if timeout_failure else 0,
            1 if opened else 0,
            time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()) if opened else None,
            error_message,
            policy['requests_per_window'],
            policy['window_seconds'],
            policy['timeout_seconds'],
            policy['failure_threshold'],
            policy['cooldown_seconds'],
            new_consecutive,
        ),
    )


def _enforce_connector_runtime_policy(tenant_id: str, service_name: str, requested_timeout_seconds: int, operation_id: str | None = None) -> dict[str, Any]:
    policy = _get_connector_runtime_policy(service_name, tenant_id)
    state = _get_connector_runtime_state(service_name, tenant_id)
    requested_timeout_seconds = int(requested_timeout_seconds or settings.connector_timeout_seconds)
    effective_timeout_seconds = max(1, min(requested_timeout_seconds, int(policy['timeout_seconds']), int(settings.connector_timeout_cap_seconds)))
    recent_execute_count = _count_recent_connector_executions(service_name, tenant_id, int(policy['window_seconds']))
    if policy['enabled']:
        opened_at = state.get('last_circuit_opened_at')
        if state['circuit_state'] == 'open' and opened_at:
            opened_ts = int(opened_at.timestamp()) if hasattr(opened_at, 'timestamp') else int(time.time())
            retry_after_seconds = max(int(policy['cooldown_seconds']) - max(0, int(time.time()) - opened_ts), 0)
            if retry_after_seconds > 0:
                _register_connector_isolation_rejection(tenant_id, service_name, policy, 'circuit_open', f'circuit open for {service_name}')
                raise HTTPException(status_code=503, detail={'code': 'CIRCUIT_OPEN', 'message': f'connector {service_name} is cooling down', 'retry_after_seconds': retry_after_seconds, 'service_name': normalize_service_name(service_name), 'operation_id': operation_id or 'default'})
            _safe_db_execute("UPDATE connector_metrics SET circuit_state='half_open', updated_at=now() WHERE tenant_id=%s AND service_name=%s", (tenant_id, normalize_service_name(service_name)))
            state['circuit_state'] = 'half_open'
        if recent_execute_count >= int(policy['requests_per_window']):
            _register_connector_isolation_rejection(tenant_id, service_name, policy, 'rate_limit', f'rate limit exceeded for {service_name}')
            raise HTTPException(status_code=429, detail={'code': 'RATE_LIMITED', 'message': f'connector {service_name} exceeded its runtime budget', 'retry_after_seconds': int(policy['window_seconds']), 'service_name': normalize_service_name(service_name), 'operation_id': operation_id or 'default'})
    return {
        'service_name': normalize_service_name(service_name),
        'policy': policy,
        'state': state,
        'recent_execute_count': recent_execute_count,
        'effective_timeout_seconds': effective_timeout_seconds,
        'timeout_capped': effective_timeout_seconds != requested_timeout_seconds,
    }


def _check_workflow_execution_cap(tenant_id: str, workflow_id: str, actor_id: str | None = None, persist: bool = True, metadata_json: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = _get_workflow_runtime_policy(workflow_id, tenant_id)
    execution_count_window = _count_recent_workflow_executions(workflow_id, tenant_id, int(policy['window_seconds']))
    allowed = True
    reason = 'ok'
    retry_after_seconds = None
    if policy['enabled'] and execution_count_window >= int(policy['max_executions_per_window']):
        allowed = False
        reason = 'workflow_cap_exceeded'
        retry_after_seconds = int(policy['window_seconds'])
    if allowed and persist:
        write_request_audit(actor_id or 'anonymous', 'workflow_execution', 'workflow', workflow_id, metadata_json or {}, tenant_id=tenant_id)
        execution_count_window += 1
    remaining = max(int(policy['max_executions_per_window']) - execution_count_window, 0)
    return {
        'status': 'ok' if allowed else 'blocked',
        'tenant_id': tenant_id,
        'workflow_id': workflow_id,
        'allowed': allowed,
        'execution_count_window': execution_count_window,
        'remaining_executions': remaining,
        'retry_after_seconds': retry_after_seconds,
        'reason': reason,
        'policy': policy,
    }


def _build_failure_isolation_report(tenant_id: str = 'default', service_names: list[str] | None = None, persist: bool = True) -> dict[str, Any]:
    allowed = {normalize_service_name(name) for name in (service_names or []) if name}
    if persist:
        _seed_runtime_policy_defaults(tenant_id)
    services: list[dict[str, Any]] = []
    open_circuit_count = 0
    half_open_count = 0
    rate_limited_services_count = 0
    for spec in list_catalog():
        service_name = spec['service_name']
        if allowed and service_name not in allowed:
            continue
        policy = _get_connector_runtime_policy(service_name, tenant_id)
        state = _get_connector_runtime_state(service_name, tenant_id)
        validation = validate_connector_config(service_name)
        recent_execute_count = _count_recent_connector_executions(service_name, tenant_id, int(policy['window_seconds']))
        circuit_open = state['circuit_state'] == 'open'
        blocked = circuit_open or recent_execute_count >= int(policy['requests_per_window'])
        if circuit_open:
            open_circuit_count += 1
        if state['circuit_state'] == 'half_open':
            half_open_count += 1
        if recent_execute_count >= int(policy['requests_per_window']):
            rate_limited_services_count += 1
        if not validation.get('configured'):
            recommended_action = 'fill_credentials'
        elif circuit_open:
            recommended_action = 'wait_for_cooldown'
        elif recent_execute_count >= int(policy['requests_per_window']):
            recommended_action = 'reduce_request_rate'
        else:
            recommended_action = 'execute_connector'
        services.append({
            'service_name': service_name,
            'display_name': spec.get('display_name', service_name),
            'configured': validation.get('configured', False),
            'implementation_status': spec.get('implementation_status', 'docs_only'),
            'integration_mode': spec.get('integration_mode', 'manual_bridge'),
            'circuit_state': state['circuit_state'],
            'circuit_open': circuit_open,
            'blocked': blocked,
            'requests_per_window': int(policy['requests_per_window']),
            'window_seconds': int(policy['window_seconds']),
            'timeout_seconds': int(policy['timeout_seconds']),
            'failure_threshold': int(policy['failure_threshold']),
            'cooldown_seconds': int(policy['cooldown_seconds']),
            'recent_execute_count': recent_execute_count,
            'consecutive_failures': state['consecutive_failures'],
            'rate_limit_rejection_count': state['rate_limit_rejection_count'],
            'circuit_open_count': state['circuit_open_count'],
            'timeout_rejection_count': state['timeout_rejection_count'],
            'recommended_action': recommended_action,
            'notes': validation.get('notes', ''),
        })
    next_actions = []
    if open_circuit_count:
        next_actions.append('Review open connectors and wait for cooldown or fix the underlying downstream error before retrying.')
    if rate_limited_services_count:
        next_actions.append('Reduce connector execution burst size or raise connector runtime policy limits only after validating downstream quotas.')
    if not next_actions:
        next_actions.append('No active connector isolation blocks detected in the local package view.')
    return {
        'status': 'ok',
        'tenant_id': tenant_id,
        'count': len(services),
        'open_circuit_count': open_circuit_count,
        'half_open_count': half_open_count,
        'rate_limited_services_count': rate_limited_services_count,
        'next_actions': next_actions,
        'services': services,
    }

def _store_ai_artifact(req: GenerateRequest, request_id: str, text: str, latency_ms: int, validation_status: str, grounding_refs: list[str], ai_model: str | None = None, ai_prompt_version: str | None = None):
    artifact = fetch_one(
        """INSERT INTO ai_output_artifacts (
            tenant_id, actor_id, request_id, action_type, ai_model, ai_prompt_version, ai_latency_ms,
            prompt_text, output_text, payload_size, validation_status, grounding_source_refs
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) RETURNING artifact_id::text AS artifact_id""",
        (req.tenant_id, req.actor_id, request_id, req.action_type, ai_model or settings.ollama_model, ai_prompt_version or req.prompt_version, latency_ms, req.prompt, text, len(text), validation_status, json.dumps(grounding_refs)),
    )
    return artifact['artifact_id']


@app.get('/health', response_model=HealthResponse)
def health():
    pg = 'ok'; ol = 'ok'
    try:
        fetch_one('SELECT 1 AS ok')
    except Exception:
        pg = 'down'
    try:
        ollama.tags()
    except Exception:
        ol = 'down'
    return HealthResponse(status='ok' if pg == 'ok' and ol == 'ok' else 'degraded', postgres=pg, ollama=ol, model=settings.ollama_model, embedding_model=settings.ollama_embedding_model, queue_depth=safe_queue_depth())


@app.get('/ready', response_model=HealthResponse)
def ready():
    try:
        fetch_one('SELECT 1 AS ok')
        ollama.tags()
    except OllamaError as e:
        raise HTTPException(status_code=503, detail={'code': e.code, 'message': e.message})
    except Exception as e:
        raise HTTPException(status_code=503, detail={'code': 'DOWNSTREAM_FAILURE', 'message': str(e)})
    return HealthResponse(status='ok', postgres='ok', ollama='ok', model=settings.ollama_model, embedding_model=settings.ollama_embedding_model, queue_depth=safe_queue_depth())


@app.get('/metrics')
def metrics(tenant_id: str = 'default', format: str = 'json'):
    data = compute_metrics(tenant_id)
    if format == 'prometheus':
        try:
            connector_row = fetch_one("SELECT COALESCE(sum(success_count),0)::int AS success_count, COALESCE(sum(failure_count),0)::int AS failure_count, COALESCE(sum(retry_count),0)::int AS retry_count FROM connector_metrics WHERE tenant_id=%s", (tenant_id,)) or {'success_count': 0, 'failure_count': 0, 'retry_count': 0}
        except Exception:
            connector_row = {'success_count': 0, 'failure_count': 0, 'retry_count': 0}
        lines = [
            '# TYPE control_plane_queue_depth gauge',
            f"control_plane_queue_depth{{tenant_id=\"{tenant_id}\"}} {data['queue_depth']}",
            '# TYPE control_plane_failed_jobs gauge',
            f"control_plane_failed_jobs{{tenant_id=\"{tenant_id}\"}} {data['failed_jobs']}",
            '# TYPE control_plane_ai_latency_ms gauge',
            f"control_plane_ai_latency_ms{{tenant_id=\"{tenant_id}\"}} {data['avg_ai_latency_ms_24h']}",
            '# TYPE control_plane_connector_success_total counter',
            f"control_plane_connector_success_total{{tenant_id=\"{tenant_id}\"}} {connector_row['success_count']}",
            '# TYPE control_plane_connector_failure_total counter',
            f"control_plane_connector_failure_total{{tenant_id=\"{tenant_id}\"}} {connector_row['failure_count']}",
            '# TYPE control_plane_connector_retry_total counter',
            f"control_plane_connector_retry_total{{tenant_id=\"{tenant_id}\"}} {connector_row['retry_count']}",
            '# TYPE control_plane_dlq_depth gauge',
            f"control_plane_dlq_depth{{tenant_id=\"{tenant_id}\"}} {data['dead_letters']}",
        ]
        return PlainTextResponse('\n'.join(lines) + '\n', media_type='text/plain; version=0.0.4')
    return MetricsResponse(status='ok', tenant_id=tenant_id, **data)


@app.post('/auth/token', response_model=AuthTokenResponse)
def auth_token(req: AuthTokenRequest):
    user = resolve_bootstrap_user(req.username, tenant_id=req.tenant_id)
    if not user:
        raise HTTPException(status_code=404, detail={'code': 'UNKNOWN_USER', 'message': req.username})
    role = req.role or user['role']
    token = issue_token(user['user_id'], role, tenant_id=req.tenant_id, scopes=list_effective_scopes(role))
    return AuthTokenResponse(status='ok', access_token=token, expires_in_seconds=settings.jwt_expiry_seconds, user_id=user['user_id'], role=role, tenant_id=req.tenant_id, scopes=list_effective_scopes(role))


@app.get('/connectors/catalog', response_model=ConnectorCatalogResponse)
def connectors_catalog():
    items = [ConnectorCatalogItem(**item) for item in list_catalog()]
    return ConnectorCatalogResponse(status='ok', count=len(items), connectors=items)


@app.post('/connectors/prepare', response_model=ConnectorPrepareResponse)
def connectors_prepare(req: ConnectorPrepareRequest):
    try:
        prepared = prepare_connector_request(req.service_name, req.operation_id, body=req.body or None, query=req.query or None, headers=req.headers or None, resolve_env=False)
    except KeyError as e:
        raise HTTPException(status_code=404, detail={'code': 'WORKFLOW_NOT_FOUND', 'message': f'connector lookup failed: {e}'})
    _log_connector_execution('default', req.service_name, prepared['operation_id'], 'prepare', {'body': req.body, 'query': req.query, 'headers': req.headers}, prepared, status='ok')
    return ConnectorPrepareResponse(status='ok', prepared=prepared, codex_prompt=build_codex_prompt(req.service_name, req.operation_id))


@app.get('/connectors/workflow-manifest', response_model=ConnectorWorkflowManifestResponse)
def connectors_workflow_manifest(service_name: str | None = None):
    service_names = [service_name] if service_name else None
    try:
        items = [ConnectorWorkflowManifestItem(**item) for item in build_workflow_manifest(service_names)]
    except KeyError as e:
        raise HTTPException(status_code=404, detail={'code': 'WORKFLOW_NOT_FOUND', 'message': f'connector workflow manifest failed: {e}'})
    _log_connector_execution('default', 'connector_registry', 'workflow_manifest', 'workflow_manifest', {'service_name': service_name}, {'count': len(items)}, status='ok')
    return ConnectorWorkflowManifestResponse(status='ok', count=len(items), connectors=items)


@app.post('/connectors/workflow-draft', response_model=WorkflowDraftResponse)
def connectors_workflow_draft(req: WorkflowDraftRequest):
    try:
        workflow = render_n8n_workflow(req.service_name, req.operation_id, req.workflow_name)
        operation_id = prepare_connector_request(req.service_name, req.operation_id)['operation_id']
    except KeyError as e:
        raise HTTPException(status_code=404, detail={'code': 'WORKFLOW_NOT_FOUND', 'message': f'connector workflow draft failed: {e}'})
    _upsert_workflow_template('default', req.service_name, operation_id, workflow['name'], workflow, 'draft')
    _log_connector_execution('default', req.service_name, operation_id, 'workflow_draft', {'workflow_name': workflow['name']}, {'workflow_name': workflow['name']}, status='ok')
    return WorkflowDraftResponse(status='ok', service_name=req.service_name, operation_id=operation_id, workflow=workflow, codex_prompt=build_codex_prompt(req.service_name, req.operation_id))


@app.post('/connectors/execute-live')
async def connectors_execute_live(req: ConnectorExecuteRequest):
    tenant_id = 'default'
    policy_ctx = None
    try:
        policy_ctx = _enforce_connector_runtime_policy(tenant_id, req.service_name, req.timeout_seconds, req.operation_id)
        result = await execute_live_request(req.service_name, req.operation_id, body=req.body or None, query=req.query or None, headers=req.headers or None, timeout_seconds=policy_ctx['effective_timeout_seconds'])
        result.setdefault('effective_timeout_seconds', policy_ctx['effective_timeout_seconds'])
        result.setdefault('timeout_capped', policy_ctx['timeout_capped'])
        _record_connector_runtime_outcome(tenant_id, req.service_name, True, policy_ctx['policy'])
        _log_connector_execution(tenant_id, req.service_name, result.get('operation_id') or (req.operation_id or 'default'), 'execute_live', {'body': req.body, 'query': req.query, 'headers': req.headers, 'timeout_seconds': policy_ctx['effective_timeout_seconds']}, result, status=result.get('status', 'ok'))
        return result
    except HTTPException as e:
        if e.status_code in {429, 503}:
            detail = e.detail if isinstance(e.detail, dict) else {'message': str(e.detail)}
            service_name = req.service_name
            if policy_ctx is None:
                policy_ctx = {'policy': _get_connector_runtime_policy(service_name, tenant_id)}
            _log_connector_execution(tenant_id, service_name, req.operation_id or 'default', 'execute_live', {'body': req.body, 'query': req.query, 'headers': req.headers}, detail, status='blocked', error_message=str(detail))
        raise
    except KeyError as e:
        raise HTTPException(status_code=404, detail={'code': 'WORKFLOW_NOT_FOUND', 'message': f'connector execution failed: {e}'})
    except httpx.TimeoutException as e:
        service_name = req.service_name
        policy = (policy_ctx or {'policy': _get_connector_runtime_policy(service_name, tenant_id)})['policy']
        _register_connector_isolation_rejection(tenant_id, service_name, policy, 'timeout', str(e))
        _record_connector_runtime_outcome(tenant_id, service_name, False, policy, str(e), timeout_failure=True)
        _log_connector_execution(tenant_id, service_name, req.operation_id or 'default', 'execute_live', {'body': req.body, 'query': req.query, 'headers': req.headers}, {}, status='error', error_message=str(e))
        raise HTTPException(status_code=504, detail={'code': 'CONNECTOR_TIMEOUT', 'message': str(e)})
    except httpx.HTTPError as e:
        service_name = req.service_name
        policy = (policy_ctx or {'policy': _get_connector_runtime_policy(service_name, tenant_id)})['policy']
        _record_connector_runtime_outcome(tenant_id, service_name, False, policy, str(e), timeout_failure=False)
        _log_connector_execution(tenant_id, service_name, req.operation_id or 'default', 'execute_live', {'body': req.body, 'query': req.query, 'headers': req.headers}, {}, status='error', error_message=str(e))
        raise HTTPException(status_code=502, detail={'code': 'DOWNSTREAM_FAILURE', 'message': str(e)})


@app.post('/connectors/validate-config', response_model=ConnectorValidateConfigResponse)
def connectors_validate_config(req: ConnectorValidateConfigRequest):
    try:
        result = validate_connector_config(req.service_name)
        spec = get_connector(req.service_name)
        _upsert_credential_metadata('default', req.service_name, spec.get('required_credentials', []), spec.get('optional_credentials', []), result.get('present_credentials', []), result.get('missing_credentials', []), result.get('notes', ''))
        _log_connector_execution('default', req.service_name, 'validate_config', 'validate', {}, result, status='ok')
        return ConnectorValidateConfigResponse(status='ok', **result)
    except KeyError as e:
        raise HTTPException(status_code=404, detail={'code': 'WORKFLOW_NOT_FOUND', 'message': f'connector validation failed: {e}'})


@app.post('/connectors/smoke-test', response_model=ConnectorSmokeTestResponse)
def connectors_smoke_test(req: ConnectorSmokeTestRequest):
    try:
        result = smoke_test_connector(req.service_name, req.operation_id, req.dry_run)
        _record_smoke_test('default', req.service_name, result.get('operation_id'), req.dry_run, result.get('configured', False), result.get('status', 'ok'), result)
        _log_connector_execution('default', req.service_name, result.get('operation_id') or (req.operation_id or 'default'), 'smoke_test', {'dry_run': req.dry_run}, result, status=result.get('status', 'ok'))
        return ConnectorSmokeTestResponse(**result)
    except KeyError as e:
        raise HTTPException(status_code=404, detail={'code': 'WORKFLOW_NOT_FOUND', 'message': f'connector smoke test failed: {e}'})


@app.post('/connectors/preflight', response_model=ConnectorPreflightResponse)
def connectors_preflight(req: ConnectorPreflightRequest):
    payload = _build_connector_preflight(req.tenant_id, req.service_names, req.persist)
    _log_connector_execution(
        req.tenant_id,
        'connector_registry',
        'preflight',
        'preflight',
        {'tenant_id': req.tenant_id, 'service_names': req.service_names, 'persist': req.persist},
        {'count': payload['count'], 'configured_count': payload['configured_count'], 'live_ready_count': payload['live_ready_count']},
        status='ok',
    )
    return ConnectorPreflightResponse(**payload)


@app.post('/connectors/readiness-report', response_model=ConnectorReadinessReportResponse)
def connectors_readiness_report(req: ConnectorReadinessReportRequest):
    payload = _build_connector_readiness_report(req.tenant_id, req.service_names, req.persist)
    _log_connector_execution(
        req.tenant_id,
        'connector_registry',
        'readiness_report',
        'readiness_report',
        {'tenant_id': req.tenant_id, 'service_names': req.service_names, 'persist': req.persist},
        {'count': payload['count'], 'configured_count': payload['configured_count'], 'live_ready_count': payload['live_ready_count'], 'import_ready_count': payload['import_ready_count'], 'draft_ready_count': payload['draft_ready_count']},
        status='ok',
    )
    return ConnectorReadinessReportResponse(**payload)



@app.post('/connectors/deployment-plan', response_model=ConnectorDeploymentPlanResponse)
def connectors_deployment_plan(req: ConnectorDeploymentPlanRequest):
    payload = _build_connector_deployment_plan(req.tenant_id, req.service_names, req.persist)
    _log_connector_execution(
        req.tenant_id,
        'connector_registry',
        'deployment_plan',
        'deployment_plan',
        {'tenant_id': req.tenant_id, 'service_names': req.service_names, 'persist': req.persist},
        {
            'count': payload['count'],
            'configured_count': payload['configured_count'],
            'live_ready_count': payload['live_ready_count'],
            'ready_to_import_count': payload['ready_to_import_count'],
            'requires_credentials_count': payload['requires_credentials_count'],
        },
        status='ok',
    )
    return ConnectorDeploymentPlanResponse(**payload)




@app.post('/connectors/persistence-report', response_model=ConnectorPersistenceReportResponse)
def connectors_persistence_report(req: ConnectorPersistenceReportRequest):
    payload = _build_connector_persistence_report(req.tenant_id)
    _log_connector_execution(
        req.tenant_id,
        'connector_registry',
        'persistence_report',
        'persistence_report',
        {'tenant_id': req.tenant_id},
        {
            'database_available': payload['database_available'],
            'existing_table_count': payload['existing_table_count'],
            'all_tables_present': payload['all_tables_present'],
            'execution_log_count': payload['execution_log_count'],
        },
        status=payload['status'],
        error_message=payload.get('error'),
    )
    return ConnectorPersistenceReportResponse(**payload)


@app.post('/connectors/rollout-bundle', response_model=ConnectorRolloutBundleResponse)
def connectors_rollout_bundle(req: ConnectorRolloutBundleRequest):
    payload = _build_connector_rollout_bundle(req.tenant_id, req.service_names, req.persist)
    _log_connector_execution(
        req.tenant_id,
        'connector_registry',
        'rollout_bundle',
        'rollout_bundle',
        {'tenant_id': req.tenant_id, 'service_names': req.service_names, 'persist': req.persist},
        {
            'count': payload['count'],
            'configured_count': payload['configured_count'],
            'live_ready_count': payload['live_ready_count'],
            'ready_to_import_count': payload['ready_to_import_count'],
            'requires_credentials_count': payload['requires_credentials_count'],
        },
        status='ok',
    )
    return ConnectorRolloutBundleResponse(**payload)


@app.post('/connectors/credential-matrix', response_model=ConnectorCredentialMatrixResponse)
def connectors_credential_matrix(req: ConnectorCredentialMatrixRequest):
    payload = _build_connector_credential_matrix(req.tenant_id, req.service_names, req.persist)
    _log_connector_execution(
        req.tenant_id,
        'connector_registry',
        'credential_matrix',
        'credential_matrix',
        {'tenant_id': req.tenant_id, 'service_names': req.service_names, 'persist': req.persist},
        {
            'count': payload['count'],
            'configured_count': payload['configured_count'],
            'live_ready_count': payload['live_ready_count'],
            'unique_credential_key_count': payload['unique_credential_key_count'],
        },
        status='ok',
    )
    return ConnectorCredentialMatrixResponse(**payload)


@app.post('/connectors/sync-registry', response_model=ConnectorSyncRegistryResponse)
def connectors_sync_registry(req: ConnectorSyncRegistryRequest):
    services = _sync_connector_registry(req.tenant_id)
    _log_connector_execution(req.tenant_id, 'connector_registry', 'sync_registry', 'sync_registry', {'tenant_id': req.tenant_id}, {'services': services}, status='ok')
    return ConnectorSyncRegistryResponse(status='ok', tenant_id=req.tenant_id, synced_count=len(services), services=services)


@app.get('/connectors/{service_name}/health', response_model=ConnectorHealthResponse)
def connector_health(request: Request, service_name: str, tenant_id: str = 'default'):
    tenant_id = _scoped_tenant_id(request, tenant_id)
    result = validate_connector_config(service_name)
    policy = _get_connector_runtime_policy(service_name, tenant_id)
    state = _get_connector_runtime_state(service_name, tenant_id)
    row = None
    try:
        row = fetch_one("SELECT last_success_at, last_failure_at, failure_rate_percent FROM connector_metrics WHERE tenant_id=%s AND service_name=%s", (tenant_id, normalize_service_name(service_name)))
    except Exception:
        row = None
    row = row or {}
    recent_execute_count = _count_recent_connector_executions(service_name, tenant_id, int(policy['window_seconds']))
    circuit_open = state['circuit_state'] == 'open'
    blocked = circuit_open or recent_execute_count >= int(policy['requests_per_window'])
    return ConnectorHealthResponse(
        status='ok',
        service_name=normalize_service_name(service_name),
        configured=result['configured'],
        implementation_status=result['implementation_status'],
        integration_mode=result['integration_mode'],
        last_success_at=row['last_success_at'].isoformat() if row.get('last_success_at') else None,
        last_failure_at=row['last_failure_at'].isoformat() if row.get('last_failure_at') else None,
        failure_rate_percent=float(row.get('failure_rate_percent') or 0),
        circuit_state=state['circuit_state'],
        circuit_open=circuit_open,
        blocked=blocked,
        consecutive_failures=state['consecutive_failures'],
        failure_threshold=int(policy['failure_threshold']),
        requests_per_window=int(policy['requests_per_window']),
        window_seconds=int(policy['window_seconds']),
        timeout_seconds=int(policy['timeout_seconds']),
        cooldown_seconds=int(policy['cooldown_seconds']),
        rate_limit_rejection_count=state['rate_limit_rejection_count'],
        circuit_open_count=state['circuit_open_count'],
        timeout_rejection_count=state['timeout_rejection_count'],
        notes=result.get('notes', ''),
    )


@app.get('/connectors/{service_name}/metrics', response_model=ConnectorMetricsResponse)
def connector_metrics(request: Request, service_name: str, tenant_id: str = 'default'):
    tenant_id = _scoped_tenant_id(request, tenant_id)
    row = None
    try:
        row = fetch_one("SELECT execution_count, success_count, failure_count, retry_count, blocked_count, rate_limit_rejection_count, circuit_open_count, timeout_rejection_count, failure_rate_percent, circuit_state, consecutive_failures, requests_per_window, window_seconds, timeout_cap_seconds, failure_threshold, cooldown_seconds, last_success_at, last_failure_at, last_circuit_opened_at, last_error_message FROM connector_metrics WHERE tenant_id=%s AND service_name=%s", (tenant_id, normalize_service_name(service_name)))
    except Exception:
        row = None
    policy = _get_connector_runtime_policy(service_name, tenant_id)
    row = row or {}
    return ConnectorMetricsResponse(
        status='ok',
        service_name=normalize_service_name(service_name),
        execution_count=int(row.get('execution_count') or 0),
        success_count=int(row.get('success_count') or 0),
        failure_count=int(row.get('failure_count') or 0),
        retry_count=int(row.get('retry_count') or 0),
        blocked_count=int(row.get('blocked_count') or 0),
        rate_limit_rejection_count=int(row.get('rate_limit_rejection_count') or 0),
        circuit_open_count=int(row.get('circuit_open_count') or 0),
        timeout_rejection_count=int(row.get('timeout_rejection_count') or 0),
        failure_rate_percent=float(row.get('failure_rate_percent') or 0),
        circuit_state=row.get('circuit_state') or 'closed',
        consecutive_failures=int(row.get('consecutive_failures') or 0),
        requests_per_window=int(row.get('requests_per_window') or policy['requests_per_window']),
        window_seconds=int(row.get('window_seconds') or policy['window_seconds']),
        timeout_seconds=int(row.get('timeout_cap_seconds') or policy['timeout_seconds']),
        cooldown_seconds=int(row.get('cooldown_seconds') or policy['cooldown_seconds']),
        last_success_at=row['last_success_at'].isoformat() if row.get('last_success_at') else None,
        last_failure_at=row['last_failure_at'].isoformat() if row.get('last_failure_at') else None,
        last_circuit_opened_at=row['last_circuit_opened_at'].isoformat() if row.get('last_circuit_opened_at') else None,
        last_error_message=row.get('last_error_message'),
    )


@app.get('/connectors/{service_name}', response_model=ConnectorCatalogItem)
def connectors_get(service_name: str):
    try:
        return ConnectorCatalogItem(**get_connector(service_name))
    except KeyError:
        raise HTTPException(status_code=404, detail={'code': 'WORKFLOW_NOT_FOUND', 'message': f'connector {service_name} not found'})


@app.post('/ai/models/register', response_model=RegistryListResponse)
def ai_model_register(req: AIModelRegisterRequest):
    _safe_db_execute(
        """INSERT INTO model_registry (tenant_id, name, type, capabilities, latency_profile, metadata_json)
           VALUES (%s,%s,%s,%s::jsonb,%s,%s::jsonb)
           ON CONFLICT (tenant_id, name) DO UPDATE SET
             type=EXCLUDED.type,
             capabilities=EXCLUDED.capabilities,
             latency_profile=EXCLUDED.latency_profile,
             metadata_json=EXCLUDED.metadata_json,
             updated_at=now()""",
        (req.tenant_id, req.name, req.type, json.dumps(req.capabilities), req.latency_profile, json.dumps(req.metadata_json)),
    )
    items = _build_ai_control_report(req.tenant_id)['models']
    return RegistryListResponse(status='ok', count=len(items), items=items)


@app.post('/ai/prompts/register', response_model=RegistryListResponse)
def ai_prompt_register(req: AIPromptRegisterRequest):
    _safe_db_execute(
        """INSERT INTO prompt_registry (tenant_id, name, version, template, model_compatibility, mode)
           VALUES (%s,%s,%s,%s,%s::jsonb,%s)
           ON CONFLICT (tenant_id, name, version) DO UPDATE SET
             template=EXCLUDED.template,
             model_compatibility=EXCLUDED.model_compatibility,
             mode=EXCLUDED.mode,
             updated_at=now()""",
        (req.tenant_id, req.name, req.version, req.template, json.dumps(req.model_compatibility), req.mode),
    )
    items = _build_ai_control_report(req.tenant_id)['prompts']
    return RegistryListResponse(status='ok', count=len(items), items=items)


@app.post('/ai/route', response_model=AIRouteResponse)
def ai_route(req: AIRouteRequest):
    route = _resolve_ai_route(
        req.tenant_id,
        req.action_type,
        prompt_version=req.prompt_version,
        generation_mode=req.generation_mode,
        preferred_model=req.preferred_model,
        fallback_models=req.fallback_models,
    )
    return AIRouteResponse(
        status='ok',
        tenant_id=req.tenant_id,
        action_type=req.action_type,
        generation_mode=req.generation_mode,
        selected_model=route['selected_model'],
        fallback_models=route['fallback_models'],
        attempted_models=route['attempted_models'],
        prompt_name=route['prompt_name'],
        prompt_version=route['prompt_version'],
        prompt_mode=route['prompt_mode'],
        route_reason=route['route_reason'],
        source=route['source'],
        available_models=route['available_models'],
        available_prompts=route['available_prompts'],
    )


@app.post('/ai/generate', response_model=GenerateResponse)

def ai_generate(req: GenerateRequest):
    request_id = req.request_id or str(uuid4())
    grounding_text = '\n\n'.join([f"[{i+1}] {g.get('title') or g.get('source_ref')}: {g.get('content','')}" for i, g in enumerate(req.grounding)])
    prompt = req.prompt if not grounding_text else f"Use this grounded context when relevant:\n{grounding_text}\n\nUser/task prompt:\n{req.prompt}"
    grounding_refs = [g.get('source_ref') for g in req.grounding if g.get('source_ref')]
    route = _resolve_ai_route(req.tenant_id, req.action_type, prompt_version=req.prompt_version, generation_mode=req.generation_mode, preferred_model=req.preferred_model, fallback_models=req.fallback_models)
    system_prompt_parts = [route.get('prompt_template'), req.system_prompt]
    combined_system_prompt = '\n\n'.join([part for part in system_prompt_parts if part]) or None
    attempted = []
    last_error = None
    for idx, model_name in enumerate(route['attempted_models']):
        attempted.append(model_name)
        try:
            text, latency_ms = ollama.generate(prompt, combined_system_prompt, req.response_schema, model=model_name)
            validation_status, _ = _validate_json(text, req.response_schema)
            artifact_id = _store_ai_artifact(req, request_id, text, latency_ms, validation_status, grounding_refs, ai_model=model_name, ai_prompt_version=route['prompt_version'])
            fallback_used = idx > 0
            _record_ai_route_run(req.tenant_id, request_id, req.action_type, req.generation_mode, model_name, attempted, route['prompt_name'], route['prompt_version'], fallback_used, 'completed', latency_ms=latency_ms)
            write_audit(request_id, req.tenant_id, req.actor_id, 'service', 'assistant', '/ai/generate', 'ai', req.action_type, 'allow', 'completed', True, model_name, req.action_type, latency_ms, grounding_source_refs=grounding_refs)
            return GenerateResponse(status='ok', ai_used=True, model=model_name, routed_model=model_name, prompt_name=route['prompt_name'], prompt_version_used=route['prompt_version'], generation_mode=req.generation_mode, fallback_used=fallback_used, route_reason=route['route_reason'], text=text, latency_ms=latency_ms, artifact_id=artifact_id, validation_status=validation_status, grounding_source_refs=grounding_refs)
        except OllamaError as e:
            last_error = e
            continue
    error = last_error or OllamaError('AI_UNAVAILABLE', 'no models were attempted')
    _record_ai_route_run(req.tenant_id, request_id, req.action_type, req.generation_mode, route['selected_model'], attempted or route['attempted_models'], route['prompt_name'], route['prompt_version'], bool(attempted and attempted[0] != route['selected_model']), 'failed', error_message=error.message)
    write_audit(request_id, req.tenant_id, req.actor_id, 'service', 'assistant', '/ai/generate', 'ai', req.action_type, 'deny', 'failed', False, None, req.action_type, None, error.code, error.message)
    raise HTTPException(status_code=503, detail={'code': error.code, 'message': error.message, 'model': route['selected_model'], 'attempted_models': attempted or route['attempted_models']})

@app.post('/ai/embed', response_model=EmbedResponse)
def ai_embed(req: EmbedRequest):
    try:
        embedding = ollama.embed(req.input_text)
        return EmbedResponse(status='ok', model=settings.ollama_embedding_model, dimensions=len(embedding), embedding=embedding)
    except OllamaError as e:
        raise HTTPException(status_code=503, detail={'code': e.code, 'message': e.message, 'model': settings.ollama_embedding_model})


@app.post('/jobs/enqueue', response_model=JobStatusResponse)
def jobs_enqueue(req: EnqueueRequest):
    existing = None
    if req.idempotency_key:
        existing = fetch_one("SELECT job_id::text AS job_id, status, retry_count, max_retries, result, last_error FROM jobs WHERE tenant_id=%s AND idempotency_key=%s", (req.tenant_id, req.idempotency_key))
    if existing:
        return JobStatusResponse(**existing)
    runtime = describe_queue_runtime()
    backend_name = runtime.get('queue_backend', 'db')
    row = fetch_one(
        """WITH new_job AS (
               INSERT INTO jobs (tenant_id, actor_id, job_type, status, priority, payload, max_retries, scheduled_at, idempotency_key, queue_backend)
               VALUES (%s,%s,%s,'queued',%s,%s::jsonb,%s,COALESCE(%s::timestamptz, now()),%s,%s)
               RETURNING job_id, tenant_id, status, retry_count, max_retries, payload, priority
             ), new_queue AS (
               INSERT INTO queue_items (tenant_id, job_id, queue_name, status, priority, schedule_at, available_at, payload, max_retries, backend_name)
               SELECT %s, job_id, 'default', 'queued', %s, COALESCE(%s::timestamptz, now()), COALESCE(%s::timestamptz, now()), payload, %s, %s FROM new_job
               RETURNING queue_item_id::text AS queue_item_id, tenant_id, job_id::text AS job_id, queue_name, priority, available_at, retry_count, max_retries, payload, backend_name
             )
             SELECT new_job.job_id::text AS job_id, new_job.status, new_job.retry_count, new_job.max_retries, new_queue.queue_item_id, new_queue.tenant_id, new_queue.priority, new_queue.available_at, new_queue.payload, new_queue.backend_name FROM new_job CROSS JOIN new_queue""",
        (req.tenant_id, req.actor_id, req.job_type, req.priority, json.dumps(req.payload), req.max_retries, req.schedule_at, req.idempotency_key, backend_name, req.tenant_id, req.priority, req.schedule_at, req.schedule_at, req.max_retries, backend_name),
    )
    enqueue_queue_item({
        'queue_item_id': row['queue_item_id'],
        'job_id': row['job_id'],
        'tenant_id': row['tenant_id'],
        'queue_name': 'default',
        'priority': row['priority'],
        'available_at': row['available_at'],
        'retry_count': row.get('retry_count', 0),
        'max_retries': row['max_retries'],
        'payload': row.get('payload') or req.payload,
        'backend_name': row.get('backend_name', backend_name),
    })
    return JobStatusResponse(job_id=row['job_id'], status=row['status'], retry_count=row['retry_count'], max_retries=row['max_retries'])


@app.post('/jobs/cancel/{job_id}', response_model=JobStatusResponse)
def jobs_cancel(job_id: str, tenant_id: str = 'default'):
    queue_row = fetch_one("SELECT queue_item_id::text AS queue_item_id FROM queue_items WHERE job_id=%s AND tenant_id=%s ORDER BY created_at DESC LIMIT 1", (job_id, tenant_id))
    execute("UPDATE jobs SET status='cancelled', updated_at=now() WHERE job_id=%s AND tenant_id=%s", (job_id, tenant_id))
    execute("UPDATE queue_items SET status='cancelled', lease_until=NULL, updated_at=now() WHERE job_id=%s AND tenant_id=%s", (job_id, tenant_id))
    cancel_queue_item(queue_row['queue_item_id'] if queue_row else None, job_id=job_id, tenant_id=tenant_id)
    payload = _fetch_job_status_payload(job_id, tenant_id=tenant_id)
    if not payload:
        raise HTTPException(status_code=404, detail={'code': 'WORKFLOW_NOT_FOUND', 'message': f'Job {job_id} not found'})
    return JobStatusResponse(**payload)


@app.get('/jobs/status/{job_id}', response_model=JobStatusResponse)
def jobs_status(request: Request, job_id: str, tenant_id: str = 'default'):
    payload = _fetch_job_status_payload(job_id, request=request, tenant_id=tenant_id)
    if not payload:
        raise HTTPException(status_code=404, detail={'code': 'WORKFLOW_NOT_FOUND', 'message': f'Job {job_id} not found'})
    return JobStatusResponse(**payload)


@app.post('/rag/documents/ingest', response_model=RAGDocumentIngestResponse)
def rag_document_ingest(req: RAGDocumentIngestRequest):
    document_id, count, mode, embedding_model = ingest_document(req.tenant_id, req.actor_id, req.source_ref, req.title or req.source_ref, req.body, req.metadata, req.mime_type, req.embedding_model)
    return RAGDocumentIngestResponse(status='ok', tenant_id=req.tenant_id, source_ref=req.source_ref, document_id=document_id, chunks_created=count, vector_mode=mode, embedding_model=embedding_model)


@app.get('/rag/governance', response_model=RAGGovernanceResponse)
def rag_governance(request: Request, tenant_id: str = 'default'):
    tenant_id = _scoped_tenant_id(request, tenant_id)
    summary = _build_rag_governance_report(tenant_id)
    return RAGGovernanceResponse(status='ok', tenant_id=tenant_id, document_count=summary.get('document_count', 0), chunk_count=summary.get('chunk_count', 0), embedding_version_count=summary.get('embedding_version_count', 0), recent_documents=summary.get('recent_documents', []), latest_embedding_models=summary.get('latest_embedding_models', []))


@app.post('/ingest/note', response_model=IngestNoteResponse)
def ingest_note(req: IngestNoteRequest):
    note = fetch_one("INSERT INTO research_notes (tenant_id, actor_id, title, body, metadata) VALUES (%s,%s,%s,%s,%s::jsonb) RETURNING research_note_id::text AS research_note_id", (req.tenant_id, req.actor_id, req.title, req.body, json.dumps(req.metadata)))
    paper_id, count, mode = ingest_paper(req.tenant_id, req.actor_id, f"research_note:{note['research_note_id']}", req.title or 'Research note', req.body, {'research_note_id': note['research_note_id'], **req.metadata})
    return IngestNoteResponse(status='ok', research_note_id=note['research_note_id'], paper_id=paper_id, chunks_created=count, vector_mode=mode)


@app.post('/ingest/paper', response_model=IngestNoteResponse)
def ingest_paper_endpoint(req: IngestPaperRequest):
    if not req.body:
        raise HTTPException(status_code=400, detail={'code': 'MISSING_ARGUMENT', 'message': 'body is required in phase 3 ingestion endpoint'})
    paper_id, count, mode = ingest_paper(req.tenant_id, req.actor_id, req.source_ref, req.title or req.source_ref, req.body, req.metadata)
    return IngestNoteResponse(status='ok', paper_id=paper_id, chunks_created=count, vector_mode=mode)


@app.post('/retrieve/query', response_model=RetrieveResponse)
def retrieve_query(req: RetrieveRequest):
    rows, mode = search_grounded(req.tenant_id, req.actor_id, req.query, req.limit, req.metadata_filters)
    items = [RetrieveItem(**r) for r in rows]
    return RetrieveResponse(status='ok', mode=mode, count=len(items), items=items)


@app.post('/approvals/evaluate')
def approval_evaluate(req: ApprovalEvaluateRequest):
    actor_ok = enforce_scope(req.tenant_id, req.actor_id, f'approve:{req.domain}') or enforce_scope(req.tenant_id, req.actor_id, 'admin')
    policy = fetch_one("SELECT approval_policy_id::text AS approval_policy_id, min_approvers, auto_approve, COALESCE(require_reviewer_separation,false) AS require_reviewer_separation FROM approval_policies WHERE tenant_id=%s AND domain=%s AND action_type=%s ORDER BY created_at DESC LIMIT 1", (req.tenant_id, req.domain, req.action_type))
    needs_approval = not (policy and policy.get('auto_approve'))
    return {'status': 'ok', 'authorized_reviewer': actor_ok, 'needs_approval': needs_approval, 'policy': policy}


@app.post('/approvals/transition')
def approval_transition(req: ApprovalTransitionRequest):
    approval = fetch_one("SELECT approval_id::text, tenant_id, requested_by, domain, action_type, status, metadata FROM approvals WHERE approval_id=%s AND tenant_id=%s", (req.approval_id, req.tenant_id))
    if not approval:
        raise HTTPException(status_code=404, detail={'code': 'WORKFLOW_NOT_FOUND', 'message': 'approval not found'})
    scope_needed = f"approve:{approval['domain']}"
    if not (enforce_scope(req.tenant_id, req.actor_id, scope_needed) or enforce_scope(req.tenant_id, req.actor_id, 'approve:general') or enforce_scope(req.tenant_id, req.actor_id, 'admin')):
        raise HTTPException(status_code=403, detail={'code': 'ACCESS_DENIED', 'message': 'approval scope required'})
    metadata = approval.get('metadata') or {}
    if metadata.get('require_reviewer_separation') and approval.get('requested_by') == req.actor_id:
        raise HTTPException(status_code=403, detail={'code': 'ACCESS_DENIED', 'message': 'reviewer separation required'})
    new_status = 'approved' if req.decision == 'approved' else 'rejected'
    execute("UPDATE approvals SET status=%s, decided_by=%s, decision_note=%s, decided_at=now(), updated_at=now() WHERE approval_id=%s AND tenant_id=%s", (new_status, req.actor_id, req.note, req.approval_id, req.tenant_id))
    execute("INSERT INTO approval_steps (approval_id, actor_id, step_name, step_status, note) VALUES (%s,%s,'decision',%s,%s)", (req.approval_id, req.actor_id, new_status, req.note))
    return {'status': 'ok', 'approval_id': req.approval_id, 'decision': new_status}


def _store_manuscript(req: CommandRequest, title: str, ai: GenerateResponse):
    ms = fetch_one("INSERT INTO manuscripts (tenant_id, title, status, artifact_ref) VALUES (%s,%s,'draft',%s) RETURNING manuscript_id::text AS manuscript_id", (req.tenant_id, title, ai.artifact_id))
    execute("INSERT INTO manuscript_sections (manuscript_id, section_name, content, grounding_source_refs) VALUES (%s,'draft',%s,%s::jsonb)", (ms['manuscript_id'], ai.text, json.dumps(ai.grounding_source_refs)))
    return ms['manuscript_id']


def _create_approval(tenant_id: str, domain: str, action_type: str, artifact_ref: str | None, actor_id: str, request_id: str, require_reviewer_separation: bool = False):
    row = fetch_one("INSERT INTO approvals (tenant_id, domain, action_type, status, artifact_ref, requested_by, metadata) VALUES (%s,%s,%s,'pending',%s,%s,%s::jsonb) RETURNING approval_id::text AS approval_id", (tenant_id, domain, action_type, artifact_ref, actor_id, json.dumps({'request_id': request_id, 'require_reviewer_separation': require_reviewer_separation})))
    execute("INSERT INTO approval_steps (approval_id, actor_id, step_name, step_status, note) VALUES (%s,%s,'requested','pending',%s)", (row['approval_id'], actor_id, f'{domain}:{action_type}'))
    return row['approval_id']


def _ai_command(cmd: str, req: CommandRequest, request_id: str) -> CommandResponse:
    query = req.args or req.text or cmd
    rows, mode = search_grounded(req.tenant_id, req.actor_id, query, settings.retrieval_limit)
    response_schema = None
    system_prompt = settings.fallback_chat_system_prompt
    prompt_version = 'phase3.command.v1'
    if cmd in ['/triage', '/meetingprep', '/followup', '/draftpost', '/manuscript', '/reliability', '/publishbundle']:
        response_schema = {'type': 'object', 'required': ['summary', 'actions'], 'properties': {'summary': {'type': 'string'}, 'actions': {'type': 'array'}}}
        system_prompt = 'Return compact valid JSON with keys summary and actions. Use only grounded context and user request. Do not invent facts.'
    prompt = f"Command: {cmd}\nArgs: {req.args}\nProvide a grounded result. State uncertainty when evidence is weak."
    ai = ai_generate(GenerateRequest(tenant_id=req.tenant_id, actor_id=req.actor_id, request_id=request_id, prompt=prompt, system_prompt=system_prompt, action_type=cmd.strip('/'), prompt_version=prompt_version, response_schema=response_schema, grounding=rows))
    data = {'validation_status': ai.validation_status, 'mode': mode, 'grounding_source_refs': ai.grounding_source_refs, 'artifact_id': ai.artifact_id}
    if cmd == '/draftpost':
        post = fetch_one("INSERT INTO social_posts (tenant_id, actor_id, post_text, status) VALUES (%s,%s,%s,'draft') RETURNING social_post_id::text AS social_post_id", (req.tenant_id, req.actor_id, ai.text))
        approval_id = _create_approval(req.tenant_id, 'social', 'draftpost', post['social_post_id'], req.actor_id, request_id, True)
        data.update({'social_post_id': post['social_post_id'], 'approval_id': approval_id})
    if cmd == '/manuscript':
        manuscript_id = _store_manuscript(req, req.args or 'Untitled manuscript', ai)
        approval_id = _create_approval(req.tenant_id, 'publication', 'manuscript', manuscript_id, req.actor_id, request_id, True)
        data.update({'manuscript_id': manuscript_id, 'approval_id': approval_id})
    return CommandResponse(status='ok', command=cmd, ai_used=True, model=settings.ollama_model, message=ai.text, request_id=request_id, data=data)


@app.post('/publishbundle/build', response_model=PublishBundleResponse)
def publishbundle_build(req: PublishBundleRequest):
    workflow_guard = _check_workflow_execution_cap(req.tenant_id, 'wf_workflow_promotion_pipeline', actor_id=req.actor_id, persist=True, metadata_json={'source': 'publishbundle_build'})
    if not workflow_guard['allowed']:
        raise HTTPException(status_code=429, detail={'code': 'WORKFLOW_CAP_EXCEEDED', 'message': 'wf_workflow_promotion_pipeline is at its execution cap', 'retry_after_seconds': workflow_guard['retry_after_seconds'], 'workflow_id': 'wf_workflow_promotion_pipeline'})
    approved_posts = fetch_all("SELECT social_post_id::text, post_text, status FROM social_posts WHERE tenant_id=%s AND status IN ('approved','published','draft') ORDER BY created_at DESC LIMIT 10", (req.tenant_id,))
    assets = fetch_all("SELECT social_asset_id::text, asset_ref, metadata FROM social_assets WHERE tenant_id=%s ORDER BY created_at DESC LIMIT 20", (req.tenant_id,))
    approvals = fetch_all("SELECT approval_id::text, domain, action_type, status, artifact_ref FROM approvals WHERE tenant_id=%s AND status='approved' ORDER BY created_at DESC LIMIT 20", (req.tenant_id,))
    bundle_payload = {
        'title': req.title,
        'metadata': req.metadata,
        'posts': approved_posts,
        'assets': assets,
        'approvals': approvals,
    }
    summary_prompt = req.summary_prompt or f"Build a concise publication release summary for '{req.title}' using the approved posts, assets, and approvals." 
    grounding = [{'source_ref': f"post:{p['social_post_id']}", 'title': 'social_post', 'content': p.get('post_text','')} for p in approved_posts] + [{'source_ref': f"asset:{a['social_asset_id']}", 'title': 'asset', 'content': a.get('asset_ref','')} for a in assets[:5]]
    summary = ai_generate(GenerateRequest(tenant_id=req.tenant_id, actor_id=req.actor_id, prompt=summary_prompt, action_type='publishbundle', prompt_version='phase3.publishbundle.v1', grounding=grounding))
    bundle = fetch_one("INSERT INTO publication_bundles (tenant_id, title, status, bundle_manifest, created_by, ai_summary_artifact_ref) VALUES (%s,%s,%s,%s::jsonb,%s,%s) RETURNING publication_bundle_id::text AS publication_bundle_id", (req.tenant_id, req.title, 'pending_approval' if req.require_approval else 'ready', json.dumps(bundle_payload), req.actor_id, summary.artifact_id))
    release = fetch_one("INSERT INTO release_artifacts (tenant_id, artifact_type, artifact_ref, metadata) VALUES (%s,'publication_bundle',%s,%s::jsonb) RETURNING release_artifact_id::text AS release_artifact_id", (req.tenant_id, bundle['publication_bundle_id'], json.dumps({'title': req.title, 'summary_artifact_id': summary.artifact_id})))
    approval_id = None
    if req.require_approval:
        approval_id = _create_approval(req.tenant_id, 'publication', 'publishbundle', bundle['publication_bundle_id'], req.actor_id, str(uuid4()), True)
    return PublishBundleResponse(status='ok', publication_bundle_id=bundle['publication_bundle_id'], release_artifact_id=release['release_artifact_id'], approval_id=approval_id, summary_artifact_id=summary.artifact_id, bundle_status='pending_approval' if req.require_approval else 'ready', included_posts=len(approved_posts), included_assets=len(assets), included_approvals=len(approvals))


@app.post('/command/execute', response_model=CommandResponse)
def command_execute(req: CommandRequest):
    request_id = req.request_id or str(uuid4())
    cmd = req.command.strip().lower()
    args = (req.args or '').strip()
    req.args = args

    if cmd == '/connectors':
        items = list_catalog()
        lines = [f"{item['service_name']} | {item['integration_mode']} | {item['status']}" for item in items]
        return CommandResponse(status='ok', command=cmd, message='\n'.join(lines), request_id=request_id, data={'connectors': items})
    if cmd == '/connector':
        if not args:
            raise HTTPException(status_code=400, detail={'code': 'MISSING_ARGUMENT', 'message': 'connector service name required'})
        spec = get_connector(args)
        return CommandResponse(status='ok', command=cmd, message=json.dumps(spec, default=str), request_id=request_id, data=spec)
    if cmd == '/workflowdraft':
        if not args:
            raise HTTPException(status_code=400, detail={'code': 'MISSING_ARGUMENT', 'message': 'expected service_name[:operation_id]'})
        service_name, _, operation_id = args.partition(':')
        workflow = render_n8n_workflow(service_name, operation_id or None)
        return CommandResponse(status='ok', command=cmd, message=f"workflow draft ready for {service_name}", request_id=request_id, data={'workflow': workflow, 'codex_prompt': build_codex_prompt(service_name, operation_id or None)})
    if cmd == '/status':
        notes = fetch_one("SELECT count(*)::int AS c FROM notes WHERE tenant_id=%s", (req.tenant_id,))['c']
        reminders = fetch_one("SELECT count(*)::int AS c FROM reminders WHERE tenant_id=%s AND status in ('pending','queued')", (req.tenant_id,))['c']
        jobs = fetch_one("SELECT count(*)::int AS c FROM jobs WHERE tenant_id=%s AND status in ('queued','running')", (req.tenant_id,))['c']
        msg = f"status ok | notes={notes} reminders={reminders} active_jobs={jobs}"
        write_audit(request_id, req.tenant_id, req.actor_id, req.source, req.channel, '/command/execute', 'operator', cmd, 'allow', 'completed')
        return CommandResponse(status='ok', command=cmd, message=msg, request_id=request_id, data={'notes': notes, 'reminders': reminders, 'jobs': jobs})
    if cmd == '/health':
        h = health()
        return CommandResponse(status='ok', command=cmd, message=f"postgres={h.postgres} ollama={h.ollama} queue_depth={h.queue_depth}", request_id=request_id, data=h.model_dump())
    if cmd == '/jobs':
        rows = fetch_all("SELECT job_id::text, job_type, status, priority, created_at FROM jobs WHERE tenant_id=%s ORDER BY created_at DESC LIMIT 10", (req.tenant_id,))
        lines = [f"{r['job_id']} {r['job_type']} {r['status']} p{r['priority']}" for r in rows] or ['no jobs']
        return CommandResponse(status='ok', command=cmd, message='\n'.join(lines), request_id=request_id, data={'jobs': rows})
    if cmd == '/logs':
        if args:
            rows = fetch_all("SELECT attempt_id::text, status, error_message, started_at, finished_at FROM queue_attempts WHERE job_id=%s ORDER BY started_at DESC LIMIT 10", (args,))
        else:
            rows = fetch_all("SELECT attempt_id::text, job_id::text, status, error_message, started_at FROM queue_attempts ORDER BY started_at DESC LIMIT 10")
        lines = [json.dumps(r, default=str) for r in rows] or ['no logs']
        return CommandResponse(status='ok', command=cmd, message='\n'.join(lines), request_id=request_id, data={'logs': rows})
    if cmd == '/note':
        execute("INSERT INTO notes (tenant_id, actor_id, note_text) VALUES (%s,%s,%s)", (req.tenant_id, req.actor_id, args))
        return CommandResponse(status='ok', command=cmd, message='note saved', request_id=request_id)
    if cmd == '/remind':
        task, due = (args.split('|', 1) + [''])[:2]
        rem = fetch_one("INSERT INTO reminders (tenant_id, actor_id, task_text, due_at, status) VALUES (%s,%s,%s,CASE WHEN %s<>'' THEN %s::timestamptz ELSE NULL END,'pending') RETURNING reminder_id::text AS reminder_id", (req.tenant_id, req.actor_id, task.strip(), due.strip(), due.strip()))
        jobs_enqueue(EnqueueRequest(tenant_id=req.tenant_id, actor_id=req.actor_id, job_type='deliver_reminder', payload={'job_type': 'deliver_reminder', 'reminder_id': rem['reminder_id']}, priority=4))
        return CommandResponse(status='ok', command=cmd, message=f"reminder saved {rem['reminder_id']}", request_id=request_id, data=rem)
    if cmd == '/reminders':
        rows = fetch_all("SELECT reminder_id::text, task_text, due_at, status FROM reminders WHERE tenant_id=%s ORDER BY created_at DESC LIMIT 20", (req.tenant_id,))
        lines = [f"{r['reminder_id']} | {r['task_text']} | {r['status']}" for r in rows] or ['no reminders']
        return CommandResponse(status='ok', command=cmd, message='\n'.join(lines), request_id=request_id, data={'reminders': rows})
    if cmd == '/researchnote':
        res = ingest_note(IngestNoteRequest(tenant_id=req.tenant_id, actor_id=req.actor_id, title='Research note', body=args, metadata={'ingested_from': 'command'}))
        return CommandResponse(status='ok', command=cmd, message=f"research note saved; chunks={res.chunks_created}", request_id=request_id, data=res.model_dump())
    if cmd == '/today':
        rows = fetch_all("SELECT task_text, due_at, status FROM reminders WHERE tenant_id=%s AND (due_at::date = current_date OR due_at IS NULL) ORDER BY due_at NULLS LAST, created_at DESC LIMIT 20", (req.tenant_id,))
        return CommandResponse(status='ok', command=cmd, message='\n'.join([f"{r['task_text']} | {r['status']}" for r in rows]) or 'nothing scheduled', request_id=request_id, data={'items': rows})
    if cmd == '/digest':
        counts = {'notes': fetch_one("SELECT count(*)::int AS c FROM notes WHERE tenant_id=%s", (req.tenant_id,))['c'], 'research_notes': fetch_one("SELECT count(*)::int AS c FROM research_notes WHERE tenant_id=%s", (req.tenant_id,))['c'], 'jobs': fetch_one("SELECT count(*)::int AS c FROM jobs WHERE tenant_id=%s", (req.tenant_id,))['c']}
        return CommandResponse(status='ok', command=cmd, message=f"digest notes={counts['notes']} research_notes={counts['research_notes']} jobs={counts['jobs']}", request_id=request_id, data=counts)
    if cmd == '/queue':
        rows = fetch_all("SELECT queue_item_id::text, job_id::text, status, priority, available_at, retry_count FROM queue_items WHERE tenant_id=%s ORDER BY created_at DESC LIMIT 20", (req.tenant_id,))
        return CommandResponse(status='ok', command=cmd, message='\n'.join([json.dumps(r, default=str) for r in rows]) or 'empty queue', request_id=request_id, data={'queue': rows})
    if cmd == '/dequeue':
        if not args:
            raise HTTPException(status_code=400, detail={'code': 'MISSING_ARGUMENT', 'message': 'job id required'})
        jobs_cancel(args, tenant_id=req.tenant_id)
        return CommandResponse(status='ok', command=cmd, message=f'cancelled {args}', request_id=request_id)
    if cmd == '/rbac':
        rows = fetch_all("SELECT r.role_name, array_agg(s.scope_name ORDER BY s.scope_name) AS scopes FROM actor_roles ar JOIN roles r ON r.role_id=ar.role_id JOIN role_scopes rs ON rs.role_id=r.role_id JOIN scopes s ON s.scope_id=rs.scope_id WHERE ar.actor_id=%s AND ar.tenant_id=%s GROUP BY r.role_name", (req.actor_id, req.tenant_id))
        return CommandResponse(status='ok', command=cmd, message='\n'.join([f"{r['role_name']}: {', '.join(r['scopes'])}" for r in rows]) or 'no roles', request_id=request_id, data={'roles': rows})
    if cmd == '/approvals':
        rows = fetch_all("SELECT approval_id::text, domain, action_type, status, artifact_ref FROM approvals WHERE tenant_id=%s AND domain<>'social' ORDER BY created_at DESC LIMIT 20", (req.tenant_id,))
        return CommandResponse(status='ok', command=cmd, message='\n'.join([json.dumps(r, default=str) for r in rows]) or 'no approvals', request_id=request_id, data={'approvals': rows})
    if cmd == '/socialapprovals':
        rows = fetch_all("SELECT approval_id::text, domain, action_type, status, artifact_ref FROM approvals WHERE tenant_id=%s AND domain='social' ORDER BY created_at DESC LIMIT 20", (req.tenant_id,))
        return CommandResponse(status='ok', command=cmd, message='\n'.join([json.dumps(r, default=str) for r in rows]) or 'no social approvals', request_id=request_id, data={'approvals': rows})
    if cmd == '/lead':
        execute("INSERT INTO accounts (tenant_id, account_name, metadata) VALUES (%s,%s,%s::jsonb)", (req.tenant_id, args[:120], json.dumps({'source': 'lead_command'})))
        return CommandResponse(status='ok', command=cmd, message='lead captured', request_id=request_id)
    if cmd == '/account':
        row = fetch_one("SELECT account_id::text, account_name, metadata FROM accounts WHERE tenant_id=%s AND (account_name ILIKE %s OR account_id::text=%s) ORDER BY created_at DESC LIMIT 1", (req.tenant_id, f'%{args}%', args))
        return CommandResponse(status='ok', command=cmd, message=json.dumps(row, default=str) if row else 'account not found', request_id=request_id, data=row or {})
    if cmd == '/deliverables':
        rows = fetch_all("SELECT deliverable_id::text, account_id::text, title, status, due_at FROM deliverables WHERE tenant_id=%s AND (account_id::text=%s OR %s='') ORDER BY created_at DESC LIMIT 20", (req.tenant_id, args, args))
        return CommandResponse(status='ok', command=cmd, message='\n'.join([json.dumps(r, default=str) for r in rows]) or 'no deliverables', request_id=request_id, data={'deliverables': rows})
    if cmd == '/idea':
        execute("INSERT INTO social_ideas (tenant_id, actor_id, idea_text) VALUES (%s,%s,%s)", (req.tenant_id, req.actor_id, args))
        return CommandResponse(status='ok', command=cmd, message='idea stored', request_id=request_id)
    if cmd == '/collectassets':
        execute("INSERT INTO social_assets (tenant_id, asset_ref, metadata) VALUES (%s,%s,%s::jsonb)", (req.tenant_id, args or 'asset-collection', json.dumps({'collected_from': 'command'})))
        return CommandResponse(status='ok', command=cmd, message='asset collection recorded', request_id=request_id)
    if cmd == '/socialstats':
        stats = compute_metrics(req.tenant_id)
        return CommandResponse(status='ok', command=cmd, message=f"published_posts={stats['published_posts']} pending_approvals={stats['pending_approvals']}", request_id=request_id, data=stats)
    if cmd == '/publish':
        if not args:
            raise HTTPException(status_code=400, detail={'code': 'MISSING_ARGUMENT', 'message': 'post id required'})
        approval = fetch_one("SELECT approval_id::text, status FROM approvals WHERE tenant_id=%s AND domain='social' AND artifact_ref=%s ORDER BY created_at DESC LIMIT 1", (req.tenant_id, args))
        if approval and approval['status'] != 'approved':
            raise HTTPException(status_code=400, detail={'code': 'VALIDATION_ERROR', 'message': 'social post must be approved before publish'})
        execute("UPDATE social_posts SET status='published', published_at=now(), updated_at=now() WHERE social_post_id=%s AND tenant_id=%s", (args, req.tenant_id))
        execute("INSERT INTO analytics_snapshots (tenant_id, snapshot_type, snapshot_data) VALUES (%s,'social_publish',%s::jsonb)", (req.tenant_id, json.dumps({'post_id': args})))
        return CommandResponse(status='ok', command=cmd, message=f'published {args}', request_id=request_id)
    if cmd == '/publishbundle':
        bundle = publishbundle_build(PublishBundleRequest(tenant_id=req.tenant_id, actor_id=req.actor_id, title=args or 'Publication bundle', require_approval=True))
        return CommandResponse(status='ok', command=cmd, ai_used=True, model=settings.ollama_model, message=f"bundle {bundle.publication_bundle_id} built with {bundle.included_posts} posts and {bundle.included_assets} assets", request_id=request_id, data=bundle.model_dump())
    if cmd in ['/research', '/methods', '/paper', '/manuscript', '/triage', '/meetingprep', '/followup', '/draftpost', '/reliability', '/compare', '/datasetqa', '/run']:
        response = _ai_command(cmd, req, request_id)
        if cmd == '/reliability':
            response.data['metrics'] = persist_snapshots(req.tenant_id)
        return response
    raise HTTPException(status_code=400, detail={'code': 'INVALID_COMMAND', 'message': f'Unsupported command {cmd}'})



@app.post('/secrets/set', response_model=SecretSetResponse)
def secrets_set(req: SecretSetRequest, request: Request):
    actor_id = getattr(request.state, 'actor_id', 'anonymous')
    payload = set_secret(req.secret_name, req.secret_value, tenant_id=req.tenant_id, created_by=actor_id, connector_binding=req.connector_binding)
    return SecretSetResponse(**payload)


@app.post('/secrets/get', response_model=SecretGetResponse)
def secrets_get(req: SecretGetRequest):
    item = get_secret(req.secret_name, tenant_id=req.tenant_id, reveal=req.reveal)
    if not item:
        raise HTTPException(status_code=404, detail={'code': 'SECRET_NOT_FOUND', 'message': req.secret_name})
    return SecretGetResponse(status='ok', secret=SecretItem(**item))


@app.post('/secrets/list', response_model=SecretListResponse)
def secrets_list(req: SecretListRequest):
    payload = list_secrets(req.tenant_id)
    payload['secrets'] = [SecretItem(**item) for item in payload['secrets']]
    return SecretListResponse(**payload)


@app.get('/admin/queue', response_model=AdminSummaryResponse)
def admin_queue(request: Request, tenant_id: str = 'default'):
    tenant_id = _scoped_tenant_id(request, tenant_id)
    summary = {}
    for key, sql in {
        'queue_depth': "SELECT count(*)::int AS c FROM queue_items WHERE tenant_id=%s AND status IN ('queued','running')",
        'dlq_size': "SELECT count(*)::int AS c FROM dead_letter_items WHERE tenant_id=%s",
        'retrying': "SELECT count(*)::int AS c FROM queue_items WHERE tenant_id=%s AND retry_count > 0",
        'highest_priority_waiting': "SELECT COALESCE(min(priority), 0)::int AS c FROM queue_items WHERE tenant_id=%s AND status='queued'",
    }.items():
        try:
            summary[key] = (fetch_one(sql, (tenant_id,)) or {'c': 0})['c']
        except Exception:
            summary[key] = 0
    summary.update(describe_queue_runtime())
    try:
        summary['active_workers'] = (fetch_one("SELECT count(*)::int AS c FROM queue_workers WHERE backend_name=%s AND last_heartbeat_at >= now() - interval '5 minutes'", (summary['queue_backend'],)) or {'c': 0})['c']
    except Exception:
        summary['active_workers'] = 0
    try:
        rows = fetch_all("SELECT tenant_id, job_id, status, priority, retry_count, created_at FROM queue_items WHERE tenant_id=%s ORDER BY created_at DESC LIMIT 10", (tenant_id,)) or []
        summary['recent_queue_items'] = _apply_tenant_row_scope(request, [dict(row) for row in rows], 'queue_items', requested_tenant_id=tenant_id, action='read')
    except Exception:
        summary['recent_queue_items'] = []
    try:
        rows = fetch_all("SELECT tenant_id, job_id, failure_reason, failed_at FROM dead_letter_items WHERE tenant_id=%s ORDER BY failed_at DESC LIMIT 10", (tenant_id,)) or []
        summary['recent_dead_letters'] = _apply_tenant_row_scope(request, [dict(row) for row in rows], 'dead_letter_items', requested_tenant_id=tenant_id, action='read')
    except Exception:
        summary['recent_dead_letters'] = []
    return AdminSummaryResponse(status='ok', tenant_id=tenant_id, summary=summary)


@app.get('/admin/jobs', response_model=AdminSummaryResponse)
def admin_jobs(request: Request, tenant_id: str = 'default'):
    tenant_id = _scoped_tenant_id(request, tenant_id)
    summary = {}
    for key, sql in {
        'queued': "SELECT count(*)::int AS c FROM jobs WHERE tenant_id=%s AND status='queued'",
        'running': "SELECT count(*)::int AS c FROM jobs WHERE tenant_id=%s AND status='running'",
        'failed': "SELECT count(*)::int AS c FROM jobs WHERE tenant_id=%s AND status='failed'",
        'completed_24h': "SELECT count(*)::int AS c FROM jobs WHERE tenant_id=%s AND completed_at >= now() - interval '24 hours'",
    }.items():
        try:
            summary[key] = (fetch_one(sql, (tenant_id,)) or {'c': 0})['c']
        except Exception:
            summary[key] = 0
    try:
        rows = fetch_all("SELECT tenant_id, job_id, workflow_id, status, retry_count, created_at, completed_at FROM jobs WHERE tenant_id=%s ORDER BY created_at DESC LIMIT 10", (tenant_id,)) or []
        summary['recent_jobs'] = _apply_tenant_row_scope(request, [dict(row) for row in rows], 'jobs', requested_tenant_id=tenant_id, action='read')
    except Exception:
        summary['recent_jobs'] = []
    return AdminSummaryResponse(status='ok', tenant_id=tenant_id, summary=summary)


@app.get('/admin/connectors', response_model=AdminSummaryResponse)
def admin_connectors(request: Request, tenant_id: str = 'default'):
    tenant_id = _scoped_tenant_id(request, tenant_id)
    summary = {'connectors': []}
    for spec in list_catalog():
        health = connector_health(spec['service_name'], tenant_id=tenant_id)
        summary['connectors'].append(health.model_dump())
    summary['connectors'] = _apply_tenant_row_scope(request, summary['connectors'], 'connector_metrics', requested_tenant_id=tenant_id, action='read')
    summary['connector_count'] = len(summary['connectors'])
    summary['configured_count'] = sum(1 for item in summary['connectors'] if item['configured'])
    return AdminSummaryResponse(status='ok', tenant_id=tenant_id, summary=summary)


@app.get('/admin/system', response_model=AdminSummaryResponse)
def admin_system(request: Request, tenant_id: str = 'default'):
    tenant_id = _scoped_tenant_id(request, tenant_id)
    summary = {'tenant_id': tenant_id, 'metrics': compute_metrics(tenant_id), 'auth_required': settings.auth_required, 'queue_backend': settings.queue_backend}
    try:
        row = fetch_one("SELECT COALESCE(sum(CASE WHEN circuit_state='open' THEN 1 ELSE 0 END),0)::int AS open_circuits, COALESCE(sum(rate_limit_rejection_count),0)::int AS rate_limit_rejections, COALESCE(sum(timeout_rejection_count),0)::int AS timeout_rejections FROM connector_metrics WHERE tenant_id=%s", (tenant_id,)) or {'open_circuits': 0, 'rate_limit_rejections': 0, 'timeout_rejections': 0}
        summary.update({'open_circuit_count': row['open_circuits'], 'rate_limit_rejections': row['rate_limit_rejections'], 'timeout_rejections': row['timeout_rejections']})
    except Exception:
        summary.update({'open_circuit_count': 0, 'rate_limit_rejections': 0, 'timeout_rejections': 0})
    return AdminSummaryResponse(status='ok', tenant_id=tenant_id, summary=summary)


@app.get('/admin/workflows', response_model=AdminSummaryResponse)
def admin_workflows(request: Request, tenant_id: str = 'default'):
    tenant_id = _scoped_tenant_id(request, tenant_id)
    summary = {}
    for key, sql in {
        'workflow_version_count': "SELECT count(*)::int AS c FROM workflow_versions WHERE tenant_id=%s",
        'published_count': "SELECT count(*)::int AS c FROM workflow_versions WHERE tenant_id=%s AND status='published'",
        'draft_count': "SELECT count(*)::int AS c FROM workflow_versions WHERE tenant_id=%s AND status='draft'",
        'workflow_event_count': "SELECT count(*)::int AS c FROM workflow_version_events WHERE tenant_id=%s",
    }.items():
        try:
            summary[key] = (fetch_one(sql, (tenant_id,)) or {'c': 0})['c']
        except Exception:
            summary[key] = 0
    try:
        rows = fetch_all(
            "SELECT workflow_id, version, status AS workflow_status FROM workflow_versions WHERE tenant_id=%s ORDER BY updated_at DESC NULLS LAST, version DESC LIMIT 10",
            (tenant_id,),
        ) or []
        summary['recent_versions'] = _apply_tenant_row_scope(request, [dict(row) for row in rows], 'workflow_versions', requested_tenant_id=tenant_id, action='read')
    except Exception:
        summary['recent_versions'] = []
    return AdminSummaryResponse(status='ok', tenant_id=tenant_id, summary=summary)


@app.post('/connectors/{service_name}/policy', response_model=ConnectorHealthResponse)
def connector_policy_upsert(service_name: str, req: ConnectorPolicyUpsertRequest):
    canonical = normalize_service_name(service_name)
    _safe_db_execute(
        """INSERT INTO connector_runtime_policies (tenant_id, service_name, enabled, requests_per_window, window_seconds, timeout_seconds, failure_threshold, cooldown_seconds)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (tenant_id, service_name)
           DO UPDATE SET enabled=EXCLUDED.enabled,
                         requests_per_window=EXCLUDED.requests_per_window,
                         window_seconds=EXCLUDED.window_seconds,
                         timeout_seconds=EXCLUDED.timeout_seconds,
                         failure_threshold=EXCLUDED.failure_threshold,
                         cooldown_seconds=EXCLUDED.cooldown_seconds,
                         updated_at=now()""",
        (req.tenant_id, canonical, req.enabled, req.requests_per_window, req.window_seconds, req.timeout_seconds, req.failure_threshold, req.cooldown_seconds),
    )
    return connector_health(canonical, tenant_id=req.tenant_id)




def _release_artifact_dir() -> Path:
    configured = (settings.release_artifact_dir or '').strip()
    if configured:
        path = Path(configured)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
    else:
        path = PROJECT_ROOT / 'artifacts'
    path.mkdir(parents=True, exist_ok=True)
    return path


_RELEASE_EXCLUDE_PATHS = {
    'service/.pytest_cache',
    'docs/generated_release_manifest.json',
    'docs/generated_release_checksum_validation.json',
    'docs/generated_release_preflight_report.json',
    'docs/generated_release_rollback_package.json',
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_json_checksum(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _release_candidate_files() -> list[Path]:
    include_dirs = ['service/app', 'service/tests', 'scripts', 'n8n/import', 'n8n/manifest', 'docs', 'migrations', 'sql', 'deploy', 'connectors', 'prompts', 'config']
    include_files = ['service/Dockerfile', 'service/requirements.txt']
    candidates: dict[str, Path] = {}
    for rel in include_dirs:
        base = PROJECT_ROOT / rel
        if not base.exists():
            continue
        for path in base.rglob('*'):
            if not path.is_file():
                continue
            rel_path = path.relative_to(PROJECT_ROOT).as_posix()
            if any(part in {'__pycache__', '.pytest_cache'} for part in path.parts):
                continue
            if rel_path in _RELEASE_EXCLUDE_PATHS:
                continue
            if rel_path.startswith('artifacts/') and rel_path.endswith('.zip'):
                continue
            candidates[rel_path] = path
    for rel in include_files:
        path = PROJECT_ROOT / rel
        if path.exists() and path.is_file():
            candidates[path.relative_to(PROJECT_ROOT).as_posix()] = path
    return [candidates[key] for key in sorted(candidates)]


def _build_release_manifest(tenant_id: str = 'default', release_version: str | None = None, package_filename: str | None = None, source_package: str | None = None, created_by: str | None = None, persist: bool = True) -> dict[str, Any]:
    files = _release_candidate_files()
    checksums = {path.relative_to(PROJECT_ROOT).as_posix(): _sha256_file(path) for path in files}
    workflow_files = [path for path in checksums if path.startswith('n8n/import/') and path.endswith('.json')]
    migration_files = [path for path in checksums if (path.startswith('migrations/') or path.startswith('sql/')) and path.endswith('.sql')]
    resolved_version = (release_version or '').strip() or f"{app.version}-release"
    payload = {
        'status': 'ok',
        'tenant_id': tenant_id,
        'release_version': resolved_version,
        'package_filename': package_filename,
        'source_package': source_package,
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'checksum_algorithm': 'sha256',
        'file_count': len(checksums),
        'workflow_count': len(workflow_files),
        'migration_count': len(migration_files),
        'checksums': checksums,
        'includes': {
            'workflow_files': workflow_files,
            'migration_files': migration_files,
            'docs_resume': 'docs/RESUME_FROM_HERE.md',
            'rollback_guide': 'docs/ROLLBACK_GUIDE.md',
            'import_order': 'n8n/manifest/import_order.txt',
        },
        'next_actions': [
            'Run /release/checksum-validate or python scripts/validate_release_checksums.py before packaging or deployment.',
            'Generate a rollback bundle before applying new migrations in a live environment.',
            'Run /release/preflight or python scripts/run_release_preflight.py before publishing the release.',
        ],
    }
    payload['manifest_checksum'] = _stable_json_checksum({k: v for k, v in payload.items() if k != 'manifest_checksum'})
    if persist:
        _safe_db_execute(
            """INSERT INTO release_manifests (tenant_id, release_version, package_filename, source_package, checksum_algorithm, manifest_checksum, manifest_json, created_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s)""",
            (tenant_id, resolved_version, package_filename, source_package, payload['checksum_algorithm'], payload['manifest_checksum'], json.dumps(payload), created_by),
        )
    return payload


def _validate_release_manifest(manifest_json: dict[str, Any], tenant_id: str = 'default', persist: bool = True) -> dict[str, Any]:
    manifest = dict(manifest_json or {})
    checksums = manifest.get('checksums') or {}
    mismatched: list[str] = []
    missing: list[str] = []
    for rel_path, expected in checksums.items():
        path = PROJECT_ROOT / rel_path
        if not path.exists():
            missing.append(rel_path)
            continue
        if _sha256_file(path) != expected:
            mismatched.append(rel_path)
    valid = not mismatched and not missing
    payload = {
        'status': 'ok',
        'tenant_id': tenant_id,
        'release_version': str(manifest.get('release_version') or f"{app.version}-release"),
        'valid': valid,
        'checksum_algorithm': manifest.get('checksum_algorithm') or 'sha256',
        'manifest_checksum': manifest.get('manifest_checksum') or _stable_json_checksum({k: v for k, v in manifest.items() if k != 'manifest_checksum'}),
        'validated_file_count': len(checksums),
        'mismatch_count': len(mismatched),
        'missing_count': len(missing),
        'mismatched_files': mismatched,
        'missing_files': missing,
        'next_actions': ['Checksums validated successfully. Proceed to release preflight or deployment.'] if valid else ['Regenerate the release manifest after fixing missing or modified files before packaging.'],
    }
    if persist:
        _safe_db_execute(
            """INSERT INTO release_preflight_runs (tenant_id, release_version, run_type, status, report_json)
               VALUES (%s,%s,'checksum_validation',%s,%s::jsonb)""",
            (tenant_id, payload['release_version'], 'passed' if valid else 'failed', json.dumps(payload)),
        )
    return payload


def _run_release_import_order_check() -> dict[str, Any]:
    import_order_path = PROJECT_ROOT / 'n8n' / 'manifest' / 'import_order.txt'
    if not import_order_path.exists():
        return {'ok': False, 'entry_count': 0, 'missing_entries': ['n8n/manifest/import_order.txt']}
    lines = [line.strip() for line in import_order_path.read_text().splitlines() if line.strip() and not line.strip().startswith('#')]
    missing: list[str] = []
    for line in lines:
        candidate = PROJECT_ROOT / line
        if not candidate.exists() and '/' not in line and line.endswith('.json'):
            candidate = PROJECT_ROOT / 'n8n' / 'import' / line
        if not candidate.exists():
            missing.append(line)
    return {'ok': not missing, 'entry_count': len(lines), 'missing_entries': missing}


def _build_release_preflight(tenant_id: str = 'default', release_version: str | None = None, persist: bool = True) -> dict[str, Any]:
    manifest = _build_release_manifest(tenant_id=tenant_id, release_version=release_version, persist=False)
    checksum_validation = _validate_release_manifest(manifest, tenant_id=tenant_id, persist=False)
    import_order = _run_release_import_order_check()
    required_paths = [
        'docs/RESUME_FROM_HERE.md',
        'docs/WORKLOG.md',
        'docs/ROLLBACK_GUIDE.md',
        'scripts/validate_package.py',
        'scripts/import_order_check.py',
        'scripts/smoke_test.sh',
        'sql/unified_production_schema_v2.sql',
        'n8n/manifest/import_order.txt',
    ]
    missing_required = [path for path in required_paths if not (PROJECT_ROOT / path).exists()]
    checks = {
        'required_files_present': not missing_required,
        'missing_required_files': missing_required,
        'checksum_validation': checksum_validation,
        'import_order': import_order,
        'workflow_files_present': manifest['workflow_count'] > 0,
        'migration_files_present': manifest['migration_count'] > 0,
    }
    ready = checks['required_files_present'] and checksum_validation['valid'] and import_order['ok'] and checks['workflow_files_present'] and checks['migration_files_present']
    artifacts = [
        'docs/generated_release_manifest.json',
        'docs/generated_release_checksum_validation.json',
        'docs/generated_release_preflight_report.json',
        'artifacts/release_rollback_bundle_default.zip',
    ]
    next_actions: list[str] = []
    if not checks['required_files_present']:
        next_actions.append('Restore the missing required release files before packaging.')
    if not checksum_validation['valid']:
        next_actions.append('Re-run checksum validation after regenerating the manifest or restoring modified files.')
    if not import_order['ok']:
        next_actions.append('Fix the n8n import order file so every referenced workflow exists.')
    if ready:
        next_actions.append('Release preflight passed locally. On a live stack, run persistence smoke and then publish the release.')
    payload = {
        'status': 'ok',
        'tenant_id': tenant_id,
        'release_version': manifest['release_version'],
        'ready': ready,
        'workflow_count': manifest['workflow_count'],
        'migration_count': manifest['migration_count'],
        'generated_artifacts': artifacts,
        'checks': checks,
        'next_actions': next_actions,
    }
    if persist:
        _safe_db_execute(
            """INSERT INTO release_preflight_runs (tenant_id, release_version, run_type, status, report_json)
               VALUES (%s,%s,'release_preflight',%s,%s::jsonb)""",
            (tenant_id, payload['release_version'], 'passed' if ready else 'failed', json.dumps(payload)),
        )
    return payload


def _build_release_rollback_package(tenant_id: str = 'default', release_version: str | None = None, package_filename: str | None = None, source_package: str | None = None, output_path: str | None = None, created_by: str | None = None, persist: bool = True) -> dict[str, Any]:
    manifest = _build_release_manifest(tenant_id=tenant_id, release_version=release_version, package_filename=package_filename, source_package=source_package, created_by=created_by, persist=persist)
    target = Path(output_path) if output_path else (_release_artifact_dir() / f'release_rollback_bundle_{tenant_id}.zip')
    if not target.is_absolute():
        target = PROJECT_ROOT / target
    target.parent.mkdir(parents=True, exist_ok=True)
    include_paths = [
        'docs/ROLLBACK_GUIDE.md',
        'docs/RESUME_FROM_HERE.md',
        'docs/WORKLOG.md',
        'n8n/manifest/import_order.txt',
        'sql/unified_production_schema_v2.sql',
        'deploy/.env.example',
        *manifest['includes']['migration_files'],
        *manifest['includes']['workflow_files'],
    ]
    include_paths = sorted(dict.fromkeys(include_paths))
    with ZipFile(target, 'w', compression=ZIP_DEFLATED) as zf:
        zf.writestr('release_manifest.json', json.dumps(manifest, indent=2, sort_keys=True))
        for rel in include_paths:
            path = PROJECT_ROOT / rel
            if path.exists():
                zf.write(path, arcname=rel)
    checksum = _sha256_file(target)
    payload = {
        'status': 'ok',
        'tenant_id': tenant_id,
        'release_version': manifest['release_version'],
        'output_path': str(target.relative_to(PROJECT_ROOT)) if str(target).startswith(str(PROJECT_ROOT)) else str(target),
        'package_checksum': checksum,
        'included_files_count': len(include_paths) + 1,
        'manifest_path': 'release_manifest.json',
        'includes': include_paths,
        'next_actions': [
            'Store the rollback bundle alongside the release artifact before applying new migrations.',
            'Use docs/ROLLBACK_GUIDE.md from the bundle during rollback drills or emergency recovery.',
        ],
    }
    if persist:
        _safe_db_execute(
            """INSERT INTO rollback_packages (tenant_id, release_version, package_path, package_checksum, manifest_checksum, includes_json, created_by)
               VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s)""",
            (tenant_id, payload['release_version'], payload['output_path'], checksum, manifest['manifest_checksum'], json.dumps(include_paths), created_by),
        )
    return payload



def _release_publication_output_path(tenant_id: str, release_version: str, output_path: str | None = None) -> Path:
    if output_path:
        target = Path(output_path)
    else:
        safe_version = ''.join(ch if ch.isalnum() or ch in {'-', '_', '.'} else '_' for ch in release_version)
        target = _release_artifact_dir() / f'release_publication_{tenant_id}_{safe_version}.zip'
    if not target.is_absolute():
        target = PROJECT_ROOT / target
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _build_release_publication(tenant_id: str = 'default', release_version: str | None = None, package_filename: str | None = None, source_package: str | None = None, output_path: str | None = None, created_by: str | None = None, persist: bool = True, require_preflight: bool = True, require_checksum_validation: bool = True, include_reports: bool = True) -> dict[str, Any]:
    manifest = _build_release_manifest(tenant_id=tenant_id, release_version=release_version, package_filename=package_filename, source_package=source_package, created_by=created_by, persist=False)
    checksum_validation = _validate_release_manifest(manifest, tenant_id=tenant_id, persist=False)
    preflight = _build_release_preflight(tenant_id=tenant_id, release_version=manifest['release_version'], persist=False)
    published = ((not require_preflight or preflight['ready']) and (not require_checksum_validation or checksum_validation['valid']))
    publication_status = 'published' if published else 'blocked'
    target = _release_publication_output_path(tenant_id, manifest['release_version'], output_path)
    files = _release_candidate_files()
    include_paths = [path.relative_to(PROJECT_ROOT).as_posix() for path in files]
    report_artifacts = [
        'docs/generated_release_manifest.json',
        'docs/generated_release_checksum_validation.json',
        'docs/generated_release_preflight_report.json',
        'docs/generated_release_rollback_package.json',
        'docs/RESUME_FROM_HERE.md',
        'docs/WORKLOG.md',
        'docs/ROLLBACK_GUIDE.md',
    ] if include_reports else []
    include_paths.extend([rel for rel in report_artifacts if (PROJECT_ROOT / rel).exists()])
    include_paths = sorted(dict.fromkeys(include_paths))
    publication_summary = {
        'tenant_id': tenant_id,
        'release_version': manifest['release_version'],
        'publication_status': publication_status,
        'published': published,
        'manifest_checksum': manifest['manifest_checksum'],
        'checksum_valid': checksum_validation['valid'],
        'preflight_ready': preflight['ready'],
        'included_files_count': len(include_paths) + 3,
    }
    with ZipFile(target, 'w', compression=ZIP_DEFLATED) as zf:
        zf.writestr('release_manifest.json', json.dumps(manifest, indent=2, sort_keys=True))
        zf.writestr('release_checksum_validation.json', json.dumps(checksum_validation, indent=2, sort_keys=True))
        zf.writestr('release_preflight_report.json', json.dumps(preflight, indent=2, sort_keys=True))
        zf.writestr('release_publication_summary.json', json.dumps(publication_summary, indent=2, sort_keys=True))
        for rel in include_paths:
            path = PROJECT_ROOT / rel
            if path.exists() and path.is_file():
                zf.write(path, arcname=rel)
    package_checksum = _sha256_file(target)
    output_value = str(target.relative_to(PROJECT_ROOT)) if str(target).startswith(str(PROJECT_ROOT)) else str(target)
    next_actions: list[str] = []
    if published:
        next_actions = [
            'Release publication bundle is ready. Store the package checksum and publish the ZIP through your release channel.',
            'Keep the rollback bundle and release manifest adjacent to the publication artifact for rollback drills.',
        ]
    else:
        if require_preflight and not preflight['ready']:
            next_actions.append('Release preflight is not ready yet. Resolve the failed checks before publishing this bundle.')
        if require_checksum_validation and not checksum_validation['valid']:
            next_actions.append('Checksum validation failed. Regenerate the manifest or restore modified files before publishing.')
        next_actions.append('The publication bundle was staged for inspection but should not be promoted until the blocking checks pass.')
    payload = {
        'status': 'ok',
        'tenant_id': tenant_id,
        'release_version': manifest['release_version'],
        'published': published,
        'publication_status': publication_status,
        'output_path': output_value,
        'package_checksum': package_checksum,
        'included_files_count': len(include_paths) + 4,
        'manifest_checksum': manifest['manifest_checksum'],
        'preflight_ready': preflight['ready'],
        'checksum_valid': checksum_validation['valid'],
        'generated_artifacts': [
            'release_manifest.json',
            'release_checksum_validation.json',
            'release_preflight_report.json',
            'release_publication_summary.json',
        ],
        'next_actions': next_actions,
    }
    if persist:
        _safe_db_execute(
            """INSERT INTO release_publications (tenant_id, release_version, publication_status, package_path, package_checksum, manifest_checksum, publication_json, created_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s)""",
            (tenant_id, payload['release_version'], publication_status, output_value, package_checksum, manifest['manifest_checksum'], json.dumps({**payload, 'preflight': preflight, 'checksum_validation': checksum_validation}), created_by),
        )
        _safe_db_execute(
            """INSERT INTO release_publication_events (tenant_id, release_version, action, status, package_path, metadata_json, created_by)
               VALUES (%s,%s,'publish_bundle',%s,%s,%s::jsonb,%s)""",
            (tenant_id, payload['release_version'], publication_status, output_value, json.dumps({'published': published, 'preflight_ready': preflight['ready'], 'checksum_valid': checksum_validation['valid']}), created_by),
        )
    return payload


def _list_release_publications(tenant_id: str = 'default', limit: int = 20) -> list[dict[str, Any]]:
    try:
        rows = fetch_all(
            """SELECT tenant_id, release_version, publication_status, package_path, package_checksum, manifest_checksum, created_by, created_at, publication_json
               FROM release_publications WHERE tenant_id=%s ORDER BY created_at DESC LIMIT %s""",
            (tenant_id, limit),
        ) or []
        return [dict(row) for row in rows]
    except Exception:
        return []

@app.post('/connectors/failure-isolation-report', response_model=ConnectorFailureIsolationReportResponse)
def connectors_failure_isolation_report(req: ConnectorFailureIsolationReportRequest):
    payload = _build_failure_isolation_report(req.tenant_id, req.service_names, req.persist)
    _log_connector_execution(req.tenant_id, 'connector_registry', 'failure_isolation_report', 'failure_isolation_report', {'tenant_id': req.tenant_id, 'service_names': req.service_names, 'persist': req.persist}, {'count': payload['count'], 'open_circuit_count': payload['open_circuit_count'], 'rate_limited_services_count': payload['rate_limited_services_count']}, status='ok')
    return ConnectorFailureIsolationReportResponse(**payload)


@app.post('/workflows/execution/policy', response_model=WorkflowExecutionCheckResponse)
def workflow_execution_policy_upsert(req: WorkflowExecutionPolicyRequest):
    _safe_db_execute(
        """INSERT INTO workflow_runtime_policies (tenant_id, workflow_id, enabled, max_executions_per_window, window_seconds)
           VALUES (%s,%s,%s,%s,%s)
           ON CONFLICT (tenant_id, workflow_id)
           DO UPDATE SET enabled=EXCLUDED.enabled,
                         max_executions_per_window=EXCLUDED.max_executions_per_window,
                         window_seconds=EXCLUDED.window_seconds,
                         updated_at=now()""",
        (req.tenant_id, req.workflow_id, req.enabled, req.max_executions_per_window, req.window_seconds),
    )
    payload = _check_workflow_execution_cap(req.tenant_id, req.workflow_id, persist=False)
    return WorkflowExecutionCheckResponse(**payload)


@app.post('/workflows/execution/check', response_model=WorkflowExecutionCheckResponse)
def workflow_execution_check(req: WorkflowExecutionCheckRequest):
    payload = _check_workflow_execution_cap(req.tenant_id, req.workflow_id, actor_id=req.actor_id, persist=req.persist, metadata_json=req.metadata_json)
    if not payload['allowed']:
        raise HTTPException(status_code=429, detail={'code': 'WORKFLOW_CAP_EXCEEDED', 'message': f"workflow {req.workflow_id} exceeded its execution window", 'retry_after_seconds': payload['retry_after_seconds'], 'workflow_id': req.workflow_id, 'policy': payload['policy']})
    return WorkflowExecutionCheckResponse(**payload)


@app.post('/workflows/version/create', response_model=WorkflowVersionResponse)
def workflow_version_create(req: WorkflowVersionCreateRequest):
    workflow_status = _validate_workflow_version_status(req.status)
    if workflow_status == 'published':
        raise HTTPException(status_code=400, detail={'code': 'PUBLISH_REQUIRES_PROMOTION', 'message': 'use /workflows/version/promote to publish'})
    existing = _fetch_workflow_version(req.tenant_id, req.workflow_id, req.version)
    if existing and existing.get('workflow_status') == 'published':
        if (existing.get('definition_json') or {}) != (req.definition_json or {}):
            raise HTTPException(status_code=409, detail={'code': 'IMMUTABLE_PUBLISHED_VERSION', 'message': f'{req.workflow_id} v{req.version} is published and immutable'})
        return WorkflowVersionResponse(**_workflow_version_response_payload(req.tenant_id, req.workflow_id, req.version, 'published', existing.get('definition_json') or {}))
    _safe_db_execute("""INSERT INTO workflow_versions (tenant_id, workflow_id, version, status, definition_json) VALUES (%s,%s,%s,%s,%s::jsonb)
        ON CONFLICT (tenant_id, workflow_id, version) DO UPDATE SET status=EXCLUDED.status, definition_json=EXCLUDED.definition_json, updated_at=now()""", (req.tenant_id, req.workflow_id, req.version, workflow_status, json.dumps(req.definition_json)))
    _record_workflow_version_event(req.tenant_id, req.workflow_id, req.version, 'create_or_update', metadata_json={'status': workflow_status})
    return WorkflowVersionResponse(**_workflow_version_response_payload(req.tenant_id, req.workflow_id, req.version, workflow_status, req.definition_json))


@app.get('/workflows/version/history/{workflow_id}', response_model=WorkflowVersionHistoryResponse)
def workflow_version_history(request: Request, workflow_id: str, tenant_id: str = 'default', include_definition: bool = True):
    tenant_id = _scoped_tenant_id(request, tenant_id)
    rows = _fetch_workflow_versions(tenant_id, workflow_id)
    items = []
    published_version = None
    for row in rows:
        definition_json = row.get('definition_json') or {}
        if not include_definition:
            definition_json = {}
        item = WorkflowVersionHistoryItem(
            workflow_id=row.get('workflow_id') or workflow_id,
            version=int(row.get('version') or 0),
            workflow_status=row.get('workflow_status') or 'draft',
            definition_json=definition_json,
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at'),
        )
        items.append(item)
        if item.workflow_status == 'published' and published_version is None:
            published_version = item.version
    return WorkflowVersionHistoryResponse(status='ok', tenant_id=tenant_id, workflow_id=workflow_id, count=len(items), published_version=published_version, versions=items)


@app.post('/workflows/version/promote', response_model=WorkflowVersionResponse)
def workflow_version_promote(req: WorkflowVersionPromoteRequest):
    target_status = _validate_workflow_version_status(req.status)
    current = _fetch_workflow_version(req.tenant_id, req.workflow_id, req.version)
    if not current:
        raise HTTPException(status_code=404, detail={'code': 'WORKFLOW_VERSION_NOT_FOUND', 'message': f'{req.workflow_id} v{req.version} not found'})
    current_status = current.get('workflow_status') or 'draft'
    if current_status == 'published' and target_status == 'published':
        return WorkflowVersionResponse(**_workflow_version_response_payload(req.tenant_id, req.workflow_id, req.version, 'published', current.get('definition_json') or {}))
    if target_status == 'published' and current_status not in {'tested', 'approved', 'published'}:
        raise HTTPException(status_code=409, detail={'code': 'INVALID_PROMOTION_TRANSITION', 'message': f'cannot publish from {current_status}'})
    if target_status == 'approved' and current_status not in {'draft', 'tested', 'approved'}:
        raise HTTPException(status_code=409, detail={'code': 'INVALID_PROMOTION_TRANSITION', 'message': f'cannot approve from {current_status}'})
    if target_status == 'published':
        _safe_db_execute("UPDATE workflow_versions SET status='approved', updated_at=now() WHERE tenant_id=%s AND workflow_id=%s AND status='published'", (req.tenant_id, req.workflow_id))
        _record_workflow_version_event(req.tenant_id, req.workflow_id, req.version, 'demote_existing_published', target_version=req.version)
    _safe_db_execute("UPDATE workflow_versions SET status=%s, updated_at=now() WHERE tenant_id=%s AND workflow_id=%s AND version=%s", (target_status, req.tenant_id, req.workflow_id, req.version))
    _record_workflow_version_event(req.tenant_id, req.workflow_id, req.version, 'promote', target_version=req.version, metadata_json={'from_status': current_status, 'to_status': target_status})
    row = _fetch_workflow_version(req.tenant_id, req.workflow_id, req.version) or {'definition_json': current.get('definition_json') or {}}
    return WorkflowVersionResponse(**_workflow_version_response_payload(req.tenant_id, req.workflow_id, req.version, target_status, row.get('definition_json') or {}))


@app.post('/workflows/version/rollback', response_model=WorkflowVersionResponse)
def workflow_version_rollback(req: WorkflowVersionRollbackRequest):
    rollback_status = _validate_workflow_version_status(req.status)
    if rollback_status == 'published':
        raise HTTPException(status_code=400, detail={'code': 'ROLLBACK_TARGET_STATUS_INVALID', 'message': 'rollback must create a non-published version'})
    source = _fetch_workflow_version(req.tenant_id, req.workflow_id, req.source_version)
    if not source:
        raise HTTPException(status_code=404, detail={'code': 'WORKFLOW_VERSION_NOT_FOUND', 'message': f'{req.workflow_id} v{req.source_version} not found'})
    new_version = req.new_version or (_fetch_latest_workflow_version(req.tenant_id, req.workflow_id) + 1)
    if new_version == req.source_version:
        raise HTTPException(status_code=409, detail={'code': 'ROLLBACK_VERSION_CONFLICT', 'message': 'new_version must differ from source_version'})
    existing = _fetch_workflow_version(req.tenant_id, req.workflow_id, new_version)
    if existing:
        raise HTTPException(status_code=409, detail={'code': 'WORKFLOW_VERSION_EXISTS', 'message': f'{req.workflow_id} v{new_version} already exists'})
    definition_json = source.get('definition_json') or {}
    _safe_db_execute("INSERT INTO workflow_versions (tenant_id, workflow_id, version, status, definition_json) VALUES (%s,%s,%s,%s,%s::jsonb)", (req.tenant_id, req.workflow_id, new_version, rollback_status, json.dumps(definition_json)))
    _record_workflow_version_event(req.tenant_id, req.workflow_id, new_version, 'rollback', actor_id=req.actor_id, source_version=req.source_version, target_version=new_version, metadata_json={'note': req.note, 'status': rollback_status})
    return WorkflowVersionResponse(**_workflow_version_response_payload(req.tenant_id, req.workflow_id, new_version, rollback_status, definition_json))



@app.post('/release/manifest', response_model=ReleaseManifestResponse)
def release_manifest_build(req: ReleaseManifestRequest):
    payload = _build_release_manifest(req.tenant_id, req.release_version, req.package_filename, req.source_package, req.created_by, req.persist)
    return ReleaseManifestResponse(**payload)


@app.post('/release/checksum-validate', response_model=ReleaseChecksumValidationResponse)
def release_checksum_validate(req: ReleaseChecksumValidateRequest):
    manifest = req.manifest_json or _build_release_manifest(req.tenant_id, req.release_version, persist=False)
    payload = _validate_release_manifest(manifest, tenant_id=req.tenant_id, persist=req.persist)
    return ReleaseChecksumValidationResponse(**payload)


@app.post('/release/rollback-package', response_model=ReleaseRollbackPackageResponse)
def release_rollback_package(req: ReleaseRollbackPackageRequest):
    payload = _build_release_rollback_package(req.tenant_id, req.release_version, req.package_filename, req.source_package, req.output_path, req.created_by, req.persist)
    return ReleaseRollbackPackageResponse(**payload)


@app.post('/release/preflight', response_model=ReleasePreflightResponse)
def release_preflight(req: ReleasePreflightRequest):
    payload = _build_release_preflight(req.tenant_id, req.release_version, req.persist)
    return ReleasePreflightResponse(**payload)


@app.post('/release/publish', response_model=ReleasePublishResponse)
def release_publish(req: ReleasePublishRequest):
    payload = _build_release_publication(req.tenant_id, req.release_version, req.package_filename, req.source_package, req.output_path, req.created_by, req.persist, req.require_preflight, req.require_checksum_validation, req.include_reports)
    return ReleasePublishResponse(**payload)


@app.get('/release/publications', response_model=ReleasePublicationListResponse)
def release_publications(request: Request, tenant_id: str = 'default', limit: int = 20):
    scoped_tenant_id = _scoped_tenant_id(request, tenant_id)
    rows = _list_release_publications(tenant_id=scoped_tenant_id, limit=limit)
    rows = _apply_tenant_row_scope(request, rows, 'release_publications', requested_tenant_id=tenant_id, action='read')
    items = [ReleasePublicationItem(**item) for item in rows]
    return ReleasePublicationListResponse(status='ok', tenant_id=scoped_tenant_id, count=len(items), items=items)


@app.get('/admin/releases', response_model=AdminSummaryResponse)
def admin_releases(request: Request, tenant_id: str = 'default'):
    tenant_id = _scoped_tenant_id(request, tenant_id)
    summary: dict[str, Any] = {}
    for key, sql in {
        'manifest_count': "SELECT count(*)::int AS c FROM release_manifests WHERE tenant_id=%s",
        'rollback_package_count': "SELECT count(*)::int AS c FROM rollback_packages WHERE tenant_id=%s",
        'publication_count': "SELECT count(*)::int AS c FROM release_publications WHERE tenant_id=%s",
        'published_count': "SELECT count(*)::int AS c FROM release_publications WHERE tenant_id=%s AND publication_status='published'",
        'blocked_count': "SELECT count(*)::int AS c FROM release_publications WHERE tenant_id=%s AND publication_status='blocked'",
    }.items():
        try:
            summary[key] = (fetch_one(sql, (tenant_id,)) or {'c': 0})['c']
        except Exception:
            summary[key] = 0
    try:
        rows = fetch_all("SELECT release_version, publication_status, package_path, created_at, tenant_id FROM release_publications WHERE tenant_id=%s ORDER BY created_at DESC LIMIT 10", (tenant_id,)) or []
        summary['recent_publications'] = _apply_tenant_row_scope(request, [dict(row) for row in rows], 'release_publications', requested_tenant_id=tenant_id, action='read')
    except Exception:
        summary['recent_publications'] = []
    return AdminSummaryResponse(status='ok', tenant_id=tenant_id, summary=summary)



@app.post('/release/channel', response_model=ReleaseChannelResponse)
def release_channel_upsert(req: ReleaseChannelUpsertRequest):
    channel = _upsert_release_channel(req.tenant_id, req.channel_name, req.channel_type, req.enabled, req.destination_path, req.endpoint_url, req.auth_secret_ref, req.created_by, req.metadata_json)
    return ReleaseChannelResponse(status='ok', channel=ReleaseChannelItem(**channel))


@app.get('/release/channels', response_model=ReleaseChannelListResponse)
def release_channels(request: Request, tenant_id: str = 'default', enabled_only: bool = False):
    scoped_tenant_id = _scoped_tenant_id(request, tenant_id)
    rows = _list_release_channels(tenant_id=scoped_tenant_id, enabled_only=enabled_only)
    rows = _apply_tenant_row_scope(request, rows, 'release_channels', requested_tenant_id=tenant_id, action='read')
    items = [ReleaseChannelItem(**item) for item in rows]
    return ReleaseChannelListResponse(status='ok', tenant_id=scoped_tenant_id, count=len(items), items=items)


@app.post('/release/channel-plan', response_model=ReleaseChannelPlanResponse)
def release_channel_plan(req: ReleaseChannelPlanRequest):
    payload = _build_release_channel_plan(req.tenant_id, req.release_version, req.package_filename, req.source_package, req.include_publication_bundle, req.output_path, req.created_by, req.persist)
    return ReleaseChannelPlanResponse(**payload)



@app.get('/admin/release-channels', response_model=AdminSummaryResponse)
def admin_release_channels(request: Request, tenant_id: str = 'default'):
    tenant_id = _scoped_tenant_id(request, tenant_id)
    channels = _apply_tenant_row_scope(request, _list_release_channels(tenant_id=tenant_id, enabled_only=False), 'release_channels', requested_tenant_id=tenant_id, action='read')
    plan = _build_release_channel_plan(tenant_id=tenant_id, persist=False)
    summary = {
        'channel_count': len(channels),
        'enabled_count': sum(1 for item in channels if item.get('enabled')),
        'ready_count': plan.get('ready_count', 0),
        'publication_ready': plan.get('publication_ready', False),
        'recent_events': _apply_tenant_row_scope(request, _list_release_channel_events(tenant_id=tenant_id, limit=10), 'release_channel_events', requested_tenant_id=tenant_id, action='read'),
    }
    return AdminSummaryResponse(status='ok', tenant_id=tenant_id, summary=summary)


@app.post('/release/channel-execute', response_model=ReleaseChannelExecuteResponse)
def release_channel_execute(req: ReleaseChannelExecuteRequest):
    payload = _build_release_channel_execution(req.tenant_id, req.release_version, req.package_filename, req.source_package, req.channel_names, req.include_publication_bundle, req.output_path, req.created_by, req.persist, req.dry_run, req.execute_webhooks)
    return ReleaseChannelExecuteResponse(**payload)


@app.get('/release/channel-executions', response_model=ReleaseChannelExecutionListResponse)
def release_channel_executions(request: Request, tenant_id: str = 'default', limit: int = 20):
    scoped_tenant_id = _scoped_tenant_id(request, tenant_id)
    rows = _list_release_channel_executions(tenant_id=scoped_tenant_id, limit=limit)
    rows = _apply_tenant_row_scope(request, rows, 'release_channel_executions', requested_tenant_id=tenant_id, action='read')
    items = [ReleaseChannelExecutionRecord(**item) for item in rows]
    return ReleaseChannelExecutionListResponse(status='ok', tenant_id=scoped_tenant_id, count=len(items), items=items)


@app.get('/admin/release-channel-executions', response_model=AdminSummaryResponse)
def admin_release_channel_executions(request: Request, tenant_id: str = 'default'):
    tenant_id = _scoped_tenant_id(request, tenant_id)
    items = _apply_tenant_row_scope(request, _list_release_channel_executions(tenant_id=tenant_id, limit=20), 'release_channel_executions', requested_tenant_id=tenant_id, action='read')
    summary = {
        'execution_count': len(items),
        'delivered_count': sum(1 for item in items if item.get('execution_status') == 'delivered'),
        'prepared_count': sum(1 for item in items if item.get('execution_status') in {'prepared', 'dry_run'}),
        'blocked_count': sum(1 for item in items if item.get('execution_status') in {'blocked', 'failed'}),
        'recent_executions': items[:10],
    }
    return AdminSummaryResponse(status='ok', tenant_id=tenant_id, summary=summary)


@app.get('/ai/models', response_model=RegistryListResponse)
def ai_models(request: Request, tenant_id: str = 'default'):
    tenant_id = _scoped_tenant_id(request, tenant_id)
    items = []
    try:
        rows = fetch_all("SELECT tenant_id, name, type, capabilities, latency_profile FROM model_registry WHERE tenant_id=%s ORDER BY name", (tenant_id,))
        items = [dict(row) for row in rows]
    except Exception:
        items = [{'tenant_id': tenant_id, 'name': settings.ollama_model, 'type': 'local', 'capabilities': ['chat'], 'latency_profile': 'medium'}, {'tenant_id': tenant_id, 'name': settings.ollama_embedding_model, 'type': 'local', 'capabilities': ['embeddings'], 'latency_profile': 'fast'}]
    items = _apply_tenant_row_scope(request, items, 'model_registry', requested_tenant_id=tenant_id, action='read')
    return RegistryListResponse(status='ok', count=len(items), items=items)


@app.get('/ai/prompts', response_model=RegistryListResponse)
def ai_prompts(request: Request, tenant_id: str = 'default'):
    tenant_id = _scoped_tenant_id(request, tenant_id)
    items = []
    try:
        rows = fetch_all("SELECT tenant_id, name, version, template, model_compatibility FROM prompt_registry WHERE tenant_id=%s ORDER BY name, version", (tenant_id,))
        items = [dict(row) for row in rows]
    except Exception:
        items = [{'tenant_id': tenant_id, 'name': 'fallback_chat', 'version': 'phase3.v1', 'template': settings.fallback_chat_system_prompt, 'model_compatibility': [settings.ollama_model]}]
    items = _apply_tenant_row_scope(request, items, 'prompt_registry', requested_tenant_id=tenant_id, action='read')
    return RegistryListResponse(status='ok', count=len(items), items=items)


@app.post('/lifecycle/policy', response_model=LifecyclePolicyResponse)
def lifecycle_policy_upsert(req: LifecyclePolicyUpsertRequest):
    try:
        row = upsert_retention_policy(req.tenant_id, req.resource_type, req.enabled, req.retain_days, req.archive_before_delete, req.batch_size, updated_by=req.updated_by, metadata_json=req.metadata_json)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={'code': 'UNSUPPORTED_RESOURCE_TYPE', 'message': str(exc)}) from exc
    payload = dict(row)
    payload['metadata_json'] = payload.get('metadata_json') or {}
    return LifecyclePolicyResponse(status='ok', policy=LifecyclePolicyItem(**payload))


@app.post('/lifecycle/report', response_model=DataLifecycleReportResponse)
def lifecycle_report(req: DataLifecycleReportRequest):
    payload = build_data_lifecycle_report(req.tenant_id, req.resource_types, req.persist)
    return DataLifecycleReportResponse(**payload)


@app.post('/lifecycle/run-cleanup', response_model=DataLifecycleCleanupResponse)
def lifecycle_run_cleanup(req: DataLifecycleCleanupRequest):
    payload = run_data_lifecycle_cleanup(req.tenant_id, req.resource_types, req.dry_run, actor_id=req.actor_id, persist=req.persist)
    return DataLifecycleCleanupResponse(**payload)


@app.get('/admin/lifecycle', response_model=AdminSummaryResponse)
def admin_lifecycle(request: Request, tenant_id: str = 'default'):
    tenant_id = _scoped_tenant_id(request, tenant_id)
    report = build_data_lifecycle_report(tenant_id=tenant_id, persist=False)
    summary = {
        'tenant_id': tenant_id,
        'policy_count': report.get('count', 0),
        'eligible_total': report.get('eligible_total', 0),
        'policies': report.get('policies', []),
    }
    return AdminSummaryResponse(status='ok', tenant_id=tenant_id, summary=summary)


@app.post('/tenants/create', response_model=TenantCreateResponse)
def tenant_create(req: TenantCreateRequest, request: Request):
    identity = getattr(request.state, 'identity', None)
    if identity is not None and identity.role not in {'admin', 'service_account'}:
        raise HTTPException(status_code=403, detail={'code': 'TENANT_WRITE_FORBIDDEN'})
    payload = ensure_tenant_exists(req.tenant_id, req.tenant_name, req.created_by or getattr(request.state, 'actor_id', None))
    return TenantCreateResponse(status='ok', **payload)


@app.post('/tenants/membership', response_model=TenantMembershipUpsertResponse)
def tenant_membership_upsert(req: TenantMembershipUpsertRequest, request: Request):
    identity = getattr(request.state, 'identity', None)
    if identity is not None and identity.role not in {'admin', 'service_account'}:
        raise HTTPException(status_code=403, detail={'code': 'TENANT_WRITE_FORBIDDEN'})
    payload = upsert_tenant_membership(
        actor_id=req.actor_id,
        tenant_id=req.tenant_id,
        role_name=req.role_name,
        created_by=req.created_by or getattr(request.state, 'actor_id', None),
        username=req.username,
        display_name=req.display_name,
        is_default=req.is_default,
        is_active=req.is_active,
        metadata_json=req.metadata_json,
    )
    return TenantMembershipUpsertResponse(status='ok', membership=TenantMembershipItem(**payload))


@app.get('/tenants/context', response_model=TenantContextResponse)
def tenant_context(request: Request, tenant_id: str | None = None):
    identity = getattr(request.state, 'identity', None)
    actor_id = getattr(request.state, 'actor_id', 'anonymous')
    payload = build_tenant_context_report(
        requested_tenant_id=tenant_id or getattr(request.state, 'tenant_id', settings.tenant_default_id),
        actor_id=actor_id,
        role=getattr(identity, 'role', 'viewer') if identity is not None else 'viewer',
        identity_tenant_id=getattr(identity, 'tenant_id', None) if identity is not None else getattr(request.state, 'tenant_id', settings.tenant_default_id),
    )
    return TenantContextResponse(**payload)


@app.get('/admin/tenants', response_model=AdminSummaryResponse)
def admin_tenants(request: Request, tenant_id: str = 'default'):
    tenant_id = _scoped_tenant_id(request, tenant_id)
    summary = list_tenants_summary(tenant_id=tenant_id)
    summary['tenant_id'] = tenant_id
    return AdminSummaryResponse(status='ok', tenant_id=tenant_id, summary=summary)


@app.post('/tenants/policy', response_model=TenantPolicyUpsertResponse)
def tenant_policy_upsert(req: TenantPolicyUpsertRequest, request: Request):
    identity = getattr(request.state, 'identity', None)
    if identity is not None and identity.role not in {'admin', 'service_account'}:
        raise HTTPException(status_code=403, detail={'code': 'TENANT_WRITE_FORBIDDEN'})
    try:
        payload = upsert_tenant_route_policy(
            tenant_id=req.tenant_id,
            route_prefix=req.route_prefix,
            resource_type=req.resource_type,
            strict_mode=req.strict_mode,
            require_membership=req.require_membership,
            allow_admin_override=req.allow_admin_override,
            allow_service_account_override=req.allow_service_account_override,
            updated_by=req.updated_by or getattr(request.state, 'actor_id', None),
            metadata_json=req.metadata_json,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={'code': 'INVALID_TENANT_POLICY', 'message': str(exc)}) from exc
    return TenantPolicyUpsertResponse(status='ok', policy=TenantPolicyItem(**payload))


@app.post('/tenants/enforcement-report', response_model=TenantEnforcementReportResponse)
def tenant_enforcement_report(req: TenantEnforcementReportRequest):
    payload = build_tenant_enforcement_report(
        tenant_id=req.tenant_id,
        route=req.route,
        method=req.method,
        actor_id=req.actor_id,
        role=req.role,
        identity_tenant_id=req.identity_tenant_id,
        requested_tenant_id=req.requested_tenant_id,
    )
    payload['policy'] = TenantPolicyItem(**payload.get('policy', {}))
    payload['policies'] = [TenantPolicyItem(**item) for item in payload.get('policies', [])]
    return TenantEnforcementReportResponse(**payload)


@app.post('/tenants/row-policy', response_model=TenantRowPolicyUpsertResponse)
def tenant_row_policy_upsert(req: TenantRowPolicyUpsertRequest, request: Request):
    identity = getattr(request.state, 'identity', None)
    if identity is not None and identity.role not in {'admin', 'service_account'}:
        raise HTTPException(status_code=403, detail={'code': 'TENANT_WRITE_FORBIDDEN'})
    try:
        payload = upsert_tenant_row_policy(
            tenant_id=req.tenant_id,
            resource_table=req.resource_table,
            strict_mode=req.strict_mode,
            require_tenant_match=req.require_tenant_match,
            allow_admin_override=req.allow_admin_override,
            allow_service_account_override=req.allow_service_account_override,
            allow_global_rows=req.allow_global_rows,
            updated_by=req.updated_by or getattr(request.state, 'actor_id', None),
            metadata_json=req.metadata_json,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={'code': 'TENANT_ROW_POLICY_INVALID', 'message': str(exc)})
    return TenantRowPolicyUpsertResponse(status='ok', policy=TenantRowPolicyItem(**payload))


@app.post('/tenants/row-isolation-report', response_model=TenantRowIsolationReportResponse)
def tenant_row_isolation_report(req: TenantRowIsolationReportRequest):
    payload = build_tenant_row_isolation_report(
        tenant_id=req.tenant_id,
        resource_table=req.resource_table,
        action=req.action,
        actor_id=req.actor_id,
        role=req.role,
        identity_tenant_id=req.identity_tenant_id,
        requested_tenant_id=req.requested_tenant_id,
    )
    payload['policy'] = TenantRowPolicyItem(**payload.get('policy', {}))
    payload['policies'] = [TenantRowPolicyItem(**item) for item in payload.get('policies', [])]
    return TenantRowIsolationReportResponse(**payload)


@app.get('/admin/tenant-isolation', response_model=AdminSummaryResponse)
def admin_tenant_isolation(request: Request, tenant_id: str = 'default'):
    tenant_id = _scoped_tenant_id(request, tenant_id)
    policies = [TenantRowPolicyItem(**item).model_dump() for item in list_tenant_row_policies(tenant_id=tenant_id)]
    summary = {
        'tenant_id': tenant_id,
        'policy_count': len(policies),
        'policies': policies,
        'strict_tenant_row_isolation': bool(settings.strict_tenant_row_isolation),
        'tenant_row_policy_default_strict_mode': settings.tenant_row_policy_default_strict_mode,
        'tenant_row_policy_default_require_tenant_match': bool(settings.tenant_row_policy_default_require_tenant_match),
    }
    return AdminSummaryResponse(status='ok', tenant_id=tenant_id, summary=summary)


@app.post('/tenants/query-scope-report', response_model=TenantQueryScopeReportResponse)
def tenant_query_scope_report(req: TenantQueryScopeReportRequest):
    payload = build_tenant_query_scope_report(
        tenant_id=req.tenant_id,
        resource_table=req.resource_table,
        route=req.route,
        action=req.action,
        actor_id=req.actor_id,
        role=req.role,
        identity_tenant_id=req.identity_tenant_id,
        requested_tenant_id=req.requested_tenant_id,
    )
    payload['policy'] = TenantRowPolicyItem(**payload.get('policy', {}))
    payload['policies'] = [TenantRowPolicyItem(**item) for item in payload.get('policies', [])]
    return TenantQueryScopeReportResponse(**payload)


@app.get('/admin/tenant-query-scope', response_model=AdminSummaryResponse)
def admin_tenant_query_scope(request: Request, tenant_id: str = 'default', resource_table: str = 'release_publications', route: str = '/release/publications'):
    tenant_id = _scoped_tenant_id(request, tenant_id)
    payload = build_tenant_query_scope_report(
        tenant_id=tenant_id,
        resource_table=resource_table,
        route=route,
        actor_id=getattr(request.state, 'actor_id', 'anonymous'),
        role=getattr(getattr(request.state, 'identity', None), 'role', 'viewer'),
        identity_tenant_id=getattr(getattr(request.state, 'identity', None), 'tenant_id', tenant_id),
        requested_tenant_id=tenant_id,
    )
    summary = {
        'tenant_id': tenant_id,
        'resource_table': resource_table,
        'route': route,
        'decision': payload.get('decision'),
        'reason': payload.get('reason'),
        'strict_tenant_row_isolation': bool(settings.strict_tenant_row_isolation),
        'visible_tenant_ids': payload.get('visible_tenant_ids', []),
        'query_scope_sql': payload.get('query_scope_sql', ''),
        'policies': [TenantRowPolicyItem(**item).model_dump() for item in payload.get('policies', [])],
    }
    return AdminSummaryResponse(status='ok', tenant_id=tenant_id, summary=summary)




@app.post('/tenants/query-coverage-target', response_model=TenantQueryCoverageTargetResponse)
def tenant_query_coverage_target_upsert(req: TenantQueryCoverageTargetRequest, request: Request):
    identity = getattr(request.state, 'identity', None)
    if identity is not None and identity.role not in {'admin', 'service_account'}:
        raise HTTPException(status_code=403, detail={'code': 'TENANT_WRITE_FORBIDDEN'})
    payload = upsert_tenant_query_scope_target(
        tenant_id=req.tenant_id,
        route=req.route,
        resource_table=req.resource_table,
        action=req.action,
        strict_mode=req.strict_mode,
        notes=req.notes,
        updated_by=req.updated_by or getattr(request.state, 'actor_id', None),
    )
    return TenantQueryCoverageTargetResponse(status='ok', target=TenantQueryCoverageTargetItem(**payload))


@app.post('/tenants/query-coverage-report', response_model=TenantQueryCoverageReportResponse)
def tenant_query_coverage_report(req: TenantQueryCoverageReportRequest):
    payload = build_tenant_query_coverage_report(
        tenant_id=req.tenant_id,
        actor_id=req.actor_id,
        role=req.role,
        identity_tenant_id=req.identity_tenant_id,
        requested_tenant_id=req.requested_tenant_id,
    )
    return TenantQueryCoverageReportResponse(**payload)


@app.get('/admin/tenant-query-coverage', response_model=AdminSummaryResponse)
def admin_tenant_query_coverage(request: Request, tenant_id: str = 'default'):
    scoped_tenant_id = _scoped_tenant_id(request, tenant_id)
    payload = build_tenant_query_coverage_report(
        tenant_id=scoped_tenant_id,
        actor_id=getattr(request.state, 'actor_id', 'anonymous'),
        role=getattr(getattr(request.state, 'identity', None), 'role', 'viewer'),
        identity_tenant_id=getattr(getattr(request.state, 'identity', None), 'tenant_id', scoped_tenant_id),
        requested_tenant_id=tenant_id,
    )
    summary = {
        'target_count': payload.get('target_count', 0),
        'covered_count': payload.get('covered_count', 0),
        'strict_target_count': payload.get('strict_target_count', 0),
        'targets': payload.get('targets', []),
        'known_target_rows': list_tenant_query_scope_targets(scoped_tenant_id),
        'strict_tenant_row_isolation': bool(settings.strict_tenant_row_isolation),
        'next_actions': payload.get('next_actions', []),
    }
    return AdminSummaryResponse(status='ok', tenant_id=scoped_tenant_id, summary=summary)


@app.get('/admin/tenant-enforcement', response_model=AdminSummaryResponse)
def admin_tenant_enforcement(request: Request, tenant_id: str = 'default'):
    tenant_id = _scoped_tenant_id(request, tenant_id)
    policies = [TenantPolicyItem(**item).model_dump() for item in list_tenant_route_policies(tenant_id=tenant_id)]
    summary = {
        'tenant_id': tenant_id,
        'policy_count': len(policies),
        'policies': policies,
        'strict_tenant_enforcement': bool(settings.strict_tenant_enforcement),
        'tenant_allow_admin_override': bool(settings.tenant_allow_admin_override),
        'tenant_policy_default_strict_mode': settings.tenant_policy_default_strict_mode,
    }
    return AdminSummaryResponse(status='ok', tenant_id=tenant_id, summary=summary)
