from fastapi.testclient import TestClient

import app.main as main_mod
from app.main import app

client = TestClient(app)


def test_tenant_context_endpoint_with_auth(monkeypatch):
    monkeypatch.setattr(main_mod.settings, 'auth_required', True)
    try:
        monkeypatch.setattr(main_mod, 'build_tenant_context_report', lambda requested_tenant_id='default', actor_id='admin', role='admin', identity_tenant_id='default': {
            'status': 'ok',
            'tenant_id': requested_tenant_id,
            'requested_tenant_id': requested_tenant_id,
            'effective_tenant_id': requested_tenant_id,
            'actor_id': actor_id,
            'role': role,
            'identity_tenant_id': identity_tenant_id,
            'strict_enforcement': False,
            'admin_override_enabled': True,
            'has_access': True,
            'resolution_mode': 'override' if requested_tenant_id != identity_tenant_id else 'identity',
            'membership_count': 2,
            'memberships': [{'tenant_id': 'default'}, {'tenant_id': requested_tenant_id}],
            'next_actions': ['Tenant context is ready.'],
        })
        token = client.post('/auth/token', json={'username': 'admin', 'tenant_id': 'default'}).json()['access_token']
        resp = client.get('/tenants/context?tenant_id=tenant-b', headers={'Authorization': f'Bearer {token}', 'x-tenant-id': 'tenant-b'})
        assert resp.status_code == 200
        payload = resp.json()
        assert payload['effective_tenant_id'] == 'tenant-b'
        assert payload['membership_count'] == 2
    finally:
        monkeypatch.setattr(main_mod.settings, 'auth_required', False)


def test_tenant_create_and_membership_endpoints(monkeypatch):
    monkeypatch.setattr(main_mod, 'ensure_tenant_exists', lambda tenant_id, tenant_name=None, created_by=None: {'tenant_id': tenant_id, 'tenant_name': tenant_name or tenant_id.title(), 'created_by': created_by})
    monkeypatch.setattr(main_mod, 'upsert_tenant_membership', lambda actor_id, tenant_id, role_name='viewer', created_by=None, username=None, display_name=None, is_default=False, is_active=True, metadata_json=None: {
        'tenant_id': tenant_id,
        'tenant_name': tenant_id.title(),
        'actor_id': actor_id,
        'role_name': role_name,
        'is_default': is_default,
        'is_active': is_active,
        'created_by': created_by,
        'metadata_json': metadata_json or {},
    })

    resp = client.post('/tenants/create', json={'tenant_id': 'tenant-x', 'tenant_name': 'Tenant X', 'created_by': 'admin'})
    assert resp.status_code == 200
    assert resp.json()['tenant_id'] == 'tenant-x'

    resp = client.post('/tenants/membership', json={'tenant_id': 'tenant-x', 'actor_id': 'operator', 'role_name': 'operator', 'created_by': 'admin', 'is_default': False, 'metadata_json': {'source': 'test'}})
    assert resp.status_code == 200
    assert resp.json()['membership']['actor_id'] == 'operator'
    assert resp.json()['membership']['role_name'] == 'operator'


def test_admin_tenants_summary(monkeypatch):
    monkeypatch.setattr(main_mod, 'list_tenants_summary', lambda tenant_id=None: {'tenant_count': 2, 'tenants': [{'tenant_id': tenant_id or 'default'}, {'tenant_id': 'tenant-x'}]})
    resp = client.get('/admin/tenants?tenant_id=default')
    assert resp.status_code == 200
    payload = resp.json()['summary']
    assert payload['tenant_count'] == 2
    assert payload['tenants'][1]['tenant_id'] == 'tenant-x'


