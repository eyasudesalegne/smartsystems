from __future__ import annotations

from typing import Any

from .base import HttpConnectorAdapter


class MlflowAdapter(HttpConnectorAdapter):
    """MLflow adapter with normalized responses for common tracking operations."""

    def normalize_response(self, operation_id: str, data: Any, response_headers: dict[str, Any] | None = None) -> dict[str, Any]:
        if not isinstance(data, dict):
            return super().normalize_response(operation_id, data, response_headers=response_headers)

        if operation_id == 'list_experiments':
            experiments = data.get('experiments', [])
            items = [
                {
                    'experiment_id': item.get('experiment_id'),
                    'name': item.get('name'),
                    'artifact_location': item.get('artifact_location'),
                    'lifecycle_stage': item.get('lifecycle_stage'),
                    'creation_time': item.get('creation_time'),
                    'last_update_time': item.get('last_update_time'),
                }
                for item in experiments
            ]
            return {
                'operation_id': operation_id,
                'items': items,
                'next_page_token': data.get('next_page_token'),
                'summary': {'kind': 'mlflow_experiments', 'record_count': len(items)},
            }

        if operation_id == 'search_runs':
            runs = data.get('runs', [])
            items = []
            for item in runs:
                info = item.get('info', {})
                metrics = item.get('data', {}).get('metrics', [])
                params = item.get('data', {}).get('params', [])
                items.append(
                    {
                        'run_id': info.get('run_id'),
                        'run_name': info.get('run_name'),
                        'experiment_id': info.get('experiment_id'),
                        'status': info.get('status'),
                        'start_time': info.get('start_time'),
                        'end_time': info.get('end_time'),
                        'metric_count': len(metrics),
                        'param_count': len(params),
                    }
                )
            return {
                'operation_id': operation_id,
                'items': items,
                'next_page_token': data.get('next_page_token'),
                'summary': {'kind': 'mlflow_runs', 'record_count': len(items)},
            }

        if operation_id == 'get_run':
            run = data.get('run', {})
            info = run.get('info', {})
            metrics = run.get('data', {}).get('metrics', [])
            params = run.get('data', {}).get('params', [])
            tags = run.get('data', {}).get('tags', [])
            return {
                'operation_id': operation_id,
                'run': {
                    'run_id': info.get('run_id'),
                    'run_name': info.get('run_name'),
                    'experiment_id': info.get('experiment_id'),
                    'status': info.get('status'),
                    'artifact_uri': info.get('artifact_uri'),
                    'lifecycle_stage': info.get('lifecycle_stage'),
                    'metric_count': len(metrics),
                    'param_count': len(params),
                    'tag_count': len(tags),
                },
                'summary': {'kind': 'mlflow_run', 'record_count': 1},
            }

        return super().normalize_response(operation_id, data, response_headers=response_headers)
