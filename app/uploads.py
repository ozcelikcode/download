"""Bounded staged uploads and protection against serving temporary files."""

import os
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path, PurePosixPath

import anyio
from fastapi import HTTPException, UploadFile
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from app.config import settings

STAGING_PREFIXES = (".upload-", ".replace-", ".remote-", ".crop-")


class UploadSafeStaticFiles(StaticFiles):
    """Never expose hidden staging files in the public uploads tree."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        if path.startswith("uploads/") and any(part.startswith(".") for part in PurePosixPath(path).parts):
            raise HTTPException(404)
        return await super().get_response(path, scope)


async def save_upload(
    file: UploadFile,
    destination: Path,
    *,
    validator: Callable[[Path], None] | None = None,
    publisher: Callable[[Path, Path], Awaitable[None]] | None = None,
    max_bytes: int | None = None,
) -> None:
    limit = min(settings.max_upload_size_bytes, max_bytes) if max_bytes is not None else settings.max_upload_size_bytes
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
        if validator is not None:
            await anyio.to_thread.run_sync(validator, temporary)
        if publisher is not None:
            await publisher(temporary, destination)
        else:
            await anyio.to_thread.run_sync(temporary.replace, destination)
    finally:
        temporary.unlink(missing_ok=True)
