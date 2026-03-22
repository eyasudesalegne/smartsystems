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


def build_local_payload(tenant_id: str, release_version: str | None, include_publication_bundle: bool, output_path: str | None, persist: bool) -> dict:
    import app.main as main_mod
    return main_mod._build_release_channel_plan(tenant_id=tenant_id, release_version=release_version, include_publication_bundle=include_publication_bundle, output_path=output_path, persist=persist)


def build_remote_payload(base_url: str, tenant_id: str, release_version: str | None, include_publication_bundle: bool, output_path: str | None, token: str | None, timeout: int, persist: bool) -> dict:
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    payload = {'tenant_id': tenant_id, 'release_version': release_version, 'include_publication_bundle': include_publication_bundle, 'output_path': output_path, 'persist': persist}
    with httpx.Client(timeout=timeout, headers=headers) as client:
        response = client.post(base_url.rstrip('/') + '/release/channel-plan', json=payload)
        response.raise_for_status()
        return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(description='Build a release channel automation plan/report from the local package or a running service.')
    parser.add_argument('--tenant-id', default=os.getenv('TENANT_ID', 'default'))
    parser.add_argument('--release-version', default=os.getenv('RELEASE_VERSION', ''))
    parser.add_argument('--include-publication-bundle', action='store_true')
    parser.add_argument('--output-path', default=os.getenv('RELEASE_CHANNEL_OUTPUT_PATH', ''))
    parser.add_argument('--token', default=os.getenv('ACCESS_TOKEN', ''))
    parser.add_argument('--remote', action='store_true')
    parser.add_argument('--persist', action='store_true')
    parser.add_argument('--timeout', type=int, default=30)
    parser.add_argument('--out', default=str(ROOT / 'docs' / 'generated_release_channel_report.json'))
    args = parser.parse_args()

    base_url = os.getenv('APP_BASE_URL', '').strip()
    release_version = args.release_version or None
    output_path = args.output_path or None
    payload = None
    if args.remote:
        if not base_url:
            raise SystemExit('APP_BASE_URL must be set when using --remote')
        payload = build_remote_payload(base_url, args.tenant_id, release_version, args.include_publication_bundle, output_path, args.token or None, args.timeout, args.persist)
    else:
        if base_url:
            try:
                payload = build_remote_payload(base_url, args.tenant_id, release_version, args.include_publication_bundle, output_path, args.token or None, args.timeout, args.persist)
            except Exception:
                payload = None
        if payload is None:
            payload = build_local_payload(args.tenant_id, release_version, args.include_publication_bundle, output_path, args.persist)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'status': 'ok', 'out': str(out_path), 'tenant_id': payload.get('tenant_id'), 'release_version': payload.get('release_version'), 'ready_count': payload.get('ready_count', 0)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
