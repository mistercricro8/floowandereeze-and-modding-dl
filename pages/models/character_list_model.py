"""Character list model with deterministic search and on-demand fallback icons."""

import logging
from textwrap import shorten
from typing import override

from PySide6 import QtGui
from PySide6.QtCore import QModelIndex, Qt
from sqlalchemy import String, cast, func

from database.models import CharacterModel
from database.objects import session
from pages.models.asset_list_model import MAX_COMPLETION_NAMES, AssetListModel
from unity.unity_utils import fetch_bundle_thumb

logger = logging.getLogger(__name__)


class CharacterListModel(AssetListModel):
    """List model for character assets with AND-combined filters and lazy thumbnails."""

    def __init__(self, characters=None):
        super().__init__(characters or [], CharacterModel)
        self.show_favorites: bool = False
        self.series_filter: str = ""
        self.filter: str = ""
        self._thumb_cache: dict[str, QtGui.QIcon | None] = {}
        self._fallback_thumb: QtGui.QIcon | None = None
        if characters is None:
            self.refresh()

    def get_names(self) -> list[str]:
        """Return distinct character names for completion, capped at 2000."""
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
            logger.exception("Failed to query character completion names")
            return []

    def _get_fallback_thumb(self) -> QtGui.QIcon | None:
        """Fetch and cache the default fallback character icon (konami_id 9998)."""
        if self._fallback_thumb is None:
            try:
                fallback_icon = (
                    session.query(self.db_model.icon)
                    .filter(self.db_model.konami_id == 9998)
                    .scalar()
                )
                if fallback_icon:
                    self._fallback_thumb = fetch_bundle_thumb(fallback_icon, (128, 128))
                else:
                    self._fallback_thumb = None
            except Exception:
                logger.exception("Failed to fetch fallback character icon (9998)")
                self._fallback_thumb = None
        return self._fallback_thumb

    def _refresh_character(self, character: CharacterModel) -> None:
        """Backward compatible helper to load a character's thumbnail."""
        if character.icon:
            character.thumb = fetch_bundle_thumb(character.icon, (128, 128))
        else:
            character.thumb = self._get_fallback_thumb()

    @override
    def _load(self, offset: int, limit: int) -> list[CharacterModel]:
        """Query characters combining search filter + series filter + favorites (all AND)."""
        try:
            query = session.query(self.db_model)

            if self.series_filter:
                query = query.filter(self.db_model.series == self.series_filter)

            if self.show_favorites:
                query = query.filter(self.db_model.favorite.is_(True))

            display_name = func.coalesce(
                func.nullif(self.db_model.name, ""),
                "Character " + cast(self.db_model.konami_id, String),
            )
            if self.filter:
                query = query.filter(
                    display_name.icontains(self.filter, autoescape=True)
                )

            return (
                query.order_by(
                    self.db_model.series.collate("NOCASE"),
                    display_name.collate("NOCASE"),
                    self.db_model.konami_id,
                )
                .offset(offset)
                .limit(limit)
                .all()
            )
        except Exception:
            logger.exception(
                "Failed to load characters at offset %d limit %d", offset, limit
            )
            return []

    @override
    def refresh(self):
        """Requery characters and invalidate thumbnail caches."""
        self._thumb_cache.clear()
        self._fallback_thumb = None
        super().refresh()

    @override
    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        """Provide display name, tooltip and lazy-loaded thumbnails with fallback icon."""
        if not index.isValid() or not (0 <= index.row() < len(self.assets)):
            return None
        asset = self.assets[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return shorten(
                asset.name or f"Character {asset.konami_id}",
                width=20,
                placeholder="...",
            )
        elif role == Qt.ItemDataRole.ToolTipRole:
            return asset.name or f"Character {asset.konami_id}"
        elif role == Qt.ItemDataRole.DecorationRole:
            if not asset.icon:
                return self._get_fallback_thumb()
            if asset.icon not in self._thumb_cache:
                try:
                    thumb = fetch_bundle_thumb(asset.icon, (128, 128))
                    self._thumb_cache[asset.icon] = thumb
                    asset.thumb = thumb
                except Exception:
                    logger.exception(
                        "Failed to load thumbnail for character icon %s", asset.icon
                    )
                    self._thumb_cache[asset.icon] = None
            cached = self._thumb_cache[asset.icon]
            if cached is not None:
                return cached
            return self._get_fallback_thumb()
        else:
            return None
