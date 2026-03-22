## Rollback

Stop n8n scheduler and worker, archive current DB, roll back the latest migration if required, then restore the previous package ZIP and re-import workflows in the original order. Publication bundle and release artifact tables were added in Phase 3 and should be included in rollback review.


Release rollback bundle generation is now available through `/release/rollback-package` and `python scripts/build_release_rollback_package.py`. Generate the bundle before each publish so rollback operators have the exact import order, workflow JSON, migrations, env template, and manifest checksum set used for that release.
