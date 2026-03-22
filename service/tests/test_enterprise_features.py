from fastapi.testclient import TestClient

import app.main as main_mod
from app.main import app

client = TestClient(app)


def test_auth_token_and_protected_admin_endpoint(monkeypatch):
    monkeypatch.setattr(main_mod.settings, 'auth_required', True)
    try:
        monkeypatch.setattr(main_mod, 'compute_metrics', lambda tenant_id='default': {'queue_depth': 0, 'queued_jobs': 0, 'running_jobs': 0, 'failed_jobs': 0, 'dead_letters': 0, 'pending_approvals': 0, 'ai_artifacts_24h': 0, 'avg_ai_latency_ms_24h': 0, 'published_posts': 0})
        token_resp = client.post('/auth/token', json={'username': 'admin', 'tenant_id': 'default'})
        assert token_resp.status_code == 200
        token = token_resp.json()['access_token']
        resp = client.get('/admin/system', headers={'Authorization': f'Bearer {token}'})
        assert resp.status_code == 200
        assert resp.json()['summary']['auth_required'] is True
    finally:
        monkeypatch.setattr(main_mod.settings, 'auth_required', False)


def test_secrets_endpoints(monkeypatch):
    monkeypatch.setattr(main_mod, 'set_secret', lambda secret_name, secret_value, tenant_id='default', created_by=None, connector_binding=None: {'status': 'ok', 'tenant_id': tenant_id, 'secret_name': secret_name, 'redacted_value': 'ab***yz', 'connector_binding': connector_binding})
    monkeypatch.setattr(main_mod, 'get_secret', lambda secret_name, tenant_id='default', reveal=False: {'tenant_id': tenant_id, 'secret_name': secret_name, 'redacted_value': 'ab***yz', 'value': 'abcxyz' if reveal else None, 'metadata': {}, 'created_by': 'tester', 'updated_by': 'tester', 'created_at': None, 'updated_at': None})
    monkeypatch.setattr(main_mod, 'list_secrets', lambda tenant_id='default': {'status': 'ok', 'tenant_id': tenant_id, 'count': 1, 'secrets': [{'tenant_id': tenant_id, 'secret_name': 'FIGMA_ACCESS_TOKEN', 'redacted_value': 'ab***yz', 'metadata': {}, 'created_by': 'tester', 'updated_by': 'tester', 'created_at': None, 'updated_at': None}]})

    resp = client.post('/secrets/set', json={'tenant_id': 'default', 'secret_name': 'FIGMA_ACCESS_TOKEN', 'secret_value': 'abcxyz'})
    assert resp.status_code == 200
    assert resp.json()['secret_name'] == 'FIGMA_ACCESS_TOKEN'

    resp = client.post('/secrets/get', json={'tenant_id': 'default', 'secret_name': 'FIGMA_ACCESS_TOKEN', 'reveal': True})
    assert resp.status_code == 200
    assert resp.json()['secret']['value'] == 'abcxyz'

    resp = client.post('/secrets/list', json={'tenant_id': 'default'})
    assert resp.status_code == 200
    assert resp.json()['count'] == 1


def test_metrics_prometheus(monkeypatch):
    monkeypatch.setattr(main_mod, 'compute_metrics', lambda tenant_id='default': {'queue_depth': 3, 'queued_jobs': 1, 'running_jobs': 1, 'failed_jobs': 2, 'dead_letters': 4, 'pending_approvals': 0, 'ai_artifacts_24h': 5, 'avg_ai_latency_ms_24h': 123, 'published_posts': 0})
    monkeypatch.setattr(main_mod, 'fetch_one', lambda sql, params=None: {'success_count': 9, 'failure_count': 1, 'retry_count': 2} if 'connector_metrics' in sql else {'c': 0})
    resp = client.get('/metrics?format=prometheus')
    assert resp.status_code == 200
    assert 'control_plane_queue_depth' in resp.text
    assert 'control_plane_connector_success_total' in resp.text


def test_connector_health_and_metrics(monkeypatch):
    monkeypatch.setattr(main_mod, 'validate_connector_config', lambda service_name: {'service_name': service_name, 'configured': True, 'implementation_status': 'live_api', 'integration_mode': 'rest_api', 'notes': 'ok'})
    monkeypatch.setattr(main_mod, 'fetch_one', lambda sql, params=None: {'last_success_at': None, 'last_failure_at': None, 'failure_rate_percent': 0, 'execution_count': 5, 'success_count': 5, 'failure_count': 0, 'retry_count': 1} if 'connector_metrics' in sql else {'c': 0})
    resp = client.get('/connectors/pubmed/health')
    assert resp.status_code == 200
    assert resp.json()['configured'] is True
    resp = client.get('/connectors/pubmed/metrics')
    assert resp.status_code == 200
    assert resp.json()['execution_count'] == 5


