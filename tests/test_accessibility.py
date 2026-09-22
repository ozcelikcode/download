"""Ortak erişilebilirlik işaretleri ve statik davranış altyapısı."""

from pathlib import Path

from httpx import AsyncClient


async def test_public_layout_has_keyboard_navigation_landmarks(client: AsyncClient):
    response = await client.get("/")

    assert response.status_code == 200
    assert 'class="skip-link"' in response.text
    assert 'href="#main-content"' in response.text
    assert 'id="main-content" tabindex="-1"' in response.text
    assert '/static/js/accessibility.js?' in response.text
    assert 'data-disclosure-button aria-controls="theme-menu"' in response.text
    assert 'data-disclosure-button aria-controls="mobile-menu"' in response.text


async def test_admin_layout_exposes_accessible_dialog_controls(
    admin_client: AsyncClient,
):
    response = await admin_client.get("/admin")

    assert response.status_code == 200
    assert 'class="skip-link"' in response.text
    assert 'id="main-content" tabindex="-1"' in response.text
    assert 'role="dialog" aria-modal="true"' in response.text
    assert 'role="alertdialog" aria-modal="true"' in response.text
    assert "data-dialog-close" in response.text
    assert "data-dialog-initial-focus" in response.text


async def test_accessibility_script_is_served(client: AsyncClient):
    response = await client.get("/static/js/accessibility.js")

    assert response.status_code == 200
    assert "MutationObserver" in response.text
    assert "data-dialog-close" in response.text
    assert "aria-expanded" in response.text


def test_styles_cover_focus_touch_and_reduced_motion():
    css = Path("app/static/css/app.css").read_text(encoding="utf-8")

    assert ":focus-visible" in css
    assert ".skip-link" in css
    assert "prefers-reduced-motion: reduce" in css
    assert "pointer: coarse" in css
