#!/usr/bin/env python3
"""Small Docker-friendly scheduler for downloader.py."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


DAYS = {
    "mon": 0,
    "monday": 0,
    "tue": 1,
    "tuesday": 1,
    "wed": 2,
    "wednesday": 2,
    "thu": 3,
    "thursday": 3,
    "fri": 4,
    "friday": 4,
    "sat": 5,
    "saturday": 5,
    "sun": 6,
    "sunday": 6,
}


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def split_env_args(value: str | None) -> list[str]:
    return shlex.split(value or "")


def build_downloader_command() -> list[str]:
    source = os.environ.get("LISTENBRAINZ_SOURCE", "listenbrainz:joebrothehobo")
    output_dir = os.environ.get("OUTPUT_DIR", "/music")
    downloader_path = os.environ.get("DOWNLOADER_PATH") or str(Path(__file__).resolve().parent / "downloader.py")
    command = [sys.executable, downloader_path, source, "--output-dir", output_dir]

    plex_section_id = os.environ.get("PLEX_SECTION_ID")
    if plex_section_id:
        command.extend(["--plex-section-id", plex_section_id])

    plex_path_map = os.environ.get("PLEX_PATH_MAP")
    if plex_path_map:
        command.extend(["--plex-path-map", plex_path_map])

    if env_bool("PLEX_REPLACE_PLAYLISTS", True):
        command.append("--plex-replace-playlists")

    if env_bool("NO_PLEX_LOCK_TRACK_TITLES"):
        command.append("--no-plex-lock-track-titles")

    plex_scan_wait = os.environ.get("PLEX_SCAN_WAIT")
    if plex_scan_wait:
        command.extend(["--plex-scan-wait", plex_scan_wait])

    plex_match_retries = os.environ.get("PLEX_MATCH_RETRIES")
    if plex_match_retries:
        command.extend(["--plex-match-retries", plex_match_retries])

    plex_match_wait = os.environ.get("PLEX_MATCH_WAIT")
    if plex_match_wait:
        command.extend(["--plex-match-wait", plex_match_wait])

    youtube_search_results = os.environ.get("YOUTUBE_SEARCH_RESULTS")
    if youtube_search_results:
        command.extend(["--youtube-search-results", youtube_search_results])

    youtube_min_score = os.environ.get("YOUTUBE_MIN_SCORE")
    if youtube_min_score:
        command.extend(["--youtube-min-score", youtube_min_score])

    limit = os.environ.get("LIMIT")
    if limit:
        command.extend(["--limit", limit])

    if env_bool("DRY_RUN"):
        command.append("--dry-run")

    command.extend(split_env_args(os.environ.get("EXTRA_ARGS")))
    return command


def log_path(log_dir: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return log_dir / f"mdl-{stamp}.log"


def run_once() -> int:
    log_dir = Path(os.environ.get("LOG_DIR", "/logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_path(log_dir)
    command = build_downloader_command()

    started = datetime.now().isoformat(timespec="seconds")
    print(f"[scheduler] starting {started}", flush=True)
    print(f"[scheduler] command: {shlex.join(command)}", flush=True)
    print(f"[scheduler] log: {path}", flush=True)

    with path.open("w", encoding="utf-8") as log_file:
        log_file.write(f"[scheduler] starting {started}\n")
        log_file.write(f"[scheduler] command: {shlex.join(command)}\n\n")
        log_file.flush()
        completed = subprocess.run(command, stdout=log_file, stderr=subprocess.STDOUT, check=False)
        finished = datetime.now().isoformat(timespec="seconds")
        log_file.write(f"\n[scheduler] finished {finished} with exit code {completed.returncode}\n")

    print(f"[scheduler] finished with exit code {completed.returncode}", flush=True)
    return completed.returncode


def next_run_at(now: datetime) -> datetime:
    day_name = os.environ.get("SCHEDULE_DAY", "monday").strip().lower()
    target_weekday = DAYS.get(day_name)
    if target_weekday is None:
        raise RuntimeError(f"Invalid SCHEDULE_DAY '{day_name}'")

    time_value = os.environ.get("SCHEDULE_TIME", "08:00").strip()
    hour_text, minute_text = time_value.split(":", 1)
    target = now.replace(
        hour=int(hour_text),
        minute=int(minute_text),
        second=0,
        microsecond=0,
    )
    days_ahead = (target_weekday - now.weekday()) % 7
    target = target + timedelta(days=days_ahead)
    if target <= now:
        target = target + timedelta(days=7)
    return target


def run_weekly() -> int:
    timezone = ZoneInfo(os.environ.get("TZ", "America/Chicago"))
    if env_bool("RUN_ON_START"):
        run_once()

    while True:
        now = datetime.now(timezone)
        target = next_run_at(now)
        seconds = max(1, int((target - now).total_seconds()))
        print(f"[scheduler] next run at {target.isoformat(timespec='seconds')}", flush=True)
        time.sleep(seconds)
        run_once()


def main() -> int:
    mode = os.environ.get("RUN_MODE", "once").strip().lower()
    if mode == "once":
        return run_once()
    if mode == "weekly":
        return run_weekly()
    raise RuntimeError("RUN_MODE must be 'once' or 'weekly'")


if __name__ == "__main__":
    raise SystemExit(main())
