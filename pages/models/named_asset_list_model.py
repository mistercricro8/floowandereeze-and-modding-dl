"""Named accessory lists with literal search and stable bundle fallbacks."""

from textwrap import shorten

from PySide6.QtCore import Qt
from sqlalchemy import func, or_

from database.objects import session
from pages.models.asset_list_model import AssetListModel
from unity.unity_utils import fetch_bundle_thumb


def asset_name(asset):
    """Show a metadata name or the stable medium bundle identifier."""
    return getattr(asset, "name", None) or getattr(asset, "medium_bundle", "Asset")


class NamedAssetListModel(AssetListModel):
    """Search accessory labels and fetch only visible thumbnails."""

    def __init__(self, assets, database_model, icon_size):
        super().__init__(assets or [], database_model)
        self.filter = ""
        self.show_favorites = False
        self.icon_size = icon_size
        self._thumb_cache = {}
        self.refresh()

    def get_names(self):
        """Return distinct available names for completion."""
        return [
            name
            for (name,) in session.query(self.db_model.name)
            .distinct()
            .order_by(self.db_model.name)
            .all()
            if name
        ]

    def refresh(self):
        """Requery results and invalidate cached previews after changes."""
        model = self.db_model
        query = session.query(model)
        if self.show_favorites:
            query = query.filter(model.favorite.is_(True))
        elif self.filter:
            query = query.filter(
                or_(
                    model.name.contains(self.filter, autoescape=True),
                    model.medium_bundle.contains(self.filter, autoescape=True),
                    model.small_bundle.contains(self.filter, autoescape=True),
                )
            )
        assets = query.order_by(
            func.coalesce(func.nullif(model.name, ""), model.medium_bundle)
        ).all()
        self._thumb_cache.clear()
        self.beginResetModel()
        self.assets = assets
        self.endResetModel()

    def data(self, index, role):
        """Provide compact labels, full tooltips and cached thumbnails."""
        if not index.isValid() or not 0 <= index.row() < len(self.assets):
            return None
        asset = self.assets[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return shorten(asset_name(asset), width=32, placeholder="...")
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"{asset_name(asset)}\n{asset.medium_bundle}"
        if role == Qt.ItemDataRole.DecorationRole:
            if asset.medium_bundle not in self._thumb_cache:
                self._thumb_cache[asset.medium_bundle] = fetch_bundle_thumb(
                    asset.medium_bundle, self.icon_size
                )
            return self._thumb_cache[asset.medium_bundle]
        return None