def test_connector_metrics_use_request_tenant_scope(monkeypatch):
    seen = []

    monkeypatch.setattr(main_mod, 'validate_connector_config', lambda service_name: {'service_name': service_name, 'configured': True, 'implementation_status': 'live_api', 'integration_mode': 'rest_api', 'notes': 'ok'})

    def fake_fetch_one(sql, params=None):
        if 'connector_metrics' in sql:
            seen.append(params)
            tenant_id = params[0]
            if tenant_id == 'tenant-b':
                return {'last_success_at': None, 'last_failure_at': None, 'failure_rate_percent': 0, 'execution_count': 7, 'success_count': 7, 'failure_count': 0, 'retry_count': 0}
            return {'last_success_at': None, 'last_failure_at': None, 'failure_rate_percent': 0, 'execution_count': 2, 'success_count': 2, 'failure_count': 0, 'retry_count': 0}
        return {'c': 0}

    monkeypatch.setattr(main_mod, 'fetch_one', fake_fetch_one)

    resp = client.get('/connectors/pubmed/metrics?tenant_id=default', headers={'x-tenant-id': 'tenant-b'})
    assert resp.status_code == 200
    assert resp.json()['execution_count'] == 7
    assert seen[0][0] == 'tenant-b'


def test_workflow_version_history_and_rollback(monkeypatch):
    calls = []

    def fake_fetch_all(sql, params=None):
        if 'FROM workflow_versions' in sql:
            return [
                {'workflow_id': 'wf_pubmed_search', 'version': 2, 'workflow_status': 'draft', 'definition_json': {'name': 'wf_pubmed_search'}, 'created_at': None, 'updated_at': None},
                {'workflow_id': 'wf_pubmed_search', 'version': 1, 'workflow_status': 'published', 'definition_json': {'name': 'wf_pubmed_search'}, 'created_at': None, 'updated_at': None},
            ]
        return []

    def fake_fetch_one(sql, params=None):
        if 'COALESCE(max(version), 0) AS max_version' in sql:
            return {'max_version': 2}
        if 'WHERE tenant_id=%s AND workflow_id=%s AND version=%s' in sql:
            version = params[2]
            if version == 1:
                return {'workflow_id': 'wf_pubmed_search', 'version': 1, 'workflow_status': 'published', 'definition_json': {'name': 'wf_pubmed_search'}, 'created_at': None, 'updated_at': None}
            if version == 2:
                return None
            return None

    monkeypatch.setattr(main_mod, 'fetch_all', fake_fetch_all)
    monkeypatch.setattr(main_mod, 'fetch_one', fake_fetch_one)
    monkeypatch.setattr(main_mod, '_safe_db_execute', lambda sql, params: calls.append((sql, params)))

    hist = client.get('/workflows/version/history/wf_pubmed_search?tenant_id=default&include_definition=false')
    assert hist.status_code == 200
    assert hist.json()['published_version'] == 1
    assert hist.json()['count'] == 2
    assert hist.json()['versions'][0]['definition_json'] == {}

    rollback = client.post('/workflows/version/rollback', json={'tenant_id': 'default', 'workflow_id': 'wf_pubmed_search', 'source_version': 1, 'new_version': 4, 'status': 'draft', 'actor_id': 'operator'})
    assert rollback.status_code == 200
    assert rollback.json()['version'] == 4
    assert any('INSERT INTO workflow_versions' in sql for sql, _ in calls)
    assert any('INSERT INTO workflow_version_events' in sql for sql, _ in calls)


def test_workflow_history_uses_request_tenant_scope(monkeypatch):
    seen = []

    def fake_fetch_all(sql, params=None):
        if 'FROM workflow_versions' in sql:
            seen.append(params)
            tenant_id = params[0]
            return [
                {'tenant_id': tenant_id, 'workflow_id': 'wf_pubmed_search', 'version': 1, 'workflow_status': 'published', 'definition_json': {'tenant_id': tenant_id}, 'created_at': None, 'updated_at': None},
            ]
        return []

    monkeypatch.setattr(main_mod, 'fetch_all', fake_fetch_all)

    resp = client.get('/workflows/version/history/wf_pubmed_search?tenant_id=default&include_definition=false', headers={'x-tenant-id': 'tenant-b'})
    assert resp.status_code == 200
    assert resp.json()['tenant_id'] == 'tenant-b'
    assert seen[0][0] == 'tenant-b'



