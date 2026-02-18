#!/usr/bin/env bash
# Run fetch_document_data.py inside the backend Docker container.
# Requires: docker compose up (backend + postgres) to be running.
#
# Usage:
#   ./scripts/run_fetch_document_data.sh [document_id] [options...]
#   ./scripts/run_fetch_document_data.sh a8ee43c2-2504-4d19-b427-28bea4e0ea7c --no-embedding
#   ./scripts/run_fetch_document_data.sh a8ee43c2-2504-4d19-b427-28bea4e0ea7c -o /tmp/doc.json

set -e
cd "$(dirname "$0")/.."
docker compose exec backend python scripts/fetch_document_data.py "$@"
