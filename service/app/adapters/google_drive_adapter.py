from __future__ import annotations

from typing import Any

from .base import HttpConnectorAdapter


class GoogleDriveAdapter(HttpConnectorAdapter):
    """Google Drive adapter with normalized file metadata outputs."""

    def normalize_response(self, operation_id: str, data: Any, response_headers: dict[str, Any] | None = None) -> dict[str, Any]:
        if operation_id == 'export_file' and isinstance(data, str):
            content_type = (response_headers or {}).get('content-type', '')
            return {
                'operation_id': operation_id,
                'export': {'content_type': content_type, 'text_preview': data[:280], 'length': len(data)},
                'summary': {'kind': 'google_drive_export', 'length': len(data)},
            }

        if not isinstance(data, dict):
            return super().normalize_response(operation_id, data, response_headers=response_headers)

        if operation_id == 'list_files':
            files = data.get('files', [])
            items = [
                {
                    'id': item.get('id'),
                    'name': item.get('name'),
                    'mime_type': item.get('mimeType'),
                    'modified_time': item.get('modifiedTime'),
                    'web_view_link': item.get('webViewLink'),
                }
                for item in files
            ]
            return {
                'operation_id': operation_id,
                'items': items,
                'next_page_token': data.get('nextPageToken'),
                'summary': {'kind': 'google_drive_files', 'record_count': len(items)},
            }

        if operation_id == 'get_file':
            return {
                'operation_id': operation_id,
                'file': {
                    'id': data.get('id'),
                    'name': data.get('name'),
                    'mime_type': data.get('mimeType'),
                    'modified_time': data.get('modifiedTime'),
                    'web_view_link': data.get('webViewLink'),
                    'size': data.get('size'),
                },
                'summary': {'kind': 'google_drive_file', 'record_count': 1},
            }

        return super().normalize_response(operation_id, data, response_headers=response_headers)

    def extract_pagination(self, operation_id: str, data: Any, response_headers: dict[str, Any] | None = None) -> dict[str, Any]:
        base = super().extract_pagination(operation_id, data, response_headers=response_headers)
        if isinstance(data, dict) and data.get('nextPageToken'):
            base['cursor'] = data['nextPageToken']
        return base
