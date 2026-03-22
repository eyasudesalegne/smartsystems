from pathlib import Path
from zipfile import ZipFile

from fastapi.testclient import TestClient

import app.main as main_mod
from app.main import app

client = TestClient(app)


def test_release_manifest_endpoint():
    resp = client.post('/release/manifest', json={'tenant_id': 'default', 'persist': False})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload['file_count'] > 0
    assert payload['workflow_count'] > 0
    assert payload['migration_count'] > 0
    assert payload['manifest_checksum']
    assert 'n8n/manifest/import_order.txt' == payload['includes']['import_order']


def test_release_checksum_validate_detects_mismatch():
    manifest = main_mod._build_release_manifest(tenant_id='default', persist=False)
    key = next(iter(manifest['checksums']))
    manifest['checksums'][key] = '0' * 64
    resp = client.post('/release/checksum-validate', json={'tenant_id': 'default', 'manifest_json': manifest, 'persist': False})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload['valid'] is False
    assert key in payload['mismatched_files']


def test_release_preflight_endpoint_ready():
    resp = client.post('/release/preflight', json={'tenant_id': 'default', 'persist': False})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload['ready'] is True
    assert payload['checks']['import_order']['ok'] is True
    assert payload['checks']['checksum_validation']['valid'] is True


def test_release_rollback_package_endpoint(tmp_path):
    out_zip = tmp_path / 'rollback_bundle.zip'
    resp = client.post('/release/rollback-package', json={'tenant_id': 'default', 'output_path': str(out_zip), 'persist': False})
    assert resp.status_code == 200
    payload = resp.json()
    assert out_zip.exists()
    assert payload['included_files_count'] > 1
    with ZipFile(out_zip) as zf:
        names = set(zf.namelist())
    assert 'release_manifest.json' in names
    assert 'docs/ROLLBACK_GUIDE.md' in names
    assert 'n8n/manifest/import_order.txt' in names


def test_release_artifact_dir_prefers_config(monkeypatch, tmp_path):
    monkeypatch.setattr(main_mod.settings, 'release_artifact_dir', str(tmp_path / 'artifacts'))
    path = main_mod._release_artifact_dir()
    assert path == tmp_path / 'artifacts'
    assert path.exists()


def test_release_publish_endpoint(tmp_path):
    out_zip = tmp_path / 'publication_bundle.zip'
    resp = client.post('/release/publish', json={'tenant_id': 'default', 'output_path': str(out_zip), 'persist': False})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload['published'] is True
    assert payload['publication_status'] == 'published'
    assert payload['preflight_ready'] is True
    assert payload['checksum_valid'] is True
    assert out_zip.exists()
    with ZipFile(out_zip) as zf:
        names = set(zf.namelist())
    assert 'release_publication_summary.json' in names
    assert 'release_manifest.json' in names
    assert 'release_preflight_report.json' in names


def test_release_publications_endpoint_empty_without_db():
    resp = client.get('/release/publications')
    assert resp.status_code == 200
    payload = resp.json()
    assert payload['status'] == 'ok'
    assert isinstance(payload['items'], list)


def test_admin_releases_endpoint():
    resp = client.get('/admin/releases')
    assert resp.status_code == 200
    payload = resp.json()
    assert payload['status'] == 'ok'
    assert 'summary' in payload
    assert 'publication_count' in payload['summary']


def test_release_channel_upsert_and_list():
    resp = client.post('/release/channel', json={'tenant_id': 'default', 'channel_name': 'ops_webhook', 'channel_type': 'webhook_notify', 'enabled': True, 'endpoint_url': 'https://example.invalid/release-hook', 'metadata_json': {'notes': 'ops hook'}})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload['channel']['channel_name'] == 'ops_webhook'
    listing = client.get('/release/channels')
    assert listing.status_code == 200
    items = listing.json()['items']
    assert any(item['channel_name'] == 'ops_webhook' for item in items)


def test_release_channel_plan_endpoint():
    resp = client.post('/release/channel-plan', json={'tenant_id': 'default', 'persist': False})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload['status'] == 'ok'
    assert payload['count'] >= 1
    assert isinstance(payload['planned_channels'], list)
    assert any(item['channel_name'] == 'manual_bundle_review' for item in payload['planned_channels'])


def test_admin_release_channels_endpoint():
    resp = client.get('/admin/release-channels')
    assert resp.status_code == 200
    payload = resp.json()
    assert payload['status'] == 'ok'
    assert 'channel_count' in payload['summary']



def test_release_channel_execute_endpoint(tmp_path):
    out_dir = tmp_path / 'channel_exec'
    resp = client.post('/release/channel-execute', json={'tenant_id': 'default', 'persist': False, 'include_publication_bundle': True, 'dry_run': True, 'output_path': str(out_dir / 'ignored.json')})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload['status'] == 'ok'
    assert payload['count'] >= 1
    assert isinstance(payload['execution_items'], list)
    assert any(item['channel_name'] == 'manual_bundle_review' for item in payload['execution_items'])
    assert payload['prepared_count'] >= 1


def test_release_channel_execution_list_and_admin():
    client.post('/release/channel-execute', json={'tenant_id': 'default', 'persist': False, 'dry_run': True})
    listing = client.get('/release/channel-executions')
    assert listing.status_code == 200
    payload = listing.json()
    assert payload['status'] == 'ok'
    assert isinstance(payload['items'], list)
    admin = client.get('/admin/release-channel-executions')
    assert admin.status_code == 200
    admin_payload = admin.json()
    assert admin_payload['status'] == 'ok'
    assert 'execution_count' in admin_payload['summary']
