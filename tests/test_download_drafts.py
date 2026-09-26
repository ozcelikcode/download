from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud


async def test_autosave_creates_and_updates_one_hidden_draft(
    admin_client: AsyncClient, client: AsyncClient, db_session: AsyncSession
) -> None:
    payload = {
        "draft_token": "draft-token-1",
        "title": "İlk Başlık",
        "description": "İlk açıklama",
        "file_type": "external",
        "icon_type": "auto",
        "is_official_source": "true",
    }
    created = await admin_client.post("/admin/downloads/drafts/autosave", data=payload)

    assert created.status_code == 200
    draft_id = created.json()["draft_id"]
    draft = await crud.get_download_by_id(db_session, draft_id)
    assert draft is not None
    assert draft.title == "İlk Başlık"
    assert draft.is_draft is True
    assert draft.is_active is False
    assert (await client.get(f"/download/{draft.slug}")).status_code == 404

    payload.update({"draft_id": str(draft_id), "title": "Tam Başlık"})
    updated = await admin_client.post("/admin/downloads/drafts/autosave", data=payload)
    db_session.expire_all()
    items, total = await crud.get_downloads_paginated(
        db_session, include_inactive=True, status="draft"
    )

    assert updated.status_code == 200
    assert updated.json()["draft_id"] == draft_id
    assert total == 1
    assert items[0].title == "Tam Başlık"

    repeated = await admin_client.post(
        "/admin/downloads/drafts/autosave",
        data={**payload, "draft_id": ""},
    )
    _, repeated_total = await crud.get_downloads_paginated(
        db_session, include_inactive=True, status="draft"
    )
    assert repeated.json()["draft_id"] == draft_id
    assert repeated_total == 1


