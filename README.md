# Spotify / YouTube Music MP3 Downloader

Small script for turning Spotify exports, Spotify links, and YouTube Music links into organized MP3 files using `yt-dlp`.

Output goes here by default:

```text
Music/Artist/Album/Track.mp3
```

If a track has featured artists, only the first artist is used for the artist folder. Example:

```text
Noah Kahan;Post Malone -> Music/Noah Kahan/...
```

The full artist list is still used for Spotify CSV/URL YouTube searches.

## Requirements

Install `yt-dlp` and make sure it is on your `PATH`.

```bash
yt-dlp --version
```

The script uses Python standard library only. No Python package install is needed.

## Basic Usage

Pass one or more sources:

```bash
./downloader.py playlist.csv
./downloader.py playlist1.csv playlist2.csv
```

Preview without downloading:

```bash
./downloader.py playlist.csv --dry-run --limit 5
```

Write somewhere other than `Music/`:

```bash
./downloader.py playlist.csv --output-dir /path/to/output
```

## Supported Inputs

Spotify CSV exports:

```bash
./downloader.py playlist.csv
```

Multiple CSVs:

```bash
./downloader.py one.csv two.csv three.csv
```

Spotify track, album, or playlist URLs:

```bash
./downloader.py "https://open.spotify.com/track/..."
./downloader.py "https://open.spotify.com/album/..."
./downloader.py "https://open.spotify.com/playlist/..."
```

Spotify URIs:

```bash
./downloader.py "spotify:album:..."
```

YouTube Music albums/playlists:

```bash
./downloader.py "https://music.youtube.com/playlist?list=..."
```

Mixed sources are fine:

```bash
./downloader.py \
  playlist.csv \
  "https://open.spotify.com/album/..." \
  "https://music.youtube.com/playlist?list=..."
```

## Spotify URL Credentials

CSV mode does not need Spotify credentials.

Spotify URL mode does. Set these in the environment that runs the script:

```bash
export SPOTIFY_CLIENT_ID="..."
export SPOTIFY_CLIENT_SECRET="..."
```

Or pass them directly:

```bash
./downloader.py "https://open.spotify.com/playlist/..." \
  --spotify-client-id "$SPOTIFY_CLIENT_ID" \
  --spotify-client-secret "$SPOTIFY_CLIENT_SECRET"
```

The script does not parse your shell files. If credentials are in `~/.zshrc`, run from a terminal that has loaded them:

```bash
source ~/.zshrc
env | grep SPOTIFY
```

## YouTube Cookies

If YouTube says you need to sign in, or a YouTube Music playlist has private entries, use cookies:

```bash
./downloader.py playlist.csv --cookies-from-browser chrome
```

Other examples:

```bash
./downloader.py "https://music.youtube.com/playlist?list=..." --cookies-from-browser safari
./downloader.py "https://music.youtube.com/playlist?list=..." --cookies /path/to/cookies.txt
```

Do not commit cookie files.

## Reruns / Skips

The script checks the final destination before downloading.

If this exists:

```text
Music/Yazoo/Upstairs At Eric's/Only You.mp3
```

that track is skipped on future runs.

This means you can fix cookies, rerun a large batch, and it will continue without redownloading completed files.

## How Downloads Are Found

Spotify CSV and Spotify URL inputs:

```text
ytsearch1:Artist - Track official audio
```

YouTube Music inputs:

```text
Uses the exact track URL from the YouTube Music album/playlist metadata.
```

## End Summary

Every run prints counts and details for:

```text
Downloaded
Skipped
Dry runs
Failed
```

Failures include the error message so you can rerun after fixing cookies or credentials.

## Ignored Files

`.gitignore` excludes:

```text
Music/
csv/
*.csv
cookies.txt
*.cookies.txt
__pycache__/
.DS_Store
```
