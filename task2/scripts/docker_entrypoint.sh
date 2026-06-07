#!/usr/bin/env bash
# Install/update Python deps on container start (repo mount or baked-in fallback).
set -euo pipefail

REQ="/repo/requirements.txt"
if [[ ! -f "$REQ" ]]; then
    REQ="/opt/requirements.txt"
fi

if [[ -f "$REQ" ]]; then
    python3 -m pip install --no-cache-dir -r "$REQ"
    # grpcio can shadow google.protobuf — same fix as Dockerfile build.
    rm -f /usr/local/lib/python3.*/site-packages/google/__init__.py 2>/dev/null || true
    rm -rf /usr/local/lib/python3.*/site-packages/google/__pycache__ 2>/dev/null || true
fi

exec "$@"
