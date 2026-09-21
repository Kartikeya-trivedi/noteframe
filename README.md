# NoteFrame

**Keep what’s on the board.**

Paste a YouTube link and turn the actual visible handwriting, slides, diagrams and code into a visual notebook. Browse a gallery, switch to reading mode, jump back to the original video, or save timestamped PDFs.

NoteFrame runs on your computer. It does not need an AI API key, generate summaries, or send your extracted notes to a hosted service.

## Windows: double-click to start

1. [Download the project ZIP](https://github.com/Kartikeya-trivedi/noteframe/archive/refs/heads/main.zip) and **Extract All** into a writable local folder. Do not run a BAT from inside the ZIP. Git users can clone the repository instead.
2. Double-click **`start.bat`**. It checks your tools, downloads anything missing, prepares the Python environment, and opens NoteFrame once the server is ready.
3. Keep the console window open while using the app. Press **Ctrl+C** to stop the server.

For a separate install/repair step, double-click **`setup.bat`**, wait for “Setup complete”, and then run **`start.bat`**.

**Supported automatic setup: Windows 10/11 x64, with Windows PowerShell 5.1 or later and internet access on the first run.** You do not need administrator access, Git, winget, or a preinstalled Python. `start.bat` uses Windows PowerShell already included in Windows.

### What the scripts do

- Reuse compatible Python **3.11–3.14 x64**, Node.js **22+**, and FFmpeg/ffprobe installations. Microsoft Store Python aliases and incompatible Python builds are skipped.
- Download missing tools into **`.tools/`**: the official CPython NuGet distribution, Node.js from nodejs.org, and the Gyan FFmpeg build linked by FFmpeg's download page. Archive versions and SHA-256 hashes are pinned in [`scripts/windows/downloads.json`](scripts/windows/downloads.json).
- Verify every archive before extracting or executing it; reject unsafe ZIP paths; retry failed downloads up to three times. Interrupted `.partial` downloads are retried, not treated as completed files.
- Create **`.venv/`**, install Python dependencies, run import checks and `pip check`, and only then mark setup complete. An invalid environment is moved to a timestamped `.venv.backup-*` folder instead of being deleted. A partially installed environment is repaired on the next run.
- Avoid package downloads on an ordinary launch when the environment and project dependency definition still match. `setup.bat` explicitly reruns package installation to repair/check the environment.
- Keep tool paths local to the launched process. They do not change your system PATH, install Windows packages, change registry settings, or permanently change PowerShell execution policy. The BAT wrapper sets execution policy only for its own PowerShell process.
- Save diagnostic output in **`.logs/`**, block competing launchers for the same folder, report occupied ports without killing another process, and preserve **`.data/`** notes.

### Command-line options

Run these from the extracted project folder in Command Prompt or PowerShell:

| Command | Action |
| --- | --- |
| `.\setup.bat` | Install or repair dependencies only |
| `.\start.bat` | Prepare if needed, start, and open the browser |
| `.\start.bat -Check -NoPause` | Check installed dependencies without downloading or starting |
| `.\start.bat -NoBrowser` | Start without opening a browser |
| `.\start.bat -Port 8768` | Use a different free port |
| `.\setup.bat -LocalTools -NoPause` | Download local tools even if compatible system tools exist |

`-NoPause` disables the closing “Press Enter” prompt for automation. `-LocalTools` chooses local runtimes; a healthy existing `.venv` is retained. The older `start.ps1` entry point forwards to the same launcher.

### If setup fails

- **Window reports an error:** read the final message and the newest `.logs/` file. Rerun `setup.bat` after fixing the cause; do not delete your `.data` folder.
- **Download/hash error:** check your connection, Windows clock, proxy/firewall, and available disk space. The scripts do not bypass TLS or hash verification. Corporate policy or antivirus restrictions may need your administrator's help.
- **Port already in use:** use the app that is already running, or stop that app yourself. Only use `-Port` to change a free port; do not run two servers against the same notes directory.
- **Project moved or Python removed:** rerun setup. An unusable environment is preserved as a backup and recreated. After checking the new environment, you may manually remove old `.venv.backup-*` folders to reclaim space.
- **Very long or protected path:** move the extracted project to a short writable local path, such as `C:\Users\YourName\NoteFrame`. UNC/network shares and automatic ARM64/32-bit installation are not supported.
- **App started manually with Python:** stop it before running setup/repair. The shared launcher lock covers BAT/PowerShell launchers, not independently started Python processes.

No installer can guarantee success on every locked-down or damaged Windows installation. These scripts fail with an error and log rather than reporting a failed install as successful.

## Manual setup / macOS / Linux

You need **Python 3.11+**, **FFmpeg** (including `ffprobe`), and **Node.js 22+** or a supported Deno runtime on your `PATH`. Node/Deno lets yt-dlp handle YouTube's JavaScript challenges. See the [yt-dlp runtime guide](https://github.com/yt-dlp/yt-dlp/wiki/EJS).

```powershell
git clone https://github.com/Kartikeya-trivedi/noteframe.git
cd noteframe
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m noteframe serve
```

Open **http://127.0.0.1:8767**. Stop the server with `Ctrl+C`. Add `--open-browser` to open the UI automatically after startup.

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

Windows bootstrap checks run on Windows PowerShell 5.1:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests\windows.ps1
```

They cover checksum rejection, retry limits, partial-download cleanup, archive traversal, special-character paths, environment backup, exit codes, and port conflicts. CI also runs the real Windows dependency bootstrap with local tools and checks it a second time. Download manifests should only be updated after verifying the archive sources and hashes; do not disable verification to work around a mismatch.

The interface uses plain HTML/CSS/JavaScript served by FastAPI: no frontend build step. `noteframe/pipeline.py` performs extraction; `jobs.py` handles the persistent local queue; `server.py` serves the API and artifacts.

## Import an earlier extraction

The companion import command accepts the `pages.json`, `pages/`, `thumbnails/`, complete PDF and optional `hourly/` layout from the original local extraction:

```sh
python -m noteframe import /path/to/notes --title "My lecture" --url "https://www.youtube.com/watch?v=VIDEO_ID"
```

Stop NoteFrame before importing, then restart it. The command makes independent copies; it does not change the source folder.

## Credits

Built from the long-lecture workflow developed while using [binh234/video2slides](https://github.com/binh234/video2slides). The comparison/selection approach is adapted; the local app, queue, viewer and PDF exporter are new. Upstream's MIT copyright notice is preserved in [LICENSE](LICENSE). See [NOTICE.md](NOTICE.md) for provenance.
