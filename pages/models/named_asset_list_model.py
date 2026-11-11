"""Named accessory lists with literal search and stable bundle fallbacks."""

import logging
from textwrap import shorten
from typing import override

from PySide6.QtCore import QModelIndex, Qt
from sqlalchemy import func, or_

from database.objects import session
from pages.models.asset_list_model import MAX_COMPLETION_NAMES, AssetListModel
from unity.unity_utils import fetch_bundle_thumb

logger = logging.getLogger(__name__)


def asset_name(asset):
    """Show a metadata name or the stable medium bundle identifier."""
    return getattr(asset, "name", None) or getattr(asset, "medium_bundle", "Asset")


class NamedAssetListModel(AssetListModel):
    """Search accessory labels and fetch only visible thumbnails."""

    def __init__(self, assets, database_model, icon_size):
        super().__init__(assets or [], database_model)
        self.filter: str = ""
        self.show_favorites: bool = False
        self.icon_size: tuple[int, int] = icon_size
        self._thumb_cache: dict[str, object] = {}
        self.refresh()

    def get_names(self) -> list[str]:
        """Return distinct available names for completion, capped at 2000."""
        try:
            return [
                name
                for (name,) in session.query(self.db_model.name)
                .filter(self.db_model.name.isnot(None), self.db_model.name != "")
                .distinct()
                .order_by(self.db_model.name)
                .limit(MAX_COMPLETION_NAMES)
                .all()
                if name
            ]
        except Exception:
            logger.exception(
                "Failed to query completion names for %s",
                getattr(self.db_model, "__tablename__", "model"),
            )
            return []

    @override
    def _load(self, offset: int, limit: int) -> list:
        """Query assets using favorites XOR filter with deterministic pagination."""
        try:
            model = self.db_model
            query = session.query(model)
            if self.show_favorites:
                query = query.filter(model.favorite.is_(True))
            elif self.filter:
                query = query.filter(
                    or_(
                        model.name.icontains(self.filter, autoescape=True),
                        model.medium_bundle.icontains(self.filter, autoescape=True),
                        model.small_bundle.icontains(self.filter, autoescape=True),
                    )
                )
            display_sort = func.coalesce(
                func.nullif(model.name, ""),
                model.medium_bundle,
            )
            return (
                query.order_by(display_sort, model.id).offset(offset).limit(limit).all()
            )
        except Exception:
            logger.exception(
                "Failed to load assets for %s at offset %d limit %d",
                getattr(self.db_model, "__tablename__", "model"),
                offset,
                limit,
            )
            return []

    @override
    def refresh(self):
        """Requery results and invalidate cached previews after changes."""
        self._thumb_cache.clear()
        super().refresh()

    @override
    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        """Provide compact labels, full tooltips and cached thumbnails."""
        if not index.isValid() or not (0 <= index.row() < len(self.assets)):
            return None
        asset = self.assets[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return shorten(asset_name(asset), width=32, placeholder="...")
        elif role == Qt.ItemDataRole.ToolTipRole:
            return f"{asset_name(asset)}\n{asset.medium_bundle}"
        elif role == Qt.ItemDataRole.DecorationRole:
            bundle = getattr(asset, "medium_bundle", None)
            if not bundle:
                return None
            if bundle not in self._thumb_cache:
                try:
                    self._thumb_cache[bundle] = fetch_bundle_thumb(
                        bundle, self.icon_size
                    )
                except Exception:
                    logger.exception("Failed to fetch thumbnail for bundle %s", bundle)
                    self._thumb_cache[bundle] = None
            return self._thumb_cache[bundle]
        else:
            return None
