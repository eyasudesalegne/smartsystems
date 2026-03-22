from fastapi.testclient import TestClient

import app.main as main_mod
from app.main import app

client = TestClient(app)


def test_lifecycle_policy_report_and_cleanup(monkeypatch):
    monkeypatch.setattr(main_mod, 'upsert_retention_policy', lambda tenant_id, resource_type, enabled, retain_days, archive_before_delete, batch_size, updated_by=None, metadata_json=None: {
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
    })
    monkeypatch.setattr(main_mod, 'build_data_lifecycle_report', lambda tenant_id='default', resource_types=None, persist=False: {
        'status': 'ok',
        'tenant_id': tenant_id,
        'count': 2,
        'eligible_total': 7,
        'report_generated_at': '2026-03-17T00:00:00Z',
        'policies': [
            {'resource_type': 'audit_logs', 'enabled': True, 'retain_days': 30, 'archive_before_delete': False, 'batch_size': 500, 'total_count': 10, 'eligible_count': 5, 'last_run_at': None, 'updated_by': 'tester', 'metadata_json': {}, 'next_action': 'run_cleanup'},
            {'resource_type': 'dead_letter_items', 'enabled': True, 'retain_days': 30, 'archive_before_delete': True, 'batch_size': 250, 'total_count': 4, 'eligible_count': 2, 'last_run_at': None, 'updated_by': 'tester', 'metadata_json': {}, 'next_action': 'run_cleanup'},
        ],
        'next_actions': ['dry_run first'],
    })
    monkeypatch.setattr(main_mod, 'run_data_lifecycle_cleanup', lambda tenant_id='default', resource_types=None, dry_run=True, actor_id=None, persist=True: {
        'status': 'ok',
        'tenant_id': tenant_id,
        'dry_run': dry_run,
        'count': 2,
        'eligible_total': 7,
        'archived_total': 2,
        'deleted_total': 5,
        'items': [
            {'resource_type': 'audit_logs', 'enabled': True, 'retain_days': 30, 'archive_before_delete': False, 'batch_size': 500, 'total_count': 10, 'eligible_count': 5, 'archived_count': 0, 'deleted_count': 5, 'dry_run': dry_run, 'last_run_at': None},
            {'resource_type': 'dead_letter_items', 'enabled': True, 'retain_days': 30, 'archive_before_delete': True, 'batch_size': 250, 'total_count': 4, 'eligible_count': 2, 'archived_count': 2, 'deleted_count': 0, 'dry_run': dry_run, 'last_run_at': None},
        ],
        'next_actions': ['inspect counts'],
    })

    resp = client.post('/lifecycle/policy', json={'tenant_id': 'default', 'resource_type': 'audit_logs', 'enabled': True, 'retain_days': 45, 'archive_before_delete': False, 'batch_size': 250, 'updated_by': 'tester'})
    assert resp.status_code == 200
    assert resp.json()['policy']['retain_days'] == 45

    report = client.post('/lifecycle/report', json={'tenant_id': 'default', 'persist': False})
    assert report.status_code == 200
    assert report.json()['eligible_total'] == 7

    cleanup = client.post('/lifecycle/run-cleanup', json={'tenant_id': 'default', 'actor_id': 'tester', 'dry_run': True, 'persist': False})
    assert cleanup.status_code == 200
    assert cleanup.json()['dry_run'] is True
    assert cleanup.json()['archived_total'] == 2


def test_admin_lifecycle(monkeypatch):
    monkeypatch.setattr(main_mod, 'build_data_lifecycle_report', lambda tenant_id='default', resource_types=None, persist=False: {'status': 'ok', 'tenant_id': tenant_id, 'count': 1, 'eligible_total': 3, 'policies': [{'resource_type': 'audit_logs'}], 'next_actions': []})
    resp = client.get('/admin/lifecycle?tenant_id=default')
    assert resp.status_code == 200
    payload = resp.json()['summary']
    assert payload['eligible_total'] == 3
    assert payload['policy_count'] == 1


def test_admin_lifecycle_uses_request_tenant_scope(monkeypatch):
    seen = []

    def fake_build_data_lifecycle_report(tenant_id='default', resource_types=None, persist=False):
        seen.append(tenant_id)
        return {'status': 'ok', 'tenant_id': tenant_id, 'count': 1, 'eligible_total': 4, 'policies': [{'resource_type': 'audit_logs'}], 'next_actions': []}

    monkeypatch.setattr(main_mod, 'build_data_lifecycle_report', fake_build_data_lifecycle_report)
    resp = client.get('/admin/lifecycle?tenant_id=default', headers={'x-tenant-id': 'tenant-b'})
    assert resp.status_code == 200
    assert resp.json()['tenant_id'] == 'tenant-b'
    assert seen == ['tenant-b']
