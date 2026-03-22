from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SERVICE_DIR = ROOT / 'service'
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

from fastapi.testclient import TestClient
import app.main as main_mod
from app.main import app

client = TestClient(app)


def main() -> None:
    state = {'versions': {}}

    def fake_fetch_one(sql, params=None):
        if 'COALESCE(max(version), 0) AS max_version' in sql:
            versions = [key[2] for key in state['versions'].keys() if key[0] == params[0] and key[1] == params[1]]
            return {'max_version': max(versions) if versions else 0}
        if 'FROM workflow_versions WHERE tenant_id=%s AND workflow_id=%s AND version=%s' in sql:
            return state['versions'].get((params[0], params[1], params[2]))
        return {'c': 0}

    def fake_fetch_all(sql, params=None):
        if 'FROM workflow_versions WHERE tenant_id=%s AND workflow_id=%s' in sql:
            rows = [row for key, row in state['versions'].items() if key[0] == params[0] and key[1] == params[1]]
            return sorted(rows, key=lambda row: row['version'], reverse=True)
        return []

    def fake_safe_db_execute(sql, params):
        if 'INSERT INTO workflow_versions' in sql:
            tenant_id, workflow_id, version, workflow_status, definition_json = params
            import json
            state['versions'][(tenant_id, workflow_id, version)] = {
                'workflow_id': workflow_id,
                'version': version,
                'workflow_status': workflow_status,
                'definition_json': json.loads(definition_json) if isinstance(definition_json, str) else definition_json,
                'created_at': None,
                'updated_at': None,
            }
        elif "UPDATE workflow_versions SET status='approved'" in sql:
            tenant_id, workflow_id = params
            for key, row in list(state['versions'].items()):
                if key[0] == tenant_id and key[1] == workflow_id and row['workflow_status'] == 'published':
                    row['workflow_status'] = 'approved'
        elif 'UPDATE workflow_versions SET status=%s' in sql:
            workflow_status, tenant_id, workflow_id, version = params
            row = state['versions'].get((tenant_id, workflow_id, version))
            if row:
                row['workflow_status'] = workflow_status

    main_mod.fetch_one = fake_fetch_one
    main_mod.fetch_all = fake_fetch_all
    main_mod._safe_db_execute = fake_safe_db_execute

    create = client.post('/workflows/version/create', json={'tenant_id': 'default', 'workflow_id': 'wf_pubmed_search', 'version': 1, 'definition_json': {'name': 'wf_pubmed_search'}, 'status': 'tested'})
    create.raise_for_status()
    promote = client.post('/workflows/version/promote', json={'tenant_id': 'default', 'workflow_id': 'wf_pubmed_search', 'version': 1, 'status': 'published'})
    promote.raise_for_status()
    history = client.get('/workflows/version/history/wf_pubmed_search?tenant_id=default&include_definition=false')
    history.raise_for_status()
    payload = history.json()
    assert payload['workflow_id'] == 'wf_pubmed_search'
    assert payload['published_version'] == 1
    rollback = client.post('/workflows/version/rollback', json={'tenant_id': 'default', 'workflow_id': 'wf_pubmed_search', 'source_version': 1, 'new_version': 2, 'status': 'draft'})
    rollback.raise_for_status()
    assert rollback.json()['version'] == 2
    print('workflow version smoke test ok')


if __name__ == '__main__':
    main()
