from __future__ import annotations

import json
import time
from typing import Any

from .config import settings
from .db import execute, fetch_all, fetch_one

DEFAULT_RETENTION_POLICIES: dict[str, dict[str, Any]] = {
    'audit_logs': {'retain_days': settings.lifecycle_default_retain_days, 'archive_before_delete': False, 'batch_size': settings.lifecycle_cleanup_batch_size},
    'connector_execution_log': {'retain_days': settings.lifecycle_default_retain_days, 'archive_before_delete': False, 'batch_size': settings.lifecycle_cleanup_batch_size},
    'smoke_test_results': {'retain_days': 14, 'archive_before_delete': False, 'batch_size': min(settings.lifecycle_cleanup_batch_size, 250)},
    'queue_backend_events': {'retain_days': 14, 'archive_before_delete': False, 'batch_size': settings.lifecycle_cleanup_batch_size},
    'workflow_version_events': {'retain_days': 90, 'archive_before_delete': False, 'batch_size': settings.lifecycle_cleanup_batch_size},
    'ai_route_runs': {'retain_days': settings.lifecycle_default_retain_days, 'archive_before_delete': False, 'batch_size': settings.lifecycle_cleanup_batch_size},
    'document_ingestion_runs': {'retain_days': 90, 'archive_before_delete': False, 'batch_size': min(settings.lifecycle_cleanup_batch_size, 250)},
    'dead_letter_items': {'retain_days': settings.lifecycle_default_retain_days, 'archive_before_delete': settings.lifecycle_archive_dead_letters, 'batch_size': min(settings.lifecycle_cleanup_batch_size, 250)},
}

RESOURCE_META: dict[str, dict[str, str]] = {
    'audit_logs': {'pk': 'id', 'time_col': 'timestamp'},
    'connector_execution_log': {'pk': 'connector_execution_log_id', 'time_col': 'created_at'},
    'smoke_test_results': {'pk': 'smoke_test_result_id', 'time_col': 'executed_at'},
    'queue_backend_events': {'pk': 'id', 'time_col': 'created_at'},
    'workflow_version_events': {'pk': 'id', 'time_col': 'created_at'},
    'ai_route_runs': {'pk': 'id', 'time_col': 'created_at'},
    'document_ingestion_runs': {'pk': 'id', 'time_col': 'created_at'},
    'dead_letter_items': {'pk': 'dead_letter_id', 'time_col': 'created_at'},
}


