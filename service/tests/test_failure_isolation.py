from fastapi.testclient import TestClient

import app.main as main_mod
from app.main import app

client = TestClient(app)


def test_connectors_execute_live_rejects_open_circuit(monkeypatch):
    monkeypatch.setattr(main_mod, '_get_connector_runtime_policy', lambda service_name, tenant_id='default': {'tenant_id': tenant_id, 'service_name': service_name, 'enabled': True, 'requests_per_window': 30, 'window_seconds': 60, 'timeout_seconds': 30, 'failure_threshold': 5, 'cooldown_seconds': 300})
    monkeypatch.setattr(main_mod, '_get_connector_runtime_state', lambda service_name, tenant_id='default': {'circuit_state': 'open', 'consecutive_failures': 5, 'last_circuit_opened_at': __import__('datetime').datetime.utcnow(), 'last_success_at': None, 'last_failure_at': None, 'rate_limit_rejection_count': 0, 'circuit_open_count': 1, 'timeout_rejection_count': 0, 'blocked_count': 0, 'last_error_message': 'boom'})
    monkeypatch.setattr(main_mod, '_count_recent_connector_executions', lambda service_name, tenant_id='default', window_seconds=60: 0)
    monkeypatch.setattr(main_mod, '_register_connector_isolation_rejection', lambda *args, **kwargs: None)
    resp = client.post('/connectors/execute-live', json={'service_name': 'pubmed', 'operation_id': 'search', 'body': {}, 'query': {}, 'headers': {}, 'timeout_seconds': 20})
    assert resp.status_code == 503
    assert resp.json()['detail']['code'] == 'CIRCUIT_OPEN'


def test_connectors_execute_live_caps_timeout(monkeypatch):
    captured = {}
    monkeypatch.setattr(main_mod, '_get_connector_runtime_policy', lambda service_name, tenant_id='default': {'tenant_id': tenant_id, 'service_name': service_name, 'enabled': True, 'requests_per_window': 30, 'window_seconds': 60, 'timeout_seconds': 10, 'failure_threshold': 5, 'cooldown_seconds': 300})
    monkeypatch.setattr(main_mod, '_get_connector_runtime_state', lambda service_name, tenant_id='default': {'circuit_state': 'closed', 'consecutive_failures': 0, 'last_circuit_opened_at': None, 'last_success_at': None, 'last_failure_at': None, 'rate_limit_rejection_count': 0, 'circuit_open_count': 0, 'timeout_rejection_count': 0, 'blocked_count': 0, 'last_error_message': None})
    monkeypatch.setattr(main_mod, '_count_recent_connector_executions', lambda service_name, tenant_id='default', window_seconds=60: 0)
    monkeypatch.setattr(main_mod, '_record_connector_runtime_outcome', lambda *args, **kwargs: None)
    monkeypatch.setattr(main_mod, '_log_connector_execution', lambda *args, **kwargs: None)

    async def fake_execute(service_name, operation_id=None, body=None, query=None, headers=None, timeout_seconds=30):
        captured['timeout_seconds'] = timeout_seconds
        return {'status': 'ok', 'service_name': service_name, 'operation_id': operation_id or 'search', 'data': {'ok': True}}

    monkeypatch.setattr(main_mod, 'execute_live_request', fake_execute)
    resp = client.post('/connectors/execute-live', json={'service_name': 'pubmed', 'operation_id': 'search', 'timeout_seconds': 55})
    assert resp.status_code == 200
    assert resp.json()['effective_timeout_seconds'] == 10
    assert captured['timeout_seconds'] == 10


def test_workflow_execution_check_respects_cap(monkeypatch):
    monkeypatch.setattr(main_mod, '_get_workflow_runtime_policy', lambda workflow_id, tenant_id='default': {'tenant_id': tenant_id, 'workflow_id': workflow_id, 'enabled': True, 'max_executions_per_window': 1, 'window_seconds': 60})
    monkeypatch.setattr(main_mod, '_count_recent_workflow_executions', lambda workflow_id, tenant_id='default', window_seconds=60: 1)
    resp = client.post('/workflows/execution/check', json={'tenant_id': 'default', 'workflow_id': 'wf_workflow_promotion_pipeline', 'persist': False})
    assert resp.status_code == 429
    assert resp.json()['detail']['code'] == 'WORKFLOW_CAP_EXCEEDED'


def test_failure_isolation_report_endpoint(monkeypatch):
    monkeypatch.setattr(main_mod, '_build_failure_isolation_report', lambda tenant_id='default', service_names=None, persist=True: {'status': 'ok', 'tenant_id': tenant_id, 'count': 1, 'open_circuit_count': 1, 'half_open_count': 0, 'rate_limited_services_count': 0, 'next_actions': ['wait'], 'services': [{'service_name': 'pubmed', 'display_name': 'PubMed', 'configured': True, 'implementation_status': 'live_api', 'integration_mode': 'rest_api', 'circuit_state': 'open', 'circuit_open': True, 'blocked': True, 'requests_per_window': 30, 'window_seconds': 60, 'timeout_seconds': 10, 'failure_threshold': 5, 'cooldown_seconds': 300, 'recent_execute_count': 2, 'consecutive_failures': 5, 'rate_limit_rejection_count': 0, 'circuit_open_count': 1, 'timeout_rejection_count': 0, 'recommended_action': 'wait_for_cooldown', 'notes': 'ok'}]})
    monkeypatch.setattr(main_mod, '_log_connector_execution', lambda *args, **kwargs: None)
    resp = client.post('/connectors/failure-isolation-report', json={'tenant_id': 'default'})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload['open_circuit_count'] == 1
    assert payload['services'][0]['circuit_state'] == 'open'
