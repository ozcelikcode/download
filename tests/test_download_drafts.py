import re
from html.parser import HTMLParser

import pytest

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.schemas import DownloadCreate


async def test_unnamed_draft_stays_empty_and_cannot_publish(admin_client, db_session):
    response = await admin_client.post('/panel/downloads/drafts/autosave', data={
        'draft_token': 'blank-draft-token', 'title': '', 'external_url': 'https://example.com',
    })
    assert response.status_code == 200
    draft = await crud.get_download_by_id(db_session, response.json()['draft_id'])
    assert draft.title == '' and draft.is_draft
    with pytest.raises(ValueError):
        await crud.bulk_update_downloads(db_session, [draft.id], 'publish')


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
    created = await admin_client.post("/panel/downloads/drafts/autosave", data=payload)

    assert created.status_code == 200
    draft_id = created.json()["draft_id"]
    draft = await crud.get_download_by_id(db_session, draft_id)
    assert draft is not None
    assert draft.title == "İlk Başlık"
    assert draft.is_draft is True
    assert draft.is_active is False
    assert (await client.get(f"/download/{draft.slug}")).status_code == 404

    payload.update({"draft_id": str(draft_id), "title": "Tam Başlık"})
    updated = await admin_client.post("/panel/downloads/drafts/autosave", data=payload)
    db_session.expire_all()
    items, total = await crud.get_downloads_paginated(
        db_session, include_inactive=True, status="draft"
    )

    assert updated.status_code == 200
    assert updated.json()["draft_id"] == draft_id
    assert total == 1
    assert items[0].title == "Tam Başlık"

    repeated = await admin_client.post(
        "/panel/downloads/drafts/autosave",
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
        "/panel/downloads/drafts/autosave",
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
        f"/panel/downloads/{draft_id}/edit",
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
    assert saved.json()["redirect_url"] == "/panel/downloads"
    assert download is not None
    assert download.is_draft is False
    assert download.is_active is True
    assert download.draft_token is None
    assert download.slug == "final-uygulama"


async def test_save_keeps_draft_unpublished_and_returns_to_edit_page(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    autosave = await admin_client.post(
        "/panel/downloads/drafts/autosave",
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
        f"/panel/downloads/{draft_id}/edit",
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
    assert saved.json()["redirect_url"] == f"/panel/downloads/{draft_id}/edit"
    assert draft is not None
    assert draft.is_draft is True
    assert draft.is_active is False
    assert draft.draft_token == "draft-token-save-only"


async def test_incomplete_draft_cannot_be_finalized(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    autosave = await admin_client.post(
        "/panel/downloads/drafts/autosave",
        data={
            "draft_token": "draft-token-3",
            "title": "Eksik Uygulama",
            "file_type": "external",
            "icon_type": "auto",
        },
    )
    draft_id = autosave.json()["draft_id"]

    response = await admin_client.post(
        f"/panel/downloads/{draft_id}/edit",
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
        "/panel/downloads/drafts/autosave",
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
    draft_form = await admin_client.get(f"/panel/downloads/{draft_id}/edit")
    assert draft_form.status_code == 200
    assert 'id="application-publish-button" type="button"' in draft_form.text

    finalized = await admin_client.post(
        f"/panel/downloads/{draft_id}/edit",
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
    assert finalized.json()["message"].startswith("Dış URL:")
    assert "validation error" not in finalized.json()["message"]
    assert "input_value" not in finalized.json()["message"]
    assert "errors.pydantic.dev" not in finalized.json()["message"]
    assert draft.is_draft is True
    assert draft.external_url == "jjj"


async def test_new_download_requires_explicit_publish_intent(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    response = await admin_client.post(
        "/panel/downloads/new",
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
        "/panel/media/upload-file",
        files={"file": ("uygulama.zip", b"archive-content", "application/zip")},
    )
    storage_path = upload.json()["storage_path"]

    autosave = await admin_client.post(
        "/panel/downloads/drafts/autosave",
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
    response = await admin_client.get("/panel/downloads/new")

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
    assert "/panel/downloads/drafts/autosave" in response.text
    preview_button = re.search(r'<button id="application-preview-button"[^>]*>', response.text)
    assert preview_button is not None and 'type="button" disabled' in preview_button.group(0)
    assert "grid-cols-[minmax(0,1fr)_6rem]" in response.text
    assert ">MB</option>" in response.text
    assert ">KB</option>" in response.text
    assert ">GB</option>" in response.text


async def test_saved_draft_can_be_previewed_only_by_admin(
    admin_client: AsyncClient, client: AsyncClient, db_session: AsyncSession
) -> None:
    autosave = await admin_client.post(
        "/panel/downloads/drafts/autosave",
        data={
            "draft_token": "draft-token-preview",
            "title": "Önizleme Taslağı",
            "description": "Yayımlanmadan kontrol edilecek içerik.",
            "file_type": "external",
            "external_url": "https://example.com/preview.zip",
            "icon_type": "auto",
        },
    )
    draft_id = autosave.json()["draft_id"]
    draft = await crud.get_download_by_id(db_session, draft_id)
    assert draft is not None

    preview_url = f"/panel/downloads/{draft_id}/preview"
    anonymous = await client.get(preview_url, follow_redirects=False)
    assert anonymous.status_code == 302
    assert anonymous.headers["location"] == "/login"

    preview = await admin_client.get(preview_url)
    edit_form = await admin_client.get(f"/panel/downloads/{draft_id}/edit")
    public_detail = await client.get(f"/download/{draft.slug}")
    preview_button = re.search(
        r'<button id="application-preview-button"[^>]*>', edit_form.text
    )

    assert preview.status_code == 200
    assert preview_button is not None and 'type="button" disabled' not in preview_button.group(0)
    assert preview.headers["cache-control"] == "no-store"
    assert '<meta name="robots" content="noindex,nofollow">' in preview.text
    assert 'rel="canonical"' not in preview.text
    assert "Taslak önizlemesi" in preview.text
    assert "Yayımlanmadan kontrol edilecek içerik." in preview.text
    assert f'href="/panel/downloads/{draft_id}/edit"' in preview.text
    assert f'href="/dl/{draft.slug}"' not in preview.text
    assert public_detail.status_code == 404


async def test_preview_rejects_published_download(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    published = await crud.create_download(
        db_session,
        DownloadCreate(
            title="Yayımlanmış İçerik",
            file_type="external",
            external_url="https://example.com/published.zip",
        ),
    )

    response = await admin_client.get(f"/panel/downloads/{published.id}/preview")

    assert response.status_code == 404


@pytest.mark.parametrize("empty_value", [None, "None"])
async def test_empty_draft_fields_round_trip_without_breaking_publish(
    admin_client: AsyncClient, db_session: AsyncSession, empty_value: str | None
) -> None:
    draft = await crud.create_download_draft(db_session, "empty-fields", "Boş alanlar")
    draft.version = empty_value
    draft.external_url = empty_value
    draft.icon_image_url = empty_value
    await db_session.commit()
    draft_id = draft.id

    class Inputs(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.values: dict[str, str | None] = {}

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            attributes = dict(attrs)
            if tag == "input" and attributes.get("name"):
                self.values[attributes["name"]] = attributes.get("value", "")

    form = await admin_client.get(f"/panel/downloads/{draft_id}/edit")
    inputs = Inputs()
    inputs.feed(form.text)
    for name in ("version", "external_url", "icon_image_url"):
        assert inputs.values[name] == ""
    assert 'src="None"' not in form.text

    published = await admin_client.post(
        f"/panel/downloads/{draft_id}/edit",
        data={
            "title": "Boş alanlar", "file_type": "external", "icon_type": "auto",
            "external_url": "https://example.com/download.zip",
            "version": inputs.values["version"],
            "icon_image_url": inputs.values["icon_image_url"],
            "submission_intent": "publish", "is_active": "true",
        },
        headers={"Accept": "application/json"},
    )
    assert published.status_code == 200
    await db_session.refresh(draft)
    assert draft.is_draft is False
    assert draft.version is None
    assert draft.icon_image_url is None


async def test_invalid_icon_url_reports_the_field_without_internal_details(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    draft = await crud.create_download_draft(db_session, "invalid-icon", "Deneme")
    response = await admin_client.post(
        f"/panel/downloads/{draft.id}/edit",
        data={
            "title": "Deneme", "file_type": "external", "icon_type": "auto",
            "external_url": "https://example.com/download.zip",
            "icon_image_url": "invalid-icon-url",
            "submission_intent": "publish", "is_active": "true",
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["message"] == (
        "İkon URL: Yalnızca tam HTTP/HTTPS adresleri kullanılabilir."
    )
    await db_session.refresh(draft)
    assert draft.is_draft is True
