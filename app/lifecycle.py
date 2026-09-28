"""Kurulum durumu ve yalnız uygulama verilerini kapsayan sıfırlama."""

from __future__ import annotations

import asyncio
import json
import logging
import posixpath
import secrets
import shutil
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import AsyncIterator, Iterator, Literal

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.engine import make_url
from starlette.concurrency import run_in_threadpool
from starlette.responses import PlainTextResponse, RedirectResponse
from starlette.requests import Request
from fastapi import HTTPException
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import settings
from app.database import AsyncSessionLocal, Base
from app.models import SiteLifecycle, SiteSettings, MenuItem

logger = logging.getLogger(__name__)
ResetAction = Literal["settings", "full", "uninstall"]


@contextmanager
def single_worker_guard() -> Iterator[None]:
    """Aynı SQLite dosyası için ikinci uygulama sürecini başlatma."""
    import fcntl

    database = Path(make_url(settings.database_url).database or "download.db").resolve()
    lock_path = database.with_name(database.name + ".runtime.lock")
    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Bu veritabanı zaten kullanılıyor. Uygulamayı tek worker ile çalıştırın.") from exc
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


async def get_lifecycle(session: AsyncSession) -> SiteLifecycle:
    state = await session.get(SiteLifecycle, 1)
    if state is None:
        raise RuntimeError("Kurulum durumu bulunamadı; make migrate çalıştırılmalıdır.")
    return state


class RequestGate:
    """Tek worker'da indirmeler/arka plan işleri bitmeden sıfırlama başlamaz."""

    def __init__(self) -> None:
        self.condition = asyncio.Condition()
        self.active = 0
        self.exclusive = False

    @asynccontextmanager
    async def enter(self, exclusive: bool) -> AsyncIterator[None]:
        async with self.condition:
            await self.condition.wait_for(lambda: not self.exclusive)
            if exclusive:
                self.exclusive = True
                try:
                    await self.condition.wait_for(lambda: self.active == 0)
                except BaseException:
                    self.exclusive = False
                    self.condition.notify_all()
                    raise
            else:
                self.active += 1
        try:
            yield
        finally:
            async with self.condition:
                if exclusive:
                    self.exclusive = False
                else:
                    self.active -= 1
                self.condition.notify_all()


class LifecycleMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.gate = RequestGate()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope["path"]
        exclusive = scope["method"] == "POST" and path in {"/setup", "/admin/settings/maintenance/confirm"}
        if exclusive:
            # Kimliksiz/yavaş bir POST bütün siteyi kilitleyemez. Küçük onay
            # gövdesini kilitten önce, boyut ve süre sınırıyla al.
            original_receive = receive
            body = bytearray()
            try:
                async with asyncio.timeout(15):
                    while True:
                        message = await original_receive()
                        if message["type"] == "http.disconnect":
                            return
                        body.extend(message.get("body", b""))
                        if len(body) > 16 * 1024:
                            raise HTTPException(413)
                        if not message.get("more_body", False):
                            break
            except (TimeoutError, HTTPException) as exc:
                response = PlainTextResponse("Request rejected", status_code=408 if isinstance(exc, TimeoutError) else 413)
                await response(scope, original_receive, send)
                return
            delivered = False

            async def buffered_receive() -> Message:
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await original_receive()

            receive = buffered_receive
            request = Request(scope, receive)
            async with AsyncSessionLocal() as session:
                state = await get_lifecycle(session)
                if path == "/setup":
                    try:
                        form = await request.form(max_files=0, max_fields=32)
                    except StarletteHTTPException:
                        response = PlainTextResponse("Invalid form", status_code=400)
                        await response(scope, original_receive, send)
                        return
                    supplied = str(form.get("setup_token", ""))
                    exclusive = (not state.installed and len(settings.setup_token) >= 32
                                 and secrets.compare_digest(supplied.encode(), settings.setup_token.encode()))
                    delivered = False
                else:
                    from app.crud import get_site_settings
                    from app.dependencies import SESSION_COOKIE, authenticated_username
                    account = await get_site_settings(session)
                    exclusive = bool(authenticated_username(request.cookies.get(SESSION_COOKIE, ""), account))
        async with self.gate.enter(exclusive):
            request = Request(scope)
            body_limit = 16 * 1024
            async with AsyncSessionLocal() as session:
                state = await get_lifecycle(session)
                installed, pending = state.installed, state.pending_reset
                if installed and scope["method"] in {"POST", "PUT", "PATCH"}:
                    from app.crud import get_site_settings
                    from app.dependencies import SESSION_COOKIE, authenticated_username
                    account = await get_site_settings(session)
                    if authenticated_username(request.cookies.get(SESSION_COOKIE, ""), account):
                        body_limit = settings.max_upload_size_bytes + 1024 * 1024
            if path in {"/setup", "/admin/login", "/admin/settings/account"} or path.startswith("/admin/settings/maintenance/"):
                body_limit = 16 * 1024
            bundled_asset = posixpath.normpath(path).startswith(("/static/css/", "/static/js/", "/static/vendor/"))
            if pending:
                response = PlainTextResponse("Bakım sürüyor / Maintenance in progress", status_code=503,
                                             headers={"Retry-After": "30", "Cache-Control": "no-store"})
                await response(scope, receive, send)
                return
            if not installed and path != "/setup" and not bundled_asset:
                if path == "/robots.txt":
                    response = PlainTextResponse("User-agent: *\nDisallow: /\n")
                else:
                    response = RedirectResponse("/setup", status_code=303)
                response.headers["Cache-Control"] = "no-store"
                response.headers["X-Robots-Tag"] = "noindex, nofollow"
                await response(scope, receive, send)
                return
            try:
                length = int(request.headers.get("content-length", "0"))
            except ValueError:
                length = body_limit + 1
            if length < 0 or length > body_limit:
                response = PlainTextResponse("İstek çok büyük / Request too large", status_code=413,
                                             headers={"Cache-Control": "no-store"})
                await response(scope, receive, send)
                return
            received = 0

            async def limited_receive() -> Message:
                nonlocal received
                message = await receive()
                if message["type"] == "http.request":
                    received += len(message.get("body", b""))
                    if received > body_limit:
                        raise HTTPException(413, "İstek boyutu sınırını aşıyor.")
                return message

            await self.app(scope, limited_receive, send)


