"""İçerik değişikliklerini aynı veritabanı işlemi içinde kaydeder."""

import enum
import json
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import event, inspect, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models import AuditLog, Category, Download, DownloadVersionHistory, MediaAsset, MenuItem, SiteSettings, Tag

TRACKED = (Download, Category, Tag, MenuItem, SiteSettings, MediaAsset, DownloadVersionHistory)
IGNORED = {"id", "created_at", "updated_at", "download_count", "sha256", "checksum_size", "checksum_mtime_ns"}
ENTITY_LABELS = {"downloads": "İçerik", "categories": "Kategori", "tags": "Etiket", "menu_items": "Menü", "site_settings": "Ayarlar", "media_assets": "Medya", "download_version_history": "Sürüm"}
ACTION_LABELS = {"create": "Eklendi", "update": "Düzenlendi", "delete": "Silindi", "replace": "Dosya değiştirildi", "crop": "Görsel kırpıldı", "reorder": "Sıralandı", "bulk": "Toplu işlem", "transfer": "Aktarıldı", "error": "Hata", "login": "Oturum açıldı"}
FIELD_LABELS = {
    "name": "Ad", "title": "Başlık", "slug": "Adres adı", "description": "Açıklama",
    "short_description": "Kısa açıklama", "position": "Sıra", "version": "Sürüm",
    "file_type": "Kaynak türü", "file_path": "Dosya yolu", "external_url": "İndirme adresi",
    "file_size_bytes": "Dosya boyutu (bayt)", "icon_type": "İkon türü", "thumbnail_path": "Küçük görsel",
    "icon_image_path": "İkon dosyası", "icon_image_url": "İkon adresi", "icon_extension": "Dosya uzantısı",
    "os_compatibility": "İşletim sistemleri", "category_id": "Kategori", "parent_id": "Bağlı sürüm",
    "is_active": "Yayında", "is_featured": "Öne çıkan", "is_official_source": "Resmî kaynak",
    "label": "Başlık", "url": "Adres", "icon": "İkon", "open_in_new_tab": "Yeni sekmede aç",
    "location": "Menü konumu", "site_name": "Site adı", "site_icon": "Site ikonu",
    "site_icon_color": "İkon rengi", "sidebar_block_order": "Yan menü sırası",
    "theme_color": "Renk teması",
    "admin_username": "Yönetici adı", "admin_password_hash": "Yönetici parolası",
    "admin_icon": "Yönetici ikonu", "admin_icon_color": "Yönetici ikon rengi",
    "session_max_age_minutes": "Oturum süresi (dakika)", "path": "Medya yolu",
    "display_name": "Görünen ad", "uploaded_by": "Yükleyen", "download_id": "İçerik",
    "changed_at": "Değişiklik zamanı",
}


def _safe_value(key: str, value: object) -> object:
    if "password" in key or "secret" in key:
        return "[gizli]"
    if isinstance(value, enum.Enum):
        return value.value
    if value is None or isinstance(value, (int, float, bool)):
        return value
    text = str(value)
    if "url" in key:
        parsed = urlsplit(text)
        text = urlunsplit((parsed.scheme, parsed.hostname or "", parsed.path, "[gizli]" if parsed.query else "", ""))
    return text[:500]


@event.listens_for(Session, "after_flush")
def capture_changes(session: Session, flush_context: object) -> None:
    actor = session.info.get("audit_actor")
    if not actor:
        return
    for action, objects in (("create", session.new), ("update", session.dirty), ("delete", session.deleted)):
        for obj in list(objects):
            if not isinstance(obj, TRACKED):
                continue
            state = inspect(obj)
            changes = {}
            for attr in state.mapper.column_attrs:
                key = attr.key
                if key in IGNORED:
                    continue
                history = state.attrs[key].history
                if action == "update" and not history.has_changes():
                    continue
                old = history.deleted[0] if history.deleted else (getattr(obj, key) if action == "delete" else None)
                new = None if action == "delete" else getattr(obj, key)
                changes[key] = [_safe_value(key, old), _safe_value(key, new)]
            if isinstance(obj, Download):
                history = state.attrs.tags.history
                if history.has_changes():
                    changes["etiketler"] = [
                        "Kaldırılan: " + ", ".join(str(t.id) for t in history.deleted),
                        "Eklenen: " + ", ".join(str(t.id) for t in history.added),
                    ]
            if not changes:
                continue
            label = next((str(getattr(obj, k)) for k in ("title", "name", "label", "path", "site_name", "version") if getattr(obj, k, None)), obj.__tablename__)
            session.add(AuditLog(
                actor=actor, action=action, entity=obj.__tablename__, entity_id=obj.id,
                label=label[:300], changes=json.dumps(changes, ensure_ascii=False), level="success",
            ))
            session.info["audit_log_written"] = True


@event.listens_for(Session, "after_flush_postexec")
def prune_audit_logs(session: Session, flush_context: object) -> None:
    """Yeni kayıt eklendiğinde geçmişi ayarlanan üst sınıra indirir."""
    if not session.info.pop("audit_log_written", False):
        return
    limit = session.execute(text("SELECT audit_log_max_records FROM site_settings ORDER BY id LIMIT 1")).scalar()
    limit = limit if limit in {50, 100, 200, 500, 800} else 200
    session.execute(text("DELETE FROM audit_logs WHERE id NOT IN (SELECT id FROM audit_logs ORDER BY id DESC LIMIT :limit)"), {"limit": limit})


def add_event(
    session: AsyncSession,
    action: str,
    entity: str,
    label: str,
    entity_id: int | None = None,
    changes: dict | None = None,
    *,
    actor: str | None = None,
    level: str = "success",
) -> None:
    actor = actor or session.info.get("audit_actor")
    if actor:
        session.add(AuditLog(actor=actor, action=action, entity=entity, entity_id=entity_id, label=label[:300], changes=json.dumps(changes or {}, ensure_ascii=False), level=level))
        session.info["audit_log_written"] = True
