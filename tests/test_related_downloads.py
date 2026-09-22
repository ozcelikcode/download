"""Detay sayfasındaki ilişkili içerik sıralaması ve CTA testleri."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.schemas import CategoryCreate, DownloadCreate, TagCreate


async def _seed_related(session: AsyncSession):
    category = await crud.create_category(session, CategoryCreate(name="Development"))
    other_category = await crud.create_category(session, CategoryCreate(name="Other"))
    editor = await crud.create_tag(session, TagCreate(name="Editor"))
    utility = await crud.create_tag(session, TagCreate(name="Utility"))

    current = await crud.create_download(
        session,
        DownloadCreate(
            title="Current App",
            external_url="https://example.com/current",
            category_id=category.id,
            tag_ids=[editor.id, utility.id],
        ),
    )
    same_category_and_tag = await crud.create_download(
        session,
        DownloadCreate(
            title="Closest Match",
            external_url="https://example.com/closest",
            category_id=category.id,
            tag_ids=[editor.id],
        ),
    )
    same_category = await crud.create_download(
        session,
        DownloadCreate(
            title="Category Match",
            external_url="https://example.com/category",
            category_id=category.id,
        ),
    )
    shared_tag = await crud.create_download(
        session,
        DownloadCreate(
            title="Tag Match",
            external_url="https://example.com/tag",
            category_id=other_category.id,
            tag_ids=[utility.id],
        ),
    )
    await crud.create_download(
        session,
        DownloadCreate(
            title="Unrelated App",
            external_url="https://example.com/unrelated",
            category_id=other_category.id,
        ),
    )
    loaded_current = await crud.get_download_by_slug(session, current.slug)
    assert loaded_current is not None
    return loaded_current, same_category_and_tag, same_category, shared_tag


async def test_related_downloads_rank_category_and_shared_tags(
    db_session: AsyncSession,
):
    current, closest, category_match, tag_match = await _seed_related(db_session)

    related = await crud.get_related_downloads(db_session, current)

    assert [item.id for item in related] == [
        closest.id,
        category_match.id,
        tag_match.id,
    ]


async def test_detail_page_renders_related_downloads_and_enhanced_external_cta(
    client: AsyncClient,
    db_session: AsyncSession,
):
    current, closest, category_match, tag_match = await _seed_related(db_session)

    response = await client.get(f"/download/{current.slug}")

    assert response.status_code == 200
    assert "İlgili İndirmeler" in response.text
    for related in (closest, category_match, tag_match):
        assert f'href="/download/{related.slug}"' in response.text
    assert "Unrelated App" not in response.text
    assert "Haricî site" in response.text
    assert "Yeni sekmede açılır" in response.text
    assert response.text.count(f'href="/dl/{current.slug}"') == 2
