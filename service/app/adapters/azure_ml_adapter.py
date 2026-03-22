from __future__ import annotations

from typing import Any

from .base import HttpConnectorAdapter


class AzureMlAdapter(HttpConnectorAdapter):
    """Azure ML adapter with normalized list/detail responses."""

    def normalize_response(self, operation_id: str, data: Any, response_headers: dict[str, Any] | None = None) -> dict[str, Any]:
        if not isinstance(data, dict):
            return super().normalize_response(operation_id, data, response_headers=response_headers)

        if operation_id in {'list_jobs', 'list_models'}:
            values = data.get('value', [])
            items = []
            for item in values:
                props = item.get('properties', {})
                items.append(
                    {
                        'id': item.get('id'),
                        'name': item.get('name'),
                        'type': item.get('type'),
                        'status': props.get('status') or props.get('provisioning_state'),
                        'creation_context': props.get('creation_context'),
                    }
                )
            return {
                'operation_id': operation_id,
                'items': items,
                'next_link': data.get('nextLink'),
                'summary': {'kind': 'azure_collection', 'record_count': len(items)},
            }

        if operation_id == 'get_job':
            props = data.get('properties', {})
            return {
                'operation_id': operation_id,
                'job': {
                    'id': data.get('id'),
                    'name': data.get('name'),
                    'type': data.get('type'),
                    'status': props.get('status'),
                    'display_name': props.get('display_name'),
                    'experiment_name': props.get('experiment_name'),
                    'creation_context': props.get('creation_context'),
                },
                'summary': {'kind': 'azure_job', 'record_count': 1},
            }

        return super().normalize_response(operation_id, data, response_headers=response_headers)

    def extract_pagination(self, operation_id: str, data: Any, response_headers: dict[str, Any] | None = None) -> dict[str, Any]:
        base = super().extract_pagination(operation_id, data, response_headers=response_headers)
        if isinstance(data, dict) and data.get('nextLink'):
            base['next'] = data['nextLink']
        return base
