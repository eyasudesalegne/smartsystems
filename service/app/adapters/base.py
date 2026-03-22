from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import base64
import json
import os
import re
import uuid
import zipfile
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import httpx
from ..config import settings
from ..secrets import resolve_secret_reference
EXPORT_ROOT = Path(settings.workspace_export_dir)
EXPORT_ROOT.mkdir(parents=True, exist_ok=True)
@dataclass
class ValidationResult:
    configured: bool
    missing_credentials: list[str]
    present_credentials: list[str]
    implementation_status: str
    integration_mode: str
    notes: str
class BaseConnectorAdapter:
    def __init__(self, spec: dict[str, Any]):
        self.spec = spec
    def _env(self, key: str) -> str:
        raw = os.getenv(key, '').strip()
        return (resolve_secret_reference(raw) or '').strip()
    def _present_credentials(self) -> list[str]:
        keys = self.spec.get('required_credentials', []) + self.spec.get('optional_credentials', [])
        return [key for key in keys if key and self._env(key)]
    def _missing_credentials(self) -> list[str]:
        required = [c for c in self.spec.get('required_credentials', []) if c]
        auth_type = self.spec.get('auth_type', 'none')
        missing = [c for c in required if not self._env(c)]
        if auth_type == 'oauth_refresh_or_bearer':
            if self._env('GOOGLE_DRIVE_ACCESS_TOKEN'):
                return []
            trio = ['GOOGLE_DRIVE_CLIENT_ID', 'GOOGLE_DRIVE_CLIENT_SECRET', 'GOOGLE_DRIVE_REFRESH_TOKEN']
            return [c for c in trio if not self._env(c)]
        if auth_type == 'oauth_bearer_or_client_credentials':
            if not self._env(self.spec.get('base_url_env', '')):
                return [self.spec.get('base_url_env', '')]
            if self._env('AZURE_ML_BEARER_TOKEN'):
                return []
            trio = ['AZURE_ML_TENANT_ID', 'AZURE_ML_CLIENT_ID', 'AZURE_ML_CLIENT_SECRET']
            alt_missing = [c for c in trio if not self._env(c)]
            return [] if not alt_missing else missing + [c for c in alt_missing if c not in missing]
        if auth_type == 'token_or_basic':
            if not self._env(self.spec.get('base_url_env', '')):
                return [self.spec.get('base_url_env', '')]
            return []
        if auth_type == 'query_params':
            return []
        return missing
    def validate_config(self) -> ValidationResult:
        missing = self._missing_credentials()
        present = self._present_credentials()
        notes = self.spec.get('rate_limit_retry_notes', '')
        if self.spec.get('auth_type') == 'oauth_refresh_or_bearer' and self._env('GOOGLE_DRIVE_ACCESS_TOKEN'):
            notes = (notes + ' Using supplied GOOGLE_DRIVE_ACCESS_TOKEN for execution.').strip()
        if self.spec.get('auth_type') == 'oauth_bearer_or_client_credentials' and self._env('AZURE_ML_BEARER_TOKEN'):
            notes = (notes + ' Using supplied AZURE_ML_BEARER_TOKEN for execution.').strip()
        if self.spec.get('auth_type') == 'oauth_bearer_or_client_credentials' and not self._env('AZURE_ML_BEARER_TOKEN'):
            trio = ['AZURE_ML_TENANT_ID', 'AZURE_ML_CLIENT_ID', 'AZURE_ML_CLIENT_SECRET']
            if all(self._env(k) for k in trio):
                notes = (notes + ' Client-credentials token minting is enabled for Azure ML.').strip()
        return ValidationResult(
            configured=not missing,
            missing_credentials=missing,
            present_credentials=present,
            implementation_status=self.spec.get('implementation_status', 'docs_only'),
            integration_mode=self.spec.get('integration_mode', 'manual_bridge'),
            notes=notes,
        )
    def get_operation(self, operation_id: str | None = None) -> dict[str, Any]:
        operations = self.spec.get('supported_operations') or self.spec.get('operations') or []
        if not operations:
            raise KeyError('operation')
        if operation_id is None:
            return json.loads(json.dumps(operations[0]))
        for op in operations:
            if op['operation_id'] == operation_id:
                return json.loads(json.dumps(op))
        raise KeyError(operation_id)
    def _resolve_auth_value(self, env_name: str, resolve_env: bool) -> str:
        return self._env(env_name) if resolve_env else f"{{$env.{env_name}}}"
    def _build_auth_headers(self, resolve_env: bool = False) -> dict[str, Any]:
        hdrs: dict[str, Any] = {}
        auth_type = self.spec.get('auth_type', 'none')
        if auth_type == 'token_or_basic':
            token = self._resolve_auth_value('MLFLOW_TOKEN', resolve_env) if 'MLFLOW_TOKEN' in self.spec.get('optional_credentials', []) else ''
            username = self._resolve_auth_value('MLFLOW_USERNAME', resolve_env) if 'MLFLOW_USERNAME' in self.spec.get('optional_credentials', []) else ''
            password = self._resolve_auth_value('MLFLOW_PASSWORD', resolve_env) if 'MLFLOW_PASSWORD' in self.spec.get('optional_credentials', []) else ''
            if token:
                hdrs['Authorization'] = f'Bearer {token}'
            elif username and password:
                hdrs['Authorization'] = 'Basic ' + base64.b64encode(f'{username}:{password}'.encode()).decode()
        elif auth_type == 'oauth_bearer_or_client_credentials':
            token = self._resolve_auth_value('AZURE_ML_BEARER_TOKEN', resolve_env) if resolve_env or self._env('AZURE_ML_BEARER_TOKEN') else ''
            if token:
                hdrs['Authorization'] = f'Bearer {token}'
            elif not resolve_env:
                hdrs['Authorization'] = 'Bearer {$env.AZURE_ML_BEARER_TOKEN|client_credentials}'
        elif auth_type in {'google_bearer', 'oauth_or_bearer'}:
            token_keys = ['NOTEBOOKLM_ACCESS_TOKEN', 'CANVAS_ACCESS_TOKEN', 'OVERLEAF_ACCESS_TOKEN', 'VSCODE_ACCESS_TOKEN', 'ANTIGRAVITY_ACCESS_TOKEN']
            for key in token_keys:
                if key in self.spec.get('required_credentials', []) + self.spec.get('optional_credentials', []):
                    hdrs['Authorization'] = f"Bearer {self._resolve_auth_value(key, resolve_env)}"
                    break
        elif auth_type == 'oauth_refresh_or_bearer':
            token = self._resolve_auth_value('GOOGLE_DRIVE_ACCESS_TOKEN', resolve_env) if resolve_env or self._env('GOOGLE_DRIVE_ACCESS_TOKEN') else ''
            if token:
                hdrs['Authorization'] = f'Bearer {token}'
            elif not resolve_env:
                hdrs['Authorization'] = 'Bearer {$env.GOOGLE_DRIVE_ACCESS_TOKEN|refresh_token_exchange}'
        elif auth_type == 'personal_access_token':
            hdrs['X-Figma-Token'] = self._resolve_auth_value('FIGMA_ACCESS_TOKEN', resolve_env)
        elif auth_type == 'basic_auth':
            user = self._resolve_auth_value('KAGGLE_USERNAME', resolve_env)
            pw = self._resolve_auth_value('KAGGLE_KEY', resolve_env)
            hdrs['Authorization'] = 'Basic ' + base64.b64encode(f'{user}:{pw}'.encode()).decode()
        return hdrs
    def build_headers(self, resolve_env: bool = False, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        hdrs: dict[str, Any] = {'Accept': 'application/json'}
        hdrs.update(self._build_auth_headers(resolve_env=resolve_env))
        if extra:
            hdrs.update(extra)
        return hdrs
    def _build_query_auth_params(self, resolve_env: bool = False) -> dict[str, Any]:
        auth_type = self.spec.get('auth_type', 'none')
        if auth_type != 'query_params':
            return {}
        params: dict[str, Any] = {}
        email = self._resolve_auth_value('PUBMED_EMAIL', resolve_env)
        api_key = self._resolve_auth_value('PUBMED_API_KEY', resolve_env)
        if resolve_env:
            if self._env('PUBMED_EMAIL'):
                params['email'] = email
            if self._env('PUBMED_API_KEY'):
                params['api_key'] = api_key
        else:
            params['email'] = email
            params['api_key'] = api_key
        return params
    def summarize_data(self, operation_id: str, data: Any) -> dict[str, Any]:
        if isinstance(data, dict):
            keys = list(data.keys())[:10]
            record_count = None
            if 'items' in data and isinstance(data['items'], list):
                record_count = len(data['items'])
            elif 'files' in data and isinstance(data['files'], list):
                record_count = len(data['files'])
            elif 'value' in data and isinstance(data['value'], list):
                record_count = len(data['value'])
            return {'kind': 'object', 'top_level_keys': keys, 'record_count': record_count}
        if isinstance(data, list):
            return {'kind': 'list', 'record_count': len(data)}
        if isinstance(data, str):
            return {'kind': 'text', 'length': len(data), 'preview': data[:280]}
        return {'kind': type(data).__name__}
    def normalize_response(self, operation_id: str, data: Any, response_headers: dict[str, Any] | None = None) -> dict[str, Any]:
        return {'operation_id': operation_id, 'summary': self.summarize_data(operation_id, data), 'items': data if isinstance(data, list) else None}
    def extract_pagination(self, operation_id: str, data: Any, response_headers: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {str(k).lower(): v for k, v in (response_headers or {}).items()}
        next_link = headers.get('link') or headers.get('x-next-page') or headers.get('next')
        cursor = None
        if isinstance(data, dict):
            cursor = data.get('next_page_token') or data.get('nextPageToken') or data.get('nextLink') or data.get('continuation_token')
        return {'next': next_link, 'cursor': cursor}
    def prepare(
        self,
        operation_id: str | None = None,
        body: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        headers: dict[str, Any] | None = None,
        resolve_env: bool = False,
    ) -> dict[str, Any]:
        op = self.get_operation(operation_id)
        base_url = self._env(self.spec['base_url_env']) if resolve_env else self.spec['base_url_placeholder']
        default_query = dict(self._build_query_auth_params(resolve_env=resolve_env))
        if query:
            default_query.update(query)
        prepared_query = default_query or json.loads(json.dumps(op.get('default_query', {})))
        if not prepared_query:
            prepared_query = {}
        prepared = {
            'service_name': self.spec['service_name'],
            'display_name': self.spec.get('display_name', self.spec['service_name']),
            'operation_id': op['operation_id'],
            'method': op['method'],
            'path': op['path'],
            'url': f"{base_url}{op['path']}" if not str(op['path']).startswith(base_url) else op['path'],
            'headers': self.build_headers(resolve_env=resolve_env, extra=headers or {}),
            'body': body if body is not None else json.loads(json.dumps(op.get('default_body', {}))),
            'query': prepared_query,
            'integration_mode': self.spec.get('integration_mode'),
            'implementation_status': self.spec.get('implementation_status'),
            'required_credentials': self.spec.get('required_credentials', []),
            'optional_credentials': self.spec.get('optional_credentials', []),
            'notes': self.spec.get('rate_limit_retry_notes', ''),
        }
        return prepared
    def smoke_test(self, operation_id: str | None = None, dry_run: bool = True) -> dict[str, Any]:
        validation = self.validate_config()
        prepared = self.prepare(operation_id=operation_id, resolve_env=False)
        return {
            'status': 'ok',
            'service_name': self.spec['service_name'],
            'operation_id': prepared['operation_id'],
            'dry_run': dry_run,
            'configured': validation.configured,
            'missing_credentials': validation.missing_credentials,
            'implementation_status': validation.implementation_status,
            'prepared': prepared,
        }
    def execute(
        self,
        operation_id: str | None = None,
        body: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        headers: dict[str, Any] | None = None,
        timeout_seconds: int = 30,
    ) -> dict[str, Any]:
        raise NotImplementedError
class HttpConnectorAdapter(BaseConnectorAdapter):
    def _render_value(self, value: Any, replacements: dict[str, str]) -> Any:
        if isinstance(value, str):
            return re.sub(r'__[A-Z0-9_]+__', lambda m: replacements.get(m.group(0), m.group(0)), value)
        if isinstance(value, list):
            return [self._render_value(v, replacements) for v in value]
        if isinstance(value, dict):
            return {k: self._render_value(v, replacements) for k, v in value.items()}
        return value
    def _replacement_map(self, body: dict[str, Any] | None = None, query: dict[str, Any] | None = None) -> dict[str, str]:
        replacements: dict[str, str] = {}
        for key, value in (query or {}).items():
            replacements[f'__{str(key).upper()}__'] = str(value)
        for key, value in (body or {}).items():
            replacements[f'__{str(key).upper()}__'] = str(value)
        for env_key in self.spec.get('required_credentials', []) + self.spec.get('optional_credentials', []):
            val = self._env(env_key)
            if val:
                replacements[f'__{env_key}__'] = val
        return replacements
    def _build_google_access_token(self, timeout_seconds: int = 30) -> str:
        direct = self._env('GOOGLE_DRIVE_ACCESS_TOKEN')
        if direct:
            return direct
        client_id = self._env('GOOGLE_DRIVE_CLIENT_ID')
        client_secret = self._env('GOOGLE_DRIVE_CLIENT_SECRET')
        refresh_token = self._env('GOOGLE_DRIVE_REFRESH_TOKEN')
        if not all([client_id, client_secret, refresh_token]):
            raise httpx.HTTPError('Google Drive refresh-token exchange requires GOOGLE_DRIVE_CLIENT_ID, GOOGLE_DRIVE_CLIENT_SECRET, and GOOGLE_DRIVE_REFRESH_TOKEN')
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(
                'https://oauth2.googleapis.com/token',
                data={
                    'client_id': client_id,
                    'client_secret': client_secret,
                    'refresh_token': refresh_token,
                    'grant_type': 'refresh_token',
                },
            )
            response.raise_for_status()
            data = response.json()
            token = data.get('access_token')
            if not token:
                raise httpx.HTTPError('Google OAuth token response did not include access_token')
            return token
    def _build_azure_access_token(self, timeout_seconds: int = 30) -> str:
        direct = self._env('AZURE_ML_BEARER_TOKEN')
        if direct:
            return direct
        tenant_id = self._env('AZURE_ML_TENANT_ID')
        client_id = self._env('AZURE_ML_CLIENT_ID')
        client_secret = self._env('AZURE_ML_CLIENT_SECRET')
        if not all([tenant_id, client_id, client_secret]):
            raise httpx.HTTPError('Azure ML client-credentials flow requires AZURE_ML_TENANT_ID, AZURE_ML_CLIENT_ID, and AZURE_ML_CLIENT_SECRET')
        token_url = f'https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token'
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(
                token_url,
                data={
                    'client_id': client_id,
                    'client_secret': client_secret,
                    'grant_type': 'client_credentials',
                    'scope': 'https://ml.azure.com/.default',
                },
            )
            response.raise_for_status()
            data = response.json()
            token = data.get('access_token')
            if not token:
                raise httpx.HTTPError('Azure OAuth token response did not include access_token')
            return token
    def _resolve_runtime_headers(self, prepared: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
        headers = dict(prepared.get('headers', {}))
        auth_type = self.spec.get('auth_type', 'none')
        if auth_type == 'oauth_refresh_or_bearer':
            headers['Authorization'] = f'Bearer {self._build_google_access_token(timeout_seconds=timeout_seconds)}'
        elif auth_type == 'oauth_bearer_or_client_credentials':
            headers['Authorization'] = f'Bearer {self._build_azure_access_token(timeout_seconds=timeout_seconds)}'
        return headers
    def _merge_url_and_query(self, url: str, query: dict[str, Any] | None) -> tuple[str, dict[str, Any] | None]:
        if not query:
            return url, None
        parsed = urlsplit(url)
        if not parsed.query:
            return url, query
        embedded = dict(parse_qsl(parsed.query, keep_blank_values=True))
        merged = {**embedded, **query}
        clean_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, '', parsed.fragment))
        return clean_url, merged
    def execute(
        self,
        operation_id: str | None = None,
        body: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        headers: dict[str, Any] | None = None,
        timeout_seconds: int = 30,
    ) -> dict[str, Any]:
        prepared = self.prepare(operation_id=operation_id, body=body, query=query, headers=headers, resolve_env=True)
        replacements = self._replacement_map(body=prepared.get('body'), query=prepared.get('query'))
        url = self._render_value(prepared['url'], replacements)
        method = prepared['method'].upper()
        request_headers = self._resolve_runtime_headers(prepared, timeout_seconds=timeout_seconds)
        request_query = self._render_value(prepared.get('query') or None, replacements)
        request_body = self._render_value(prepared.get('body') or None, replacements)
        url, request_query = self._merge_url_and_query(url, request_query)
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.request(
                method,
                url,
                headers=request_headers,
                params=request_query,
                json=request_body if method not in {'GET', 'DELETE'} else None,
            )
            content_type = response.headers.get('content-type', '')
            data: Any
            if 'application/json' in content_type:
                data = response.json()
            else:
                data = response.text
            response_headers = dict(response.headers)
            pagination = self.extract_pagination(prepared['operation_id'], data, response_headers=response_headers)
            normalized = self.normalize_response(prepared['operation_id'], data, response_headers=response_headers)
            return {
                'status': 'ok' if response.is_success else 'error',
                'service_name': self.spec['service_name'],
                'operation_id': prepared['operation_id'],
                'http_status': response.status_code,
                'url': url if not request_query else f"{url}?{urlencode(request_query, doseq=True)}",
                'response_headers': response_headers,
                'data': data,
                'normalized': normalized,
                'pagination': pagination,
                'summary': normalized.get('summary') if isinstance(normalized, dict) else self.summarize_data(prepared['operation_id'], data),
            }
class LocalArtifactAdapter(BaseConnectorAdapter):
    def _mkdir(self) -> Path:
        target = EXPORT_ROOT / self.spec['service_name']
        target.mkdir(parents=True, exist_ok=True)
        return target
    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    def _safe_name(self, value: str) -> str:
        return re.sub(r'[^a-zA-Z0-9_-]+', '_', value.lower()).strip('_') or 'artifact'
    def _local_result(self, operation_id: str, raw: dict[str, Any], normalized: dict[str, Any]) -> dict[str, Any]:
        summary = normalized.get('summary') if isinstance(normalized, dict) else self.summarize_data(operation_id, raw)
        return {
            'status': 'ok',
            'service_name': self.spec['service_name'],
            'operation_id': operation_id,
            **raw,
            'data': raw,
            'normalized': normalized,
            'pagination': {'next': None, 'cursor': None},
            'summary': summary,
        }
    def _build_drawio_xml(self, title: str, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> str:
        cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']
        for idx, node in enumerate(nodes, start=2):
            x = 40 + (idx - 2) * 180
            label = str(node.get('label', node.get('id', f'Node {idx}'))).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            nid = str(node.get('id', idx))
            cells.append(
                f'<mxCell id="{nid}" value="{label}" style="rounded=1;whiteSpace=wrap;html=1;" vertex="1" parent="1"><mxGeometry x="{x}" y="80" width="140" height="60" as="geometry"/></mxCell>'
            )
        for eidx, edge in enumerate(edges, start=1):
            eid = f'e{eidx}'
            src = edge.get('source') or edge.get('from') or ''
            tgt = edge.get('target') or edge.get('to') or ''
            label = str(edge.get('label', '')).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            cells.append(
                f'<mxCell id="{eid}" value="{label}" edge="1" parent="1" source="{src}" target="{tgt}"><mxGeometry relative="1" as="geometry"/></mxCell>'
            )
        inner = ''.join(cells)
        return f'<mxfile host="app.diagrams.net"><diagram name="{title}"><mxGraphModel><root>{inner}</root></mxGraphModel></diagram></mxfile>'
    def _drawio_embed_base_url(self) -> str:
        base = self._env('DRAWIO_BASE_URL') or 'https://embed.diagrams.net/'
        if not base.endswith('/'):
            base += '/'
        return base
    def execute(
        self,
        operation_id: str | None = None,
        body: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        headers: dict[str, Any] | None = None,
        timeout_seconds: int = 30,
    ) -> dict[str, Any]:
        op = self.get_operation(operation_id)
        payload = body or json.loads(json.dumps(op.get('default_body', {})))
        target = self._mkdir()
        ts = uuid.uuid4().hex[:10]
        op_id = op['operation_id']
        if self.spec['service_name'] == 'drawio':
            if op_id == 'build_xml_artifact':
                title = payload.get('title', 'Diagram')
                nodes = payload.get('nodes', [])
                edges = payload.get('edges', [])
                xml = self._build_drawio_xml(title, nodes, edges)
                path = target / f"{ts}_{self._safe_name(title)}.drawio"
                path.write_text(xml)
                meta = target / f"{path.stem}.json"
                self._write_json(meta, {'title': title, 'nodes': nodes, 'edges': edges})
                raw = {'artifact_path': str(path), 'metadata_path': str(meta)}
                normalized = {
                    'operation_id': op_id,
                    'artifact_kind': 'drawio_xml',
                    'artifact_path': str(path),
                    'metadata_path': str(meta),
                    'title': title,
                    'node_count': len(nodes),
                    'edge_count': len(edges),
                    'import_hint': 'Open the .drawio file in app.diagrams.net or diagrams.net desktop.',
                    'summary': {'kind': 'local_artifact', 'artifact_kind': 'drawio_xml', 'record_count': len(nodes)},
                }
                return self._local_result(op_id, raw, normalized)
            if op_id == 'emit_embed_link':
                diagram_name = payload.get('diagram_name', 'connector-diagram')
                artifact_path = payload.get('artifact_path', '')
                embed_url = f"{self._drawio_embed_base_url()}?embed=1&ui=min&spin=1&proto=json"
                embed_payload = {
                    'action': 'load',
                    'autosave': 1,
                    'title': diagram_name,
                    'xml_file': artifact_path or None,
                }
                raw = {'embed_url': embed_url, 'embed_payload': embed_payload}
                normalized = {
                    'operation_id': op_id,
                    'artifact_kind': 'drawio_embed_payload',
                    'embed_url': embed_url,
                    'embed_payload': embed_payload,
                    'summary': {'kind': 'local_bridge', 'artifact_kind': 'drawio_embed_payload', 'record_count': 1},
                }
                return self._local_result(op_id, raw, normalized)
        if self.spec['service_name'] == 'mermaid':
            diagram = payload.get('diagram', 'flowchart TD\nA-->B')
            mmd = target / f'{ts}_diagram.mmd'
            html = target / f'{ts}_diagram.html'
            mmd.write_text(diagram)
            html.write_text(
                '<html><body><pre class="mermaid">' + diagram + '</pre>'
                '<script type="module">import mermaid from '
                '"https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";'
                'mermaid.initialize({startOnLoad:true});</script></body></html>'
            )
            raw = {'artifact_path': str(mmd), 'html_preview_path': str(html)}
            normalized = {
                'operation_id': op_id,
                'artifact_kind': 'mermaid_source',
                'artifact_path': str(mmd),
                'html_preview_path': str(html),
                'render_mode': 'local_artifact' if op_id == 'build_mermaid_artifact' else 'local_fallback',
                'diagram_line_count': len(diagram.splitlines()),
                'summary': {'kind': 'local_artifact', 'artifact_kind': 'mermaid_source', 'record_count': len(diagram.splitlines())},
            }
            return self._local_result(op_id, raw, normalized)
        if self.spec['service_name'] == 'overleaf':
            files = payload.get('files', {})
            if op_id == 'build_project_bundle':
                zip_path = target / f'{ts}_overleaf_bundle.zip'
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for name, content in files.items():
                        zf.writestr(name, content)
                main_document = payload.get('main_document', 'main.tex')
                open_url_hint = 'https://www.overleaf.com/docs?snip_uri=' + str(zip_path)
                manifest = target / f'{ts}_overleaf_manifest.json'
                self._write_json(manifest, {'main_document': main_document, 'bundle_path': str(zip_path), 'open_url_hint': open_url_hint, 'file_count': len(files)})
                raw = {'bundle_path': str(zip_path), 'manifest_path': str(manifest), 'open_url_hint': open_url_hint}
                normalized = {
                    'operation_id': op_id,
                    'artifact_kind': 'overleaf_bundle',
                    'bundle_path': str(zip_path),
                    'manifest_path': str(manifest),
                    'main_document': main_document,
                    'file_count': len(files),
                    'open_url_hint': open_url_hint,
                    'summary': {'kind': 'local_artifact', 'artifact_kind': 'overleaf_bundle', 'record_count': len(files)},
                }
                return self._local_result(op_id, raw, normalized)
            if op_id == 'open_in_overleaf':
                snip_uri = payload.get('snip_uri') or payload.get('bundle_path') or ''
                open_url = f'https://www.overleaf.com/docs?snip_uri={snip_uri}' if snip_uri else 'https://www.overleaf.com/docs'
                form_payload = {'snip_uri': snip_uri} if snip_uri else {}
                raw = {'open_url': open_url, 'form_payload': form_payload}
                normalized = {
                    'operation_id': op_id,
                    'artifact_kind': 'overleaf_open_payload',
                    'open_url': open_url,
                    'form_payload': form_payload,
                    'summary': {'kind': 'local_bridge', 'artifact_kind': 'overleaf_open_payload', 'record_count': 1},
                }
                return self._local_result(op_id, raw, normalized)
        if self.spec['service_name'] in {'antigravity', 'vscode'}:
            workspace_name = payload.get('workspace_name', self.spec['service_name'] + '-workspace')
            workspace_dir = target / f"{ts}_{self._safe_name(workspace_name)}"
            workspace_dir.mkdir(parents=True, exist_ok=True)
            for name, content in payload.get('files', {}).items():
                file_path = workspace_dir / name
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content)
            if self.spec['service_name'] == 'vscode':
                vscode_dir = workspace_dir / '.vscode'
                vscode_dir.mkdir(exist_ok=True)
                tasks = payload.get('tasks') or [{'label': 'Validate package', 'type': 'shell', 'command': 'python scripts/validate_package.py'}]
                self._write_json(vscode_dir / 'tasks.json', {'version': '2.0.0', 'tasks': tasks})
                self._write_json(vscode_dir / 'launch.json', {'version': '0.2.0', 'configurations': []})
            manifest = workspace_dir / 'bridge_manifest.json'
            manifest_payload = {
                'workspace_name': workspace_name,
                'service_name': self.spec['service_name'],
                'files': list(payload.get('files', {}).keys()),
                'task_count': len(payload.get('tasks') or []),
                'operation_id': op_id,
            }
            self._write_json(manifest, manifest_payload)
            zip_path = target / f'{workspace_dir.name}.zip'
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for p in workspace_dir.rglob('*'):
                    if p.is_file():
                        zf.write(p, p.relative_to(workspace_dir))
            raw = {'workspace_path': str(workspace_dir), 'manifest_path': str(manifest), 'bundle_path': str(zip_path)}
            normalized = {
                'operation_id': op_id,
                'artifact_kind': 'workspace_bundle',
                'workspace_path': str(workspace_dir),
                'bundle_path': str(zip_path),
                'manifest_path': str(manifest),
                'workspace_name': workspace_name,
                'file_count': len(payload.get('files', {})),
                'task_count': len(payload.get('tasks') or []),
                'summary': {'kind': 'local_artifact', 'artifact_kind': 'workspace_bundle', 'record_count': len(payload.get('files', {}))},
            }
            return self._local_result(op_id, raw, normalized)
        prepared = self.prepare(operation_id=operation_id, body=body, query=query, headers=headers, resolve_env=False)
        normalized = {
            'operation_id': op_id,
            'prepared': prepared,
            'summary': {'kind': 'placeholder_bridge', 'record_count': 1},
        }
        return {
            'status': 'placeholder_bridge',
            'service_name': self.spec['service_name'],
            'operation_id': op_id,
            'prepared': prepared,
            'data': {'prepared': prepared},
            'normalized': normalized,
            'pagination': {'next': None, 'cursor': None},
            'summary': normalized['summary'],
        }
class ManualBridgeAdapter(LocalArtifactAdapter):
    pass
class LocalOrHttpAdapter(LocalArtifactAdapter, HttpConnectorAdapter):
    def execute(
        self,
        operation_id: str | None = None,
        body: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        headers: dict[str, Any] | None = None,
        timeout_seconds: int = 30,
    ) -> dict[str, Any]:
        op = self.get_operation(operation_id)
        if op['method'].upper() == 'LOCAL' or (op['operation_id'] == 'render_via_service' and not self._env(self.spec['base_url_env'])):
            return LocalArtifactAdapter.execute(self, operation_id=operation_id, body=body, query=query, headers=headers, timeout_seconds=timeout_seconds)
        return HttpConnectorAdapter.execute(self, operation_id=operation_id, body=body, query=query, headers=headers, timeout_seconds=timeout_seconds)
ADAPTER_BY_NAME = {
    'mlflow': HttpConnectorAdapter,
    'azure_ml': HttpConnectorAdapter,
    'drawio': LocalArtifactAdapter,
    'figma': HttpConnectorAdapter,
    'mermaid': LocalOrHttpAdapter,
    'canvas': HttpConnectorAdapter,
    'kaggle': HttpConnectorAdapter,
    'notebooklm': HttpConnectorAdapter,
    'google_drive': HttpConnectorAdapter,
    'overleaf': ManualBridgeAdapter,
    'pubmed': HttpConnectorAdapter,
    'arxiv': HttpConnectorAdapter,
    'antigravity': LocalArtifactAdapter,
    'vscode': LocalArtifactAdapter,
}
def get_adapter(spec: dict[str, Any]) -> BaseConnectorAdapter:
    cls = ADAPTER_BY_NAME.get(spec['service_name'], BaseConnectorAdapter)
    return cls(spec)
