"""Card list model with on-demand thumbnail loading and deterministic pagination."""

import logging
from textwrap import shorten
from typing import override

from PySide6 import QtGui
from PySide6.QtCore import QModelIndex, Qt
from sqlalchemy import or_

from database.models import CardModel
from database.objects import session
from pages.models.asset_list_model import MAX_COMPLETION_NAMES, AssetListModel
from unity.unity_utils import fetch_bundle_thumb
from util.enums import CardArtCoordinates

logger = logging.getLogger(__name__)


class CardListModel(AssetListModel):
    """List model for card assets supporting pagination and on-demand art loading."""

    def __init__(self, cards=None):
        super().__init__(cards or [], CardModel)
        self.filter: str = ""
        self.show_favorites: bool = False
        self.search_description: bool = False
        self._thumb_cache: dict[str, QtGui.QIcon | None] = {}
        if cards is None:
            self.refresh()

    def get_names(self) -> list[str]:
        """Return distinct card names for completion, capped at 2000."""
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
            logger.exception("Failed to query card completion names")
            return []

    @override
    def _load(self, offset: int, limit: int) -> list[CardModel]:
        """Query card assets with name/bundle search or favorites filter."""
        try:
            model = self.db_model
            query = session.query(model)
            if self.show_favorites:
                query = query.filter(model.favorite.is_(True))
            elif self.filter:
                query = query.filter(
                    or_(
                        model.name.icontains(self.filter, autoescape=True),
                        model.large_bundle.icontains(self.filter, autoescape=True),
                        model.medium_bundle.icontains(self.filter, autoescape=True),
                        model.small_bundle.icontains(self.filter, autoescape=True),
                    )
                )
            return (
                query.order_by(model.name, model.id).offset(offset).limit(limit).all()
            )
        except Exception:
            logger.exception(
                "Failed to load cards at offset %d limit %d", offset, limit
            )
            return []

    def _load_card_thumb(self, card: CardModel) -> QtGui.QIcon | None:
        """Fetch and crop thumbnail on demand, marking unity_file lazily."""
        try:
            thumb = fetch_bundle_thumb(
                card.medium_bundle,
                (128, 128),
                crop_coordinates=CardArtCoordinates.MEDIUM.value,
            )
            if not thumb:
                thumb = fetch_bundle_thumb(
                    card.medium_bundle,
                    (128, 128),
                    True,
                    CardArtCoordinates.MEDIUM.value,
                )
                card.unity_file = True
            card.thumb = thumb
            return thumb
        except Exception:
            logger.exception(
                "Failed to load thumbnail for card %s (%s)",
                card.name,
                card.medium_bundle,
            )
            return None

    def _refresh_card(self, card: CardModel) -> None:
        """Backward compatible helper to load a card's thumbnail."""
        self._load_card_thumb(card)

    @override
    def refresh(self):
        """Requery card results and invalidate thumbnail cache."""
        self._thumb_cache.clear()
        super().refresh()

    @override
    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        """Provide card name, tooltip details, and lazy-loaded thumbnails."""
        if not index.isValid() or not (0 <= index.row() < len(self.assets)):
            return None
        card = self.assets[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return shorten(
                card.name,
                width=20,
                placeholder="...",
                replace_whitespace=False,
            )
        elif role == Qt.ItemDataRole.ToolTipRole:
            status = "\nBackup: Secured" if card.has_backup else ""
            return f"{card.name}\nBundle: {card.large_bundle}{status}"
        elif role == Qt.ItemDataRole.DecorationRole:
            bundle = card.medium_bundle
            if not bundle:
                return None
            if bundle not in self._thumb_cache:
                self._thumb_cache[bundle] = self._load_card_thumb(card)
            return self._thumb_cache[bundle]
        else:
            return None
