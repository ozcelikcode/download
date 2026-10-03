"""Bounded encrypted site archives; private recovery keys never enter the server."""

from __future__ import annotations

import base64
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import struct
import tempfile
import uuid
import zipfile

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from sqlalchemy.engine import make_url

from app.config import settings
from app.database import Base

MAGIC = b"DLBACK01"
BACKUP_NAME = re.compile(r"\d{8}T\d{12}Z_[a-f0-9]{32}\.dbackup\Z")
JOB_ID = re.compile(r"[a-f0-9]{32}\Z")
INTERVALS = (1, 3, 5, 7, 14)
HISTORY_LIMIT = 7
KEEP = HISTORY_LIMIT + 1


class BackupError(ValueError):
    """A safe, localizable error code without submitted values."""


def backup_root() -> Path:
    root = Path(settings.backup_dir)
    if any(path.is_symlink() for path in (root, *root.parents)):
        raise BackupError("backup_storage_unsafe")
    root = root.resolve()
    project = Path.cwd().resolve()
    forbidden = [project / "app/static", settings.upload_path.resolve(), settings.download_path.resolve()]
    broad = {Path(p).resolve() for p in ("/tmp", "/var", "/private", "/opt", "/srv", "/home", "/Users", "/Volumes", "/mnt")}
    if root in broad | {project, Path.home().resolve(), Path(root.anchor)} or any(root == p or root.is_relative_to(p) or p.is_relative_to(root) for p in forbidden) or (root.is_relative_to(project) and root != project / "storage/backups"):
        raise BackupError("backup_storage_unsafe")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    return root


def size_limit() -> int:
    return max(1, min(settings.max_backup_size_mb, 8192)) * 1024 * 1024


def public_key(pem: str) -> rsa.RSAPublicKey:
    try:
        key = serialization.load_pem_public_key(pem.encode("ascii"))
    except (ValueError, TypeError, UnicodeError) as exc:
        raise BackupError("backup_invalid") from exc
    if not isinstance(key, rsa.RSAPublicKey) or key.key_size not in {3072, 4096} or key.public_numbers().e != 65537:
        raise BackupError("backup_invalid")
    return key


def fingerprint(pem: str) -> str:
    der = public_key(pem).public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return hashlib.sha256(der).hexdigest()


def schema_fingerprint() -> str:
    schema = {table.name: [(column.name, str(column.type), column.nullable) for column in table.columns]
              for table in Base.metadata.sorted_tables if table.name != "backup_policy"}
    return hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest()


def database_path() -> Path:
    return Path(make_url(settings.database_url).database).resolve()


def write_archive(destination: Path, database: Path | None = None) -> None:
    """Caller holds the site gate so database and media represent one snapshot."""
    database = database or database_path()
    uploads, downloads = settings.upload_path.resolve(), settings.download_path.resolve()
    tables = [table for table in Base.metadata.sorted_tables if table.name != "backup_policy"]
    with tempfile.TemporaryDirectory(prefix="snapshot-", dir=backup_root()) as work:
        snapshot = Path(work) / "data.db"
        with closing(sqlite3.connect(f"file:{database}?mode=ro", uri=True)) as source, closing(sqlite3.connect(snapshot)) as target:
            source.backup(target)
        with closing(sqlite3.connect(snapshot)) as source, zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as archive:
            source.row_factory = sqlite3.Row
            data = {table.name: [dict(row) for row in source.execute('SELECT * FROM "' + table.name + '"')] for table in tables}
            account = data["site_settings"][0]
            if not data["site_lifecycle"] or not data["site_lifecycle"][0]["installed"]:
                raise BackupError("backup_missing")
            manifest = {"format": 1, "schema": schema_fingerprint(), "site_name": account["site_name"],
                        "created_at": datetime.now(timezone.utc).isoformat(), "download_root": str(downloads)}
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
            encoded_data = json.dumps(data, ensure_ascii=False).encode("utf-8")
            if len(encoded_data) > 128 * 1024 * 1024:
                raise BackupError("backup_too_large")
            archive.writestr("data.json", encoded_data)
            total = destination.stat().st_size
            file_count = 2
            for label, root in (("uploads", uploads), ("downloads", downloads)):
                for path in sorted(root.rglob("*")):
                    if path.is_symlink():
                        raise BackupError("backup_storage_unsafe")
                    if path.is_file():
                        file_count += 1
                        if file_count > 100_000:
                            raise BackupError("backup_too_large")
                        total += path.stat().st_size
                        if total > size_limit():
                            raise BackupError("backup_too_large")
                        archive.write(path, label + "/" + path.relative_to(root).as_posix())
            if destination.stat().st_size > size_limit():
                raise BackupError("backup_too_large")
        if destination.stat().st_size > size_limit():
            raise BackupError("backup_too_large")


