from __future__ import annotations

from datetime import datetime, timezone

from app import crud
from app.models import AuditLog


async def test_recent_audit_logs_are_newest_first(db_session):
    db_session.add_all(
        [
            AuditLog(
                actor="admin",
                action="create",
                level="success",
                entity="downloads",
                entity_id=1,
                label="Eski işlem",
                changes="{}",
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
            AuditLog(
                actor="admin",
                action="update",
                level="success",
                entity="downloads",
                entity_id=2,
                label="Yeni işlem",
                changes="{}",
                created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            ),
        ]
    )
    await db_session.commit()

    rows = await crud.get_recent_audit_logs(db_session, limit=1)

    assert [row.label for row in rows] == ["Yeni işlem"]


async def test_dashboard_renders_recent_activity(admin_client, db_session):
    db_session.add_all(
        [
            AuditLog(
                actor="admin",
                action="create",
                level="success",
                entity="categories",
                entity_id=1,
                label="Araçlar",
                changes="{}",
                created_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            ),
            AuditLog(
                actor="system",
                action="error",
                level="error",
                entity="request",
                label="GET /admin → 500",
                changes="{}",
                created_at=datetime(2026, 1, 2, 11, 30, tzinfo=timezone.utc),
            ),
        ]
    )
    await db_session.commit()

    response = await admin_client.get("/admin")

    assert response.status_code == 200
    assert "Son İşlemler" in response.text
    assert 'href="/admin/audit"' in response.text
    assert "GET /admin → 500" in response.text
    assert "hata oluştu" in response.text
    assert "Araçlar" in response.text
    assert "eklendi" in response.text
    assert response.text.index("GET /admin → 500") < response.text.index("Araçlar")
    assert 'datetime="2026-01-02T11:30:00' in response.text


async def test_dashboard_activity_has_empty_state(admin_client):
    response = await admin_client.get("/admin")

    assert response.status_code == 200
    assert "Henüz kayıtlı bir işlem yok." in response.text
