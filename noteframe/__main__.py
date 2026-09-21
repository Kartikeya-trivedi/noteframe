import argparse
import json
import os
import shutil
import uuid
from pathlib import Path

from .jobs import now
from .models import youtube_url


def import_notes(source, root, title, url, duration=0, channel="Imported notebook"):
    """Import the previous local extraction without downloading the lecture again."""
    url = youtube_url(url)
    source = source.resolve()
    records = json.loads((source / "pages.json").read_text(encoding="utf-8"))
    if not records:
        raise ValueError("The notes folder contains no pages")
    for record in records:
        name = record["filename"]
        if Path(name).name != name or not (source / "pages" / name).is_file():
            raise ValueError("Invalid page manifest")
    pdf = source / "LLM-Context-Engineering-Part-1-Notes.pdf"
    if not pdf.exists():
        pdf = source / "notes.pdf"
    if not pdf.exists():
        raise ValueError("The source folder has no complete PDF")
    folder = root.resolve() / uuid.uuid4().hex
    folder.mkdir(parents=True)

    def copy(src, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Independent copies ensure removing or changing one library never changes the source.
        shutil.copy2(src, dest)

    for record in records:
        copy(source / "pages" / record["filename"], folder / "pages" / record["filename"])
        thumb = source / "thumbnails" / record["filename"]
        if thumb.is_file():
            copy(thumb, folder / "thumbnails" / record["filename"])
        else:
            from PIL import Image

            (folder / "thumbnails").mkdir(exist_ok=True)
            with Image.open(source / "pages" / record["filename"]) as im:
                im.thumbnail((660, 420))
                im.save(folder / "thumbnails" / record["filename"])
    copy(pdf, folder / "notes.pdf")
    exports = []
    for hour, path in enumerate(sorted((source / "hourly").glob("*.pdf")), 1):
        filename = f"hourly/hour-{hour:02}.pdf"
        copy(path, folder / filename)
        exports.append(
            {
                "hour": hour,
                "filename": filename,
                "pages": sum(int(p["timestamp"]) // 3600 == hour - 1 for p in records),
            }
        )
    (folder / "pages.json").write_text(json.dumps(records), encoding="utf-8")
    job = {
        "id": folder.name,
        "url": url,
        "title": title,
        "channel": channel,
        "preset": "board",
        "quality": 1080,
        "status": "complete",
        "progress": 100,
        "message": "Imported from your earlier extraction",
        "created_at": now(),
        "finished_at": now(),
        "page_count": len(records),
        "duration": duration,
        "exports": exports,
        "pdf_bytes": pdf.stat().st_size,
        "cover": records[0]["filename"],
    }
    (folder / "job.json").write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    return job


def main():
    parser = argparse.ArgumentParser(description="NoteFrame — turn video notes into a notebook")
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("NOTEFRAME_DATA_DIR", ".data")))
    sub = parser.add_subparsers(dest="command")
    serve = sub.add_parser("serve", help="Open the local web app")
    serve.add_argument("--port", type=int, default=8767)
    imp = sub.add_parser("import", help="Import a previously extracted notes folder")
    imp.add_argument("folder", type=Path)
    imp.add_argument("--title", required=True)
    imp.add_argument("--url", required=True)
    imp.add_argument("--duration", type=float, default=0, help="Known source duration in seconds (optional)")
    imp.add_argument("--channel", default="Imported notebook")
    args = parser.parse_args()
    if args.command == "import":
        job = import_notes(args.folder, args.data_dir, args.title, args.url, args.duration, args.channel)
        print(f"Imported {job['page_count']} pages. Start NoteFrame to open your library.")
    else:
        import uvicorn

        from .server import create_app

        uvicorn.run(create_app(args.data_dir), host="127.0.0.1", port=getattr(args, "port", 8767))


if __name__ == "__main__":
    main()
