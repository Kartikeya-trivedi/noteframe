import json
import shutil
import subprocess
import sys
import threading
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from pypdf import PdfReader

from noteframe.jobs import JobManager
from noteframe.models import NewJob, youtube_url
from noteframe.pipeline import Cancelled, extract_video, run_process, select_views
from noteframe.server import create_app

URL = "https://www.youtube.com/watch?v=biO6qPn3xVs"


@pytest.mark.parametrize(
    "url",
    [
        URL,
        "https://youtu.be/biO6qPn3xVs?t=12",
        "https://m.youtube.com/watch?v=biO6qPn3xVs&list=abc",
        "https://youtube.com/live/biO6qPn3xVs",
    ],
)
def test_youtube_normalization(url):
    assert youtube_url(url) == URL


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://127.0.0.1:8000/watch?v=biO6qPn3xVs",
        "https://youtube.com.evil.test/watch?v=biO6qPn3xVs",
        "https://youtube.com@evil.test/watch?v=biO6qPn3xVs",
        "https://youtube.com/playlist?list=x",
        "https://youtu.be/invalid",
        "https://youtube.com:999/watch?v=biO6qPn3xVs",
    ],
)
def test_rejects_arbitrary_urls(url):
    with pytest.raises(ValueError):
        NewJob(url=url)


def wait_until(predicate, timeout=4):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("Job did not reach expected state")


def test_queue_cancellation_and_restart(tmp_path):
    started = threading.Event()

    def runner(job, folder, cancel, update, metadata):
        update("downloading", 10, "Downloading")
        started.set()
        cancel.wait(3)
        raise Cancelled()

    manager = JobManager(tmp_path, runner)
    try:
        first = manager.create(NewJob(url=URL).model_dump())
        assert started.wait(2)
        # Duplicate submissions share the active extraction.
        assert manager.create(NewJob(url=URL).model_dump())["id"] == first["id"]
        second = manager.create(NewJob(url=URL, preset="slides").model_dump())
        manager.cancel(second["id"])
        manager.cancel(first["id"])
        wait_until(lambda: manager.get(first["id"])["status"] == "cancelled")
    finally:
        manager.close()
    assert not manager.events
    restarted = JobManager(tmp_path, runner)
    try:
        assert len(restarted.list()) == 2
        restarted.delete(second["id"])
        assert not (tmp_path / second["id"]).exists()
    finally:
        restarted.close()


def test_interrupted_job_is_recoverable(tmp_path):
    folder = tmp_path / ("a" * 32)
    folder.mkdir()
    (folder / "job.json").write_text(
        json.dumps({"id": folder.name, "status": "extracting", "created_at": "2026"})
    )
    manager = JobManager(tmp_path)
    try:
        job = manager.get(folder.name)
        assert job["status"] == "failed"
        assert "Retry" in job["message"]
    finally:
        manager.close()


def test_api_validation_and_local_access(tmp_path, monkeypatch):
    monkeypatch.setattr("noteframe.server.shutil.which", lambda _: "/bin/tool")

    def runner(job, folder, cancel, update, metadata):
        (folder / "pages.json").write_text("[]")
        (folder / "notes.pdf").write_bytes(b"%PDF-1.4 test")
        return {"page_count": 0}

    with TestClient(create_app(tmp_path, runner)) as client:
        assert client.get("/").status_code == 200
        assert client.post("/api/jobs", json={"url": "https://evil.test"}).status_code == 422
        assert (
            client.post("/api/jobs", json={"url": URL}, headers={"Origin": "https://evil.test"}).status_code
            == 403
        )
        assert client.get("/api/jobs", headers={"Host": "evil.test"}).status_code == 400
        response = client.post("/api/jobs", json={"url": URL})
        assert response.status_code == 202
        job_id = response.json()["id"]
        wait_until(lambda: client.get(f"/api/jobs/{job_id}").json()["status"] == "complete")
        assert client.get(f"/api/jobs/{job_id}/pages").json() == []
        assert client.get(f"/files/{job_id}/notes.pdf").status_code == 200
        assert client.get(f"/files/{job_id}/job.json").status_code == 404
        assert client.get(f"/files/{job_id}/pages/%2E%2E/job.json").status_code == 404
        assert client.get("/api/jobs/missing").status_code == 404
        assert client.delete(f"/api/jobs/{job_id}").status_code == 204
        assert client.get("/api/jobs").json() == []


def test_cancels_stalled_subprocess(tmp_path):
    event = threading.Event()
    timer = threading.Timer(0.25, event.set)
    timer.start()
    start = time.monotonic()
    try:
        with pytest.raises(Cancelled):
            run_process(
                [sys.executable, "-c", "import time; time.sleep(30)"], tmp_path / "process.log", event
            )
        assert time.monotonic() - start < 6
    finally:
        timer.cancel()


def test_preserves_new_writing_and_removes_exact_revisits(tmp_path):
    files = []
    for index, color in enumerate(["white", "white", "black", "black", "white", "white"]):
        path = tmp_path / f"{index}.jpg"
        Image.new("RGB", (640, 360), color).save(path)
        files.append(path)
    selected = select_views(files, [0, 5, 10, 15, 20, 25], "slides", threading.Event(), lambda *args: None)
    assert [item["timestamp"] for item in selected] == [5, 15]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg is needed for real media integration")
def test_real_video_to_timestamped_pdfs(tmp_path):
    # Generated fixture: three different visible boards, six seconds per board.
    for index, color in enumerate(["white", "#263b34", "#ebcf69"]):
        image = Image.new("RGB", (640, 360), color)
        ImageDraw.Draw(image).text((80, 100), f"BOARD {index + 1}: visible notes", fill="red", font_size=30)
        image.save(tmp_path / f"board-{index}.png")
    video = tmp_path / "fixture.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-framerate",
            "1/6",
            "-i",
            str(tmp_path / "board-%d.png"),
            "-c:v",
            "libx264",
            "-r",
            "2",
            "-g",
            "2",
            "-pix_fmt",
            "yuv420p",
            str(video),
        ],
        check=True,
    )
    output = tmp_path / "output"
    output.mkdir()
    result = extract_video(
        video, output, "slides", "Test notebook", URL, 18, threading.Event(), lambda *args: None
    )
    records = json.loads((output / "pages.json").read_text())
    assert result["page_count"] == 3
    assert [p["timestamp"] for p in records] == sorted(p["timestamp"] for p in records)
    assert records[-1]["timestamp"] >= 12
    pdf = PdfReader(output / "notes.pdf")
    assert len(pdf.pages) == 3
    assert len(PdfReader(output / "hourly" / "hour-01.pdf").pages) == 3
    for record, page in zip(records, pdf.pages, strict=True):
        assert record["time"] in page.extract_text()
        assert page["/Annots"][0].get_object()["/A"]["/URI"] == f"{URL}&t={int(record['timestamp'])}s"
        assert (output / "thumbnails" / record["filename"]).is_file()
