#!/bin/sh
set -e

# YouTube breaks extractors often; refresh yt-dlp before every run.
echo "[entrypoint] updating yt-dlp..."
pip install -q -U "yt-dlp[default]" || echo "[entrypoint] warning: yt-dlp update failed; using image version"

yt-dlp --version || true
yt-dlp --rm-cache-dir >/dev/null 2>&1 || true

exec python /app/scheduler.py
