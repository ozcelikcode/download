"""Display zones, permission boundaries, and UTC preservation."""

from datetime import datetime, timezone
import json
import zipfile

import pytest
from sqlalchemy import select

from app import backups
from app.dependencies import SESSION_COOKIE, create_admin_session_token
from app.models import AuditLog, SiteSettings, User
from app.templating import _format_date, templates
from app.timezones import local_datetime, validate_timezone
from app.locales.timezones import STRINGS


def test_utc_naive_and_aware_timestamps():
    naive = datetime(2026, 10, 4, 8, 57, 31)
    aware = naive.replace(tzinfo=timezone.utc)
    assert local_datetime(naive, "Europe/Istanbul") == local_datetime(aware, "Europe/Istanbul")
    templates.env.globals["site_timezone"] = "Europe/Istanbul"
    assert _format_date(naive, "%H:%M:%S") == "11:57:31"
    assert _format_date(None) == "-"
    assert naive.hour == 8


def test_daylight_saving_and_date_rollover():
    assert local_datetime(datetime(2026, 1, 1, 12), "America/New_York").hour == 7
    assert local_datetime(datetime(2026, 7, 1, 12), "America/New_York").hour == 8
    assert local_datetime(datetime(2026, 10, 4, 23), "Europe/Istanbul").day == 5


@pytest.mark.parametrize("value", ["../etc/passwd", "Unknown/Zone", "UTC" * 100, ""])
def test_invalid_timezone(value):
    with pytest.raises(ValueError):
        validate_timezone(value)


@pytest.mark.parametrize("role", ["admin", "manager", "editor"])
async def test_timezone_setting_permissions(client, db_session, role):
    user = await db_session.scalar(select(User).where(User.username == "admin"))
    user.role = role
    await db_session.commit()
    token = create_admin_session_token(user.username, user.password_hash, user_id=user.id)
    client.cookies.set(SESSION_COOKIE, token, domain="test.local", path="/")
    response = await client.post("/panel/settings/timezone", data={"site_timezone": "Europe/Istanbul"})
    account = await db_session.scalar(select(SiteSettings))
    if role == "editor":
        assert response.status_code == 403 and account.site_timezone == "UTC"
    else:
        assert response.status_code == 302 and account.site_timezone == "Europe/Istanbul"
        page = await client.get("/panel/settings/general")
        assert 'value="Europe/Istanbul" selected' in page.text
        assert templates.env.globals["site_timezone"] == "Europe/Istanbul"


async def test_invalid_zone_does_not_change_settings(admin_client, db_session):
    response = await admin_client.post("/panel/settings/timezone", data={"site_timezone": "Invalid/Zone"})
    assert response.status_code == 302
    assert (await db_session.scalar(select(SiteSettings))).site_timezone == "UTC"


async def test_audit_uses_selected_zone_without_changing_records(admin_client, db_session):
    row = AuditLog(actor="anonymous", action="error", entity="request", label="GET <unmatched> → 404", level="error", changes="{}", created_at=datetime(2026, 10, 4, 8, 57, 31))
    db_session.add(row)
    await db_session.commit()
    await admin_client.post("/panel/settings/timezone", data={"site_timezone": "Europe/Istanbul"})
    html = (await admin_client.get("/panel/audit")).text
    assert "04.10.2026 11:57:31" in html
    assert "Europe/Istanbul" in html
    assert "04.10.2026 08:57:31 UTC" not in html
    assert 'datetime="2026-10-04T08:57:31Z"' in html
    await db_session.refresh(row)
    assert row.created_at.hour == 8


@pytest.mark.parametrize("language", ["en", "es", "fr", "tr"])
def test_timezone_translation_coverage(language):
    assert set(STRINGS[language]) == set(STRINGS["en"])


async def test_backup_before_timezone_remains_importable(db_session):
    stage = backups.new_stage()
    try:
        backups.write_archive(stage / "incoming.zip")
        with zipfile.ZipFile(stage / "incoming.zip") as archive:
            manifest = json.loads(archive.read("manifest.json"))
            data = json.loads(archive.read("data.json"))
        del data["site_settings"][0]["site_timezone"]
        manifest["schema"] = backups.schema_fingerprint(before_timezone=True)
        with zipfile.ZipFile(stage / "incoming.zip", "w") as archive:
            archive.writestr("manifest.json", json.dumps(manifest))
            archive.writestr("data.json", json.dumps(data))
        _, imported = backups.validate_archive(stage)
        assert imported["site_settings"][0]["site_timezone"] == "UTC"
    finally:
        backups.remove_stage(stage)
