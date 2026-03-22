import argparse, json, sys
from pathlib import Path
import httpx
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'service'))
import app.main as main_mod  # noqa: E402

parser = argparse.ArgumentParser(description='Run release preflight checks from the local package or a running service.')
parser.add_argument('--remote', action='store_true')
parser.add_argument('--base-url', default='http://localhost:8080')
parser.add_argument('--tenant-id', default='default')
parser.add_argument('--release-version', default='')
parser.add_argument('--persist', action='store_true')
parser.add_argument('--out', default=str(ROOT / 'docs' / 'generated_release_preflight_report.json'))
args = parser.parse_args()
if args.remote:
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(args.base_url.rstrip('/') + '/release/preflight', json={'tenant_id': args.tenant_id, 'release_version': args.release_version or None, 'persist': args.persist})
        resp.raise_for_status()
        payload = resp.json()
else:
    payload = main_mod._build_release_preflight(tenant_id=args.tenant_id, release_version=args.release_version or None, persist=args.persist)
out = Path(args.out)
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(payload, indent=2, sort_keys=True))
print(f'wrote release preflight report to {out}')
