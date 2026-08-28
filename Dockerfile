FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV DENO_INSTALL=/usr/local

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl ffmpeg tzdata unzip \
 && curl -fsSL https://deno.land/install.sh | sh \
 && pip install --no-cache-dir -U "yt-dlp[default]" \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY downloader.py scheduler.py README.md entrypoint.sh /app/
RUN chmod +x /app/entrypoint.sh

VOLUME ["/music", "/logs"]

ENTRYPOINT ["/app/entrypoint.sh"]
