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


def build_local_payload(tenant_id: str, route: str, method: str, actor_id: str, role: str, identity_tenant_id: str, requested_tenant_id: str | None) -> dict:
    import app.main as main_mod
    return main_mod.build_tenant_enforcement_report(
        tenant_id=tenant_id,
        route=route,
        method=method,
        actor_id=actor_id,
        role=role,
        identity_tenant_id=identity_tenant_id,
        requested_tenant_id=requested_tenant_id,
    )


def build_remote_payload(base_url: str, tenant_id: str, route: str, method: str, token: str | None, timeout: int, actor_id: str, role: str, identity_tenant_id: str, requested_tenant_id: str | None) -> dict:
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    payload = {
        'tenant_id': tenant_id,
        'route': route,
        'method': method,
        'actor_id': actor_id,
        'role': role,
        'identity_tenant_id': identity_tenant_id,
        'requested_tenant_id': requested_tenant_id,
    }
    with httpx.Client(timeout=timeout, headers=headers) as client:
        response = client.post(base_url.rstrip('/') + '/tenants/enforcement-report', json=payload)
        response.raise_for_status()
        return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(description='Build a tenant-enforcement report from the local package or a running service.')
    parser.add_argument('--tenant-id', default=os.getenv('TENANT_ID', 'default'))
    parser.add_argument('--route', default=os.getenv('TENANT_ROUTE', '/connectors/catalog'))
    parser.add_argument('--method', default=os.getenv('TENANT_METHOD', 'GET'))
    parser.add_argument('--actor-id', default=os.getenv('ACTOR_ID', 'anonymous'))
    parser.add_argument('--role', default=os.getenv('ACTOR_ROLE', 'viewer'))
    parser.add_argument('--identity-tenant-id', default=os.getenv('IDENTITY_TENANT_ID', 'default'))
    parser.add_argument('--requested-tenant-id', default=os.getenv('REQUESTED_TENANT_ID', ''))
    parser.add_argument('--token', default=os.getenv('ACCESS_TOKEN', ''))
    parser.add_argument('--remote', action='store_true')
    parser.add_argument('--timeout', type=int, default=20)
    parser.add_argument('--out', default=str(ROOT / 'docs' / 'generated_tenant_enforcement_report.json'))
    args = parser.parse_args()

    base_url = os.getenv('APP_BASE_URL', '').strip()
    payload = None
    requested_tenant_id = args.requested_tenant_id or None
    if args.remote:
        if not base_url:
            raise SystemExit('APP_BASE_URL must be set when using --remote')
        payload = build_remote_payload(base_url, args.tenant_id, args.route, args.method, args.token or None, args.timeout, args.actor_id, args.role, args.identity_tenant_id, requested_tenant_id)
    else:
        if base_url:
            try:
                payload = build_remote_payload(base_url, args.tenant_id, args.route, args.method, args.token or None, args.timeout, args.actor_id, args.role, args.identity_tenant_id, requested_tenant_id)
            except Exception:
                payload = None
        if payload is None:
            payload = build_local_payload(args.tenant_id, args.route, args.method, args.actor_id, args.role, args.identity_tenant_id, requested_tenant_id)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'status': 'ok', 'out': str(out_path), 'tenant_id': payload.get('tenant_id'), 'decision': payload.get('decision')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
