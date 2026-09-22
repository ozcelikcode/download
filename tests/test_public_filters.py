"""Herkese açık liste sıralama ve filtreleme davranışları."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.config import settings
from app.schemas import CategoryCreate, DownloadCreate, TagCreate


async def _seed_filter_downloads(session: AsyncSession):
    alpha = await crud.create_download(
        session,
        DownloadCreate(
            title="Alpha Official",
            external_url="https://official.example.com/alpha",
            os_compatibility=["windows", "macos"],
            is_official_source=True,
        ),
    )
    zulu = await crud.create_download(
        session,
        DownloadCreate(
            title="Zulu Mirror",
            external_url="https://mirror.example.com/zulu",
            os_compatibility=["linux"],
            is_official_source=False,
        ),
    )
    local_path = settings.download_path / "beta.zip"
    local_path.write_bytes(b"beta")
    beta = await crud.create_download(
        session,
        DownloadCreate(
            title="Beta Local",
            file_type="local",
            file_path=str(local_path),
            os_compatibility=["windows"],
        ),
    )
    alpha.download_count = 2
    beta.download_count = 5
    zulu.download_count = 20
    await session.commit()
    return alpha, beta, zulu


async def test_crud_public_sort_options(db_session: AsyncSession):
    await _seed_filter_downloads(db_session)

    popular, _ = await crud.get_downloads_paginated(db_session, sort="popular")
    alphabetical, _ = await crud.get_downloads_paginated(db_session, sort="title")

    assert [item.title for item in popular] == [
        "Zulu Mirror",
        "Beta Local",
        "Alpha Official",
    ]
    assert [item.title for item in alphabetical] == [
        "Alpha Official",
        "Beta Local",
        "Zulu Mirror",
    ]


async def test_crud_public_filters_match_exact_values(db_session: AsyncSession):
    await _seed_filter_downloads(db_session)

    windows, windows_total = await crud.get_downloads_paginated(
        db_session, os_filter="windows"
    )
    local, local_total = await crud.get_downloads_paginated(
        db_session, file_type_filter="local"
    )
    official, official_total = await crud.get_downloads_paginated(
        db_session, official_filter="official"
    )
    third_party, third_party_total = await crud.get_downloads_paginated(
        db_session, official_filter="third_party"
    )

    assert {item.title for item in windows} == {"Alpha Official", "Beta Local"}
    assert windows_total == 2
    assert [item.title for item in local] == ["Beta Local"]
    assert local_total == 1
    assert [item.title for item in official] == ["Alpha Official"]
    assert official_total == 1
    assert [item.title for item in third_party] == ["Zulu Mirror"]
    assert third_party_total == 1


async def test_public_filter_ui_and_ordering(
    client: AsyncClient, db_session: AsyncSession
):
    await _seed_filter_downloads(db_session)

    response = await client.get("/?sort=popular&os=windows")

    assert response.status_code == 200
    assert 'id="public-sort"' in response.text
    assert '<option value="popular" selected>' in response.text
    assert '<option value="windows" selected>' in response.text
    assert response.text.index("Beta Local") < response.text.index("Alpha Official")
    assert "Zulu Mirror" not in response.text
    assert "Aktif filtreler" in response.text


async def test_search_keeps_query_while_filtering(
    client: AsyncClient, db_session: AsyncSession
):
    await crud.create_download(
        db_session,
        DownloadCreate(
            title="Searchable Linux Tool",
            external_url="https://example.com/linux",
            os_compatibility=["linux"],
        ),
    )

    response = await client.get("/search?q=Searchable&os=linux&source=external")

    assert response.status_code == 200
    assert 'name="q" value="Searchable"' in response.text
    assert "Searchable Linux Tool" in response.text
    assert "os=linux" in response.text
    assert "source=external" in response.text


async def test_category_and_tag_pages_apply_the_same_filters(
    client: AsyncClient, db_session: AsyncSession
):
    category = await crud.create_category(db_session, CategoryCreate(name="Tools"))
    tag = await crud.create_tag(db_session, TagCreate(name="Utility"))
    await crud.create_download(
        db_session,
        DownloadCreate(
            title="Linux Match",
            external_url="https://example.com/linux-match",
            category_id=category.id,
            tag_ids=[tag.id],
            os_compatibility=["linux"],
        ),
    )
    await crud.create_download(
        db_session,
        DownloadCreate(
            title="Windows Excluded",
            external_url="https://example.com/windows-excluded",
            category_id=category.id,
            tag_ids=[tag.id],
            os_compatibility=["windows"],
        ),
    )

    for path in (f"/category/{category.slug}?os=linux", f"/tag/{tag.slug}?os=linux"):
        response = await client.get(path)
        assert response.status_code == 200
        assert "Linux Match" in response.text
        assert "Windows Excluded" not in response.text


async def test_invalid_public_filter_values_return_422(client: AsyncClient):
    for query in ("sort=random", "os=other", "source=filesystem", "trust=unknown"):
        response = await client.get(f"/?{query}")
        assert response.status_code == 422, query
