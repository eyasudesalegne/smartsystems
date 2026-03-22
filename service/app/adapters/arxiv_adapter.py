from __future__ import annotations

from typing import Any
from xml.etree import ElementTree as ET

from .base import HttpConnectorAdapter


class ArxivAdapter(HttpConnectorAdapter):
    """arXiv adapter with Atom-feed normalization."""

    def normalize_response(self, operation_id: str, data: Any, response_headers: dict[str, Any] | None = None) -> dict[str, Any]:
        if not isinstance(data, str):
            return super().normalize_response(operation_id, data, response_headers=response_headers)
        try:
            root = ET.fromstring(data)
        except ET.ParseError:
            return {
                'operation_id': operation_id,
                'summary': {'kind': 'arxiv_feed_text', 'length': len(data), 'parse_error': True},
                'raw_preview': data[:500],
            }
        ns = {'atom': 'http://www.w3.org/2005/Atom', 'arxiv': 'http://arxiv.org/schemas/atom'}
        entries = []
        for entry in root.findall('atom:entry', ns):
            entries.append(
                {
                    'id': entry.findtext('atom:id', default='', namespaces=ns),
                    'title': ' '.join((entry.findtext('atom:title', default='', namespaces=ns) or '').split()),
                    'summary': ' '.join((entry.findtext('atom:summary', default='', namespaces=ns) or '').split()),
                    'published': entry.findtext('atom:published', default='', namespaces=ns),
                    'updated': entry.findtext('atom:updated', default='', namespaces=ns),
                    'authors': [author.findtext('atom:name', default='', namespaces=ns) for author in entry.findall('atom:author', ns)],
                    'primary_category': (entry.find('arxiv:primary_category', ns).attrib.get('term') if entry.find('arxiv:primary_category', ns) is not None else None),
                }
            )
        return {
            'operation_id': operation_id,
            'items': entries,
            'summary': {'kind': 'arxiv_feed', 'record_count': len(entries)},
        }