def test_admin_tenants_uses_request_tenant_scope(monkeypatch):
    seen = []

    def fake_list_tenants_summary(tenant_id=None):
        seen.append(tenant_id)
        return {'tenant_count': 1, 'tenants': [{'tenant_id': tenant_id}]}

    monkeypatch.setattr(main_mod, 'list_tenants_summary', fake_list_tenants_summary)
    resp = client.get('/admin/tenants?tenant_id=default', headers={'x-tenant-id': 'tenant-b'})
    assert resp.status_code == 200
    payload = resp.json()['summary']
    assert payload['tenant_id'] == 'tenant-b'
    assert payload['tenants'][0]['tenant_id'] == 'tenant-b'
    assert seen == ['tenant-b']


def test_tenant_policy_and_enforcement_report_endpoints(monkeypatch):
    monkeypatch.setattr(main_mod, 'upsert_tenant_route_policy', lambda tenant_id, route_prefix, resource_type, strict_mode='inherit', require_membership=True, allow_admin_override=True, allow_service_account_override=False, updated_by=None, metadata_json=None: {
        'tenant_id': tenant_id,
        'route_prefix': route_prefix,
        'resource_type': resource_type,
        'strict_mode': strict_mode,
        'require_membership': require_membership,
        'allow_admin_override': allow_admin_override,
        'allow_service_account_override': allow_service_account_override,
        'metadata_json': metadata_json or {},
        'source': 'db',
        'updated_by': updated_by,
    })
    monkeypatch.setattr(main_mod, 'build_tenant_enforcement_report', lambda tenant_id='default', route='/connectors/catalog', method='GET', actor_id='anonymous', role='viewer', identity_tenant_id='default', requested_tenant_id=None: {
        'status': 'ok',
        'tenant_id': requested_tenant_id or tenant_id,
        'requested_tenant_id': requested_tenant_id or tenant_id,
        'effective_tenant_id': requested_tenant_id or tenant_id,
        'actor_id': actor_id,
        'role': role,
        'identity_tenant_id': identity_tenant_id,
        'route': route,
        'method': method,
        'decision': 'allow',
        'reason': 'active_membership',
        'strict_enforcement': True,
        'policy': {
            'tenant_id': tenant_id,
            'route_prefix': '/secrets/',
            'resource_type': 'secrets',
            'strict_mode': 'enforce',
            'require_membership': True,
            'allow_admin_override': False,
            'allow_service_account_override': False,
            'metadata_json': {'notes': 'strict'},
            'source': 'db',
        },
        'membership_count': 1,
        'memberships': [{'tenant_id': requested_tenant_id or tenant_id, 'role_name': 'admin'}],
        'accessible_tenants': [requested_tenant_id or tenant_id],
        'policy_count': 1,
        'policies': [{
            'tenant_id': tenant_id,
            'route_prefix': '/secrets/',
            'resource_type': 'secrets',
            'strict_mode': 'enforce',
            'require_membership': True,
            'allow_admin_override': False,
            'allow_service_account_override': False,
            'metadata_json': {'notes': 'strict'},
            'source': 'db',
        }],
        'next_actions': ['ok'],
    })

    resp = client.post('/tenants/policy', json={
        'tenant_id': 'tenant-x',
        'route_prefix': '/secrets/',
        'resource_type': 'secrets',
        'strict_mode': 'enforce',
        'require_membership': True,
        'allow_admin_override': False,
    })
    assert resp.status_code == 200
    assert resp.json()['policy']['route_prefix'] == '/secrets/'
    assert resp.json()['policy']['allow_admin_override'] is False

    resp = client.post('/tenants/enforcement-report', json={
        'tenant_id': 'tenant-x',
        'requested_tenant_id': 'tenant-x',
        'route': '/secrets/list',
        'method': 'POST',
        'actor_id': 'admin',
        'role': 'admin',
        'identity_tenant_id': 'default',
    })
    assert resp.status_code == 200
    payload = resp.json()
    assert payload['decision'] == 'allow'
    assert payload['policy']['resource_type'] == 'secrets'


