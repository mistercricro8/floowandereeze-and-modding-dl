from textwrap import shorten
from threading import Thread
from typing import override

from PySide6.QtGui import Qt
from sqlalchemy import String, cast, func

from database.models import CharacterModel
from database.objects import session
from pages.models.asset_list_model import AssetListModel
from unity.unity_utils import fetch_bundle_thumb


class CharacterListModel(AssetListModel):
    def __init__(self, characters=None):
        super().__init__(characters or [], CharacterModel)
        self.show_favorites = False
        self.series_filter = ""
        self.filter = ""
        self.refresh()

    @override
    def refresh(self):
        query = session.query(self.db_model)

        if self.series_filter != "":
            query = query.filter(self.db_model.series == self.series_filter)

        if self.show_favorites:
            query = query.filter(self.db_model.favorite.is_(True))

        display_name = func.coalesce(
            func.nullif(self.db_model.name, ""),
            "Character " + cast(self.db_model.konami_id, String),
        )
        if self.filter:
            query = query.filter(display_name.icontains(self.filter, autoescape=True))

        assets = query.order_by(
            self.db_model.series.collate("NOCASE"),
            display_name.collate("NOCASE"),
            self.db_model.konami_id,
        ).all()
        self.beginResetModel()
        self.assets = assets

        self._fallback_thumb = None
        if any(not character.icon for character in self.assets):
            fallback_icon = (
                session.query(self.db_model.icon)
                .filter(self.db_model.konami_id == 9998)
                .scalar()
            )
            if fallback_icon:
                self._fallback_thumb = fetch_bundle_thumb(fallback_icon, (128, 128))

        refresh_threads = [
            Thread(target=lambda character=char: self._refresh_character(character))
            for char in self.assets
            if char.icon
        ]

        for thread in refresh_threads:
            thread.start()
        for thread in refresh_threads:
            thread.join()
        self.endResetModel()

    def _refresh_character(self, character: CharacterModel):
        character.thumb = fetch_bundle_thumb(character.icon, (128, 128))

    def data(self, index, role):
        if role == Qt.DisplayRole:
            asset = self.assets[index.row()]
            return shorten(
                asset.name or f"Character {asset.konami_id}",
                width=20,
                placeholder="...",
            )

        if role == Qt.ToolTipRole:
            asset = self.assets[index.row()]
            return asset.name or f"Character {asset.konami_id}"

        if role == Qt.DecorationRole:
            asset = self.assets[index.row()]
            return asset.thumb if asset.icon else self._fallback_thumb
