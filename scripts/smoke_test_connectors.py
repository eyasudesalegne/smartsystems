from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SERVICE_DIR = ROOT / 'service'
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def ensure_ok(method: str, path: str, json: dict | None = None) -> dict:
    response = client.request(method, path, json=json)
    response.raise_for_status()
    payload = response.json()
    assert payload.get('status') in {'ok', 'placeholder_bridge'}
    return payload


def main() -> None:
    catalog = ensure_ok('GET', '/connectors/catalog')
    assert catalog['count'] >= 14

    sync = ensure_ok('POST', '/connectors/sync-registry', {'tenant_id': 'default'})
    assert sync['synced_count'] >= 14

    prepared = ensure_ok('POST', '/connectors/prepare', {'service_name': 'pubmed', 'operation_id': 'search'})
    assert prepared['prepared']['service_name'] == 'pubmed'

    draft = ensure_ok('POST', '/connectors/workflow-draft', {'service_name': 'pubmed', 'operation_id': 'search'})
    assert draft['workflow']['name']

    smoke = ensure_ok('POST', '/connectors/smoke-test', {'service_name': 'drawio', 'operation_id': 'build_xml_artifact', 'dry_run': True})
    assert smoke['service_name'] == 'drawio'

    live_drawio = ensure_ok(
        'POST',
        '/connectors/execute-live',
        {
            'service_name': 'drawio',
            'operation_id': 'build_xml_artifact',
            'body': {
                'title': 'Connector Smoke Diagram',
                'nodes': [{'id': 'n1', 'label': 'Start'}, {'id': 'n2', 'label': 'Done'}],
                'edges': [{'source': 'n1', 'target': 'n2', 'label': 'flows'}],
            },
        },
    )
    assert live_drawio['service_name'] == 'drawio'
    assert live_drawio['artifact_path'].endswith('.drawio')
    assert live_drawio['normalized']['artifact_kind'] == 'drawio_xml'

    live_mermaid = ensure_ok(
        'POST',
        '/connectors/execute-live',
        {
            'service_name': 'mermaid',
            'operation_id': 'build_mermaid_artifact',
            'body': {'diagram': 'flowchart TD\nA-->B'},
        },
    )
    assert live_mermaid['service_name'] == 'mermaid'
    assert live_mermaid['artifact_path'].endswith('.mmd')
    assert live_mermaid['normalized']['artifact_kind'] == 'mermaid_source'

    print('connector smoke test ok')


if __name__ == '__main__':
    main()
