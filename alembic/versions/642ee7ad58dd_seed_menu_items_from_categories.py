"""seed menu items from categories

Sitenin üst menüsü artık tamamen `menu_items` tablosundan besleniyor
(otomatik kategori menüsü kaldırıldı). Bu migration, geçiş sırasında
sitenin görünümünü bozmamak için mevcut kategorileri gerçek, admin
panelinden düzenlenebilir MenuItem kayıtlarına dönüştürür.

Revision ID: 642ee7ad58dd
Revises: 36a2f2e1e04c
Create Date: 2026-07-10 14:47:02.565563

"""
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '642ee7ad58dd'
down_revision: Union[str, None] = '36a2f2e1e04c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


menu_items_table = sa.table(
    "menu_items",
    sa.column("label", sa.String),
    sa.column("url", sa.String),
    sa.column("icon", sa.String),
    sa.column("position", sa.Integer),
    sa.column("is_active", sa.Boolean),
    sa.column("open_in_new_tab", sa.Boolean),
    sa.column("created_at", sa.DateTime),
    sa.column("updated_at", sa.DateTime),
)

categories_table = sa.table(
    "categories",
    sa.column("id", sa.Integer),
    sa.column("name", sa.String),
    sa.column("slug", sa.String),
)


def upgrade() -> None:
    bind = op.get_bind()

    # menu_items zaten doluysa (ör. taze kurulum değilse) dokunma.
    existing = bind.execute(sa.select(sa.func.count()).select_from(menu_items_table)).scalar()
    if existing:
        return

    now = datetime.now(timezone.utc)
    rows = [
        {
            "label": "Tümü",
            "url": "/",
            "icon": "layers",
            "position": 0,
            "is_active": True,
            "open_in_new_tab": False,
            "created_at": now,
            "updated_at": now,
        }
    ]

    categories = bind.execute(
        sa.select(categories_table.c.name, categories_table.c.slug).order_by(categories_table.c.name)
    ).fetchall()

    for position, (name, slug) in enumerate(categories, start=1):
        rows.append(
            {
                "label": name,
                "url": f"/category/{slug}",
                "icon": "folder",
                "position": position,
                "is_active": True,
                "open_in_new_tab": False,
                "created_at": now,
                "updated_at": now,
            }
        )

    op.bulk_insert(menu_items_table, rows)


def downgrade() -> None:
    # Veri geri alma işlemi kasıtlı olarak no-op'tur: hangi kayıtların bu
    # migration ile mi yoksa admin tarafından mı eklendiğini ayırt etmek
    # mümkün değil.
    pass
