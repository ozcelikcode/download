"""Boyut sınırlı yükleme; başarısız işlemde mevcut dosyayı korur."""

import os
import tempfile
from pathlib import Path

import anyio
from fastapi import HTTPException, UploadFile

from app.config import settings


async def save_upload(file: UploadFile, destination: Path) -> None:
    limit = settings.max_upload_size_bytes
    if file.size is not None and file.size > limit:
        raise HTTPException(status_code=413, detail="Dosya yükleme boyutu sınırını aşıyor.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".upload-", suffix=".part", dir=destination.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        received = 0
        async with await anyio.open_file(temporary, "wb") as output:
            while chunk := await file.read(64 * 1024):
                received += len(chunk)
                if received > limit:
                    raise HTTPException(status_code=413, detail="Dosya yükleme boyutu sınırını aşıyor.")
                await output.write(chunk)
        await anyio.to_thread.run_sync(temporary.replace, destination)
    finally:
        temporary.unlink(missing_ok=True)
