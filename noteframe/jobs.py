import copy
import json
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from .pipeline import Cancelled, pipeline

TERMINAL = {"complete", "failed", "cancelled"}


def now():
    return datetime.now(UTC).isoformat()


class JobManager:
    def __init__(self, root: Path, runner=pipeline):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.runner = runner
        self.lock = threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="noteframe")
        self.events = {}
        self.jobs = {}
        self.last_write = {}
        for path in self.root.glob("*/job.json"):
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
                if job["id"] != path.parent.name:
                    continue
                if job["status"] not in TERMINAL:
                    job.update(
                        status="failed", message="The app stopped during extraction. Retry to start again."
                    )
                self.jobs[job["id"]] = job
                self._save(job)
            except (ValueError, KeyError, OSError):
                continue

    def _save(self, job):
        folder = self.root / job["id"]
        folder.mkdir(exist_ok=True)
        temp = folder / "job.json.tmp"
        temp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(folder / "job.json")
        self.last_write[job["id"]] = time.monotonic()

    def list(self):
        with self.lock:
            return copy.deepcopy(sorted(self.jobs.values(), key=lambda j: j["created_at"], reverse=True))

    def get(self, job_id):
        with self.lock:
            if job_id not in self.jobs:
                raise KeyError(job_id)
            return copy.deepcopy(self.jobs[job_id])

    def create(self, request):
        with self.lock:
            active = [j for j in self.jobs.values() if j["status"] not in TERMINAL]
            for job in active:
                if all(job[key] == value for key, value in request.items()):
                    return copy.deepcopy(job)
            if len(active) >= 5:
                raise ValueError("Five videos are already queued. Wait for one to finish.")
            job_id = uuid.uuid4().hex
            job = {
                **request,
                "id": job_id,
                "title": "New YouTube notebook",
                "channel": "YouTube",
                "status": "queued",
                "progress": 0,
                "message": "Waiting to start",
                "created_at": now(),
                "page_count": 0,
                "duration": 0,
                "exports": [],
            }
            self.jobs[job_id] = job
            self.events[job_id] = threading.Event()
            self._save(job)
            self.pool.submit(self._run, job_id)
            return copy.deepcopy(job)

    def _run(self, job_id):
        with self.lock:
            if self.jobs[job_id]["status"] == "cancelled":
                self.events.pop(job_id, None)
                return
        event = self.events[job_id]

        def metadata(**values):
            with self.lock:
                self.jobs[job_id].update(values)
                self._save(self.jobs[job_id])

        def update(stage, progress, message):
            with self.lock:
                job = self.jobs[job_id]
                if event.is_set():
                    return
                previous = job["status"]
                job.update(status=stage, progress=round(progress, 1), message=message)
                if previous != stage or time.monotonic() - self.last_write.get(job_id, 0) > 1:
                    self._save(job)

        try:
            result = self.runner(self.get(job_id), self.root / job_id, event, update, metadata)
            with self.lock:
                if event.is_set():
                    raise Cancelled()
                metadata(
                    **result,
                    status="complete",
                    progress=100,
                    message="Your notes are ready",
                    finished_at=now(),
                )
        except Cancelled:
            metadata(status="cancelled", message="Extraction cancelled. You can retry whenever you like.")
        except Exception as exc:  # noqa: BLE001 -- Persist any worker failure instead of losing the job.
            metadata(status="failed", message=str(exc)[:600] or "Extraction failed. Please retry.")
        finally:
            with self.lock:
                self.events.pop(job_id, None)

    def cancel(self, job_id):
        with self.lock:
            job = self.jobs[job_id]
            if job["status"] not in TERMINAL:
                self.events[job_id].set()
                # Queued work can be cancelled immediately; running work acknowledges its own exit.
                if job["status"] == "queued":
                    job.update(status="cancelled", message="Cancelled before extraction started")
                else:
                    job.update(status="cancelling", message="Stopping extraction…")
                self._save(job)
            return copy.deepcopy(job)

    def delete(self, job_id):
        with self.lock:
            job = self.jobs[job_id]
            if job["status"] not in TERMINAL or job_id in self.events:
                raise ValueError("Wait for extraction to stop before removing this notebook.")
            folder = (self.root / job_id).resolve()
            if folder.parent != self.root or folder.name != job_id:
                raise ValueError("Invalid notebook directory")
            shutil.rmtree(folder)
            del self.jobs[job_id]
            self.last_write.pop(job_id, None)

    def close(self):
        with self.lock:
            for event in self.events.values():
                event.set()
        self.pool.shutdown(wait=True, cancel_futures=False)
