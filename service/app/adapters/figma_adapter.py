from __future__ import annotations

from typing import Any

from .base import HttpConnectorAdapter


class FigmaAdapter(HttpConnectorAdapter):
    """Figma adapter with normalized file and image metadata."""

    def normalize_response(self, operation_id: str, data: Any, response_headers: dict[str, Any] | None = None) -> dict[str, Any]:
        if not isinstance(data, dict):
            return super().normalize_response(operation_id, data, response_headers=response_headers)

        if operation_id == 'get_file':
            document = data.get('document', {})
            return {
                'operation_id': operation_id,
                'file': {
                    'name': data.get('name'),
                    'version': data.get('version'),
                    'last_modified': data.get('lastModified'),
                    'document_id': document.get('id'),
                    'document_name': document.get('name'),
                    'child_count': len(document.get('children', []) or []),
                },
                'summary': {'kind': 'figma_file', 'record_count': 1},
            }

        if operation_id == 'get_nodes':
            nodes = data.get('nodes', {})
            items = []
            for node_id, node_payload in nodes.items():
                document = node_payload.get('document', {})
                items.append({'node_id': node_id, 'name': document.get('name'), 'type': document.get('type')})
            return {'operation_id': operation_id, 'items': items, 'summary': {'kind': 'figma_nodes', 'record_count': len(items)}}

        if operation_id == 'get_images':
            images = data.get('images', {})
            items = [{'node_id': node_id, 'url': url} for node_id, url in images.items()]
            return {'operation_id': operation_id, 'items': items, 'summary': {'kind': 'figma_images', 'record_count': len(items)}}

        return super().normalize_response(operation_id, data, response_headers=response_headers)
