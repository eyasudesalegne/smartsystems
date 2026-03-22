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


def build_local_payload(tenant_id: str) -> dict:
    import app.main as main_mod

    return main_mod._build_rag_governance_report(tenant_id=tenant_id)


def build_remote_payload(base_url: str, tenant_id: str, timeout: int) -> dict:
    with httpx.Client(timeout=timeout) as client:
        response = client.get(base_url.rstrip('/') + '/rag/governance', params={'tenant_id': tenant_id})
        response.raise_for_status()
        payload = response.json()
        payload['next_actions'] = payload.get('next_actions', []) or [
            'Review governed document counts and embedding versions before changing retrieval prompts or retention policies.'
        ]
        return payload


def main() -> int:
    parser = argparse.ArgumentParser(description='Build a RAG governance report from the local package or a running service.')
    parser.add_argument('--tenant-id', default=os.getenv('TENANT_ID', 'default'))
    parser.add_argument('--remote', action='store_true')
    parser.add_argument('--timeout', type=int, default=20)
    parser.add_argument('--out', default=str(ROOT / 'docs' / 'generated_rag_governance_report.json'))
    args = parser.parse_args()

    base_url = os.getenv('APP_BASE_URL', '').strip()
    payload = None
    if args.remote:
        if not base_url:
            raise SystemExit('APP_BASE_URL must be set when using --remote')
        payload = build_remote_payload(base_url, args.tenant_id, args.timeout)
    else:
        if base_url:
            try:
                payload = build_remote_payload(base_url, args.tenant_id, args.timeout)
            except Exception:
                payload = None
        if payload is None:
            payload = build_local_payload(args.tenant_id)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'status': 'ok', 'out': str(out_path), 'document_count': payload.get('document_count', 0), 'embedding_version_count': payload.get('embedding_version_count', 0)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