def test_workflow_version_promote_rejects_invalid_transition(monkeypatch):
    monkeypatch.setattr(main_mod, 'fetch_one', lambda sql, params=None: {'workflow_id': 'wf_pubmed_search', 'version': 1, 'workflow_status': 'draft', 'definition_json': {'name': 'wf_pubmed_search'}} if 'WHERE tenant_id=%s AND workflow_id=%s AND version=%s' in sql else {'c': 0})
    resp = client.post('/workflows/version/promote', json={'tenant_id': 'default', 'workflow_id': 'wf_pubmed_search', 'version': 1, 'status': 'published'})
    assert resp.status_code == 409
    assert resp.json()['detail']['code'] == 'INVALID_PROMOTION_TRANSITION'


def test_admin_workflows_summary(monkeypatch):
    def fake_fetch_one(sql, params=None):
        if 'workflow_version_events' in sql:
            return {'c': 4}
        if "status='published'" in sql:
            return {'c': 1}
        if "status='draft'" in sql:
            return {'c': 2}
        if 'workflow_versions' in sql:
            return {'c': 3}
        return {'c': 0}

    monkeypatch.setattr(main_mod, 'fetch_one', fake_fetch_one)
    monkeypatch.setattr(main_mod, 'fetch_all', lambda sql, params=None: [{'workflow_id': 'wf_pubmed_search', 'version': 1, 'workflow_status': 'published'}])
    resp = client.get('/admin/workflows')
    assert resp.status_code == 200
    payload = resp.json()['summary']
    assert payload['workflow_version_count'] == 3
    assert payload['workflow_event_count'] == 4
    assert payload['recent_versions'][0]['workflow_id'] == 'wf_pubmed_search'


def test_ai_route_prefers_registered_model(monkeypatch):
    def fake_fetch_all(sql, params=None):
        if 'FROM model_registry' in sql:
            return [
                {'name': 'gemma3', 'type': 'local', 'capabilities': ['chat', 'fallback_chat', 'summarize'], 'latency_profile': 'medium', 'metadata_json': {'default': True, 'modes': ['deterministic', 'creative'], 'fallback_models': ['gemma3-fallback']}},
                {'name': 'gemma3-fallback', 'type': 'local', 'capabilities': ['chat', 'fallback_chat'], 'latency_profile': 'medium', 'metadata_json': {'modes': ['deterministic']}},
            ]
        if 'FROM prompt_registry' in sql:
            return [
                {'name': 'fallback_chat', 'version': 'phase3.v1', 'template': 'Be grounded.', 'model_compatibility': ['gemma3'], 'mode': 'deterministic', 'updated_at': None},
            ]
        return []

    monkeypatch.setattr(main_mod, 'fetch_all', fake_fetch_all)
    resp = client.post('/ai/route', json={'tenant_id': 'default', 'action_type': 'fallback_chat', 'generation_mode': 'deterministic'})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload['selected_model'] == 'gemma3'
    assert payload['fallback_models'] == ['gemma3-fallback']
    assert payload['prompt_name'] == 'fallback_chat'



def test_ai_generate_uses_fallback_model(monkeypatch):
    monkeypatch.setattr(main_mod, '_resolve_ai_route', lambda tenant_id, action_type, prompt_version=None, generation_mode='deterministic', preferred_model=None, fallback_models=None: {
        'selected_model': 'bad-model',
        'fallback_models': ['good-model'],
        'attempted_models': ['bad-model', 'good-model'],
        'prompt_name': 'fallback_chat',
        'prompt_version': 'phase3.v1',
        'prompt_template': 'Stay grounded.',
        'prompt_mode': 'deterministic',
        'route_reason': 'test_route',
        'source': 'db',
        'available_models': ['bad-model', 'good-model'],
        'available_prompts': ['fallback_chat:phase3.v1'],
    })

    calls = []

    def fake_generate(prompt, system_prompt=None, format_schema=None, model=None):
        calls.append(model)
        if model == 'bad-model':
            raise main_mod.OllamaError('AI_UNAVAILABLE', 'bad model unavailable')
        return 'final answer', 42

    monkeypatch.setattr(main_mod.ollama, 'generate', fake_generate)
    monkeypatch.setattr(main_mod, '_store_ai_artifact', lambda *args, **kwargs: 'artifact-1')
    monkeypatch.setattr(main_mod, '_record_ai_route_run', lambda *args, **kwargs: None)
    monkeypatch.setattr(main_mod, 'write_audit', lambda *args, **kwargs: None)

    resp = client.post('/ai/generate', json={'tenant_id': 'default', 'actor_id': 'operator', 'prompt': 'hello', 'action_type': 'fallback_chat', 'generation_mode': 'deterministic'})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload['model'] == 'good-model'
    assert payload['fallback_used'] is True
    assert payload['route_reason'] == 'test_route'
    assert calls == ['bad-model', 'good-model']



