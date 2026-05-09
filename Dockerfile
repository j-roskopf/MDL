FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates ffmpeg tzdata \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir yt-dlp

WORKDIR /app
COPY downloader.py scheduler.py README.md /app/

VOLUME ["/music", "/logs"]

CMD ["python", "/app/scheduler.py"]
