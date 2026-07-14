#!/bin/sh
# Entrypoint for the AWS Lambda Web Adapter layer.
# The adapter proxies Lambda invokes to this local HTTP server, so the same
# FastAPI/uvicorn app runs unchanged on Lambda, App Runner, ECS, or locally.
# Use `python -m uvicorn` (not bare `uvicorn`): pip install -t bundles the
# uvicorn package but not its CLI launcher, so the bare command isn't runnable.
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
