#!/usr/bin/env python3
"""Download songs from a Spotify playlist CSV using yt-dlp.

The CSV is expected to contain Spotify export columns:
Track Name, Album Name, and Artist Name(s).
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
SPACE_RUN = re.compile(r"\s+")


@dataclass
class TrackResult:
    status: str
    artists: str
    track: str
    destination: Path | None = None
    error: str | None = None

    @property
    def label(self) -> str:
        return f"{self.artists} - {self.track}"


@dataclass
class TrackMetadata:
    track: str
    artists: str
    album: str
    destination: Path
    source_url: str | None = None


def clean_path_part(value: str, fallback: str) -> str:
    value = value.strip().replace("\ufeff", "")
    value = INVALID_PATH_CHARS.sub("-", value)
    value = SPACE_RUN.sub(" ", value)
    value = value.strip(" .-_")
    return value or fallback


def clean_track_filename(track: str, artists: str) -> str:
    """Create a tidy file stem, stripping common artist prefixes/suffixes."""
    name = clean_path_part(track, "Unknown Track")

    artist_names = [
        part.strip()
        for part in re.split(r",|;|&|\bfeat\.?\b|\bft\.?\b", artists, flags=re.I)
        if part.strip()
    ]

    for artist in artist_names:
        artist_pattern = re.escape(clean_path_part(artist, artist))
        name = re.sub(rf"^\s*{artist_pattern}\s*[-_–—:]+\s*", "", name, flags=re.I)
        name = re.sub(rf"\s*[-_–—:]+\s*{artist_pattern}\s*$", "", name, flags=re.I)

    return clean_path_part(name, "Unknown Track")


def primary_artist_name(artists: str) -> str:
    """Use the first Spotify artist for folder organization."""
    primary = artists.split(";", 1)[0]
    return clean_path_part(primary, "Unknown Artist")


def build_track_metadata(
    track: str,
    artists: str,
    album: str,
    output_dir: Path,
    source_url: str | None = None,
) -> TrackMetadata:
    """Build the final artist/album/track path from Spotify metadata."""
    track = track.strip()
    artists = artists.strip()
    album = album.strip()

    artist_dir = primary_artist_name(artists)
    album_dir = clean_path_part(album, "Unknown Album")
    track_stem = clean_track_filename(track, artists)
    destination = output_dir / artist_dir / album_dir / f"{track_stem}.mp3"

    return TrackMetadata(
        track=track,
        artists=artists,
        album=album,
        destination=destination,
        source_url=source_url,
    )


def track_from_csv_row(row: dict[str, str], output_dir: Path) -> TrackMetadata:
    """Build metadata from Spotify CSV columns."""
    return build_track_metadata(
        row["Track Name"],
        row["Artist Name(s)"],
        row.get("Album Name", ""),
        output_dir,
    )


def read_tracks(csv_path: Path, output_dir: Path) -> list[TrackMetadata]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        required = {"Track Name", "Album Name", "Artist Name(s)"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise RuntimeError(
                f"{csv_path} is missing required CSV column(s): {', '.join(sorted(missing))}"
            )

        return [
            track_from_csv_row(row, output_dir)
            for row in reader
            if row.get("Track Name") and row.get("Artist Name(s)")
        ]


def parse_spotify_source(source: str) -> tuple[str, str] | None:
    if source.startswith("spotify:"):
        parts = source.split(":")
        if len(parts) >= 3 and parts[1] in {"track", "album", "playlist"}:
            return parts[1], parts[2]
        return None

    parsed = urlparse(source)
    if parsed.netloc not in {"open.spotify.com", "play.spotify.com"}:
        return None

    path_parts = [part for part in parsed.path.split("/") if part]
    if path_parts and re.fullmatch(r"intl-[a-z]{2}", path_parts[0], flags=re.I):
        path_parts = path_parts[1:]

    if len(path_parts) >= 2 and path_parts[0] in {"track", "album", "playlist"}:
        return path_parts[0], path_parts[1]

    return None


def parse_youtube_music_source(source: str) -> bool:
    parsed = urlparse(source)
    if parsed.netloc not in {
        "music.youtube.com",
        "www.music.youtube.com",
        "youtube.com",
        "www.youtube.com",
    }:
        return False

    if parsed.path == "/playlist" and "list=" in parsed.query:
        return True

    return parsed.path == "/watch" and "v=" in parsed.query


def spotify_request(url: str, token: str) -> dict:
    request = Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Spotify API error {exc.code}: {details}") from exc
    except URLError as exc:
        raise RuntimeError(f"Spotify API request failed: {exc.reason}") from exc


def get_spotify_token(client_id: str, client_secret: str) -> str:
    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    body = b"grant_type=client_credentials"
    request = Request(
        "https://accounts.spotify.com/api/token",
        data=body,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )

    try:
        with urlopen(request) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Spotify auth failed {exc.code}: {details}") from exc
    except URLError as exc:
        raise RuntimeError(f"Spotify auth failed: {exc.reason}") from exc

    return data["access_token"]


def load_spotify_credentials(args: argparse.Namespace) -> tuple[str | None, str | None]:
    client_id = args.spotify_client_id or os.environ.get("SPOTIFY_CLIENT_ID")
    client_secret = args.spotify_client_secret or os.environ.get("SPOTIFY_CLIENT_SECRET")
    return client_id, client_secret


def artist_names(artists: list[dict]) -> str:
    return ";".join(artist["name"] for artist in artists if artist.get("name"))


def metadata_from_spotify_track(track: dict, output_dir: Path) -> TrackMetadata | None:
    if not track or track.get("type") != "track" or track.get("is_local"):
        return None

    album = track.get("album") or {}
    return build_track_metadata(
        track.get("name", ""),
        artist_names(track.get("artists") or []),
        album.get("name", ""),
        output_dir,
    )


def clean_youtube_music_album_title(title: str) -> str:
    title = title.strip()
    for prefix in ("Album - ", "Playlist - "):
        if title.startswith(prefix):
            return title.removeprefix(prefix).strip()
    return title


def clean_youtube_music_artist(value: str) -> str:
    value = value.strip()
    return re.sub(r"\s+-\s+Topic$", "", value).strip()


def youtube_music_entry_url(entry: dict) -> str | None:
    if entry.get("webpage_url"):
        return entry["webpage_url"]
    if entry.get("original_url"):
        return entry["original_url"]
    if entry.get("url") and str(entry["url"]).startswith(("http://", "https://")):
        return entry["url"]
    if entry.get("id"):
        return f"https://music.youtube.com/watch?v={entry['id']}"
    return None


def metadata_from_youtube_music_entry(
    entry: dict,
    output_dir: Path,
    fallback_album: str,
) -> TrackMetadata | None:
    title = entry.get("track") or entry.get("alt_title") or entry.get("title") or ""
    title = title.strip()
    if not title or title.startswith("["):
        return None

    artists = entry.get("artists")
    if isinstance(artists, list):
        artist = ";".join(str(item) for item in artists if item)
    else:
        artist = entry.get("artist") or entry.get("creator") or entry.get("uploader") or entry.get("channel") or ""
    artist = clean_youtube_music_artist(artist)

    album = entry.get("album") or fallback_album or entry.get("playlist_title") or "YouTube Music"
    source_url = youtube_music_entry_url(entry)
    return build_track_metadata(title, artist, album, output_dir, source_url=source_url)


def read_youtube_music_url(
    source: str,
    output_dir: Path,
    cookie_args: list[str],
    metadata_limit: int | None,
) -> list[TrackMetadata]:
    cmd = [
        "yt-dlp",
        "--dump-single-json",
        "--ignore-errors",
        "--no-warnings",
        *cookie_args,
    ]
    if metadata_limit is not None:
        cmd.extend(["--playlist-end", str(metadata_limit)])
    cmd.append(source)

    completed = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if not completed.stdout.strip():
        message = completed.stderr.strip() or f"yt-dlp exited with status {completed.returncode}"
        raise RuntimeError(f"Could not read YouTube Music metadata for {source}: {message}")

    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        message = completed.stderr.strip() or f"yt-dlp exited with status {completed.returncode}"
        raise RuntimeError(f"Could not parse YouTube Music metadata for {source}: {message}") from exc
    fallback_album = clean_youtube_music_album_title(data.get("title") or "YouTube Music")
    entries = data.get("entries")
    if not entries:
        metadata = metadata_from_youtube_music_entry(data, output_dir, fallback_album)
        return [metadata] if metadata else []

    tracks = []
    for entry in entries:
        if not entry:
            continue
        metadata = metadata_from_youtube_music_entry(entry, output_dir, fallback_album)
        if metadata:
            tracks.append(metadata)

    if not tracks and completed.returncode != 0:
        message = completed.stderr.strip() or f"yt-dlp exited with status {completed.returncode}"
        if "Private video" in message or "Sign in" in message:
            message = (
                "No readable YouTube Music tracks were found. The playlist may contain private videos; "
                "try --cookies-from-browser chrome or --cookies /path/to/cookies.txt."
            )
        raise RuntimeError(f"Could not read YouTube Music metadata for {source}: {message}")

    return tracks


def read_spotify_url(source: str, output_dir: Path, token: str) -> list[TrackMetadata]:
    parsed = parse_spotify_source(source)
    if not parsed:
        raise RuntimeError(f"Not a supported Spotify share URL or URI: {source}")

    source_type, source_id = parsed
    api_base = "https://api.spotify.com/v1"

    if source_type == "track":
        track = spotify_request(f"{api_base}/tracks/{source_id}", token)
        metadata = metadata_from_spotify_track(track, output_dir)
        return [metadata] if metadata else []

    if source_type == "album":
        album = spotify_request(f"{api_base}/albums/{source_id}", token)
        album_name = album.get("name", "")
        tracks: list[TrackMetadata] = []
        next_url = f"{api_base}/albums/{source_id}/tracks?limit=50"
        while next_url:
            page = spotify_request(next_url, token)
            for track in page.get("items", []):
                tracks.append(
                    build_track_metadata(
                        track.get("name", ""),
                        artist_names(track.get("artists") or []),
                        album_name,
                        output_dir,
                    )
                )
            next_url = page.get("next")
        return tracks

    tracks = []
    next_url = f"{api_base}/playlists/{source_id}/tracks?limit=100"
    while next_url:
        page = spotify_request(next_url, token)
        for item in page.get("items", []):
            metadata = metadata_from_spotify_track(item.get("track") or {}, output_dir)
            if metadata:
                tracks.append(metadata)
        next_url = page.get("next")
    return tracks


def get_spotify_token_for_sources(sources: list[str], args: argparse.Namespace) -> str | None:
    if not any(parse_spotify_source(source) for source in sources):
        return None

    client_id, client_secret = load_spotify_credentials(args)
    if not client_id or not client_secret:
        raise RuntimeError(
            "Spotify URL mode needs credentials. Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET, "
            "or pass --spotify-client-id and --spotify-client-secret."
        )

    return get_spotify_token(client_id, client_secret)


def read_source(
    source: str,
    output_dir: Path,
    args: argparse.Namespace,
    spotify_token: str | None,
    cookie_args: list[str],
) -> list[TrackMetadata]:
    if parse_spotify_source(source):
        if not spotify_token:
            raise RuntimeError(f"Spotify token was not loaded for source: {source}")
        return read_spotify_url(source, output_dir, spotify_token)

    if parse_youtube_music_source(source):
        return read_youtube_music_url(source, output_dir, cookie_args, args.limit)

    csv_path = Path(source).expanduser().resolve()
    if not csv_path.exists():
        raise RuntimeError(f"CSV not found: {csv_path}")

    return read_tracks(csv_path, output_dir)


def read_sources(
    sources: list[str],
    output_dir: Path,
    args: argparse.Namespace,
    cookie_args: list[str],
) -> list[TrackMetadata]:
    tracks: list[TrackMetadata] = []
    spotify_token = get_spotify_token_for_sources(sources, args)

    for source in sources:
        source_tracks = read_source(source, output_dir, args, spotify_token, cookie_args)
        print(f"[source] {source}: {len(source_tracks)} track(s)")
        tracks.extend(source_tracks)

    return tracks


def build_cookie_args(args: argparse.Namespace) -> list[str]:
    cookie_args: list[str] = []

    if args.cookies_from_browser:
        cookie_args.extend(["--cookies-from-browser", args.cookies_from_browser])

    if args.cookies:
        cookie_args.extend(["--cookies", str(args.cookies.expanduser().resolve())])

    return cookie_args


def download_track(
    track: TrackMetadata,
    output_dir: Path,
    dry_run: bool,
    cookie_args: list[str],
) -> TrackResult:
    destination_dir = track.destination.parent

    query = f"ytsearch1:{track.artists} - {track.track} official audio"
    download_url = track.source_url or query

    if dry_run:
        print(f"[dry-run] {download_url} -> {track.destination}")
        return TrackResult("dry-run", track.artists, track.track, track.destination)

    if track.destination.exists():
        print(f"[skip] {track.destination}")
        return TrackResult("skipped", track.artists, track.track, track.destination)

    destination_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="spotify-yt-", dir=output_dir) as tmp:
        temp_dir = Path(tmp)
        cmd = [
            "yt-dlp",
            "--quiet",
            "--no-warnings",
            *cookie_args,
            "-x",
            "--audio-format",
            "mp3",
            "--audio-quality",
            "0",
            "-o",
            str(temp_dir / "%(title).200B [%(id)s].%(ext)s"),
            download_url,
        ]

        print(f"[download] {track.artists} - {track.track}")
        subprocess.run(cmd, check=True)

        mp3s = sorted(temp_dir.glob("*.mp3"), key=lambda item: item.stat().st_mtime, reverse=True)
        if not mp3s:
            raise RuntimeError(f"yt-dlp did not produce an mp3 for: {track.artists} - {track.track}")

        shutil.move(str(mp3s[0]), track.destination)
        print(f"[saved] {track.destination}")
        return TrackResult("downloaded", track.artists, track.track, track.destination)


def print_summary(results: list[TrackResult]) -> None:
    downloaded = [result for result in results if result.status == "downloaded"]
    skipped = [result for result in results if result.status == "skipped"]
    dry_runs = [result for result in results if result.status == "dry-run"]
    failed = [result for result in results if result.status == "failed"]

    print("\nSummary")
    print(f"  Downloaded: {len(downloaded)}")
    print(f"  Skipped:    {len(skipped)}")
    print(f"  Dry runs:   {len(dry_runs)}")
    print(f"  Failed:     {len(failed)}")

    def print_result_group(title: str, group: list[TrackResult], include_error: bool = False) -> None:
        if not group:
            return

        print(f"\n{title}")
        for result in group:
            if result.destination:
                print(f"  - {result.label} -> {result.destination}")
            else:
                print(f"  - {result.label}")

            if include_error and result.error:
                print(f"    error: {result.error}")

    print_result_group("Downloaded", downloaded)
    print_result_group("Skipped", skipped)
    print_result_group("Dry Run", dry_runs)
    print_result_group("Failed", failed, include_error=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Spotify CSVs/URLs and YouTube Music albums/playlists from YouTube.",
        epilog=(
            "Examples:\n"
            "  ./downloader.py playlist1.csv playlist2.csv\n"
            "  ./downloader.py 'https://open.spotify.com/track/...' "
            "'https://open.spotify.com/album/...'\n"
            "  ./downloader.py playlist.csv 'https://open.spotify.com/playlist/...'\n"
            "  ./downloader.py 'https://music.youtube.com/playlist?list=...'"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "sources",
        nargs="+",
        help="Spotify CSV path(s), Spotify URL(s), or YouTube Music album/playlist URL(s).",
    )
    parser.add_argument("-o", "--output-dir", default=Path("Music"), type=Path)
    parser.add_argument("--limit", type=int, help="Download only the first N tracks.")
    parser.add_argument("--dry-run", action="store_true", help="Show searches and output paths without downloading.")
    parser.add_argument(
        "--cookies-from-browser",
        metavar="BROWSER",
        help="Use browser cookies for YouTube, for example: chrome, safari, firefox, edge, brave.",
    )
    parser.add_argument(
        "--cookies",
        type=Path,
        help="Use a cookies.txt file for YouTube authentication.",
    )
    parser.add_argument(
        "--spotify-client-id",
        help="Spotify API client ID. Defaults to SPOTIFY_CLIENT_ID.",
    )
    parser.add_argument(
        "--spotify-client-secret",
        help="Spotify API client secret. Defaults to SPOTIFY_CLIENT_SECRET.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()

    if shutil.which("yt-dlp") is None and not args.dry_run:
        print("yt-dlp is not installed or is not on PATH.", file=sys.stderr)
        return 1

    if args.cookies_from_browser and args.cookies:
        print("Use either --cookies-from-browser or --cookies, not both.", file=sys.stderr)
        return 1

    cookie_args = build_cookie_args(args)

    try:
        tracks = read_sources(args.sources, output_dir, args, cookie_args)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1

    if args.limit is not None:
        tracks = tracks[: args.limit]

    results: list[TrackResult] = []
    for index, track in enumerate(tracks, start=1):
        try:
            print(f"\n[{index}/{len(tracks)}]")
            results.append(download_track(track, output_dir, args.dry_run, cookie_args))
        except (RuntimeError, subprocess.CalledProcessError) as exc:
            error = str(exc)
            results.append(TrackResult("failed", track.artists, track.track, track.destination, error=error))
            print(f"[error] {error}", file=sys.stderr)

    print_summary(results)

    if any(result.status == "failed" for result in results):
        return 1

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