def test_admin_tenant_enforcement_summary(monkeypatch):
    monkeypatch.setattr(main_mod, 'list_tenant_route_policies', lambda tenant_id='default': [{
        'tenant_id': tenant_id,
        'route_prefix': '/secrets/',
        'resource_type': 'secrets',
        'strict_mode': 'enforce',
        'require_membership': True,
        'allow_admin_override': False,
        'allow_service_account_override': False,
        'metadata_json': {'notes': 'strict'},
        'source': 'db',
    }])
    resp = client.get('/admin/tenant-enforcement?tenant_id=default')
    assert resp.status_code == 200
    payload = resp.json()['summary']
    assert payload['policy_count'] == 1
    assert payload['policies'][0]['resource_type'] == 'secrets'


def test_cross_tenant_secret_access_denied_when_policy_disallows_admin_override(monkeypatch):
    from app.auth import Identity
    from app.tenant import enforce_tenant_route_policy

    monkeypatch.setattr(main_mod.settings, 'strict_tenant_enforcement', True)
    monkeypatch.setattr(main_mod.settings, 'tenant_allow_admin_override', True)
    try:
        identity = Identity(user_id='admin', tenant_id='default', role='admin', scopes=[], subject='admin')
        try:
            enforce_tenant_route_policy('tenant-b', 'tenant-b', '/secrets/list', 'POST', identity)
            assert False, 'expected tenant route policy denial'
        except Exception as exc:
            assert getattr(exc, 'status_code', None) == 403
            assert exc.detail['code'] == 'TENANT_ROUTE_POLICY_DENIED'
    finally:
        monkeypatch.setattr(main_mod.settings, 'strict_tenant_enforcement', False)



def test_tenant_row_policy_and_isolation_report_endpoints(monkeypatch):
    monkeypatch.setattr(main_mod, 'upsert_tenant_row_policy', lambda tenant_id, resource_table, strict_mode='inherit', require_tenant_match=True, allow_admin_override=True, allow_service_account_override=False, allow_global_rows=False, updated_by=None, metadata_json=None: {
        'tenant_id': tenant_id,
        'resource_table': resource_table,
        'strict_mode': strict_mode,
        'require_tenant_match': require_tenant_match,
        'allow_admin_override': allow_admin_override,
        'allow_service_account_override': allow_service_account_override,
        'allow_global_rows': allow_global_rows,
        'metadata_json': metadata_json or {},
        'source': 'db',
        'updated_by': updated_by,
    })
    monkeypatch.setattr(main_mod, 'build_tenant_row_isolation_report', lambda tenant_id='default', resource_table='jobs', action='read', actor_id='anonymous', role='viewer', identity_tenant_id='default', requested_tenant_id=None: {
        'status': 'ok',
        'tenant_id': requested_tenant_id or tenant_id,
        'requested_tenant_id': requested_tenant_id or tenant_id,
        'effective_tenant_id': requested_tenant_id or tenant_id,
        'actor_id': actor_id,
        'role': role,
        'identity_tenant_id': identity_tenant_id,
        'resource_table': resource_table,
        'action': action,
        'decision': 'allow',
        'reason': 'active_membership',
        'strict_enforcement': True,
        'policy': {
            'tenant_id': tenant_id,
            'resource_table': resource_table,
            'strict_mode': 'enforce',
            'require_tenant_match': True,
            'allow_admin_override': False,
            'allow_service_account_override': False,
            'allow_global_rows': False,
            'metadata_json': {'notes': 'strict'},
            'source': 'db',
        },
        'membership_count': 1,
        'memberships': [{'tenant_id': requested_tenant_id or tenant_id, 'role_name': 'admin'}],
        'accessible_tenants': [requested_tenant_id or tenant_id],
        'policy_count': 1,
        'policies': [{
            'tenant_id': tenant_id,
            'resource_table': resource_table,
            'strict_mode': 'enforce',
            'require_tenant_match': True,
            'allow_admin_override': False,
            'allow_service_account_override': False,
            'allow_global_rows': False,
            'metadata_json': {'notes': 'strict'},
            'source': 'db',
        }],
        'next_actions': ['ok'],
    })

    resp = client.post('/tenants/row-policy', json={
        'tenant_id': 'tenant-x',
        'resource_table': 'jobs',
        'strict_mode': 'enforce',
        'require_tenant_match': True,
        'allow_admin_override': False,
        'allow_global_rows': False,
    })
    assert resp.status_code == 200
    assert resp.json()['policy']['resource_table'] == 'jobs'
    assert resp.json()['policy']['allow_admin_override'] is False

    resp = client.post('/tenants/row-isolation-report', json={
        'tenant_id': 'tenant-x',
        'requested_tenant_id': 'tenant-x',
        'resource_table': 'jobs',
        'action': 'read',
        'actor_id': 'admin',
        'role': 'admin',
        'identity_tenant_id': 'default',
    })
    assert resp.status_code == 200
    payload = resp.json()
    assert payload['decision'] == 'allow'
    assert payload['policy']['resource_table'] == 'jobs'


