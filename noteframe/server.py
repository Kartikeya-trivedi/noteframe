import json
import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .jobs import JobManager
from .models import NewJob

STATIC = Path(__file__).parent / "static"


def create_app(data_dir=None, runner=None):
    root = Path(data_dir or os.environ.get("NOTEFRAME_DATA_DIR", ".data")).resolve()

    @asynccontextmanager
    async def lifespan(app):
        app.state.manager = JobManager(root, **({"runner": runner} if runner else {}))
        yield
        app.state.manager.close()

    app = FastAPI(title="NoteFrame", lifespan=lifespan, docs_url="/api/docs", redoc_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"])

    @app.middleware("http")
    async def local_requests(request: Request, call_next):
        # Block browser cross-origin writes and DNS rebinding on this local, unauthenticated app.
        origin = request.headers.get("origin")
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "Open NoteFrame directly to make changes."}, status_code=403)
            if origin and urlsplit(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": "Cross-origin requests are not allowed."}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
            "connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def manager():
        return app.state.manager

    def get_job(job_id):
        try:
            return manager().get(job_id)
        except KeyError:
            raise HTTPException(404, "Notebook not found") from None

    @app.get("/api/health")
    def health():
        dependencies = {name: bool(shutil.which(name)) for name in ["ffmpeg", "ffprobe"]}
        dependencies["javascript"] = bool(shutil.which("node") or shutil.which("deno"))
        return {"app": "noteframe", "ready": all(dependencies.values()), "dependencies": dependencies}

    @app.get("/api/jobs")
    def list_jobs():
        return manager().list()

    @app.post("/api/jobs", status_code=202)
    def create_job(request: NewJob):
        if not health()["ready"]:
            raise HTTPException(503, "Install FFmpeg and Node.js (or Deno), then restart NoteFrame.")
        try:
            return manager().create(request.model_dump())
        except ValueError as exc:
            raise HTTPException(429, str(exc)) from None

    @app.get("/api/jobs/{job_id}")
    def job_detail(job_id: str):
        return get_job(job_id)

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str):
        get_job(job_id)
        return manager().cancel(job_id)

    @app.delete("/api/jobs/{job_id}", status_code=204)
    def delete_job(job_id: str):
        get_job(job_id)
        try:
            manager().delete(job_id)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None

    @app.get("/api/jobs/{job_id}/pages")
    def pages(job_id: str):
        job = get_job(job_id)
        if job["status"] != "complete":
            raise HTTPException(409, "Notes are still being prepared")
        return json.loads((root / job_id / "pages.json").read_text(encoding="utf-8"))

    @app.get("/files/{job_id}/{filename:path}")
    def artifact(job_id: str, filename: str):
        job = get_job(job_id)
        if job["status"] != "complete":
            raise HTTPException(409, "Notes are still being prepared")
        folder = (root / job_id).resolve()
        path = (folder / filename).resolve()
        allowed = (
            filename == "notes.pdf"
            or (path.parent in {folder / "pages", folder / "thumbnails"} and path.suffix == ".jpg")
            or (path.parent == folder / "hourly" and path.suffix == ".pdf")
        )
        if not allowed or not path.is_relative_to(folder) or not path.is_file():
            raise HTTPException(404, "File not found")
        return FileResponse(path)

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def home():
        return FileResponse(STATIC / "index.html")

    return app
