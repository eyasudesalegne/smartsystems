import json
from pathlib import Path


def test_env_example_covers_connector_specs():
    env_lines = Path('..', 'deploy', '.env.example').read_text().splitlines()
    keys = {line.split('=', 1)[0] for line in env_lines if line and not line.startswith('#') and '=' in line}
    spec_dir = Path('..', 'connectors', 'specs')
    missing = []
    for path in spec_dir.glob('*.json'):
        spec = json.loads(path.read_text())
        needed = {spec['base_url_env'], *spec.get('required_credentials', []), *spec.get('optional_credentials', [])}
        for key in sorted(needed):
            if key and key not in keys:
                missing.append((spec['service_name'], key))
    assert not missing, missing


def test_import_templates_use_canonical_connector_env_names():
    text = '\n'.join(p.read_text() for p in Path('..', 'n8n', 'import').glob('wf_ext_*.json'))
    legacy = [
        'MLFLOW_BASE_URL',
        'FIGMA_TOKEN',
        'GOOGLE_DRIVE_BEARER_TOKEN',
        'OVERLEAF_BEARER_TOKEN',
        'NOTEBOOKLM_BEARER_TOKEN',
        'CANVAS_BEARER_TOKEN',
        'ANTIGRAVITY_BEARER_TOKEN',
        'VSCODE_BEARER_TOKEN',
        'VSCODE_BASE_URL',
        'MERMAID_BASE_URL',
        'AZURE_SUBSCRIPTION_ID',
        'AZURE_RESOURCE_GROUP',
    ]
    assert not [item for item in legacy if item in text]
