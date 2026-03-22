## Test plan

Run `scripts/bootstrap_db.sh`, start the stack with docker compose, then run `scripts/smoke_test.sh`. Validate: health/ready, AI generation, retrieval over ingested note content, queue enqueue/status, worker execution, approval transition, and publishbundle creation.