def test_admin_tenant_isolation_summary(monkeypatch):
    monkeypatch.setattr(main_mod, 'list_tenant_row_policies', lambda tenant_id='default': [{
        'tenant_id': tenant_id,
        'resource_table': 'jobs',
        'strict_mode': 'enforce',
        'require_tenant_match': True,
        'allow_admin_override': False,
        'allow_service_account_override': False,
        'allow_global_rows': False,
        'metadata_json': {'notes': 'strict'},
        'source': 'db',
    }])
    resp = client.get('/admin/tenant-isolation?tenant_id=default')
    assert resp.status_code == 200
    payload = resp.json()['summary']
    assert payload['policy_count'] == 1
    assert payload['policies'][0]['resource_table'] == 'jobs'



def test_tenant_query_scope_report_endpoint(monkeypatch):
    monkeypatch.setattr(main_mod, 'build_tenant_query_scope_report', lambda tenant_id='default', resource_table='release_publications', route='/release/publications', action='read', actor_id='anonymous', role='viewer', identity_tenant_id='default', requested_tenant_id=None: {
        'status': 'ok',
        'tenant_id': tenant_id,
        'requested_tenant_id': requested_tenant_id or tenant_id,
        'effective_tenant_id': tenant_id,
        'actor_id': actor_id,
        'role': role,
        'identity_tenant_id': identity_tenant_id,
        'resource_table': resource_table,
        'route': route,
        'action': action,
        'decision': 'allow',
        'reason': 'same_tenant',
        'strict_enforcement': True,
        'policy': {
            'tenant_id': tenant_id,
            'resource_table': resource_table,
            'strict_mode': 'enforce',
            'require_tenant_match': True,
            'allow_admin_override': False,
            'allow_service_account_override': False,
            'allow_global_rows': False,
            'metadata_json': {'notes': 'strict'},
            'source': 'db',
        },
        'visible_tenant_ids': [tenant_id],
        'query_scope_sql': "WHERE tenant_id IN ('default')",
        'records_before': 0,
        'records_after': 0,
        'filtered_count': 0,
        'policy_count': 1,
        'policies': [{
            'tenant_id': tenant_id,
            'resource_table': resource_table,
            'strict_mode': 'enforce',
            'require_tenant_match': True,
            'allow_admin_override': False,
            'allow_service_account_override': False,
            'allow_global_rows': False,
            'metadata_json': {'notes': 'strict'},
            'source': 'db',
        }],
        'next_actions': ['ok'],
    })
    resp = client.post('/tenants/query-scope-report', json={
        'tenant_id': 'default',
        'requested_tenant_id': 'default',
        'resource_table': 'release_publications',
        'route': '/release/publications',
        'action': 'read',
        'actor_id': 'admin',
        'role': 'admin',
        'identity_tenant_id': 'default',
    })
    assert resp.status_code == 200
    payload = resp.json()
    assert payload['decision'] == 'allow'
    assert payload['visible_tenant_ids'] == ['default']


