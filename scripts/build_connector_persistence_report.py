from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE_DIR = ROOT / 'service'
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

import urllib.request

import app.main as main_mod


def build_local(tenant_id: str) -> dict:
    return main_mod._build_connector_persistence_report(tenant_id=tenant_id)


def build_remote(base_url: str, tenant_id: str) -> dict:
    url = base_url.rstrip('/') + '/connectors/persistence-report'
    req = urllib.request.Request(
        url,
        data=json.dumps({'tenant_id': tenant_id}).encode(),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    parser = argparse.ArgumentParser(description='Build a connector persistence report from the local package or a running service.')
    parser.add_argument('--tenant-id', default='default')
    parser.add_argument('--remote', action='store_true')
    parser.add_argument('--base-url', default='http://localhost:8080')
    parser.add_argument('--out', default=str(ROOT / 'docs' / 'generated_connector_persistence_report.json'))
    args = parser.parse_args()

    payload = build_remote(args.base_url, args.tenant_id) if args.remote else build_local(args.tenant_id)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + '\n')
    print(json.dumps({'status': payload.get('status'), 'out': str(out_path), 'database_available': payload.get('database_available')}, indent=2))


if __name__ == '__main__':
    main()
