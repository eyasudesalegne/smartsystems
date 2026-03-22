import base64

import httpx

from app.connectors import get_adapter_for, validate_connector_config


class DummyResponse:
    def __init__(self, status_code=200, json_data=None, text='', headers=None):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self.headers = headers or {'content-type': 'application/json'}
        self.is_success = 200 <= status_code < 300

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if not self.is_success:
            raise httpx.HTTPStatusError('error', request=httpx.Request('GET', 'http://test'), response=httpx.Response(self.status_code))


def test_google_drive_validate_allows_direct_access_token(monkeypatch):
    monkeypatch.setenv('GOOGLE_DRIVE_ACCESS_TOKEN', 'token-123')
    result = validate_connector_config('google_drive')
    assert result['configured'] is True
    assert result['missing_credentials'] == []


def test_mlflow_builds_basic_auth_when_username_password_present(monkeypatch):
    monkeypatch.setenv('MLFLOW_USERNAME', 'user1')
    monkeypatch.setenv('MLFLOW_PASSWORD', 'pass1')
    adapter = get_adapter_for('mlflow')
    headers = adapter.build_headers(resolve_env=True)
    expected = 'Basic ' + base64.b64encode(b'user1:pass1').decode()
    assert headers['Authorization'] == expected


def test_pubmed_prepare_includes_optional_query_auth_placeholders():
    adapter = get_adapter_for('pubmed')
    prepared = adapter.prepare('search', resolve_env=False)
    assert prepared['query']['email'] == '{$env.PUBMED_EMAIL}'
    assert prepared['query']['api_key'] == '{$env.PUBMED_API_KEY}'


def test_google_drive_execute_uses_refresh_token_exchange(monkeypatch):
    monkeypatch.setenv('GOOGLE_DRIVE_BASE_URL', 'https://www.googleapis.com')
    monkeypatch.setenv('GOOGLE_DRIVE_CLIENT_ID', 'cid')
    monkeypatch.setenv('GOOGLE_DRIVE_CLIENT_SECRET', 'csecret')
    monkeypatch.setenv('GOOGLE_DRIVE_REFRESH_TOKEN', 'refresh')

    calls = []

    def fake_post(self, url, data=None, **kwargs):
        calls.append(('post', url, data))
        return DummyResponse(json_data={'access_token': 'drive-access'})

    def fake_request(self, method, url, headers=None, params=None, json=None, **kwargs):
        calls.append(('request', method, url, headers, params, json))
        return DummyResponse(json_data={'files': []})

    monkeypatch.setattr(httpx.Client, 'post', fake_post)
    monkeypatch.setattr(httpx.Client, 'request', fake_request)

    adapter = get_adapter_for('google_drive')
    result = adapter.execute('list_files', query={'GOOGLE_DRIVE_QUERY': "name contains 'paper'"})

    assert result['status'] == 'ok'
    assert calls[0][0] == 'post'
    assert 'oauth2.googleapis.com/token' in calls[0][1]
    assert calls[1][3]['Authorization'] == 'Bearer drive-access'


def test_azure_ml_execute_uses_client_credentials(monkeypatch):
    monkeypatch.setenv('AZURE_ML_BASE_URL', 'https://workspace.api.azureml.ms')
    monkeypatch.setenv('AZURE_ML_TENANT_ID', 'tenant')
    monkeypatch.setenv('AZURE_ML_CLIENT_ID', 'client')
    monkeypatch.setenv('AZURE_ML_CLIENT_SECRET', 'secret')

    calls = []

    def fake_post(self, url, data=None, **kwargs):
        calls.append(('post', url, data))
        return DummyResponse(json_data={'access_token': 'azure-access'})

    def fake_request(self, method, url, headers=None, params=None, json=None, **kwargs):
        calls.append(('request', method, url, headers, params, json))
        return DummyResponse(json_data={'value': []})

    monkeypatch.setattr(httpx.Client, 'post', fake_post)
    monkeypatch.setattr(httpx.Client, 'request', fake_request)

    adapter = get_adapter_for('azure_ml')
    result = adapter.execute('list_jobs')

    assert result['status'] == 'ok'
    assert 'login.microsoftonline.com/tenant/oauth2/v2.0/token' in calls[0][1]
    assert calls[1][3]['Authorization'] == 'Bearer azure-access'
