# Release Engineering Guide

Use the release layer to create a checksum-backed manifest, validate package integrity, generate a rollback bundle, and run a local release preflight before publishing.

## API surfaces
- `POST /release/manifest`
- `POST /release/checksum-validate`
- `POST /release/rollback-package`
- `POST /release/preflight`

## Local scripts
- `python scripts/build_release_manifest.py`
- `python scripts/validate_release_checksums.py`
- `python scripts/build_release_rollback_package.py`
- `python scripts/run_release_preflight.py`

## Rollback bundle contents
The rollback bundle includes the release manifest, rollback guide, resume/worklog handoff files, import order, unified schema, all additive migrations, all checked-in n8n workflow JSON files, and the env template.


## release publication automation
- `POST /release/publish` builds a staged publication bundle ZIP.
- `GET /release/publications` lists recorded publication attempts.
- `GET /admin/releases` summarizes manifests, rollback packages, and publication counts.

### Local publication script
- `python scripts/build_release_publication_report.py --out docs/generated_release_publication_report.json --out-zip artifacts/release_publication_bundle_default.zip`

### Publication bundle contents
A publication bundle includes the full package candidate set plus `release_manifest.json`, `release_checksum_validation.json`, `release_preflight_report.json`, and `release_publication_summary.json`. When preflight or checksum validation blocks release, the ZIP is still generated for inspection but is marked `publication_status=blocked`.


## release channel automation
Release publication now includes channel configuration and planning on top of staged bundles. Use `/release/channel` to register a manual review channel, a file-drop destination, or a webhook-notify channel. Use `/release/channel-plan` or `scripts/build_release_channel_report.py` to see which channels are publish-ready, which are blocked by missing config, and which next action each channel expects.


## Release channel execution automation
The package now separates **channel planning** from **channel execution**.

- Use `POST /release/channel-plan` or `wf_release_channel_plan.json` to see which channels are ready, blocked, or next.
- Use `POST /release/channel-execute` or `wf_release_channel_execute.json` to perform a dry run or real execution.
- Manual channels produce a handoff JSON artifact instead of pretending to publish.
- File-drop channels can copy the staged publication bundle into a configured destination.
- Webhook channels default to preview-mode unless webhook sending is explicitly enabled; this keeps the package honest in environments without real publication APIs.
- Audit recent executions through `GET /release/channel-executions`, `GET /admin/release-channel-executions`, or `wf_release_channel_execution_audit.json`.

- Release/publication list and admin endpoints now apply request-context tenant row scoping in addition to their tenant-aware SQL so local caches and fallback paths do not bleed cross-tenant artifacts.


Tenant query coverage now applies to release publication, release channel, and release channel execution read paths even when local fallback caches are used. Direct tenant-scoped reads such as connector health/metrics, job status, and lifecycle admin summaries should also be exercised with the tenant header during release validation so request-context resolution is verified end-to-end.
