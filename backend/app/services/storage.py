"""Protected file storage for listing photos and proof-of-collection images.

Files are stored outside any public static directory, with random names, after
checking size and magic bytes. They are only served through authorised endpoints.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Tuple

from fastapi import HTTPException, UploadFile, status

from ..config import get_settings

IMAGE_SIGNATURES = {
    b"\xff\xd8\xff": ("image/jpeg", ".jpg"),
    b"\x89PNG\r\n\x1a\n": ("image/png", ".png"),
}

AUDIO_TYPES = {
    "audio/wav", "audio/x-wav", "audio/wave", "audio/mpeg", "audio/mp3", "audio/webm", "audio/ogg",
    "audio/mp4", "audio/aac", "audio/x-m4a", "audio/flac", "video/webm",
}


def _detect_image(data: bytes) -> Tuple[str, str]:
    for sig, info in IMAGE_SIGNATURES.items():
        if data.startswith(sig):
            return info
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ("image/webp", ".webp")
    raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only JPEG, PNG or WebP images are allowed.")


async def read_limited(upload: UploadFile, max_bytes: int) -> bytes:
    data = await upload.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"File exceeds {max_bytes // (1024 * 1024)} MB limit.")
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uploaded file is empty.")
    return data


async def save_image(upload: UploadFile, subdir: str) -> str:
    s = get_settings()
    data = await read_limited(upload, s.max_image_bytes)
    _mime, ext = _detect_image(data)
    folder = Path(s.upload_dir) / subdir
    folder.mkdir(parents=True, exist_ok=True)
    name = secrets.token_hex(16) + ext
    path = folder / name
    with open(path, "wb") as fh:
        fh.write(data)
    os.chmod(path, 0o640)
    return f"{subdir}/{name}"


def resolve(rel_path: str) -> Path:
    base = Path(get_settings().upload_dir).resolve()
    p = (base / rel_path).resolve()
    if base not in p.parents or not p.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    return p


async def read_audio(upload: UploadFile) -> bytes:
    ctype = (upload.content_type or "").split(";")[0].strip().lower()
    if ctype not in AUDIO_TYPES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"Unsupported audio type '{ctype}'.")
    return await read_limited(upload, get_settings().max_audio_bytes)