def reset_storage_roots() -> list[Path]:
    """Yanlış yapılandırılmış geniş/kod/veritabanı dizinlerini silmeyi reddet."""
    project = Path(__file__).resolve().parent.parent
    database = Path(make_url(settings.database_url).database or "download.db").resolve()
    roots = [Path(settings.upload_dir).absolute(), Path(settings.download_dir).absolute()]
    protected = [Path.home().resolve(), project, project / "app", project / ".git", project / ".venv", database]
    broad_roots = {
        Path(value).resolve() for value in ("/tmp", "/var", "/private", "/opt", "/srv", "/home", "/Users", "/Volumes", "/mnt", "/media")
    } | {Path.home() / name for name in ("Documents", "Downloads", "Desktop", "Pictures", "Music", "Movies")}
    system_roots = [Path(value).resolve() for value in ("/etc", "/usr", "/bin", "/sbin", "/System", "/Library", "/Applications", "/dev", "/proc", "/sys", "/boot")]
    for root in roots:
        if any(parent.is_symlink() for parent in (root, *root.parents)):
            raise ValueError("reset_storage_unsafe")
        root = root.resolve()
        if root in broad_roots or any(root == base or root.is_relative_to(base) for base in system_roots):
            raise ValueError("reset_storage_unsafe")
        if root == Path(root.anchor) or any(item == root or item.is_relative_to(root) for item in protected):
            raise ValueError("reset_storage_unsafe")
        # Checkout içindeki yalnız iki standart veri kökü silinebilir.
        if root.is_relative_to(project) and root not in {
            project / "app/static/uploads", project / "storage/downloads",
        }:
            raise ValueError("reset_storage_unsafe")
        if root.exists() and not root.is_dir():
            raise ValueError("reset_storage_unsafe")
    resolved = [root.resolve() for root in roots]
    if any(a == b or a.is_relative_to(b) or b.is_relative_to(a) for a, b in [(resolved[0], resolved[1])]):
        raise ValueError("reset_storage_unsafe")
    return resolved


def purge_storage(roots: list[Path]) -> None:
    # Sadece doğrulanmış iki veri dizininin çocukları; sembolik bağ hedefi izlenmez.
    for root in roots:
        root.mkdir(parents=True, exist_ok=True)
        for child in root.iterdir():
            if child.name == ".gitkeep" and child.is_file() and not child.is_symlink():
                continue
            if child.is_symlink() or not child.is_dir():
                child.unlink()
            else:
                shutil.rmtree(child)


async def finish_pending_reset(session: AsyncSession) -> None:
    """DB temizliği commit edilmiştir; kesilen dosya temizliği yeniden denenir."""
    state = await get_lifecycle(session)
    if not state.pending_reset:
        return
    roots = reset_storage_roots()
    if json.loads(state.purge_roots or "[]") != [str(root) for root in roots]:
        raise ValueError("reset_storage_unsafe")
    await run_in_threadpool(purge_storage, roots)
    state.installed = state.pending_reset != "uninstall"
    state.pending_reset = None
    state.purge_roots = None
    await session.commit()
    logger.info("Site verilerinin sıfırlanması tamamlandı")


async def reset_site(session: AsyncSession, action: ResetAction) -> SiteSettings:
    from app.crud import get_site_settings

    current = await get_site_settings(session)
    state = await get_lifecycle(session)
    roots = reset_storage_roots() if action != "settings" else []
    session.info["audit_suppressed"] = True
    username = current.admin_username or settings.admin_username
    password_hash = current.admin_password_hash or settings.admin_password_hash
    language = current.site_language
    if action == "settings":
        await session.execute(delete(MenuItem))
    else:
        for table in reversed(Base.metadata.sorted_tables):
            if table.name not in {"site_lifecycle", "site_settings"}:
                await session.execute(delete(table))
        state.pending_reset = action
        state.purge_roots = json.dumps([str(root) for root in roots])
    await session.delete(current)
    await session.flush()
    fresh = SiteSettings(
        admin_username=username if action != "uninstall" else None,
        admin_password_hash=password_hash if action != "uninstall" else None,
        site_language=language if action != "uninstall" else "tr",
        session_generation=secrets.token_hex(32),
    )
    session.add(fresh)
    await session.commit()
    if action != "settings":
        await finish_pending_reset(session)
    return fresh
