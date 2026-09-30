import json

import pytest
from sqlalchemy import select

from app import crud
from app.models import AuditLog
from app.schemas import CategoryCreate


async def test_admin_changes_record_actor_and_old_new_values(admin_client, db_session):
    created = await admin_client.post("/admin/categories", data={"name": "Önce"})
    assert created.status_code == 302
    category = (await crud.get_categories(db_session))[0]
    edited = await admin_client.post(f"/admin/categories/{category.id}/edit", data={"name": "Sonra"})
    assert edited.status_code == 302
    logs = (await db_session.scalars(select(AuditLog).order_by(AuditLog.id))).all()
    assert [log.action for log in logs] == ["create", "update"]
    assert all(log.actor == "admin" for log in logs)
    assert json.loads(logs[-1].changes)["name"] == ["Önce", "Sonra"]
    page = await admin_client.get("/admin/audit")
    assert "Önce" in page.text and "Sonra" in page.text
    assert 'id="audit-density-toggle"' in page.text
    assert 'id="audit-list"' in page.text
    assert 'action="/admin/settings/audit-log-limit"' in page.text


async def test_audit_retention_update_returns_to_log(admin_client):
    response = await admin_client.post(
        "/admin/settings/audit-log-limit", data={"max_records": "100"}
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/admin/audit"
    page = await admin_client.get("/admin/audit")
    assert "Maksimum kayıt · 100" in page.text


async def test_rolled_back_changes_leave_no_history(db_session):
    from app.models import Category
    db_session.info["audit_actor"] = "admin"
    db_session.add(Category(name="Rolled back", slug="rolled-back"))
    await db_session.flush()
    await db_session.rollback()
    assert not (await db_session.scalars(select(AuditLog))).all()


async def test_sensitive_values_are_redacted(db_session):
    db_session.info["audit_actor"] = "admin"
    account = await crud.get_site_settings(db_session)
    account.session_generation = "secret-generation-not-for-history"
    await db_session.commit()
    logs = (await db_session.scalars(select(AuditLog))).all()
    assert logs
    assert all("secret-generation-not-for-history" not in log.changes for log in logs)
    assert any("[gizli]" in log.changes for log in logs)


async def test_deleted_entity_keeps_its_history(admin_client, db_session):
    category = await crud.create_category(db_session, CategoryCreate(name="Removed"))
    response = await admin_client.post(f"/admin/categories/{category.id}/delete")
    assert response.status_code == 302
    log = await db_session.scalar(select(AuditLog).where(AuditLog.action == "delete"))
    assert log.label == "Removed"
    assert log.entity_id == category.id


@pytest.mark.parametrize("path", ["/admin/audit", "/admin/links", "/admin/site-health"])
async def test_reports_require_admin(client, path):
    response = await client.get(path)
    assert response.status_code == 302
    assert response.headers["location"] == "/admin/login"
