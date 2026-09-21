# NoteFrame

**Keep what’s on the board.**

Paste a YouTube link and turn the actual visible handwriting, slides, diagrams and code into a visual notebook. Browse a gallery, switch to reading mode, jump back to the original video, or save timestamped PDFs.

NoteFrame runs on your computer. It does not need an AI API key, generate summaries, or send your extracted notes to a hosted service.

## Start locally

You need **Python 3.11+**, **FFmpeg** (including `ffprobe`), and **Node.js 22+** or a supported Deno runtime on your `PATH`. Node/Deno lets yt-dlp handle YouTube's JavaScript challenges. See the [yt-dlp runtime guide](https://github.com/yt-dlp/yt-dlp/wiki/EJS).

```powershell
git clone https://github.com/Kartikeya-trivedi/noteframe.git
cd noteframe
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m noteframe serve
```

Open **http://127.0.0.1:8767**. On subsequent runs, `./start.ps1` starts the Windows app. Stop the server with `Ctrl+C`.

On macOS/Linux, activate with `source .venv/bin/activate`, install with `python -m pip install -e .`, and run `python -m noteframe serve`.

## From link to notebook

1. Paste an individual YouTube video link. Share links, `/watch`, `/shorts`, `/live` recordings and `/embed` URLs are supported; playlists are not downloaded.
2. Choose a preset and 720p or 1080p quality.
3. Watch the download, capture, selection and export stages. You can queue up to five jobs, cancel, or browse completed notebooks while one runs.
4. Open the original images in the gallery or reading view. Filter by hour, search a page number or timestamp, and use the full-screen reader with arrow keys.
5. Open the complete PDF or smaller hourly PDFs. Each page has a clickable video timestamp and a bookmark.

| Preset | Best for | Sampling and comparison |
| --- | --- | --- |
| Whiteboard & writing | A central board with browser controls or a webcam near the top | Video keyframes; compare the central 89.5% of width and vertical 17–96% region |
| Slides & screen shares | Slides, code, diagrams and notes near the screen edges | Video keyframes; compare the full image |
| Detailed capture | Faster writing and small changes | A frame every 3 seconds; lower change threshold; slower and more pages |

Comparison regions only affect which images are selected. **Exports preserve the full captured frame.** Keyframe spacing depends on the source video; there is no fixed sampling interval in the two fast presets. The selector favors stable views, keeps occasional views during continuous movement, and removes near-identical revisits among the last 200 retained views.

## Storage and operation

- Notebooks are saved under `.data/`, which Git ignores. Each notebook has `job.json`, `pages.json`, full-resolution `pages/`, `thumbnails/`, `notes.pdf`, and `hourly/` exports.
- Change the location with `python -m noteframe --data-dir /path/to/notes serve` or `NOTEFRAME_DATA_DIR`. Use one server per data directory.
- Jobs run serially to limit resource usage. Progress is saved to disk. A job interrupted by a server restart is marked failed and can be retried from the UI; partial jobs do not resume automatically.
- Temporary video downloads and keyframes are removed after each normal run or cancellation. After an abrupt machine shutdown, interrupted temporary files may remain until that notebook is removed.
- Videos up to 12 hours are accepted. At least 2 GB of free disk is required to start; long videos can require substantially more. Complete PDFs may be large, which is why hourly exports are included.
- Keep the server running while extracting. Closing the browser alone does not cancel a job.
- Removing a notebook deletes that notebook's local artifacts; it does not affect the YouTube source.

The server binds to loopback only and checks Host and browser Origin headers. It is a **single-user local app**, not an authenticated public hosting service. Do not expose it through a public tunnel without adding authentication, quotas, and a proper worker service.

## What it can and cannot capture

These are image-based notes, not editable text or OCR. Search finds page numbers and timestamps, not the words in the images. Content between sampled frames may be missed; zooming, partial annotations and similar views may remain. Material that was never visible in the recording cannot be recovered. Speaker-only segments are not automatically recognized as such.

Private, age-restricted, region-restricted, unavailable, or bot-blocked videos may fail. No browser cookies are read automatically. YouTube changes regularly; update the downloader if an otherwise public video stops working:

```sh
python -m pip install --upgrade "yt-dlp[default]"
```

Use videos you have permission to download and retain.

## Development and verification

```sh
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
node --check noteframe/static/app.js
```

Tests cover allowed/rejected URLs, cross-origin writes, artifact access, job cancellation and restart state, duplicate selection, stalled subprocess cancellation, and a real FFmpeg → images → timestamped PDF pipeline using a generated video. FFmpeg integration is skipped if FFmpeg is absent; CI installs it explicitly. No network is needed for these tests.

The interface uses plain HTML/CSS/JavaScript served by FastAPI: no frontend build step. `noteframe/pipeline.py` performs extraction; `jobs.py` handles the persistent local queue; `server.py` serves the API and artifacts.

## Import an earlier extraction

The companion import command accepts the `pages.json`, `pages/`, `thumbnails/`, complete PDF and optional `hourly/` layout from the original local extraction:

```sh
python -m noteframe import /path/to/notes --title "My lecture" --url "https://www.youtube.com/watch?v=VIDEO_ID"
```

Stop NoteFrame before importing, then restart it. The command makes independent copies; it does not change the source folder.

## Credits

Built from the long-lecture workflow developed while using [binh234/video2slides](https://github.com/binh234/video2slides). The comparison/selection approach is adapted; the local app, queue, viewer and PDF exporter are new. Upstream's MIT copyright notice is preserved in [LICENSE](LICENSE). See [NOTICE.md](NOTICE.md) for provenance.