def test_release_publications_uses_request_tenant_scope(monkeypatch):
    monkeypatch.setattr(main_mod, '_list_release_publications', lambda tenant_id='default', limit=20: [
        {'tenant_id': 'default', 'release_version': '1.0.0', 'publication_status': 'published', 'package_path': 'a.zip', 'created_at': 'now'},
        {'tenant_id': 'tenant-b', 'release_version': '1.0.1', 'publication_status': 'published', 'package_path': 'b.zip', 'created_at': 'now'},
    ])
    resp = client.get('/release/publications?tenant_id=default', headers={'x-tenant-id': 'tenant-b'})
    assert resp.status_code == 200
    items = resp.json()['items']
    assert len(items) == 1
    assert items[0]['tenant_id'] == 'tenant-b'


def test_tenant_query_coverage_endpoints(monkeypatch):
    monkeypatch.setattr(main_mod, 'upsert_tenant_query_scope_target', lambda tenant_id, route, resource_table, action='read', strict_mode='inherit', notes=None, updated_by=None: {
        'tenant_id': tenant_id,
        'route': route,
        'resource_table': resource_table,
        'action': action,
        'strict_mode': strict_mode,
        'notes': notes,
        'source': 'db',
        'updated_by': updated_by,
    })
    monkeypatch.setattr(main_mod, 'build_tenant_query_coverage_report', lambda tenant_id='default', actor_id='anonymous', role='viewer', identity_tenant_id='default', requested_tenant_id=None: {
        'status': 'ok',
        'tenant_id': requested_tenant_id or tenant_id,
        'requested_tenant_id': requested_tenant_id or tenant_id,
        'effective_tenant_id': requested_tenant_id or tenant_id,
        'actor_id': actor_id,
        'role': role,
        'identity_tenant_id': identity_tenant_id,
        'target_count': 2,
        'covered_count': 2,
        'strict_target_count': 1,
        'targets': [{'route': '/admin/jobs', 'resource_table': 'jobs', 'decision': 'allow'}],
        'next_actions': ['ok'],
    })
    monkeypatch.setattr(main_mod, 'list_tenant_query_scope_targets', lambda tenant_id='default': [
        {'tenant_id': tenant_id, 'route': '/admin/jobs', 'resource_table': 'jobs', 'action': 'read', 'strict_mode': 'inherit', 'notes': 'jobs', 'source': 'db', 'updated_by': 'admin'}
    ])

    resp = client.post('/tenants/query-coverage-target', json={'tenant_id': 'tenant-x', 'route': '/admin/jobs', 'resource_table': 'jobs', 'action': 'read', 'strict_mode': 'inherit', 'notes': 'jobs'})
    assert resp.status_code == 200
    assert resp.json()['target']['resource_table'] == 'jobs'

    resp = client.post('/tenants/query-coverage-report', json={'tenant_id': 'tenant-x', 'requested_tenant_id': 'tenant-x', 'actor_id': 'admin', 'role': 'admin', 'identity_tenant_id': 'tenant-x'})
    assert resp.status_code == 200
    assert resp.json()['covered_count'] == 2

    resp = client.get('/admin/tenant-query-coverage?tenant_id=tenant-x')
    assert resp.status_code == 200
    payload = resp.json()['summary']
    assert payload['target_count'] == 2
    assert payload['known_target_rows'][0]['resource_table'] == 'jobs'


def test_ai_registry_reads_are_tenant_scoped(monkeypatch):
    monkeypatch.setattr(main_mod, 'fetch_all', lambda sql, params=(): [
        {'tenant_id': params[0], 'name': 'tenant-model', 'type': 'local', 'capabilities': ['chat'], 'latency_profile': 'fast'},
        {'tenant_id': 'other-tenant', 'name': 'other-model', 'type': 'local', 'capabilities': ['chat'], 'latency_profile': 'slow'},
    ])
    resp = client.get('/ai/models?tenant_id=tenant-x', headers={'x-tenant-id': 'tenant-x'})
    assert resp.status_code == 200
    items = resp.json()['items']
    assert len(items) == 1
    assert items[0]['tenant_id'] == 'tenant-x'
