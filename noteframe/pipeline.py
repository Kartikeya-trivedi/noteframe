"""Download, select visible views, and export. No transcript or model API needed.

Selection extends the local long-lecture adaptation of binh234/video2slides.
See NOTICE.md for provenance and the retained upstream MIT license.
"""

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from reportlab.pdfgen import canvas

from .models import stamp


class Cancelled(Exception):
    pass


def check_cancel(cancel):
    if cancel.is_set():
        raise Cancelled("Extraction cancelled.")


def stop_process(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def run_process(command, log: Path, cancel, on_line=None, timeout=7200):
    """Poll an owned process so cancellation works even when its output stalls."""
    started = time.monotonic()
    options = (
        {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    )
    with log.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(
            command,
            stdout=output,
            stderr=subprocess.STDOUT,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            **options,
        )
        try:
            with log.open(encoding="utf-8", errors="replace") as reader:
                pending = ""

                def drain(final=False):
                    nonlocal pending
                    pending += reader.read()
                    lines = pending.split("\n")
                    pending = lines.pop()
                    if final and pending:
                        lines.append(pending)
                        pending = ""
                    if on_line:
                        for line in lines:
                            on_line(line)

                while True:
                    check_cancel(cancel)
                    if time.monotonic() - started > timeout:
                        raise RuntimeError("This step timed out. Try a shorter video or retry later.")
                    drain()
                    if process.poll() is not None:
                        # Drain output written between EOF and the process-exit check.
                        drain(final=True)
                        break
                    cancel.wait(0.2)
            if process.returncode:
                detail = log.read_text(encoding="utf-8", errors="replace")[-3000:]
                error = next((line for line in reversed(detail.splitlines()) if "ERROR:" in line), "")
                raise RuntimeError(error[:500] or f"{Path(command[0]).name} failed. See the local job log.")
        finally:
            stop_process(process)


def signature(path: Path, preset="board"):
    frame = cv2.imread(str(path))
    if frame is None:
        raise RuntimeError("An extracted frame could not be read.")
    h, w = frame.shape[:2]
    if preset == "board":
        # Matches the screen-share layout used in the original long lecture.
        frame = frame[int(h * 0.17) : int(h * 0.96), int(w * 0.035) : int(w * 0.93)]
    gray = cv2.cvtColor(cv2.resize(frame, (640, 360)), cv2.COLOR_BGR2GRAY)
    return cv2.GaussianBlur(gray, (3, 3), 0)


def changed(a, b):
    return float(np.mean(cv2.absdiff(a, b) > 35))


def select_views(frames, timestamps, preset, cancel, update):
    threshold = 0.008 if preset == "detailed" else 0.018
    groups, group, anchor = [], None, None
    for index, (path, timestamp) in enumerate(zip(frames, timestamps, strict=True)):
        check_cancel(cancel)
        sig = signature(path, preset)
        if anchor is None or changed(anchor, sig) > threshold:
            if group:
                groups.append(group)
            group = {"path": path, "timestamp": timestamp, "samples": 1}
            anchor = sig
        else:
            group.update(path=path, timestamp=timestamp, samples=group["samples"] + 1)
        if index % 100 == 0:
            update(
                "selecting", 60 + 15 * index / len(frames), f"Comparing view {index + 1:,} of {len(frames):,}"
            )
    if group:
        groups.append(group)
    candidates, last_time = [], -1000
    for group in groups:
        stable = group["samples"] >= 2 or preset == "detailed"
        if stable or group["timestamp"] - last_time >= 60:
            candidates.append(group)
            last_time = group["timestamp"]
    if groups and (not candidates or candidates[-1] is not groups[-1]):
        candidates.append(groups[-1])
    # Check a bounded set of recent views: avoids quadratic memory and time growth.
    selected, seen = [], []
    for group in candidates:
        check_cancel(cancel)
        sig = signature(group["path"], preset)
        thumb = cv2.resize(sig, (160, 90))
        duplicate = any(
            changed(thumb, old_thumb) < 0.007 and changed(sig, old_sig) < 0.003 for old_thumb, old_sig in seen
        )
        if not duplicate:
            selected.append(group)
            seen.append((thumb, sig))
            seen = seen[-200:]
    return selected


def export_pdf(target, pages_dir, records, title, source_url, cancel):
    pdf = canvas.Canvas(str(target), pageCompression=1)
    pdf.setTitle(title)
    pdf.setAuthor("NoteFrame")
    current_hour = None
    for record in records:
        check_cancel(cancel)
        path = pages_dir / record["filename"]
        with Image.open(path) as im:
            width, height = im.size
        # Keep source JPEG bytes in the PDF; the footer never covers the notes.
        pdf.setPageSize((width, height + 38))
        pdf.drawImage(str(path), 0, 38, width=width, height=height)
        pdf.setFillColorRGB(0.09, 0.32, 0.27)
        pdf.setFont("Helvetica", 14)
        pdf.drawString(20, 14, f"Page {record['page']}  /  {record['time']}  /  Watch this moment on YouTube")
        pdf.linkURL(f"{source_url}&t={int(record['timestamp'])}s", (0, 0, width, 38), relative=0)
        key = f"page-{record['page']}"
        pdf.bookmarkPage(key)
        hour = int(record["timestamp"]) // 3600
        if current_hour != hour:
            pdf.addOutlineEntry(f"Hour {hour + 1}", key, level=0)
            current_hour = hour
        pdf.addOutlineEntry(f"Page {record['page']} - {record['time']}", key, level=1)
        pdf.showPage()
    pdf.save()


def export_notes(folder, records, title, source_url, cancel, update):
    thumbnails = folder / "thumbnails"
    thumbnails.mkdir(exist_ok=True)
    for record in records:
        check_cancel(cancel)
        with Image.open(folder / "pages" / record["filename"]) as im:
            im.thumbnail((660, 420))
            im.convert("RGB").save(thumbnails / record["filename"], quality=82)
    (folder / "pages.json").write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    update("exporting", 85, "Building the complete PDF with video timestamps")
    export_pdf(folder / "notes.pdf", folder / "pages", records, title, source_url, cancel)
    hours = sorted({int(p["timestamp"]) // 3600 for p in records})
    (folder / "hourly").mkdir(exist_ok=True)
    exports = []
    for index, hour in enumerate(hours):
        chunk = [p for p in records if int(p["timestamp"]) // 3600 == hour]
        name = f"hourly/hour-{hour + 1:02}.pdf"
        export_pdf(folder / name, folder / "pages", chunk, title, source_url, cancel)
        exports.append({"hour": hour + 1, "filename": name, "pages": len(chunk)})
        update("exporting", 90 + 9 * (index + 1) / len(hours), f"Exporting hour {hour + 1}")
    return {
        "page_count": len(records),
        "pdf_bytes": (folder / "notes.pdf").stat().st_size,
        "exports": exports,
        "cover": records[0]["filename"],
    }


def pipeline(job, folder, cancel, update, metadata):
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise RuntimeError(f"Install {tool} and add it to PATH, then restart NoteFrame.")
    work = folder / "work"
    work.mkdir(exist_ok=True)
    try:
        base = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--ignore-config",
            "--no-playlist",
            "--no-colors",
            "--socket-timeout",
            "20",
            "--retries",
            "3",
            "--js-runtimes",
            "node",
        ]
        update("checking", 2, "Reading the video title and duration")
        info_log = work / "metadata.json"
        run_process(
            base + ["--dump-single-json", "--skip-download", "--no-warnings", job["url"]],
            info_log,
            cancel,
            timeout=180,
        )
        lines = info_log.read_text(encoding="utf-8").splitlines()
        info = json.loads(next(line for line in reversed(lines) if line.startswith("{")))
        duration = float(info.get("duration") or 0)
        if info.get("is_live") or duration <= 0:
            raise RuntimeError("Use a finished video; live streams cannot be extracted while broadcasting.")
        if duration > 12 * 3600:
            raise RuntimeError("This local version supports videos up to 12 hours long.")
        # Save just the machine-readable JSON for yt-dlp's load-info-json input.
        info_log.write_text(json.dumps(info), encoding="utf-8")
        title = info.get("title") or "Untitled video"
        metadata(title=title, duration=duration, channel=info.get("channel") or "YouTube")
        if shutil.disk_usage(folder).free < 2 * 1024**3:
            raise RuntimeError(
                "Free at least 2 GB on the output drive, then retry. Long videos may need more."
            )

        def download_progress(line):
            match = re.search(r"NF_PROGRESS:\s*([\d.]+)%", line)
            if match:
                percent = float(match[1])
                update("downloading", 5 + 0.35 * percent, f"Downloading video · {percent:.0f}%")

        update("downloading", 5, "Downloading the video picture stream")
        run_process(
            base
            + [
                "--load-info-json",
                str(info_log),
                "-f",
                f"bestvideo[height<={job['quality']}][ext=mp4]/bestvideo[height<={job['quality']}]/best[height<={job['quality']}]",
                "--newline",
                "--progress",
                "--progress-delta",
                "1",
                "--progress-template",
                "download:NF_PROGRESS:%(progress._percent_str)s",
                "-o",
                str(work / "source.%(ext)s"),
            ],
            folder / "download.log",
            cancel,
            download_progress,
            timeout=6 * 3600,
        )
        video = next((p for p in work.glob("source.*") if p.suffix not in {".part", ".ytdl"}), None)
        if video is None:
            raise RuntimeError("The video download did not produce a usable file.")
        return extract_video(video, folder, job["preset"], title, job["url"], duration, cancel, update)
    finally:
        # Temporary video and keyframes are private to this run, never the user's source.
        shutil.rmtree(work, ignore_errors=True)


def extract_video(video, folder, preset, title, source_url, duration, cancel, update):
    work = folder / "work"
    frames_dir = work / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    timestamps = []

    def frame_progress(line):
        match = re.search(r"\bn:\s*\d+.*?pts_time:([\d.e+-]+)", line)
        if match:
            timestamp = max(0, float(match[1]))
            timestamps.append(timestamp)
            if len(timestamps) % 50 == 0:
                update(
                    "extracting",
                    40 + 20 * min(timestamp / max(duration, 1), 1),
                    f"Capturing visible notes · {stamp(timestamp)} / {stamp(duration)}",
                )

    update("extracting", 40, "Capturing original video frames")
    sampling = [] if preset == "detailed" else ["-skip_frame", "nokey"]
    filters = "fps=1/3,showinfo" if preset == "detailed" else "showinfo"
    # showinfo provides actual presentation timestamps, including variable-frame-rate videos.
    run_process(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-y",
            *sampling,
            "-threads",
            "4",
            "-i",
            str(video),
            "-an",
            "-vf",
            filters,
            "-fps_mode",
            "vfr",
            "-q:v",
            "2",
            str(frames_dir / "%07d.jpg"),
        ],
        folder / "frames.log",
        cancel,
        frame_progress,
    )
    frames = sorted(frames_dir.glob("*.jpg"))
    if not frames or len(frames) != len(timestamps):
        raise RuntimeError("Could not match captured frames to video timestamps.")
    selected = select_views(frames, timestamps, preset, cancel, update)
    if not selected:
        raise RuntimeError("No readable views found. Try the Detailed preset.")
    pages = folder / "pages"
    pages.mkdir(exist_ok=True)
    records = []
    for number, group in enumerate(selected, 1):
        check_cancel(cancel)
        filename = f"{number:04}_{stamp(group['timestamp']).replace(':', '-')}.jpg"
        shutil.copy2(group["path"], pages / filename)
        records.append(
            {
                "page": number,
                "timestamp": round(group["timestamp"], 3),
                "time": stamp(group["timestamp"]),
                "filename": filename,
            }
        )
    result = export_notes(folder, records, title, source_url, cancel, update)
    result["sampled_frames"] = len(frames)
    return result
