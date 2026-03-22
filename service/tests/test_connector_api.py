from fastapi.testclient import TestClient

import app.main as main_mod
from app.main import app


client = TestClient(app)


def test_connector_catalog_endpoint():
    response = client.get('/connectors/catalog')
    assert response.status_code == 200
    payload = response.json()
    assert payload['count'] >= 14


def test_connector_validate_endpoint():
    response = client.post('/connectors/validate-config', json={'service_name': 'drawio'})
    assert response.status_code == 200
    payload = response.json()
    assert payload['service_name'] == 'drawio'
    assert 'configured' in payload


def test_connector_smoke_test_endpoint():
    response = client.post('/connectors/smoke-test', json={'service_name': 'drawio', 'operation_id': 'build_xml_artifact', 'dry_run': True})
    assert response.status_code == 200
    payload = response.json()
    assert payload['service_name'] == 'drawio'
    assert payload['operation_id'] == 'build_xml_artifact'


def test_connector_sync_registry_endpoint(monkeypatch):
    calls = []
    monkeypatch.setattr(main_mod, '_safe_db_execute', lambda sql, params: calls.append((sql, params)))

    response = client.post('/connectors/sync-registry', json={'tenant_id': 'default'})
    assert response.status_code == 200
    payload = response.json()
    assert payload['tenant_id'] == 'default'
    assert payload['synced_count'] >= 14
    assert 'pubmed' in payload['services']
    assert len(calls) >= payload['synced_count']


def test_health_endpoint_degrades_safely_when_db_is_down(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError('db down')

    monkeypatch.setattr(main_mod, 'fetch_one', boom)
    monkeypatch.setattr(main_mod.ollama, 'tags', lambda: ['gemma3'])

    response = client.get('/health')
    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'degraded'
    assert payload['postgres'] == 'down'
    assert payload['queue_depth'] == 0


def test_connector_preflight_endpoint(monkeypatch):
    calls = []
    monkeypatch.setattr(main_mod, '_safe_db_execute', lambda sql, params: calls.append((sql, params)))

    response = client.post('/connectors/preflight', json={'tenant_id': 'default', 'service_names': ['drawio', 'pubmed'], 'persist': True})
    assert response.status_code == 200
    payload = response.json()
    assert payload['tenant_id'] == 'default'
    assert payload['count'] == 2
    assert {item['service_name'] for item in payload['connectors']} == {'drawio', 'pubmed'}
    assert len(calls) >= 2



def test_connector_readiness_report_endpoint(monkeypatch):
    calls = []
    monkeypatch.setattr(main_mod, '_safe_db_execute', lambda sql, params: calls.append((sql, params)))

    response = client.post('/connectors/readiness-report', json={'tenant_id': 'default', 'service_names': ['drawio', 'pubmed'], 'persist': True})
    assert response.status_code == 200
    payload = response.json()
    assert payload['tenant_id'] == 'default'
    assert payload['count'] == 2
    items = {item['service_name']: item for item in payload['connectors']}
    assert items['drawio']['recommended_action'] == 'import_packaged_workflow'
    assert items['pubmed']['recommended_action'] in {'fill_credentials_then_import', 'import_packaged_workflow'}
    assert len(calls) >= 2


def test_connector_deployment_plan_endpoint(monkeypatch):
    calls = []
    monkeypatch.setattr(main_mod, '_safe_db_execute', lambda sql, params: calls.append((sql, params)))

    response = client.post('/connectors/deployment-plan', json={'tenant_id': 'default', 'service_names': ['drawio', 'google_drive'], 'persist': True})
    assert response.status_code == 200
    payload = response.json()
    assert payload['tenant_id'] == 'default'
    assert payload['count'] == 2
    items = {item['service_name']: item for item in payload['connectors']}
    assert items['drawio']['primary_step'] == 'import_workflow'
    assert any(step['action'] == 'import_workflow' for step in items['drawio']['steps'])
    assert items['google_drive']['primary_step'] == 'fill_credentials'
    assert len(calls) >= 2


def test_connector_rollout_bundle_endpoint(monkeypatch):
    calls = []
    monkeypatch.setattr(main_mod, '_safe_db_execute', lambda sql, params: calls.append((sql, params)))

    response = client.post('/connectors/rollout-bundle', json={'tenant_id': 'default', 'service_names': ['drawio', 'google_drive'], 'persist': True})
    assert response.status_code == 200
    payload = response.json()
    assert payload['tenant_id'] == 'default'
    assert payload['count'] == 2
    items = {item['service_name']: item for item in payload['services']}
    assert items['drawio']['primary_step'] == 'import_workflow'
    assert items['google_drive']['primary_step'] == 'fill_credentials'
    assert 'python scripts/build_connector_deployment_plan.py --remote --persist' in payload['command_sequence']
    assert len(calls) >= 2


def test_connector_persistence_report_endpoint_degrades_safely(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError('db unavailable')

    monkeypatch.setattr(main_mod, 'fetch_one', boom)

    response = client.post('/connectors/persistence-report', json={'tenant_id': 'default'})
    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'degraded'
    assert payload['database_available'] is False
    assert payload['existing_table_count'] == 0
    assert payload['tables'][0]['note']



def test_connector_credential_matrix_endpoint(monkeypatch):
    calls = []
    monkeypatch.setattr(main_mod, '_safe_db_execute', lambda sql, params: calls.append((sql, params)))

    response = client.post('/connectors/credential-matrix', json={'tenant_id': 'default', 'service_names': ['drawio', 'google_drive'], 'persist': True})
    assert response.status_code == 200
    payload = response.json()
    assert payload['tenant_id'] == 'default'
    assert payload['count'] == 2
    assert payload['unique_credential_key_count'] >= 2
    key_rows = {item['credential_key']: item for item in payload['credential_keys']}
    assert 'GOOGLE_DRIVE_CLIENT_ID' in key_rows
    assert 'drawio' in {item['service_name'] for item in payload['services']}
    assert len(calls) >= 2
