# Spotify / YouTube Music MP3 Downloader

Small script for turning Spotify exports, Spotify links, YouTube Music links, and ListenBrainz playlists into organized MP3 files using `yt-dlp`.

Output goes here by default:

```text
Music/Artist/Album/Track.mp3
```

If a track has featured artists, only the first artist is used for the artist folder. Example:

```text
Noah Kahan;Post Malone -> Music/Noah Kahan/...
Daft Punk feat. Pharrell Williams & Nile Rodgers -> Music/Daft Punk/...
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

## Full Examples

Preview the current ListenBrainz curated playlist for `joebrothehobo` without downloading:

```bash
cd /Users/joeroskopf/Code/MDL/MDL

./downloader.py listenbrainz:joebrothehobo \
  --dry-run \
  --limit 10
```

Download the current ListenBrainz curated playlist into the local default `Music/` folder:

```bash
cd /Users/joeroskopf/Code/MDL/MDL

./downloader.py listenbrainz:joebrothehobo
```

Download the current ListenBrainz curated playlist to the NAS folder that Plex scans, refresh Plex section `2`, translate the Mac NAS path to Plex's `/data/Music` path, and replace matching Plex playlists:

```bash
cd /Users/joeroskopf/Code/MDL/MDL

./downloader.py listenbrainz:joebrothehobo \
  --output-dir /Volumes/storage-share/Music \
  --plex-section-id 2 \
  --plex-path-map /Volumes/storage-share/Music=/data/Music \
  --plex-replace-playlists
```

Run the same ListenBrainz to Plex flow, but inspect only the first 5 tracks:

```bash
cd /Users/joeroskopf/Code/MDL/MDL

./downloader.py listenbrainz:joebrothehobo \
  --output-dir /Volumes/storage-share/Music \
  --plex-section-id 2 \
  --plex-path-map /Volumes/storage-share/Music=/data/Music \
  --plex-replace-playlists \
  --dry-run \
  --limit 5
```

Use stricter YouTube matching by searching more candidates and requiring a higher score:

```bash
./downloader.py listenbrainz:joebrothehobo \
  --output-dir /Volumes/storage-share/Music \
  --youtube-search-results 15 \
  --youtube-min-score 70
```

Download one specific ListenBrainz playlist by MBID:

```bash
./downloader.py listenbrainz:playlist:ba47bea7-56fe-4729-8b63-a50afa04c6ba \
  --output-dir /Volumes/storage-share/Music
```

Download from a Spotify playlist URL:

```bash
export SPOTIFY_CLIENT_ID="..."
export SPOTIFY_CLIENT_SECRET="..."

./downloader.py "https://open.spotify.com/playlist/..." \
  --output-dir /Volumes/storage-share/Music
```

Download from a YouTube Music playlist, using browser cookies if YouTube needs authentication:

```bash
./downloader.py "https://music.youtube.com/playlist?list=..." \
  --output-dir /Volumes/storage-share/Music \
  --cookies-from-browser safari
```

Download from a Spotify CSV export:

```bash
./downloader.py playlist.csv \
  --output-dir /Volumes/storage-share/Music
```

Download mixed sources in one run:

```bash
./downloader.py \
  playlist.csv \
  listenbrainz:joebrothehobo \
  "https://open.spotify.com/album/..." \
  "https://music.youtube.com/playlist?list=..." \
  --output-dir /Volumes/storage-share/Music
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

ListenBrainz curated playlists created for a user:

```bash
./downloader.py listenbrainz:joebrothehobo
```

For `listenbrainz:USERNAME`, the script fetches ListenBrainz `createdfor` playlists and keeps the current `weekly-exploration` playlist. Plex playlist names are normalized to:

```text
Weekly Playlist YYYY-MM-DD
```

Example:

```text
Weekly Playlist 2026-05-05
```

Specific ListenBrainz playlists:

```bash
./downloader.py listenbrainz:playlist:ba47bea7-56fe-4729-8b63-a50afa04c6ba
./downloader.py "https://listenbrainz.org/playlist/ba47bea7-56fe-4729-8b63-a50afa04c6ba"
```

Mixed sources are fine:

```bash
./downloader.py \
  playlist.csv \
  "https://open.spotify.com/album/..." \
  "https://music.youtube.com/playlist?list=..."
```

## Plex Sync

If the output directory is inside a Plex music library, the script can ask Plex to refresh that library and create audio playlists matching ListenBrainz playlist titles.

Set your Plex server URL and token:

```bash
export PLEX_URL="http://localhost:32400"
export PLEX_TOKEN="..."
```

Or put them in a local `.env` file. The script loads `.env` automatically, and `.env` is ignored by git.

Then run:

```bash
./downloader.py listenbrainz:joebrothehobo \
  --output-dir /path/to/plex/Music \
  --plex-section-id 2 \
  --plex-replace-playlists
```

If Plex sees a different path than your local machine does, add a path map:

```bash
./downloader.py listenbrainz:joebrothehobo \
  --output-dir /Users/me/Music \
  --plex-section-id 2 \
  --plex-path-map /Users/me/Music=/music
```

`--plex-replace-playlists` deletes and recreates a matching Plex audio playlist. Without it, existing playlists are left alone.

If Plex is slow to index new NAS files, increase the scan/match waits:

```bash
./downloader.py listenbrainz:joebrothehobo \
  --output-dir /Volumes/storage-share/Music \
  --plex-section-id 2 \
  --plex-path-map /Volumes/storage-share/Music=/data/Music \
  --plex-scan-wait 120 \
  --plex-match-retries 5 \
  --plex-match-wait 60 \
  --plex-replace-playlists
```

Those retry settings are useful when downloads finish quickly but Plex has not indexed every new track yet.

When Plex matches a downloaded track, the script also updates and locks the Plex track title to the downloaded metadata title. This avoids cases where Plex guesses the wrong album track, such as showing `Royals.mp3` as `Tennis Court` because of stale or inferred album metadata.

Disable that behavior with:

```bash
./downloader.py listenbrainz:joebrothehobo \
  --output-dir /Volumes/storage-share/Music \
  --plex-section-id 2 \
  --plex-path-map /Volumes/storage-share/Music=/data/Music \
  --no-plex-lock-track-titles
```

## Docker / TrueNAS Weekly Run

The Docker setup can run in two modes:

```text
RUN_MODE=once    Run one job and exit. Good for testing.
RUN_MODE=weekly  Stay running and run once per week.
```

The scheduler writes each run to stdout and to a timestamped log file in `/logs`:

```text
/logs/mdl-YYYYMMDD-HHMMSS.log
```

### TrueNAS SCALE Setup

These commands assume TrueNAS SCALE with Docker Compose available from the TrueNAS shell. Replace `POOL` with your actual pool name. Your Mac path `/Volumes/storage-share/Music` will usually be a TrueNAS path like `/mnt/POOL/storage-share/Music` when running on the NAS.

Copy or clone this repo somewhere on TrueNAS, for example:

```bash
mkdir -p /mnt/POOL/apps
cd /mnt/POOL/apps
git clone <this-repo-url> mdl
cd mdl
```

If you copied the folder manually instead of using git, just `cd` into that copied folder.

Create a log folder:

```bash
mkdir -p /mnt/POOL/storage-share/mdl-logs
```

Create your compose file from the example:

```bash
cp docker-compose.example.yml docker-compose.yml
```

Edit `docker-compose.yml`:

```yaml
volumes:
  - /mnt/POOL/storage-share/Music:/music
  - /mnt/POOL/storage-share/mdl-logs:/logs
```

Set your Plex values:

```yaml
PLEX_URL: http://192.168.86.43:32400
PLEX_TOKEN: your-token-here
PLEX_SECTION_ID: "2"
PLEX_PATH_MAP: /music=/data/Music
```

Keep `PLEX_PATH_MAP: /music=/data/Music` if this downloader container sees the music folder as `/music` and Plex sees the same files as `/data/Music`.

Build the image:

```bash
docker compose build
```

Test with a dry run:

```bash
docker compose run --rm \
  -e RUN_MODE=once \
  -e DRY_RUN=true \
  -e LIMIT=5 \
  mdl
```

Run one real test track:

```bash
docker compose run --rm \
  -e RUN_MODE=once \
  -e DRY_RUN=false \
  -e LIMIT=1 \
  mdl
```

Start the weekly scheduler:

```bash
docker compose up -d
```

Watch container logs:

```bash
docker logs -f mdl-listenbrainz
```

List saved run logs:

```bash
ls -lh /mnt/POOL/storage-share/mdl-logs
```

Read the newest run log:

```bash
tail -n 200 /mnt/POOL/storage-share/mdl-logs/$(ls -1 /mnt/POOL/storage-share/mdl-logs | sort | tail -1)
```

Stop the weekly scheduler:

```bash
docker compose down
```

### Weekly Schedule Settings

The example compose file runs every Monday at `08:00` in `America/Chicago`:

```yaml
RUN_MODE: weekly
TZ: America/Chicago
SCHEDULE_DAY: monday
SCHEDULE_TIME: "08:00"
```

To run immediately when the container starts and then continue weekly:

```yaml
RUN_ON_START: "true"
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

## MP3 Metadata

New downloads are tagged with ID3 metadata before they are saved.

The script writes every field it knows:

```text
Title, artist, album artist, album, year, track number, source URL, and embedded artwork
```

Spotify URL inputs usually provide the richest tags because the Spotify API includes release dates, track numbers, and album artwork. YouTube Music inputs use metadata and thumbnails reported by `yt-dlp`. CSV inputs always include title, artist, and album; if your CSV also has columns like `Release Date`, `Year`, `Track Number`, `Album Image URL`, or `Artwork URL`, those are used too.

## How Downloads Are Found

Spotify CSV, Spotify URL, and ListenBrainz inputs:

```text
ytsearch10:Artist - Track Album
```

For metadata-only sources, the script scores YouTube candidates before downloading. It prefers results that match the artist, title, album, and duration, and penalizes likely wrong versions such as live, cover, karaoke, lyric, remix, sped up, or instrumental uploads.

If ListenBrainz provides a duration, YouTube candidates more than 10 seconds away from that duration are rejected. This avoids official videos with long intros, outros, or extra scenes.

Tune the matching behavior with:

```bash
./downloader.py listenbrainz:joebrothehobo \
  --youtube-search-results 15 \
  --youtube-min-score 60
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
.env
cookies.txt
*.cookies.txt
__pycache__/
.DS_Store
```
