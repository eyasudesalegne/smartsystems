#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / 'service'
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.connectors import build_workflow_manifest  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build connector workflow manifest from package files or remote service.')
    parser.add_argument('--remote', action='store_true', help='Fetch from running service instead of local package files')
    parser.add_argument('--service-name', action='append', default=[], help='Optional service filter; may be passed multiple times')
    parser.add_argument('--app-base-url', default=None, help='Override APP_BASE_URL for --remote mode')
    parser.add_argument('--out', default='docs/generated_connector_workflow_manifest.json', help='Output path for generated manifest JSON')
    return parser.parse_args()


def build_local_payload(service_names: list[str]) -> dict:
    items = build_workflow_manifest(service_names or None)
    return {'status': 'ok', 'count': len(items), 'connectors': items}


def build_remote_payload(service_names: list[str], app_base_url: str | None) -> dict:
    base_url = (app_base_url or 'http://localhost:8080').rstrip('/')
    params = {}
    if service_names:
        # Remote endpoint accepts a single service_name filter at a time today; use first when supplied.
        params['service_name'] = service_names[0]
    with httpx.Client(timeout=60) as client:
        response = client.get(f'{base_url}/connectors/workflow-manifest', params=params)
        response.raise_for_status()
        return response.json()


def main() -> int:
    args = parse_args()
    payload = build_remote_payload(args.service_name, args.app_base_url) if args.remote else build_local_payload(args.service_name)
    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')
    print(f'wrote workflow manifest to {out_path}')
    print(json.dumps({'count': payload.get('count', 0), 'services': [item['service_name'] for item in payload.get('connectors', [])[:10]]}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
