import re
from typing import Literal
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, Field, field_validator


def youtube_url(value: str) -> str:
    """Accept individual YouTube videos only; never pass arbitrary URLs to a downloader."""
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        raise ValueError("Paste a complete YouTube video link.")
    try:
        if parsed.port not in {None, 80, 443}:
            raise ValueError("Use a standard YouTube video link.")
    except ValueError:
        raise ValueError("Use a standard YouTube video link.") from None
    host = parsed.hostname
    parts = parsed.path.strip("/").split("/")
    if host == "youtu.be" and len(parts) == 1:
        video_id = parts[0]
    elif host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif len(parts) == 2 and parts[0] in {"shorts", "live", "embed"}:
            video_id = parts[1]
        else:
            video_id = ""
    else:
        video_id = ""
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise ValueError("Paste a YouTube video link, not a channel or playlist.")
    return f"https://www.youtube.com/watch?v={video_id}"


class NewJob(BaseModel):
    url: str = Field(max_length=2048)
    preset: Literal["board", "slides", "detailed"] = "board"
    quality: Literal[720, 1080] = 1080

    @field_validator("url")
    @classmethod
    def validate_url(cls, value):
        return youtube_url(value)


def stamp(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}"
