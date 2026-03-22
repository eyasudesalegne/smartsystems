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

    return main_mod._build_ai_control_report(tenant_id=tenant_id)


def build_remote_payload(base_url: str, tenant_id: str, timeout: int) -> dict:
    base = base_url.rstrip('/')
    with httpx.Client(timeout=timeout) as client:
        models = client.get(base + '/ai/models', params={'tenant_id': tenant_id})
        models.raise_for_status()
        prompts = client.get(base + '/ai/prompts', params={'tenant_id': tenant_id})
        prompts.raise_for_status()
        route_samples = []
        for action_type in ['fallback_chat', 'summarize', 'retrieve_answer']:
            route = client.post(base + '/ai/route', json={'tenant_id': tenant_id, 'action_type': action_type, 'generation_mode': 'deterministic'})
            route.raise_for_status()
            route_samples.append(route.json())
        return {
            'status': 'ok',
            'tenant_id': tenant_id,
            'model_count': models.json().get('count', 0),
            'prompt_count': prompts.json().get('count', 0),
            'models': models.json().get('items', []),
            'prompts': prompts.json().get('items', []),
            'route_samples': route_samples,
            'next_actions': [
                'Review routed models and prompt versions for each action before enabling strict auth in production.',
                'Register additional models or prompt versions if you need non-default routing behavior.',
            ],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description='Build an AI control report from the local package or a running service.')
    parser.add_argument('--tenant-id', default=os.getenv('TENANT_ID', 'default'))
    parser.add_argument('--remote', action='store_true')
    parser.add_argument('--timeout', type=int, default=20)
    parser.add_argument('--out', default=str(ROOT / 'docs' / 'generated_ai_control_report.json'))
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
    print(json.dumps({'status': 'ok', 'out': str(out_path), 'model_count': payload.get('model_count', 0), 'prompt_count': payload.get('prompt_count', 0)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
