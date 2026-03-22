from __future__ import annotations

from typing import Any

from .base import HttpConnectorAdapter


class CanvasAdapter(HttpConnectorAdapter):
    """Canvas LMS adapter with normalized course and module payloads."""

    def normalize_response(self, operation_id: str, data: Any, response_headers: dict[str, Any] | None = None) -> dict[str, Any]:
        if isinstance(data, list):
            if operation_id == 'list_courses':
                items = [{'id': item.get('id'), 'name': item.get('name'), 'course_code': item.get('course_code')} for item in data]
                return {'operation_id': operation_id, 'items': items, 'summary': {'kind': 'canvas_courses', 'record_count': len(items)}}
            if operation_id == 'list_modules':
                items = [{'id': item.get('id'), 'name': item.get('name'), 'position': item.get('position')} for item in data]
                return {'operation_id': operation_id, 'items': items, 'summary': {'kind': 'canvas_modules', 'record_count': len(items)}}
        if isinstance(data, dict) and operation_id == 'get_course':
            return {
                'operation_id': operation_id,
                'course': {'id': data.get('id'), 'name': data.get('name'), 'course_code': data.get('course_code')},
                'summary': {'kind': 'canvas_course', 'record_count': 1},
            }
        return super().normalize_response(operation_id, data, response_headers=response_headers)
