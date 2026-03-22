#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
import httpx
ROOT = Path(__file__).resolve().parents[1]
SERVICE_DIR = ROOT / 'service'
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

def build_local_payload(tenant_id: str, workflow_id: str, actor_id: str, persist: bool) -> dict:
    import app.main as main_mod
    return main_mod._check_workflow_execution_cap(tenant_id=tenant_id, workflow_id=workflow_id, actor_id=actor_id, persist=persist, metadata_json={'source': 'check_workflow_execution_caps.py'})

def build_remote_payload(base_url: str, tenant_id: str, workflow_id: str, actor_id: str, persist: bool, timeout: int) -> dict:
    url = base_url.rstrip('/') + '/workflows/execution/check'
    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, json={'tenant_id': tenant_id, 'workflow_id': workflow_id, 'actor_id': actor_id, 'persist': persist, 'metadata_json': {'source': 'check_workflow_execution_caps.py'}})
        response.raise_for_status()
        return response.json()

def main() -> int:
    parser = argparse.ArgumentParser(description='Check workflow execution cap state from the local package or a running service.')
    parser.add_argument('--tenant-id', default=os.getenv('TENANT_ID', 'default'))
    parser.add_argument('--workflow-id', default=os.getenv('WORKFLOW_ID', 'wf_workflow_promotion_pipeline'))
    parser.add_argument('--actor-id', default=os.getenv('ACTOR_ID', 'operator'))
    parser.add_argument('--persist', action='store_true', default=False)
    parser.add_argument('--remote', action='store_true')
    parser.add_argument('--timeout', type=int, default=20)
    parser.add_argument('--out', default=str(ROOT / 'docs' / 'generated_workflow_execution_cap_report.json'))
    args = parser.parse_args()
    base_url = os.getenv('APP_BASE_URL', '').strip()
    payload = None
    if args.remote:
        if not base_url:
            raise SystemExit('APP_BASE_URL must be set when using --remote')
        payload = build_remote_payload(base_url, args.tenant_id, args.workflow_id, args.actor_id, args.persist, args.timeout)
    else:
        if base_url:
            try:
                payload = build_remote_payload(base_url, args.tenant_id, args.workflow_id, args.actor_id, args.persist, args.timeout)
            except Exception:
                payload = None
        if payload is None:
            payload = build_local_payload(args.tenant_id, args.workflow_id, args.actor_id, args.persist)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'status': 'ok', 'out': str(out_path), 'workflow_id': payload.get('workflow_id'), 'allowed': payload.get('allowed'), 'remaining_executions': payload.get('remaining_executions', 0)}))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