def test_jobs_status_uses_request_tenant_scope(monkeypatch):
    def fake_fetch_one(sql, params=None):
        if 'FROM jobs WHERE job_id=%s AND tenant_id=%s' in sql:
            job_id, tenant_id = params
            if tenant_id == 'tenant-b':
                return {'job_id': job_id, 'tenant_id': tenant_id, 'status': 'completed', 'retry_count': 0, 'max_retries': 3, 'result': {'tenant_id': tenant_id}, 'last_error': None}
            return None
        if 'FROM jobs WHERE job_id=%s' in sql:
            job_id = params[0]
            return {'job_id': job_id, 'tenant_id': 'default', 'status': 'completed', 'retry_count': 0, 'max_retries': 3, 'result': {'tenant_id': 'default'}, 'last_error': None}
        return {'c': 0}

    monkeypatch.setattr(main_mod, 'fetch_one', fake_fetch_one)
    resp = client.get('/jobs/status/job-1?tenant_id=default', headers={'x-tenant-id': 'tenant-b'})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload['result']['tenant_id'] == 'tenant-b'


def test_rag_document_ingest_endpoint(monkeypatch):
    monkeypatch.setattr(main_mod, 'ingest_document', lambda tenant_id, actor_id, source_ref, title, body, metadata, mime_type, embedding_model: ('doc-1', 3, 'tracked_embeddings', 'embeddinggemma'))
    resp = client.post('/rag/documents/ingest', json={'tenant_id': 'default', 'actor_id': 'operator', 'source_ref': 'docs:1', 'title': 'Doc 1', 'body': 'body', 'mime_type': 'text/plain', 'metadata': {'classification': 'internal'}})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload['document_id'] == 'doc-1'
    assert payload['chunks_created'] == 3
    assert payload['embedding_model'] == 'embeddinggemma'



def test_rag_governance_endpoint(monkeypatch):
    monkeypatch.setattr(main_mod, '_build_rag_governance_report', lambda tenant_id='default': {
        'status': 'ok',
        'tenant_id': tenant_id,
        'document_count': 2,
        'chunk_count': 7,
        'embedding_version_count': 7,
        'recent_documents': [{'document_id': 'doc-1', 'source_ref': 'docs:1', 'title': 'Doc 1'}],
        'latest_embedding_models': [{'embedding_model': 'embeddinggemma', 'chunk_count': 7}],
    })
    resp = client.get('/rag/governance?tenant_id=default')
    assert resp.status_code == 200
    payload = resp.json()
    assert payload['document_count'] == 2
    assert payload['latest_embedding_models'][0]['embedding_model'] == 'embeddinggemma'


def test_rag_governance_uses_request_tenant_scope(monkeypatch):
    seen = []

    def fake_build_rag_governance_report(tenant_id='default'):
        seen.append(tenant_id)
        return {
            'status': 'ok',
            'tenant_id': tenant_id,
            'document_count': 1,
            'chunk_count': 2,
            'embedding_version_count': 1,
            'recent_documents': [{'document_id': 'doc-tenant', 'source_ref': f'docs:{tenant_id}', 'title': tenant_id}],
            'latest_embedding_models': [{'embedding_model': 'embeddinggemma', 'chunk_count': 2}],
        }

    monkeypatch.setattr(main_mod, '_build_rag_governance_report', fake_build_rag_governance_report)
    resp = client.get('/rag/governance?tenant_id=default', headers={'x-tenant-id': 'tenant-b'})
    assert resp.status_code == 200
    assert resp.json()['tenant_id'] == 'tenant-b'
    assert seen == ['tenant-b']
