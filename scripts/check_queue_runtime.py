from pathlib import Path
import argparse
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
SERVICE_DIR = ROOT / 'service'
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

from fastapi.testclient import TestClient
import httpx
import app.main as main_mod
from app.main import app


def build_local_report() -> dict:
    client = TestClient(app)

    def fake_fetch_one(sql, params=None):
        if 'queue_workers' in sql:
            return {'c': 1}
        return {'c': 0}

    main_mod.fetch_one = fake_fetch_one
    response = client.get('/admin/queue')
    response.raise_for_status()
    return response.json()


def build_remote_report(app_base_url: str) -> dict:
    response = httpx.get(f"{app_base_url.rstrip('/')}/admin/queue", params={'tenant_id': 'default'}, timeout=30.0)
    response.raise_for_status()
    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--remote', action='store_true')
    parser.add_argument('--out', default='')
    args = parser.parse_args()

    payload = build_remote_report(os.getenv('APP_BASE_URL', 'http://localhost:8080')) if args.remote else build_local_report()
    summary = payload['summary']
    assert 'queue_backend' in summary
    assert 'requested_queue_backend' in summary
    assert 'worker_concurrency' in summary
    assert 'retry_backoff_base_seconds' in summary
    assert 'queue_max_claim_batch' in summary
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2))
    print('queue runtime smoke test ok')


if __name__ == '__main__':
    main()
