import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.connectors import build_workflow_manifest
from app.main import app
import app.main as main_mod

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[2]


def test_build_workflow_manifest_covers_pubmed_and_notebooklm():
    items = {item['service_name']: item for item in build_workflow_manifest()}
    assert 'pubmed' in items
    assert 'search' in items['pubmed']['packaged_operations']
    assert 'summary' in items['pubmed']['unpackaged_operations']
    assert 'notebooklm' in items
    assert items['notebooklm']['recommended_import_workflow'] == 'wf_ext_notebooklm_sync_bundle_stub.json'


def test_connector_workflow_manifest_endpoint_returns_manifest():
    response = client.get('/connectors/workflow-manifest')
    assert response.status_code == 200
    payload = response.json()
    assert payload['count'] >= 14
    items = {item['service_name']: item for item in payload['connectors']}
    assert items['google_drive']['recommended_import_workflow'] == 'wf_google_drive_fetch.json'
    assert 'export_file' in items['google_drive']['unpackaged_operations']


def test_connector_readiness_report_combines_preflight_and_manifest():
    response = client.post('/connectors/readiness-report', json={'tenant_id': 'default', 'service_names': ['google_drive', 'overleaf'], 'persist': False})
    assert response.status_code == 200
    payload = response.json()
    assert payload['count'] == 2
    items = {item['service_name']: item for item in payload['connectors']}
    assert items['google_drive']['recommended_import_workflow'] == 'wf_google_drive_fetch.json'
    assert items['google_drive']['packaged_operations_count'] >= 1
    assert items['overleaf']['recommended_action'] == 'import_packaged_workflow'


def test_connector_deployment_plan_builds_ordered_steps():
    payload = main_mod._build_connector_deployment_plan(tenant_id='default', service_names=['google_drive', 'overleaf'], persist=False)
    assert payload['count'] == 2
    items = {item['service_name']: item for item in payload['connectors']}
    assert items['google_drive']['recommended_import_workflow'] == 'wf_google_drive_fetch.json'
    assert items['google_drive']['steps'][0]['action'] in {'fill_credentials', 'sync_registry'}
    assert any(step['action'] == 'import_workflow' for step in items['overleaf']['steps'])
    assert payload['summary']['import_packaged_workflow'] >= 2


def test_connector_rollout_bundle_aggregates_reports():
    payload = main_mod._build_connector_rollout_bundle(tenant_id='default', service_names=['google_drive', 'overleaf'], persist=False)
    assert payload['count'] == 2
    items = {item['service_name']: item for item in payload['services']}
    assert items['google_drive']['recommended_import_workflow'] == 'wf_google_drive_fetch.json'
    assert payload['reports']['readiness']['count'] == 2
    assert payload['reports']['deployment']['ready_to_import_count'] >= 1


def test_connector_persistence_report_builds_actions_without_db(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError('db unavailable')

    monkeypatch.setattr(main_mod, 'fetch_one', boom)
    payload = main_mod._build_connector_persistence_report(tenant_id='default')
    assert payload['status'] == 'degraded'
    assert payload['database_available'] is False
    assert payload['all_tables_present'] is False
    assert payload['next_actions']



def test_generated_credential_matrix_report_exists():
    payload = json.loads((ROOT / 'docs' / 'generated_connector_credential_matrix.json').read_text())
    assert payload['status'] == 'ok'
    assert payload['unique_credential_key_count'] >= 1
    assert payload['credential_keys']