def encrypt_archive(source: Path, destination: Path, pem: str) -> None:
    key, iv = os.urandom(32), os.urandom(12)
    wrapped = public_key(pem).encrypt(key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    metadata = json.dumps({"format": 1, "key_id": fingerprint(pem), "iv": base64.b64encode(iv).decode(),
                           "wrapped_key": base64.b64encode(wrapped).decode(), "created_at": datetime.now(timezone.utc).isoformat()}, separators=(",", ":")).encode()
    header = MAGIC + struct.pack(">I", len(metadata)) + metadata
    encryptor = Cipher(algorithms.AES(key), modes.GCM(iv)).encryptor()
    encryptor.authenticate_additional_data(header)
    with source.open("rb") as plain, destination.open("xb") as encrypted:
        destination.chmod(0o600)
        encrypted.write(header)
        while chunk := plain.read(1024 * 1024):
            encrypted.write(encryptor.update(chunk))
        encrypted.write(encryptor.finalize())
        encrypted.write(encryptor.tag)
        encrypted.flush()
        os.fsync(encrypted.fileno())


def list_backups() -> list[Path]:
    return sorted((p for p in backup_root().iterdir() if BACKUP_NAME.fullmatch(p.name) and p.is_file() and not p.is_symlink()), reverse=True)


def sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def create_backup(pem: str, database: Path | None = None) -> Path:
    public_key(pem)
    root = backup_root()
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "_" + uuid.uuid4().hex + ".dbackup"
    with tempfile.TemporaryDirectory(prefix="snapshot-", dir=root) as work:
        archive, encrypted = Path(work) / "archive.zip", Path(work) / "encrypted.part"
        write_archive(archive, database)
        encrypt_archive(archive, encrypted, pem)
        destination = root / name
        encrypted.replace(destination)
        sync_directory(root)
    # Never prune until a complete, authenticated replacement has been written.
    for old in list_backups()[KEEP:]:
        old.unlink()
    return destination


def delete_backup(name: str) -> None:
    files = list_backups()
    if not BACKUP_NAME.fullmatch(name) or not any(p.name == name for p in files):
        raise BackupError("backup_missing")
    if files[0].name == name:
        raise BackupError("backup_latest_protected")
    (backup_root() / name).unlink()


def new_stage() -> Path:
    work = backup_root() / ".work"
    work.mkdir(mode=0o700, exist_ok=True)
    stage = work / uuid.uuid4().hex
    stage.mkdir(mode=0o700)
    return stage


def stage_path(stage_id: str) -> Path:
    if not JOB_ID.fullmatch(stage_id):
        raise BackupError("backup_invalid")
    root = backup_root() / ".work"
    stage = root / stage_id
    if stage.is_symlink() or root.is_symlink() or not stage.is_dir():
        raise BackupError("backup_missing")
    return stage


def validate_archive(stage: Path) -> tuple[dict, dict]:
    """Reject traversal, links, compression bombs, incompatible schemas, and extra files."""
    try:
        with zipfile.ZipFile(stage / "incoming.zip") as archive:
            infos = archive.infolist()
            if len(infos) > 100_000 or sum(info.file_size for info in infos) > size_limit():
                raise BackupError("backup_too_large")
            names: set[str] = set()
            for info in infos:
                path = PurePosixPath(info.filename)
                if info.filename in names or info.filename != path.as_posix() or info.is_dir() or path.is_absolute() or ".." in path.parts or "\\" in info.filename or any(ord(c) < 32 for c in info.filename):
                    raise BackupError("backup_invalid")
                names.add(info.filename)
                if info.compress_type != zipfile.ZIP_STORED or (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise BackupError("backup_invalid")
                if info.filename not in {"manifest.json", "data.json"} and (len(path.parts) < 2 or path.parts[0] not in {"uploads", "downloads"}):
                    raise BackupError("backup_invalid")
            if archive.getinfo("manifest.json").file_size > 8192 or archive.getinfo("data.json").file_size > 128 * 1024 * 1024:
                raise BackupError("backup_too_large")
            manifest = json.loads(archive.read("manifest.json"))
            data = json.loads(archive.read("data.json"))
            if not isinstance(manifest, dict):
                raise BackupError("backup_invalid")
            if manifest.get("format") != 1 or manifest.get("schema") != schema_fingerprint():
                raise BackupError("backup_incompatible")
            expected = {t.name for t in Base.metadata.sorted_tables if t.name != "backup_policy"}
            if not isinstance(data, dict) or set(data) != expected:
                raise BackupError("backup_invalid")
            for table in Base.metadata.sorted_tables:
                if table.name == "backup_policy":
                    continue
                rows = data[table.name]
                if not isinstance(rows, list) or any(not isinstance(row, dict) or set(row) != set(table.columns.keys()) or any(not isinstance(value, (str, int, float, bool, type(None))) for value in row.values()) for row in rows):
                    raise BackupError("backup_invalid")
            if len(data["site_settings"]) != 1 or len(data["site_lifecycle"]) != 1:
                raise BackupError("backup_invalid")
            if data["site_lifecycle"][0]["id"] != 1:
                raise BackupError("backup_invalid")
            extracted = stage / "extracted"
            extracted.mkdir(mode=0o700, exist_ok=True)
            for info in infos:
                if info.filename in {"manifest.json", "data.json"} or info.is_dir():
                    continue
                target = extracted.joinpath(*PurePosixPath(info.filename).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output, 1024 * 1024)
            for label in ("uploads", "downloads"):
                (extracted / label).mkdir(exist_ok=True)
            return manifest, data
    except BackupError:
        raise
    except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile, RecursionError) as exc:
        raise BackupError("backup_invalid") from exc


def remove_stage(stage: Path) -> None:
    if stage.parent != backup_root() / ".work" or not JOB_ID.fullmatch(stage.name) or stage.is_symlink():
        raise BackupError("backup_storage_unsafe")
    shutil.rmtree(stage)


def clean_stages() -> None:
    """Remove abandoned plaintext imports after their 15-minute review window."""
    import time

    root = backup_root()
    for abandoned in root.iterdir():
        if re.fullmatch(r"snapshot-[a-z0-9_]{8}", abandoned.name) and abandoned.is_dir() and not abandoned.is_symlink() and time.time() - abandoned.stat().st_mtime > 900:
            shutil.rmtree(abandoned)
    work = root / ".work"
    if not work.is_dir() or work.is_symlink():
        return
    journal = backup_root() / "restore.json"
    protected = json.loads(journal.read_text())["stage"] if journal.exists() else None
    for stage in work.iterdir():
        if JOB_ID.fullmatch(stage.name) and stage.name != protected and not stage.is_symlink() and stage.is_dir() and time.time() - stage.stat().st_mtime > 900:
            remove_stage(stage)


def write_journal(stage: Path) -> None:
    temporary = backup_root() / "restore.tmp"
    with temporary.open("w") as output:
        json.dump({"stage": stage.name}, output)
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(backup_root() / "restore.json")
    sync_directory(backup_root())


def recover_restore(committed_marker: str | None) -> None:
    """Database commit decides whether a crash completes or rolls back media swaps."""
    journal = backup_root() / "restore.json"
    if not journal.exists():
        return
    stage = stage_path(json.loads(journal.read_text())["stage"])
    from app.lifecycle import reset_storage_roots
    roots = reset_storage_roots()
    if committed_marker != stage.name:
        for label, root in zip(("uploads", "downloads"), roots):
            old = stage / ("old-" + label)
            if old.exists():
                if root.exists():
                    root.rename(stage / ("failed-" + label))
                old.rename(root)
    journal.unlink()
    remove_stage(stage)


def install_media(stage: Path) -> None:
    from app.lifecycle import reset_storage_roots
    roots = reset_storage_roots()
    if any(root.stat().st_dev != stage.stat().st_dev for root in roots):
        raise BackupError("backup_storage_unsafe")
    write_journal(stage)
    for label, root in zip(("uploads", "downloads"), roots):
        root.rename(stage / ("old-" + label))
        (stage / "extracted" / label).rename(root)
        sync_directory(root.parent)
    sync_directory(stage)
