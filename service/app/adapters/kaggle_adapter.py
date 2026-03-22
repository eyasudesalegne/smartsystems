from __future__ import annotations

from typing import Any

from .base import HttpConnectorAdapter


class KaggleAdapter(HttpConnectorAdapter):
    """Kaggle adapter with normalized dataset/file collection outputs."""

    def normalize_response(self, operation_id: str, data: Any, response_headers: dict[str, Any] | None = None) -> dict[str, Any]:
        if isinstance(data, list):
            if operation_id == 'list_datasets':
                items = [{'ref': item.get('ref') or item.get('datasetRef'), 'title': item.get('title'), 'size': item.get('totalBytes')} for item in data]
                return {'operation_id': operation_id, 'items': items, 'summary': {'kind': 'kaggle_datasets', 'record_count': len(items)}}
            if operation_id == 'list_files':
                items = [{'name': item.get('name'), 'size': item.get('totalBytes')} for item in data]
                return {'operation_id': operation_id, 'items': items, 'summary': {'kind': 'kaggle_files', 'record_count': len(items)}}
        return super().normalize_response(operation_id, data, response_headers=response_headers)