async def test_publish_finalizes_draft_and_regenerates_slug(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    autosave = await admin_client.post(
        "/admin/downloads/drafts/autosave",
        data={
            "draft_token": "draft-token-2",
            "title": "A",
            "file_type": "external",
            "icon_type": "auto",
            "is_official_source": "true",
        },
    )
    draft_id = autosave.json()["draft_id"]

    saved = await admin_client.post(
        f"/admin/downloads/{draft_id}/edit",
        data={
            "title": "Final Uygulama",
            "file_type": "external",
            "external_url": "https://example.com/app.zip",
            "icon_type": "auto",
            "submission_intent": "publish",
            "is_active": "true",
            "is_official_source": "true",
        },
        headers={"Accept": "application/json"},
    )
    download = await crud.get_download_by_id(db_session, draft_id)

    assert saved.status_code == 200
    assert saved.json()["redirect_url"] == "/admin/downloads"
    assert download is not None
    assert download.is_draft is False
    assert download.is_active is True
    assert download.draft_token is None
    assert download.slug == "final-uygulama"


async def test_save_keeps_draft_unpublished_and_returns_to_edit_page(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    autosave = await admin_client.post(
        "/admin/downloads/drafts/autosave",
        data={
            "draft_token": "draft-token-save-only",
            "title": "Kaydedilen Taslak",
            "file_type": "external",
            "external_url": "https://example.com/draft.zip",
            "icon_type": "auto",
        },
    )
    draft_id = autosave.json()["draft_id"]

    saved = await admin_client.post(
        f"/admin/downloads/{draft_id}/edit",
        data={
            "title": "Kaydedilen Taslak",
            "file_type": "external",
            "external_url": "https://example.com/draft.zip",
            "icon_type": "auto",
            "submission_intent": "save",
            "is_active": "true",
        },
        headers={"Accept": "application/json"},
    )
    draft = await crud.get_download_by_id(db_session, draft_id)

    assert saved.status_code == 200
    assert saved.json()["redirect_url"] == f"/admin/downloads/{draft_id}/edit"
    assert draft is not None
    assert draft.is_draft is True
    assert draft.is_active is False
    assert draft.draft_token == "draft-token-save-only"


async def test_incomplete_draft_cannot_be_finalized(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    autosave = await admin_client.post(
        "/admin/downloads/drafts/autosave",
        data={
            "draft_token": "draft-token-3",
            "title": "Eksik Uygulama",
            "file_type": "external",
            "icon_type": "auto",
        },
    )
    draft_id = autosave.json()["draft_id"]

    response = await admin_client.post(
        f"/admin/downloads/{draft_id}/edit",
        data={
            "title": "Eksik Uygulama",
            "file_type": "external",
            "icon_type": "auto",
            "submission_intent": "publish",
        },
        headers={"Accept": "application/json"},
    )
    draft = await crud.get_download_by_id(db_session, draft_id)

    assert response.status_code == 422
    assert "Dış bağlantı zorunludur" in response.json()["message"]
    assert draft is not None
    assert draft.is_draft is True


async def test_autosave_preserves_partial_url_but_publish_rejects_it(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    autosaved = await admin_client.post(
        "/admin/downloads/drafts/autosave",
        data={
            "draft_token": "draft-token-partial-url",
            "title": "Kısmi URL",
            "file_type": "external",
            "external_url": "jjj",
            "icon_type": "auto",
            "is_official_source": "true",
        },
    )
    assert autosaved.status_code == 200
    draft_id = autosaved.json()["draft_id"]
    draft = await crud.get_download_by_id(db_session, draft_id)

    assert draft is not None
    assert draft.external_url == "jjj"
    assert draft.is_draft is True
    draft_form = await admin_client.get(f"/admin/downloads/{draft_id}/edit")
    assert draft_form.status_code == 200
    assert 'id="application-publish-button" type="button"' in draft_form.text

    finalized = await admin_client.post(
        f"/admin/downloads/{draft_id}/edit",
        data={
            "title": "Kısmi URL",
            "file_type": "external",
            "external_url": "jjj",
            "icon_type": "auto",
            "submission_intent": "publish",
            "is_active": "true",
            "is_official_source": "true",
        },
        headers={"Accept": "application/json"},
    )
    await db_session.refresh(draft)

    assert finalized.status_code == 422
    assert draft.is_draft is True
    assert draft.external_url == "jjj"


async def test_new_download_requires_explicit_publish_intent(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    response = await admin_client.post(
        "/admin/downloads/new",
        data={
            "title": "Yanlışlıkla Yayınlanmamalı",
            "file_type": "external",
            "external_url": "https://example.com/app.zip",
            "icon_type": "auto",
            "is_active": "true",
        },
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 409
    assert "Yayınla" in response.json()["message"]
    assert (
        await crud.get_download_by_slug(db_session, "yanlislikla-yayinlanmamali")
        is None
    )


async def test_local_file_is_uploaded_before_draft_autosave(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    upload = await admin_client.post(
        "/admin/media/upload-file",
        files={"file": ("uygulama.zip", b"archive-content", "application/zip")},
    )
    storage_path = upload.json()["storage_path"]

    autosave = await admin_client.post(
        "/admin/downloads/drafts/autosave",
        data={
            "draft_token": "draft-token-local",
            "title": "Lokal Uygulama",
            "file_type": "local",
            "file_final_path": storage_path,
            "icon_type": "auto",
        },
    )
    draft = await crud.get_download_by_id(db_session, autosave.json()["draft_id"])

    assert upload.status_code == 200
    assert autosave.status_code == 200
    assert draft is not None
    assert draft.file_path == storage_path
    assert draft.is_draft is True


async def test_draft_form_exposes_live_save_controls(admin_client: AsyncClient) -> None:
    response = await admin_client.get("/admin/downloads/new")

    assert response.status_code == 200
    assert 'id="save-status"' in response.text
    assert 'id="application-save-button"' in response.text
    assert 'id="application-save-button" type="submit" formnovalidate' in response.text
    assert 'id="application-publish-button" type="button"' in response.text
    assert 'id="submission-intent" name="submission_intent" value="save"' in response.text
    assert response.text.index('id="application-publish-button"') < response.text.index(
        'id="application-save-button"'
    )
    assert "submissionIntent.value = 'publish'" in response.text
    assert "activeToggle.checked = true" in response.text
    assert "if (autosaveEnabled && !shouldPublish)" in response.text
    assert "(!autosaveEnabled || shouldPublish) && !form.reportValidity()" in response.text
    assert 'data-autosave="true"' in response.text
    assert "/admin/downloads/drafts/autosave" in response.text
    assert "grid-cols-[minmax(0,1fr)_6rem]" in response.text
    assert ">MB</option>" in response.text
    assert ">KB</option>" in response.text
    assert ">GB</option>" in response.text
