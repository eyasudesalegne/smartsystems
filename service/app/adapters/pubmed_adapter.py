from __future__ import annotations

from typing import Any

from .base import HttpConnectorAdapter


class PubmedAdapter(HttpConnectorAdapter):
    """PubMed adapter with normalized search, summary, and abstract payloads."""

    def normalize_response(self, operation_id: str, data: Any, response_headers: dict[str, Any] | None = None) -> dict[str, Any]:
        if operation_id == 'fetch_abstracts' and isinstance(data, str):
            lines = [line.strip() for line in data.splitlines() if line.strip()]
            return {
                'operation_id': operation_id,
                'abstract_text': data,
                'abstract_preview': ' '.join(lines[:4])[:500],
                'summary': {'kind': 'pubmed_abstract_text', 'length': len(data)},
            }

        if not isinstance(data, dict):
            return super().normalize_response(operation_id, data, response_headers=response_headers)

        if operation_id == 'search':
            search_result = data.get('esearchresult', {})
            ids = search_result.get('idlist', [])
            return {
                'operation_id': operation_id,
                'pmids': ids,
                'count': int(search_result.get('count', len(ids) or 0)),
                'query_translation': search_result.get('querytranslation'),
                'summary': {'kind': 'pubmed_search', 'record_count': len(ids)},
            }

        if operation_id == 'summary':
            result = data.get('result', {})
            uids = result.get('uids', [])
            items = []
            for uid in uids:
                item = result.get(uid, {})
                items.append(
                    {
                        'uid': uid,
                        'title': item.get('title'),
                        'pubdate': item.get('pubdate'),
                        'source': item.get('source'),
                        'authors': [author.get('name') for author in item.get('authors', []) if author.get('name')],
                    }
                )
            return {
                'operation_id': operation_id,
                'items': items,
                'summary': {'kind': 'pubmed_summary', 'record_count': len(items)},
            }

        return super().normalize_response(operation_id, data, response_headers=response_headers)
