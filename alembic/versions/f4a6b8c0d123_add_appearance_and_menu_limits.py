"""Görünüm, hero, logo ve menü sınırları.

Revision ID: f4a6b8c0d123
Revises: e3f5a7b9c012
"""

from alembic import op
import sqlalchemy as sa

revision = "f4a6b8c0d123"
down_revision = "e3f5a7b9c012"
branch_labels = None
depends_on = None

_HERO_DEFAULT = '[{"type":"eyebrow","text":"İndirme Merkezi","text_en":"Download Center"},{"type":"title","text":"Güvenli ve Ücretsiz Yazılımlar","text_en":"Safe and Free Software"},{"type":"description","text":"Aradığınız yazılımı bulun, tek tıkla indirin.","text_en":"Find the software you need and download it in one click."},{"type":"search","text":"Yazılım, araç veya kategori ara…","text_en":"Search for software, tools, or categories…"},{"type":"stats","text":"","text_en":""}]'


def upgrade() -> None:
    op.add_column("site_settings", sa.Column("logo_mode", sa.String(20), nullable=False, server_default="icon_text"))
    op.add_column("site_settings", sa.Column("logo_light_path", sa.String(500), nullable=True))
    op.add_column("site_settings", sa.Column("logo_dark_path", sa.String(500), nullable=True))
    op.add_column("site_settings", sa.Column("hero_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("site_settings", sa.Column("hero_background", sa.String(20), nullable=False, server_default="soft"))
    op.add_column("site_settings", sa.Column("hero_image_path", sa.String(500), nullable=True))
    op.add_column("site_settings", sa.Column("hero_components", sa.Text(), nullable=False, server_default=_HERO_DEFAULT))
    op.add_column("site_settings", sa.Column("navbar_limit", sa.Integer(), nullable=False, server_default="8"))
    op.add_column("site_settings", sa.Column("footer_limit", sa.Integer(), nullable=False, server_default="8"))
    op.add_column("site_settings", sa.Column("sidebar_category_limit", sa.Integer(), nullable=False, server_default="10"))
    op.add_column("site_settings", sa.Column("sidebar_tag_limit", sa.Integer(), nullable=False, server_default="25"))


def downgrade() -> None:
    for column in ("sidebar_tag_limit", "sidebar_category_limit", "footer_limit", "navbar_limit", "hero_components", "hero_image_path", "hero_background", "hero_enabled", "logo_dark_path", "logo_light_path", "logo_mode"):
        op.drop_column("site_settings", column)
