from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

APP_BASE_URL = os.getenv('APP_BASE_URL', 'http://localhost:8080').rstrip('/')
DATABASE_URL = os.getenv('DATABASE_URL', '')


def call(path: str, payload: dict | None = None) -> dict:
    req = urllib.request.Request(
        APP_BASE_URL + path,
        data=(json.dumps(payload).encode() if payload is not None else None),
        headers={'Content-Type': 'application/json'},
        method='POST' if payload is not None else 'GET',
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        raise SystemExit(f'{path} failed with HTTP {exc.code}: {body}')


def verify_db() -> dict:
    if not DATABASE_URL:
        return {'status': 'skipped', 'reason': 'DATABASE_URL not set'}
    try:
        import psycopg
    except Exception as exc:  # pragma: no cover - optional at runtime
        return {'status': 'skipped', 'reason': f'psycopg unavailable: {exc}'}
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            counts = {}
            for table in ['connector_registry', 'connector_execution_log', 'workflow_templates', 'smoke_test_results', 'connector_credentials_meta']:
                cur.execute(f'SELECT count(*) FROM {table}')
                counts[table] = cur.fetchone()[0]
    assert counts['connector_registry'] >= 14, counts
    assert counts['connector_execution_log'] >= 4, counts
    assert counts['workflow_templates'] >= 1, counts
    assert counts['smoke_test_results'] >= 1, counts
    assert counts['connector_credentials_meta'] >= 2, counts
    return {'status': 'ok', 'counts': counts}


def main() -> None:
    sync = call('/connectors/sync-registry', {'tenant_id': 'default'})
    assert sync['status'] == 'ok'
    assert sync['synced_count'] >= 14

    validate = call('/connectors/validate-config', {'service_name': 'pubmed'})
    assert validate['status'] == 'ok'

    draft = call('/connectors/workflow-draft', {'service_name': 'pubmed', 'operation_id': 'search'})
    assert draft['status'] == 'ok'

    smoke = call('/connectors/smoke-test', {'service_name': 'drawio', 'operation_id': 'build_xml_artifact', 'dry_run': True})
    assert smoke['status'] == 'ok'

    report = {
        'sync': {'synced_count': sync['synced_count']},
        'validate': {'service_name': validate['service_name'], 'configured': validate['configured']},
        'draft': {'workflow_name': draft['workflow']['name']},
        'smoke': {'service_name': smoke['service_name'], 'operation_id': smoke['operation_id']},
        'db': verify_db(),
    }
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
