#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ ! -f .env ]]; then
  echo 'Copy .env.example to .env, replace ADMIN_TOKEN, and configure merchant placeholders first.' >&2
  exit 1
fi
# .env is trusted local shell configuration. Never source an untrusted file.
set -a
source .env
set +a
if [[ ! -x .venv/bin/python ]]; then
  echo 'Create .venv and install requirements.txt first; see README.md.' >&2
  exit 1
fi
exec .venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers
