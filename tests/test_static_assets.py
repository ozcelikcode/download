from pathlib import Path
import re

import pytest
from httpx import AsyncClient


VENDOR_ASSETS = (
    "/static/vendor/lucide/1.24.0/lucide.min.js",
    "/static/vendor/cropperjs/1.6.2/cropper.min.css",
    "/static/vendor/cropperjs/1.6.2/cropper.min.js",
    "/static/vendor/quill/2.0.3/quill.snow.css",
    "/static/vendor/quill/2.0.3/quill.js",
)


@pytest.mark.asyncio
@pytest.mark.parametrize("asset_path", VENDOR_ASSETS)
async def test_vendor_asset_is_served_locally(
    client: AsyncClient, asset_path: str
) -> None:
    response = await client.get(asset_path)

    assert response.status_code == 200
    assert response.content
    assert response.headers["content-type"].startswith(("text/css", "text/javascript"))


def test_templates_do_not_load_runtime_assets_from_a_cdn() -> None:
    templates = Path("app/templates")
    external_asset = re.compile(
        r'<(?:script\b[^>]*\bsrc|link\b[^>]*\bhref)=["\']https?://',
        re.IGNORECASE,
    )

    offenders = [
        str(path)
        for path in templates.rglob("*.html")
        if external_asset.search(path.read_text(encoding="utf-8"))
    ]

    assert offenders == []
