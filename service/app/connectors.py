from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
from typing import Any

from .adapters import get_adapter

SPEC_DIR = Path(__file__).resolve().parents[2] / 'connectors' / 'specs'
ALIASES = {
    'draw_io': 'drawio',
    'google drive': 'google_drive',
    'azure ml': 'azure_ml',
    'vs code': 'vscode',
}


def _slug(name: str) -> str:
    return (name or '').strip().lower().replace('-', '_').replace(' ', '_')


def _load_registry() -> dict[str, dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    for path in sorted(SPEC_DIR.glob('*.json')):
        spec = json.loads(path.read_text())
        items[spec['service_name']] = spec
    for alias, target in ALIASES.items():
        if target in items:
            items[alias] = items[target]
    return items


CONNECTOR_REGISTRY = _load_registry()

N8N_IMPORT_DIR = Path(__file__).resolve().parents[2] / 'n8n' / 'import'

WORKFLOW_MANIFEST_HINTS = {
    'mlflow': {
        'primary_files': ['wf_mlflow_run_lookup.json'],
        'operation_files': {'get_run': ['wf_mlflow_run_lookup.json']},
    },
    'azure_ml': {
        'primary_files': ['wf_azure_ml_job_lookup.json'],
        'operation_files': {'get_job': ['wf_azure_ml_job_lookup.json']},
    },
    'drawio': {
        'primary_files': ['wf_ext_drawio_build_xml_artifact.json'],
        'operation_files': {'build_xml_artifact': ['wf_ext_drawio_build_xml_artifact.json']},
    },
    'figma': {
        'primary_files': ['wf_figma_file_inspect.json', 'wf_ext_figma_get_file.json'],
        'operation_files': {'get_file': ['wf_figma_file_inspect.json', 'wf_ext_figma_get_file.json']},
    },
    'mermaid': {
        'primary_files': ['wf_ext_mermaid_build_mermaid_artifact.json'],
        'operation_files': {'build_mermaid_artifact': ['wf_ext_mermaid_build_mermaid_artifact.json']},
    },
    'canvas': {
        'primary_files': ['wf_ext_canvas_sync_artifact_stub.json'],
        'operation_files': {'list_courses': ['wf_ext_canvas_sync_artifact_stub.json']},
        'notes': 'Packaged workflow is a bridge stub; use workflow-draft for list_courses/get_course/list_modules variants.',
    },
    'kaggle': {
        'primary_files': ['wf_kaggle_dataset_lookup.json', 'wf_ext_kaggle_list_datasets.json'],
        'operation_files': {'list_datasets': ['wf_kaggle_dataset_lookup.json', 'wf_ext_kaggle_list_datasets.json']},
    },
    'notebooklm': {
        'primary_files': ['wf_ext_notebooklm_sync_bundle_stub.json'],
        'operation_files': {'list_recent': ['wf_ext_notebooklm_sync_bundle_stub.json']},
        'notes': 'Packaged workflow is a notebook-management bridge stub; use workflow-draft for other enterprise operations.',
    },
    'google_drive': {
        'primary_files': ['wf_google_drive_fetch.json', 'wf_ext_google_drive_list_files.json'],
        'operation_files': {
            'get_file': ['wf_google_drive_fetch.json'],
            'list_files': ['wf_ext_google_drive_list_files.json'],
        },
    },
    'overleaf': {
        'primary_files': ['wf_overleaf_project_bridge.json', 'wf_ext_overleaf_sync_project_stub.json'],
        'operation_files': {'build_project_bundle': ['wf_overleaf_project_bridge.json', 'wf_ext_overleaf_sync_project_stub.json']},
        'notes': 'Packaged workflows focus on bundle/import bridge behavior rather than undocumented live project APIs.',
    },
    'pubmed': {
        'primary_files': ['wf_pubmed_search.json', 'wf_ext_pubmed_search.json'],
        'operation_files': {'search': ['wf_pubmed_search.json', 'wf_ext_pubmed_search.json']},
    },
    'arxiv': {
        'primary_files': ['wf_arxiv_search.json', 'wf_ext_arxiv_search.json'],
        'operation_files': {'search': ['wf_arxiv_search.json', 'wf_ext_arxiv_search.json']},
    },
    'antigravity': {
        'primary_files': ['wf_ext_antigravity_push_workspace_stub.json'],
        'operation_files': {'push_workspace_stub': ['wf_ext_antigravity_push_workspace_stub.json']},
    },
    'vscode': {
        'primary_files': ['wf_vscode_local_bridge.json', 'wf_ext_vscode_push_workspace_stub.json'],
        'operation_files': {'push_workspace_stub': ['wf_vscode_local_bridge.json', 'wf_ext_vscode_push_workspace_stub.json']},
    },
}


def normalize_service_name(service_name: str) -> str:
    key = _slug(service_name)
    if key in CONNECTOR_REGISTRY:
        return key
    if service_name in CONNECTOR_REGISTRY:
        return service_name
    raise KeyError(service_name)


def list_catalog() -> list[dict[str, Any]]:
    seen = set()
    rows = []
    for key, spec in CONNECTOR_REGISTRY.items():
        canonical = spec['service_name']
        if canonical in seen:
            continue
        seen.add(canonical)
        rows.append(get_connector(canonical))
    return sorted(rows, key=lambda row: row['service_name'])


def get_connector(service_name: str) -> dict[str, Any]:
    key = normalize_service_name(service_name)
    return deepcopy(CONNECTOR_REGISTRY[key])


def get_adapter_for(service_name: str):
    spec = get_connector(service_name)
    return get_adapter(spec)




def _existing_import_workflows() -> set[str]:
    return {path.name for path in N8N_IMPORT_DIR.glob('*.json')}


def _ext_operation_map() -> dict[tuple[str, str], list[str]]:
    mapping: dict[tuple[str, str], list[str]] = {}
    service_names = sorted({spec['service_name'] for spec in CONNECTOR_REGISTRY.values()}, key=len, reverse=True)
    for path in N8N_IMPORT_DIR.glob('wf_ext_*.json'):
        stem = path.stem[len('wf_ext_'):]
        matched_service = None
        for service_name in service_names:
            prefix = service_name + '_'
            if stem.startswith(prefix):
                matched_service = service_name
                op = stem[len(prefix):]
                mapping.setdefault((service_name, op), []).append(path.name)
                break
        if matched_service is None:
            continue
    return mapping


def build_workflow_manifest(service_names: list[str] | None = None) -> list[dict[str, Any]]:
    allowed = {normalize_service_name(name) for name in (service_names or []) if name}
    ext_map = _ext_operation_map()
    existing = _existing_import_workflows()
    items: list[dict[str, Any]] = []
    for spec in list_catalog():
        service_name = spec['service_name']
        if allowed and service_name not in allowed:
            continue
        hints = WORKFLOW_MANIFEST_HINTS.get(service_name, {})
        operations = [op['operation_id'] for op in spec.get('supported_operations', [])]
        operation_files: dict[str, list[str]] = {}
        for operation_id in operations:
            files = []
            files.extend(ext_map.get((service_name, operation_id), []))
            files.extend(hints.get('operation_files', {}).get(operation_id, []))
            uniq = []
            for item in files:
                if item in existing and item not in uniq:
                    uniq.append(item)
            if uniq:
                operation_files[operation_id] = uniq
        primary_files = []
        for item in hints.get('primary_files', []):
            if item in existing and item not in primary_files:
                primary_files.append(item)
        for files in operation_files.values():
            for item in files:
                if item not in primary_files:
                    primary_files.append(item)
        packaged_operations = [op for op in operations if op in operation_files]
        unpackaged_operations = [op for op in operations if op not in operation_files]
        recommended_operation_id = operations[0] if operations else None
        recommended_import_workflow = primary_files[0] if primary_files else None
        items.append({
            'service_name': service_name,
            'display_name': spec.get('display_name', service_name),
            'implementation_status': spec.get('implementation_status', 'docs_only'),
            'integration_mode': spec.get('integration_mode', 'manual_bridge'),
            'supported_operations': operations,
            'draftable_operations': operations,
            'packaged_operations': packaged_operations,
            'unpackaged_operations': unpackaged_operations,
            'packaged_workflows': primary_files,
            'operation_workflow_files': operation_files,
            'packaged_workflow_count': len(primary_files),
            'recommended_import_workflow': recommended_import_workflow,
            'recommended_draft_operation_id': recommended_operation_id,
            'notes': hints.get('notes', ''),
        })
    return sorted(items, key=lambda row: row['service_name'])

def catalog_rows_for_sync(tenant_id: str = 'default') -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in list_catalog():
        rows.append({
            'tenant_id': tenant_id,
            'service_name': spec['service_name'],
            'display_name': spec['display_name'],
            'category': spec['category'],
            'integration_mode': spec['integration_mode'],
            'auth_type': spec['auth_type'],
            'base_url_env': spec['base_url_env'],
            'required_credentials': spec.get('required_credentials', []),
            'optional_credentials': spec.get('optional_credentials', []),
            'implementation_status': spec.get('implementation_status') or spec.get('status') or 'docs_only',
            'notes': spec.get('notes') or spec.get('rate_limit_retry_notes', ''),
            'docs_reference': spec.get('docs_reference'),
        })
    return rows


def prepare_connector_request(service_name: str, operation_id: str | None = None, body: dict[str, Any] | None = None, query: dict[str, Any] | None = None, headers: dict[str, Any] | None = None, resolve_env: bool = False) -> dict[str, Any]:
    return get_adapter_for(service_name).prepare(operation_id=operation_id, body=body, query=query, headers=headers, resolve_env=resolve_env)


def build_codex_prompt(service_name: str, operation_id: str | None = None) -> str:
    spec = get_connector(service_name)
    prepared = prepare_connector_request(service_name, operation_id)
    return (
        f"Generate an importable n8n workflow JSON for {spec['display_name']} using the backend connector bridge. "
        f"Call POST /connectors/execute-live with service_name={spec['service_name']} and operation_id={prepared['operation_id']}. "
        f"Keep all credentials as placeholders. integration_mode={spec['integration_mode']}, implementation_status={spec['implementation_status']}. "
        f"Required credentials: {', '.join(spec.get('required_credentials', [])) or 'none'}. "
        f"Optional credentials: {', '.join(spec.get('optional_credentials', [])) or 'none'}. "
        f"Include Manual Trigger, retry/error branch, and sticky note setup guidance."
    )


def json_escape(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def uuid_from_name(*parts: str) -> str:
    import uuid
    return str(uuid.uuid5(uuid.NAMESPACE_URL, '::'.join(parts)))


def render_n8n_workflow(service_name: str, operation_id: str | None = None, workflow_name: str | None = None) -> dict[str, Any]:
    spec = get_connector(service_name)
    prepared = prepare_connector_request(service_name, operation_id)
    workflow_name = workflow_name or f"wf_ext_{spec['service_name']}_{prepared['operation_id']}"
    trigger_name = 'Manual Trigger'
    payload_name = 'Build Connector Request'
    request_name = 'Execute Live Connector'
    normalize_name = 'Normalize Response'
    note = {
        'parameters': {'content': f"{spec['display_name']} connector bridge. Fill env placeholders in deploy/.env or n8n env before live execution."},
        'id': uuid_from_name(workflow_name, 'overview'),
        'name': 'Overview',
        'type': 'n8n-nodes-base.stickyNote',
        'typeVersion': 1,
        'position': [-860, -160],
    }
    trigger = {
        'parameters': {},
        'id': uuid_from_name(workflow_name, 'trigger'),
        'name': trigger_name,
        'type': 'n8n-nodes-base.manualTrigger',
        'typeVersion': 1,
        'position': [-820, 40],
    }
    payload = {
        'parameters': {'jsCode': "return [{json:" + json_escape({'service_name': spec['service_name'], 'operation_id': prepared['operation_id'], 'body': prepared.get('body', {}), 'query': prepared.get('query', {}), 'headers': {}, 'timeout_seconds': 30}) + "}];"},
        'id': uuid_from_name(workflow_name, 'payload'),
        'name': payload_name,
        'type': 'n8n-nodes-base.code',
        'typeVersion': 2,
        'position': [-520, 40],
    }
    http = {
        'parameters': {
            'method': 'POST',
            'url': r'={{($env.SERVICE_BASE_URL || "http://host.docker.internal:8000").replace(/\/$/, "") + "/connectors/execute-live"}}',
            'sendBody': True,
            'specifyBody': 'json',
            'jsonBody': '={{$json}}',
            'options': {'timeout': 120000},
        },
        'id': uuid_from_name(workflow_name, 'request'),
        'name': request_name,
        'type': 'n8n-nodes-base.httpRequest',
        'typeVersion': 4.2,
        'position': [-180, 40],
        'onError': 'continueRegularOutput',
    }
    normalize = {
        'parameters': {'jsCode': "const body = $json.body || $json; return [{json:{status: body.status || 'ok', service_name: body.service_name || $json.service_name, operation_id: body.operation_id || $json.operation_id, summary: body.summary || null, pagination: body.pagination || null, result: body.normalized || body.data || body}}];"},
        'id': uuid_from_name(workflow_name, 'normalize'),
        'name': normalize_name,
        'type': 'n8n-nodes-base.code',
        'typeVersion': 2,
        'position': [160, 40],
    }
    return {
        'name': workflow_name,
        'nodes': [note, trigger, payload, http, normalize],
        'connections': {
            trigger_name: {'main': [[{'node': payload_name, 'type': 'main', 'index': 0}]]},
            payload_name: {'main': [[{'node': request_name, 'type': 'main', 'index': 0}]]},
            request_name: {'main': [[{'node': normalize_name, 'type': 'main', 'index': 0}]]},
        },
        'pinData': {},
        'active': False,
        'settings': {'executionOrder': 'v1'},
        'meta': {'templateCredsSetupCompleted': False},
        'tags': [],
    }


def validate_connector_config(service_name: str) -> dict[str, Any]:
    adapter = get_adapter_for(service_name)
    result = adapter.validate_config()
    return {
        'service_name': service_name,
        'configured': result.configured,
        'missing_credentials': result.missing_credentials,
        'present_credentials': result.present_credentials,
        'implementation_status': result.implementation_status,
        'integration_mode': result.integration_mode,
        'notes': result.notes,
    }


def smoke_test_connector(service_name: str, operation_id: str | None = None, dry_run: bool = True) -> dict[str, Any]:
    return get_adapter_for(service_name).smoke_test(operation_id=operation_id, dry_run=dry_run)


async def execute_live_request(service_name: str, operation_id: str | None = None, body: dict[str, Any] | None = None, query: dict[str, Any] | None = None, headers: dict[str, Any] | None = None, timeout_seconds: int = 30) -> dict[str, Any]:
    return get_adapter_for(service_name).execute(operation_id=operation_id, body=body, query=query, headers=headers, timeout_seconds=timeout_seconds)
