import argparse, json, sys
from pathlib import Path
import httpx
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'service'))
import app.main as main_mod  # noqa: E402

parser = argparse.ArgumentParser(description='Validate the current package against a release manifest checksum set.')
parser.add_argument('--remote', action='store_true')
parser.add_argument('--base-url', default='http://localhost:8080')
parser.add_argument('--tenant-id', default='default')
parser.add_argument('--manifest', default=str(ROOT / 'docs' / 'generated_release_manifest.json'))
parser.add_argument('--persist', action='store_true')
parser.add_argument('--out', default=str(ROOT / 'docs' / 'generated_release_checksum_validation.json'))
args = parser.parse_args()
manifest_path = Path(args.manifest)
manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
if args.remote:
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(args.base_url.rstrip('/') + '/release/checksum-validate', json={'tenant_id': args.tenant_id, 'manifest_json': manifest, 'persist': args.persist})
        resp.raise_for_status()
        payload = resp.json()
else:
    manifest = manifest or main_mod._build_release_manifest(tenant_id=args.tenant_id, persist=False)
    payload = main_mod._validate_release_manifest(manifest, tenant_id=args.tenant_id, persist=args.persist)
out = Path(args.out)
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(payload, indent=2, sort_keys=True))
print(f'wrote release checksum validation to {out}')
