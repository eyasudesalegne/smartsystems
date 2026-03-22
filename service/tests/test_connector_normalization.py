import httpx

from app.connectors import get_adapter_for


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


def test_mlflow_normalizes_experiment_list(monkeypatch):
    monkeypatch.setenv('MLFLOW_TRACKING_URI', 'https://mlflow.example.com')

    def fake_request(self, method, url, headers=None, params=None, json=None, **kwargs):
        return DummyResponse(json_data={'experiments': [{'experiment_id': '1', 'name': 'baseline'}], 'next_page_token': 'tok1'})

    monkeypatch.setattr(httpx.Client, 'request', fake_request)
    result = get_adapter_for('mlflow').execute('list_experiments')
    assert result['normalized']['items'][0]['name'] == 'baseline'
    assert result['pagination']['cursor'] == 'tok1'


def test_pubmed_normalizes_search_results(monkeypatch):
    monkeypatch.setenv('PUBMED_BASE_URL', 'https://eutils.ncbi.nlm.nih.gov')

    def fake_request(self, method, url, headers=None, params=None, json=None, **kwargs):
        return DummyResponse(json_data={'esearchresult': {'count': '2', 'idlist': ['101', '102'], 'querytranslation': 'cancer'}})

    monkeypatch.setattr(httpx.Client, 'request', fake_request)
    result = get_adapter_for('pubmed').execute('search', query={'PUBMED_TERM': 'cancer'})
    assert result['normalized']['pmids'] == ['101', '102']
    assert result['summary']['record_count'] == 2


def test_arxiv_normalizes_atom_feed(monkeypatch):
    monkeypatch.setenv('ARXIV_BASE_URL', 'https://export.arxiv.org')
    feed = '''<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
      <entry>
        <id>http://arxiv.org/abs/1234.5678v1</id>
        <updated>2026-01-01T00:00:00Z</updated>
        <published>2025-12-31T00:00:00Z</published>
        <title> Test Paper </title>
        <summary> Example summary. </summary>
        <author><name>Jane Doe</name></author>
        <arxiv:primary_category term="cs.AI"/>
      </entry>
    </feed>'''

    def fake_request(self, method, url, headers=None, params=None, json=None, **kwargs):
        return DummyResponse(text=feed, headers={'content-type': 'application/atom+xml'})

    monkeypatch.setattr(httpx.Client, 'request', fake_request)
    result = get_adapter_for('arxiv').execute('search', query={'ARXIV_QUERY': 'llm'})
    assert result['normalized']['items'][0]['title'] == 'Test Paper'
    assert result['summary']['record_count'] == 1


def test_google_drive_normalizes_file_listing(monkeypatch):
    monkeypatch.setenv('GOOGLE_DRIVE_BASE_URL', 'https://www.googleapis.com')
    monkeypatch.setenv('GOOGLE_DRIVE_ACCESS_TOKEN', 'token-123')

    def fake_request(self, method, url, headers=None, params=None, json=None, **kwargs):
        return DummyResponse(json_data={'files': [{'id': 'f1', 'name': 'paper.pdf', 'mimeType': 'application/pdf'}], 'nextPageToken': 'next-1'})

    monkeypatch.setattr(httpx.Client, 'request', fake_request)
    result = get_adapter_for('google_drive').execute('list_files', query={'GOOGLE_DRIVE_QUERY': "name contains 'paper'"})
    assert result['normalized']['items'][0]['id'] == 'f1'
    assert result['pagination']['cursor'] == 'next-1'


def test_drawio_local_artifact_returns_normalized_payload():
    result = get_adapter_for('drawio').execute(
        'build_xml_artifact',
        body={
            'title': 'System Flow',
            'nodes': [{'id': 'n1', 'label': 'Start'}, {'id': 'n2', 'label': 'Finish'}],
            'edges': [{'source': 'n1', 'target': 'n2'}],
        },
    )
    assert result['normalized']['artifact_kind'] == 'drawio_xml'
    assert result['summary']['artifact_kind'] == 'drawio_xml'
    assert result['normalized']['node_count'] == 2
    assert result['artifact_path'].endswith('.drawio')


def test_overleaf_bundle_returns_normalized_payload():
    result = get_adapter_for('overleaf').execute(
        'build_project_bundle',
        body={
            'main_document': 'main.tex',
            'files': {'main.tex': r'\documentclass{article}\begin{document}Hi\end{document}'},
        },
    )
    assert result['normalized']['artifact_kind'] == 'overleaf_bundle'
    assert result['summary']['artifact_kind'] == 'overleaf_bundle'
    assert result['normalized']['file_count'] == 1
    assert result['bundle_path'].endswith('.zip')


def test_vscode_workspace_bundle_returns_normalized_payload():
    result = get_adapter_for('vscode').execute(
        'push_workspace_stub',
        body={
            'workspace_name': 'connector-export',
            'files': {'README.md': '# Export'},
            'tasks': [{'label': 'Run validation', 'type': 'shell', 'command': 'pytest -q'}],
        },
    )
    assert result['normalized']['artifact_kind'] == 'workspace_bundle'
    assert result['summary']['artifact_kind'] == 'workspace_bundle'
    assert result['normalized']['task_count'] == 1
    assert result['bundle_path'].endswith('.zip')
