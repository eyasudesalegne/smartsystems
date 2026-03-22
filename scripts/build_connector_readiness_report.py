#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
SERVICE_DIR = ROOT / 'service'
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))


def build_local_payload(tenant_id: str, service_names: list[str], persist: bool) -> dict:
    import app.main as main_mod

    return main_mod._build_connector_readiness_report(tenant_id=tenant_id, service_names=service_names, persist=persist)


def build_remote_payload(base_url: str, tenant_id: str, service_names: list[str], persist: bool, timeout: int) -> dict:
    url = base_url.rstrip('/') + '/connectors/readiness-report'
    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, json={'tenant_id': tenant_id, 'service_names': service_names, 'persist': persist})
        response.raise_for_status()
        return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(description='Build a combined connector readiness report from the local package or a running service.')
    parser.add_argument('--tenant-id', default=os.getenv('TENANT_ID', 'default'))
    parser.add_argument('--service', action='append', default=[], dest='services', help='Optional service_name to include; can be repeated.')
    parser.add_argument('--persist', action='store_true', default=False, help='Persist connector credential metadata when the target environment supports it.')
    parser.add_argument('--remote', action='store_true', help='Force HTTP mode using APP_BASE_URL.')
    parser.add_argument('--timeout', type=int, default=20)
    parser.add_argument('--out', default=str(ROOT / 'docs' / 'generated_connector_readiness_report.json'))
    args = parser.parse_args()

    base_url = os.getenv('APP_BASE_URL', '').strip()
    payload = None
    if args.remote:
        if not base_url:
            raise SystemExit('APP_BASE_URL must be set when using --remote')
        payload = build_remote_payload(base_url, args.tenant_id, args.services, args.persist, args.timeout)
    else:
        if base_url:
            try:
                payload = build_remote_payload(base_url, args.tenant_id, args.services, args.persist, args.timeout)
            except Exception:
                payload = None
        if payload is None:
            payload = build_local_payload(args.tenant_id, args.services, args.persist)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({
        'status': 'ok',
        'out': str(out_path),
        'count': payload.get('count', 0),
        'configured_count': payload.get('configured_count', 0),
        'live_ready_count': payload.get('live_ready_count', 0),
        'import_ready_count': payload.get('import_ready_count', 0),
        'draft_ready_count': payload.get('draft_ready_count', 0),
    }))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
