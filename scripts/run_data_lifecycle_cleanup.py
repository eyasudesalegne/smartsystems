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


def build_local_payload(tenant_id: str, actor_id: str | None, resource_types: list[str], dry_run: bool, persist: bool) -> dict:
    import app.main as main_mod
    return main_mod.run_data_lifecycle_cleanup(tenant_id=tenant_id, resource_types=resource_types, dry_run=dry_run, actor_id=actor_id, persist=persist)


def build_remote_payload(base_url: str, tenant_id: str, actor_id: str | None, resource_types: list[str], dry_run: bool, persist: bool, timeout: int) -> dict:
    url = base_url.rstrip('/') + '/lifecycle/run-cleanup'
    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, json={'tenant_id': tenant_id, 'actor_id': actor_id, 'resource_types': resource_types, 'dry_run': dry_run, 'persist': persist})
        response.raise_for_status()
        return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(description='Run or simulate data-lifecycle cleanup from the local package or a running service.')
    parser.add_argument('--tenant-id', default=os.getenv('TENANT_ID', 'default'))
    parser.add_argument('--actor-id', default=os.getenv('ACTOR_ID', 'system_cleanup'))
    parser.add_argument('--resource', action='append', default=[], dest='resources')
    parser.add_argument('--dry-run', action='store_true', default=False)
    parser.add_argument('--persist', action='store_true', default=False)
    parser.add_argument('--remote', action='store_true')
    parser.add_argument('--timeout', type=int, default=20)
    parser.add_argument('--out', default=str(ROOT / 'docs' / 'generated_data_lifecycle_cleanup.json'))
    args = parser.parse_args()

    base_url = os.getenv('APP_BASE_URL', '').strip()
    payload = None
    if args.remote:
        if not base_url:
            raise SystemExit('APP_BASE_URL must be set when using --remote')
        payload = build_remote_payload(base_url, args.tenant_id, args.actor_id, args.resources, args.dry_run, args.persist, args.timeout)
    else:
        if base_url:
            try:
                payload = build_remote_payload(base_url, args.tenant_id, args.actor_id, args.resources, args.dry_run, args.persist, args.timeout)
            except Exception:
                payload = None
        if payload is None:
            payload = build_local_payload(args.tenant_id, args.actor_id, args.resources, args.dry_run, args.persist)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'status': 'ok', 'out': str(out_path), 'count': payload.get('count', 0), 'eligible_total': payload.get('eligible_total', 0), 'deleted_total': payload.get('deleted_total', 0), 'archived_total': payload.get('archived_total', 0), 'dry_run': payload.get('dry_run', True)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