def _safe_fetch_one(sql: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
    try:
        return fetch_one(sql, params)
    except Exception:
        return None


def _safe_fetch_all(sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    try:
        return fetch_all(sql, params) or []
    except Exception:
        return []


def _safe_execute(sql: str, params: tuple[Any, ...]) -> None:
    try:
        execute(sql, params)
    except Exception:
        pass


def seed_lifecycle_policy_defaults(tenant_id: str = 'default') -> None:
    for resource_type, policy in DEFAULT_RETENTION_POLICIES.items():
        _safe_execute(
            """INSERT INTO retention_policies (tenant_id, resource_type, enabled, retain_days, archive_before_delete, batch_size, updated_by, metadata_json)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
               ON CONFLICT (tenant_id, resource_type)
               DO UPDATE SET retain_days=EXCLUDED.retain_days,
                             archive_before_delete=EXCLUDED.archive_before_delete,
                             batch_size=EXCLUDED.batch_size,
                             metadata_json=EXCLUDED.metadata_json,
                             updated_at=now()""",
            (tenant_id, resource_type, True, int(policy['retain_days']), bool(policy['archive_before_delete']), int(policy['batch_size']), 'system_seed', json.dumps({'seeded': True})),
        )


def upsert_retention_policy(tenant_id: str, resource_type: str, enabled: bool, retain_days: int, archive_before_delete: bool, batch_size: int, updated_by: str | None = None, metadata_json: dict[str, Any] | None = None) -> dict[str, Any]:
    resource_type = resource_type.strip()
    if resource_type not in DEFAULT_RETENTION_POLICIES:
        raise ValueError(f'unsupported resource_type={resource_type}')
    _safe_execute(
        """INSERT INTO retention_policies (tenant_id, resource_type, enabled, retain_days, archive_before_delete, batch_size, updated_by, metadata_json)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
           ON CONFLICT (tenant_id, resource_type)
           DO UPDATE SET enabled=EXCLUDED.enabled,
                         retain_days=EXCLUDED.retain_days,
                         archive_before_delete=EXCLUDED.archive_before_delete,
                         batch_size=EXCLUDED.batch_size,
                         updated_by=EXCLUDED.updated_by,
                         metadata_json=EXCLUDED.metadata_json,
                         updated_at=now()""",
        (tenant_id, resource_type, enabled, retain_days, archive_before_delete, batch_size, updated_by, json.dumps(metadata_json or {})),
    )
    row = _safe_fetch_one("SELECT tenant_id, resource_type, enabled, retain_days, archive_before_delete, batch_size, last_run_at, updated_by, metadata_json, created_at, updated_at FROM retention_policies WHERE tenant_id=%s AND resource_type=%s", (tenant_id, resource_type))
    if row:
        row['metadata_json'] = row.get('metadata_json') or {}
        return row
    return {
        'tenant_id': tenant_id,
        'resource_type': resource_type,
        'enabled': enabled,
        'retain_days': retain_days,
        'archive_before_delete': archive_before_delete,
        'batch_size': batch_size,
        'last_run_at': None,
        'updated_by': updated_by,
        'metadata_json': metadata_json or {},
        'created_at': None,
        'updated_at': None,
    }


def _fetch_policy_rows(tenant_id: str) -> list[dict[str, Any]]:
    rows = _safe_fetch_all(
        "SELECT tenant_id, resource_type, enabled, retain_days, archive_before_delete, batch_size, last_run_at, updated_by, metadata_json, created_at, updated_at FROM retention_policies WHERE tenant_id=%s ORDER BY resource_type",
        (tenant_id,),
    )
    seen = {row['resource_type'] for row in rows}
    for resource_type, defaults in DEFAULT_RETENTION_POLICIES.items():
        if resource_type not in seen:
            rows.append({
                'tenant_id': tenant_id,
                'resource_type': resource_type,
                'enabled': True,
                'retain_days': int(defaults['retain_days']),
                'archive_before_delete': bool(defaults['archive_before_delete']),
                'batch_size': int(defaults['batch_size']),
                'last_run_at': None,
                'updated_by': 'system_default',
                'metadata_json': {'seeded': False},
                'created_at': None,
                'updated_at': None,
            })
    rows.sort(key=lambda item: item['resource_type'])
    return rows


def _count_for_resource(tenant_id: str, resource_type: str, retain_days: int) -> tuple[int, int]:
    meta = RESOURCE_META[resource_type]
    total_row = _safe_fetch_one(f"SELECT count(*)::int AS c FROM {resource_type} WHERE tenant_id=%s", (tenant_id,)) or {'c': 0}
    eligible_row = _safe_fetch_one(
        f"SELECT count(*)::int AS c FROM {resource_type} WHERE tenant_id=%s AND {meta['time_col']} < now() - (%s || ' days')::interval",
        (tenant_id, int(retain_days)),
    ) or {'c': 0}
    return int(total_row.get('c') or 0), int(eligible_row.get('c') or 0)


def build_data_lifecycle_report(tenant_id: str = 'default', resource_types: list[str] | None = None, persist: bool = False) -> dict[str, Any]:
    requested = [item for item in (resource_types or []) if item in DEFAULT_RETENTION_POLICIES]
    rows = _fetch_policy_rows(tenant_id)
    items = []
    total_eligible = 0
    for row in rows:
        resource_type = row['resource_type']
        if requested and resource_type not in requested:
            continue
        total_count, eligible_count = _count_for_resource(tenant_id, resource_type, int(row['retain_days']))
        total_eligible += eligible_count
        items.append({
            'resource_type': resource_type,
            'enabled': bool(row.get('enabled', True)),
            'retain_days': int(row.get('retain_days') or 0),
            'archive_before_delete': bool(row.get('archive_before_delete', False)),
            'batch_size': int(row.get('batch_size') or DEFAULT_RETENTION_POLICIES[resource_type]['batch_size']),
            'total_count': total_count,
            'eligible_count': eligible_count,
            'last_run_at': row.get('last_run_at'),
            'updated_by': row.get('updated_by'),
            'metadata_json': row.get('metadata_json') or {},
            'next_action': 'run_cleanup' if bool(row.get('enabled', True)) and eligible_count > 0 else 'monitor',
        })
    payload = {
        'status': 'ok',
        'tenant_id': tenant_id,
        'count': len(items),
        'eligible_total': total_eligible,
        'report_generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'policies': items,
        'next_actions': [
            'Review large eligible_count values before enabling destructive cleanup in production.',
            'Run /lifecycle/run-cleanup with dry_run=true first, then rerun with dry_run=false when the report is acceptable.',
            'Archive DLQ rows before delete if dead-letter evidence must be preserved for incident review.',
        ],
    }
    if persist:
        _safe_execute(
            "INSERT INTO lifecycle_runs (tenant_id, run_type, dry_run, resource_types, status, summary_json, created_by) VALUES (%s,%s,%s,%s::jsonb,%s,%s::jsonb,%s)",
            (tenant_id, 'report', True, json.dumps(requested or [item['resource_type'] for item in items]), 'ok', json.dumps(payload), 'system_report'),
        )
    return payload


def _archive_dead_letter_rows(tenant_id: str, retain_days: int, batch_size: int, archived_by: str | None = None) -> tuple[int, int]:
    rows = _safe_fetch_all(
        "SELECT dead_letter_id, job_id, queue_item_id, reason, payload, created_at FROM dead_letter_items WHERE tenant_id=%s AND created_at < now() - (%s || ' days')::interval ORDER BY created_at ASC LIMIT %s",
        (tenant_id, int(retain_days), int(batch_size)),
    )
    archived = 0
    deleted = 0
    for row in rows:
        _safe_execute(
            """INSERT INTO dlq_archives (tenant_id, dead_letter_id, archived_payload, source_created_at, archived_by, reason)
               VALUES (%s,%s,%s::jsonb,%s,%s,%s)
               ON CONFLICT (tenant_id, dead_letter_id) DO NOTHING""",
            (
                tenant_id,
                row.get('dead_letter_id'),
                json.dumps({
                    'job_id': str(row.get('job_id')) if row.get('job_id') is not None else None,
                    'queue_item_id': str(row.get('queue_item_id')) if row.get('queue_item_id') is not None else None,
                    'reason': row.get('reason'),
                    'payload': row.get('payload') or {},
                }),
                row.get('created_at'),
                archived_by,
                row.get('reason'),
            ),
        )
        archived += 1
        _safe_execute("DELETE FROM dead_letter_items WHERE tenant_id=%s AND dead_letter_id=%s", (tenant_id, row.get('dead_letter_id')))
        deleted += 1
    return archived, deleted


def _cleanup_generic_resource(tenant_id: str, resource_type: str, retain_days: int, batch_size: int) -> None:
    meta = RESOURCE_META[resource_type]
    _safe_execute(
        f"""WITH doomed AS (
                SELECT {meta['pk']} AS pk
                FROM {resource_type}
                WHERE tenant_id=%s AND {meta['time_col']} < now() - (%s || ' days')::interval
                ORDER BY {meta['time_col']} ASC
                LIMIT %s
            )
            DELETE FROM {resource_type} target
            USING doomed
            WHERE target.{meta['pk']} = doomed.pk AND target.tenant_id=%s""",
        (tenant_id, int(retain_days), int(batch_size), tenant_id),
    )


def run_data_lifecycle_cleanup(tenant_id: str = 'default', resource_types: list[str] | None = None, dry_run: bool = True, actor_id: str | None = None, persist: bool = True) -> dict[str, Any]:
    requested = [item for item in (resource_types or []) if item in DEFAULT_RETENTION_POLICIES]
    rows = _fetch_policy_rows(tenant_id)
    items = []
    archived_total = 0
    deleted_total = 0
    eligible_total = 0
    for row in rows:
        resource_type = row['resource_type']
        if requested and resource_type not in requested:
            continue
        retain_days = int(row.get('retain_days') or DEFAULT_RETENTION_POLICIES[resource_type]['retain_days'])
        batch_size = int(row.get('batch_size') or DEFAULT_RETENTION_POLICIES[resource_type]['batch_size'])
        total_count, eligible_count = _count_for_resource(tenant_id, resource_type, retain_days)
        eligible_total += eligible_count
        archived_count = 0
        deleted_count = 0
        if bool(row.get('enabled', True)) and eligible_count > 0 and not dry_run:
            if resource_type == 'dead_letter_items' and bool(row.get('archive_before_delete', False)):
                archived_count, deleted_count = _archive_dead_letter_rows(tenant_id, retain_days, batch_size, archived_by=actor_id)
            else:
                _cleanup_generic_resource(tenant_id, resource_type, retain_days, batch_size)
                deleted_count = min(eligible_count, batch_size)
            _safe_execute(
                "UPDATE retention_policies SET last_run_at=now(), updated_at=now() WHERE tenant_id=%s AND resource_type=%s",
                (tenant_id, resource_type),
            )
        archived_total += archived_count
        deleted_total += deleted_count
        items.append({
            'resource_type': resource_type,
            'enabled': bool(row.get('enabled', True)),
            'retain_days': retain_days,
            'archive_before_delete': bool(row.get('archive_before_delete', False)),
            'batch_size': batch_size,
            'total_count': total_count,
            'eligible_count': eligible_count,
            'archived_count': archived_count,
            'deleted_count': deleted_count,
            'dry_run': dry_run,
            'last_run_at': row.get('last_run_at'),
        })
    payload = {
        'status': 'ok',
        'tenant_id': tenant_id,
        'dry_run': dry_run,
        'count': len(items),
        'eligible_total': eligible_total,
        'archived_total': archived_total,
        'deleted_total': deleted_total,
        'items': items,
        'next_actions': [
            'Inspect archived_total and deleted_total before increasing batch sizes.',
            'Keep dead-letter archiving enabled for incident-heavy environments so failures remain reviewable.',
            'Schedule wf_data_lifecycle_cleanup only after the dry-run report is stable for the tenant.',
        ],
    }
    if persist:
        _safe_execute(
            "INSERT INTO lifecycle_runs (tenant_id, run_type, dry_run, resource_types, status, summary_json, created_by) VALUES (%s,%s,%s,%s::jsonb,%s,%s::jsonb,%s)",
            (tenant_id, 'cleanup', dry_run, json.dumps(requested or [item['resource_type'] for item in items]), 'ok', json.dumps(payload), actor_id or 'system_cleanup'),
        )
    return payload
