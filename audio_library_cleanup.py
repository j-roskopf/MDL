#!/usr/bin/env python3
"""Clean up audio library tags and misplaced playlist albums.

This script recursively scans a directory for audio files, then:

* repairs files whose album tag contains "Indie/Rock Playlist"
* repairs files whose album tag contains an SXSW showcase placeholder
* copies the artist tag into album artist when album artist is Various Artists

Changes are previewed by default. Pass --apply to move files and write tags.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

try:
    from mutagen import File
except ImportError:  # pragma: no cover - exercised by users without mutagen installed
    File = None


AUDIO_EXTENSIONS = {
    ".aac",
    ".aiff",
    ".alac",
    ".ape",
    ".flac",
    ".m4a",
    ".m4b",
    ".mp3",
    ".mp4",
    ".oga",
    ".ogg",
    ".opus",
    ".wav",
    ".wma",
}
DEFAULT_DELETE_ALBUM_TEXT = "Indie/Rock Playlist"
INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
SPACE_RUN = re.compile(r"\s+")
WORD_CHARS = re.compile(r"[^a-z0-9]+")
DATE_LIKE_ALBUM = re.compile(r"\b(?:19|20)\d{2}[-./]\d{1,2}[-./]\d{1,2}\b")
BAD_RELEASE_WORDS = {"bootleg", "concert", "festival", "live", "session", "sessions"}
IGNORABLE_FOLDER_FILENAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
IGNORABLE_FOLDER_SUFFIXES = {".nfo"}


@dataclass
class ScanStats:
    folders_visited: int = 0
    scanned: int = 0
    unreadable: int = 0
    playlist_album_matches: int = 0
    sxsw_album_matches: int = 0
    album_repairs: int = 0
    album_repair_skips: int = 0
    tag_updates: int = 0
    skipped_updates: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def repair_matches(self) -> int:
        return self.playlist_album_matches + self.sxsw_album_matches

    @property
    def planned_or_applied_changes(self) -> int:
        return self.album_repairs + self.tag_updates


@dataclass(frozen=True)
class AlbumLookup:
    album: str
    artist: str | None = None
    title: str | None = None
    source: str = ""
    score: int = 0


def normalized_text(value: str) -> str:
    value = value.strip().casefold()
    return SPACE_RUN.sub(" ", value)


def normalized_words(value: str) -> set[str]:
    return {word for word in WORD_CHARS.split(value.casefold()) if word}


def compact_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def album_text_matches(album: str, target: str) -> bool:
    return normalized_text(target) in normalized_text(album) or compact_text(target) in compact_text(album)


def is_sxsw_showcase_album(value: str) -> bool:
    compact = compact_text(value)
    return "sxsw" in compact and (
        "showcastingartists" in compact or "showcasingartists" in compact
    )


def clean_path_part(value: str, fallback: str) -> str:
    value = value.strip().replace("\ufeff", "")
    value = INVALID_PATH_CHARS.sub("-", value)
    value = SPACE_RUN.sub(" ", value)
    value = value.strip(" .-_")
    return value or fallback


def looks_like_non_canonical_release(value: str) -> bool:
    words = normalized_words(value)
    return bool(BAD_RELEASE_WORDS.intersection(words) or DATE_LIKE_ALBUM.search(value))


def is_various_artists(value: str) -> bool:
    return compact_text(value) in {"variousartist", "variousartists", "va"}


def tag_values(audio: object, keys: tuple[str, ...]) -> list[str]:
    tags = getattr(audio, "tags", None)
    if not tags:
        return []

    values: list[str] = []
    for key in keys:
        raw_values = tags.get(key)
        if raw_values is None:
            continue
        if isinstance(raw_values, str):
            raw_values = [raw_values]
        for raw_value in raw_values:
            text = str(raw_value).strip()
            if text:
                values.append(text)
    return values


def first_tag_value(audio: object, keys: tuple[str, ...]) -> str | None:
    values = tag_values(audio, keys)
    return values[0] if values else None


def valid_artist_values(values: list[str]) -> list[str]:
    return [
        value
        for value in values
        if value.strip()
        and not is_various_artists(value)
        and normalized_text(value) != "unknown artist"
    ]


def read_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def json_request(url: str, headers: dict[str, str] | None = None, data: bytes | None = None) -> dict:
    request = Request(url, headers=headers or {}, data=data)
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"lookup request failed for {url}: {exc}") from exc


def spotify_token() -> str | None:
    client_id = os.environ.get("SPOTIFY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None

    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    data = json_request(
        "https://accounts.spotify.com/api/token",
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data=b"grant_type=client_credentials",
    )
    return str(data["access_token"])


def lookup_album_spotify(artist: str, title: str, limit: int, token: str | None) -> AlbumLookup | None:
    if not token:
        return None

    query = quote(f'track:"{title}" artist:"{artist}"')
    data = json_request(
        f"https://api.spotify.com/v1/search?q={query}&type=track&limit={limit}",
        headers={"Authorization": f"Bearer {token}"},
    )
    best: AlbumLookup | None = None
    for item in ((data.get("tracks") or {}).get("items") or []):
        candidate_title = str(item.get("name") or "").strip()
        album = item.get("album") or {}
        album_name = str(album.get("name") or "").strip()
        artist_names = [str(value.get("name") or "").strip() for value in item.get("artists") or []]
        artist_names = [value for value in artist_names if value]
        if not candidate_title or not album_name or not artist_names:
            continue

        title_ok = normalized_text(candidate_title) == normalized_text(title)
        artist_ok = any(normalized_text(value) == normalized_text(artist) for value in artist_names)
        if not (title_ok and artist_ok):
            continue

        score = 100
        lookup = AlbumLookup(album=album_name, artist=artist_names[0], title=candidate_title, source="spotify", score=score)
        if best is None or lookup.score > best.score:
            best = lookup
    return best


def musicbrainz_artist_credit(recording: dict) -> str:
    return "".join(
        f"{credit.get('name', '')}{credit.get('joinphrase', '')}"
        for credit in recording.get("artist-credit") or []
        if isinstance(credit, dict)
    ).strip()


def musicbrainz_release_score(release: dict, artist: str) -> int:
    score = 0
    status = str(release.get("status") or "")
    if status == "Official":
        score += 20

    release_group = release.get("release-group") or {}
    primary_type = str(release_group.get("primary-type") or "")
    if primary_type == "Album":
        score += 30
    elif primary_type in {"EP", "Single"}:
        score += 20
    elif primary_type:
        score += 5

    release_artist = musicbrainz_artist_credit(release)
    if normalized_text(release_artist) == normalized_text(artist):
        score += 30
    elif release_artist and normalized_text(release_artist) != "various artists":
        score += 10
    else:
        score -= 20

    return score


def lookup_album_musicbrainz(artist: str, title: str, limit: int) -> AlbumLookup | None:
    query = quote(f'recording:"{title}" AND artist:"{artist}"')
    data = json_request(
        f"https://musicbrainz.org/ws/2/recording/?query={query}&fmt=json&limit={limit}",
        headers={"User-Agent": "MDL audio-library-cleanup/1.0 (https://github.com/)"},
    )

    best: AlbumLookup | None = None
    for recording in data.get("recordings") or []:
        candidate_title = str(recording.get("title") or "").strip()
        candidate_artist = musicbrainz_artist_credit(recording)
        if normalized_text(candidate_title) != normalized_text(title):
            continue
        if normalized_text(candidate_artist) != normalized_text(artist):
            continue

        search_score = int(recording.get("score") or 0)
        if search_score < 95:
            continue

        for release in recording.get("releases") or []:
            album = str(release.get("title") or "").strip()
            if not album:
                continue
            if looks_like_non_canonical_release(album):
                continue
            score = search_score + musicbrainz_release_score(release, artist)
            lookup = AlbumLookup(
                album=album,
                artist=candidate_artist,
                title=candidate_title,
                source="musicbrainz",
                score=score,
            )
            if best is None or lookup.score > best.score:
                best = lookup
    return best


def lookup_album_itunes(artist: str, title: str, limit: int) -> AlbumLookup | None:
    search_term = f"{artist} {title}"
    params = urlencode(
        {
            "term": search_term,
            "media": "music",
            "entity": "song",
            "limit": limit,
        }
    )
    data = json_request(
        f"https://itunes.apple.com/search?{params}",
        headers={"User-Agent": "MDL audio-library-cleanup/1.0"},
    )

    best: AlbumLookup | None = None

    for item in data.get("results") or []:
        album = str(item.get("collectionName") or "").strip()
        candidate_title = str(item.get("trackName") or "").strip()
        candidate_artist = str(item.get("artistName") or "").strip()
        if not album or not candidate_title or not candidate_artist:
            continue

        if normalized_text(candidate_title) != normalized_text(title):
            continue
        if normalized_text(candidate_artist) != normalized_text(artist):
            continue

        score = 100

        if item.get("wrapperType") == "track" and item.get("kind") == "song":
            score += 5

        lookup = AlbumLookup(album=album, artist=candidate_artist, title=candidate_title, source="itunes", score=score)
        if best is None or lookup.score > best.score:
            best = lookup

    return best


def lookup_album(artist: str, title: str, limit: int, spotify_access_token: str | None) -> AlbumLookup | None:
    providers = []
    if spotify_access_token:
        providers.append(("spotify", lambda: lookup_album_spotify(artist, title, limit, spotify_access_token)))
    providers.extend(
        [
            ("itunes", lambda: lookup_album_itunes(artist, title, limit)),
            ("musicbrainz", lambda: lookup_album_musicbrainz(artist, title, limit)),
        ]
    )

    for provider_name, provider in providers:
        try:
            lookup = provider()
        except RuntimeError as exc:
            print(f"lookup warning: {provider_name} failed for {artist!r} - {title!r}: {exc}", flush=True)
            continue
        if lookup:
            return lookup

    return None


def load_audio(path: Path) -> object | None:
    if File is None:
        raise RuntimeError("Missing dependency: install mutagen with `python3 -m pip install mutagen`")
    return File(path, easy=True)


def is_ignorable_folder_file(path: Path) -> bool:
    return (
        path.is_file()
        and (path.name in IGNORABLE_FOLDER_FILENAMES or path.suffix.casefold() in IGNORABLE_FOLDER_SUFFIXES)
    )


def remove_old_folder(start: Path, stop: Path, apply: bool) -> None:
    stop = stop.resolve()
    start = start.resolve()
    if start == stop or stop not in start.parents:
        return

    print(f"{'DELETE' if apply else 'would delete'} old folder {start}")
    if apply:
        shutil.rmtree(start)

    current = start.parent
    while current != stop and stop in current.resolve().parents:
        ignorable = [path for path in current.iterdir() if is_ignorable_folder_file(path)]
        visible_entries = [path for path in current.iterdir() if path not in ignorable]
        if visible_entries:
            shown = ", ".join(path.name for path in visible_entries[:5])
            extra = "" if len(visible_entries) <= 5 else f", and {len(visible_entries) - 5} more"
            print(f"keep folder {current} (still contains: {shown}{extra})")
            return

        for path in ignorable:
            if apply:
                path.unlink()
            else:
                print(f"would remove ignorable file {path}")

        print(f"{'REMOVE' if apply else 'would remove'} empty folder {current}")
        try:
            if apply:
                current.rmdir()
        except OSError:
            return
        current = current.parent


def unique_destination(path: Path) -> Path:
    if not path.exists():
        return path

    for index in range(1, 1000):
        candidate = path.with_name(f"{path.stem} ({index}){path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"could not find an unused destination for {path}")


def repair_playlist_album(
    path: Path,
    audio: object,
    root: Path,
    apply: bool,
    lookup_limit: int,
    spotify_access_token: str | None,
    stats: ScanStats,
    reason: str,
) -> None:
    title = first_tag_value(audio, ("title",)) or path.stem
    artists = valid_artist_values(tag_values(audio, ("artist",)))
    if not artists:
        artists = valid_artist_values(tag_values(audio, ("albumartist",)))
    artist = artists[0] if artists else None
    if not title:
        stats.album_repair_skips += 1
        print(f"skip {path} ({reason}, but title tag is missing/invalid)")
        return
    if not artist:
        stats.album_repair_skips += 1
        print(f"skip {path} ({reason}, but artist tag is missing/invalid; refusing title-only lookup)")
        return

    try:
        lookup = lookup_album(artist, title, lookup_limit, spotify_access_token)
    except RuntimeError as exc:
        stats.album_repair_skips += 1
        stats.errors.append(f"{path}: {exc}")
        return

    if not lookup:
        stats.album_repair_skips += 1
        query = f"{artist} - {title}" if artist else title
        print(f"skip {path} (no album lookup match for {query!r})")
        return

    album_dir = clean_path_part(lookup.album, "Unknown Album")
    destination_dir = path.parent.parent / album_dir
    destination = unique_destination(destination_dir / path.name)
    stats.album_repairs += 1
    print(
        f"{'REPAIR' if apply else 'would repair'} {path} "
        f"({reason}; {lookup.source}: {lookup.artist} - {lookup.title}; album: {lookup.album!r}, "
        f"move to: {destination})"
    )

    if apply:
        try:
            audio["album"] = [lookup.album]
            audio.save()
            destination.parent.mkdir(parents=True, exist_ok=True)
            path.rename(destination)
            remove_old_folder(path.parent, root, apply)
        except Exception as exc:
            stats.errors.append(f"{path}: could not repair and move: {exc}")


def repair_various_album_artist(path: Path, audio: object, apply: bool, stats: ScanStats) -> None:
    album_artists = tag_values(audio, ("albumartist",))
    artists = valid_artist_values(tag_values(audio, ("artist",)))
    if not (album_artists and all(is_various_artists(value) for value in album_artists)):
        return

    if artists:
        stats.tag_updates += 1
        print(
            f"{'UPDATE' if apply else 'would update'} {path} "
            f"(albumartist: {album_artists!r} -> {artists!r})"
        )
        if apply:
            try:
                audio["albumartist"] = artists
                audio.save()
            except Exception as exc:
                stats.errors.append(f"{path}: could not save tags: {exc}")
    else:
        stats.skipped_updates += 1
        print(f"skip {path} (albumartist is Various Artists, but artist tag is missing/invalid)")


def process_file(
    path: Path,
    root: Path,
    playlist_album_text: str,
    apply: bool,
    lookup_limit: int,
    spotify_access_token: str | None,
    stats: ScanStats,
) -> None:
    try:
        audio = load_audio(path)
    except Exception as exc:
        stats.unreadable += 1
        stats.errors.append(f"{path}: could not read tags: {exc}")
        return

    if audio is None:
        stats.unreadable += 1
        stats.errors.append(f"{path}: unsupported or unreadable audio file")
        return

    stats.scanned += 1
    album = first_tag_value(audio, ("album",))
    repair_various_album_artist(path, audio, apply, stats)

    if album and album_text_matches(album, playlist_album_text):
        stats.playlist_album_matches += 1
        repair_playlist_album(
            path,
            audio,
            root,
            apply,
            lookup_limit,
            spotify_access_token,
            stats,
            "playlist album",
        )
    elif album and is_sxsw_showcase_album(album):
        stats.sxsw_album_matches += 1
        repair_playlist_album(
            path,
            audio,
            root,
            apply,
            lookup_limit,
            spotify_access_token,
            stats,
            "SXSW showcase album",
        )


def iter_audio_files(root: Path, directory_progress_every: int, stats: ScanStats):
    for current_root, _, filenames in os.walk(root):
        stats.folders_visited += 1
        current_path = Path(current_root)
        if directory_progress_every and stats.folders_visited % directory_progress_every == 0:
            print(f"progress: visited {stats.folders_visited} folder(s); current: {current_path}", flush=True)

        for filename in filenames:
            path = current_path / filename
            if path.suffix.casefold() in AUDIO_EXTENSIONS:
                yield path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recursively clean audio tags and repair misplaced playlist albums."
    )
    parser.add_argument("directory", type=Path, help="Directory to scan recursively.")
    parser.add_argument(
        "--playlist-album-text",
        "--delete-album-text",
        dest="playlist_album_text",
        default=DEFAULT_DELETE_ALBUM_TEXT,
        help=f"Repair audio files whose album tag contains this text. Default: {DEFAULT_DELETE_ALBUM_TEXT!r}.",
    )
    parser.add_argument(
        "--lookup-limit",
        type=int,
        default=10,
        help="Number of lookup candidates to inspect for each playlist-album track. Default: 10.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually move files and write tag updates. Without this, only preview changes.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=250,
        help="Print progress after this many audio files are scanned. Use 0 to disable. Default: 250.",
    )
    parser.add_argument(
        "--directory-progress-every",
        type=int,
        default=100,
        help="Print progress after this many folders are visited while discovering files. Use 0 to disable. Default: 100.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = args.directory.expanduser().resolve()
    if not root.is_dir():
        raise RuntimeError(f"{root} is not a directory")

    stats = ScanStats()
    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"{mode}: scanning {root}", flush=True)
    read_dotenv(Path(__file__).resolve().parent / ".env")
    try:
        access_token = spotify_token()
    except RuntimeError as exc:
        access_token = None
        print(f"Spotify lookup unavailable: {exc}", flush=True)
    if access_token:
        print("Using Spotify lookup first, then strict iTunes, then filtered MusicBrainz fallback.", flush=True)
    else:
        print("Using strict iTunes lookup first, then filtered MusicBrainz fallback.", flush=True)

    print("Walking folders and processing audio files as they are found...", flush=True)
    for path in iter_audio_files(root, args.directory_progress_every, stats):
        process_file(path, root, args.playlist_album_text, args.apply, args.lookup_limit, access_token, stats)
        if args.progress_every and stats.scanned % args.progress_every == 0:
            print(f"progress: scanned {stats.scanned} audio file(s); current: {path}", flush=True)

    print()
    print("Summary")
    print(f"Total folders visited: {stats.folders_visited}")
    print(f"Total audio files scanned: {stats.scanned}")
    print(f"Total repair matches: {stats.repair_matches}")
    print(f"Total changes {'applied' if args.apply else 'planned'}: {stats.planned_or_applied_changes}")
    print(f"Total skips/errors: {stats.unreadable + stats.album_repair_skips + stats.skipped_updates + len(stats.errors)}")
    print()
    print("Breakdown")
    print(f"Unreadable/skipped audio files: {stats.unreadable}")
    print(f"Playlist album matches: {stats.playlist_album_matches}")
    print(f"SXSW album matches: {stats.sxsw_album_matches}")
    print(f"Album repairs {'applied' if args.apply else 'planned'}: {stats.album_repairs}")
    print(f"Album repair skips: {stats.album_repair_skips}")
    print(f"Album artist updates {'applied' if args.apply else 'planned'}: {stats.tag_updates}")
    print(f"Album artist update skips: {stats.skipped_updates}")
    print(f"Errors: {len(stats.errors)}")

    if stats.errors:
        print()
        print("Errors:")
        for error in stats.errors:
            print(f"- {error}")

    return 1 if stats.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
