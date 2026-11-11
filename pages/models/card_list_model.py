from textwrap import shorten
from threading import Thread
from typing import override

from PySide6.QtGui import Qt
from sqlalchemy import or_

from database.models import CardModel
from database.objects import session
from pages.models.asset_list_model import AssetListModel
from unity.unity_utils import fetch_bundle_thumb
from util.enums import CardArtCoordinates


class CardListModel(AssetListModel):
    def __init__(self, cards=None):
        super().__init__(cards or [], CardModel)
        self.filter = ""
        self.show_favorites = False
        self.search_description = False

    @override
    def refresh(self):
        query = session.query(self.db_model)

        if self.filter != "" and not self.show_favorites:
            if self.search_description:
                query = query.filter(
                    or_(
                        self.db_model.name.contains(self.filter),
                        self.db_model.large_bundle.contains(self.filter),
                    )
                )
            else:
                query = query.filter(self.db_model.name.contains(self.filter))

        if self.show_favorites:
            query = query.filter(self.db_model.favorite.is_(True))

        self.assets = query.order_by(self.db_model.name).all()

        refresh_threads = [
            Thread(target=lambda card=cards_card: self._refresh_card(card))
            for cards_card in self.assets
        ]

        for thread in refresh_threads:
            thread.start()
        for thread in refresh_threads:
            thread.join()

    def _refresh_card(self, card):
        card.thumb = fetch_bundle_thumb(
            card.medium_bundle,
            (128, 128),
            crop_coordinates=CardArtCoordinates.MEDIUM.value,
        )
        if not card.thumb:
            card.thumb = fetch_bundle_thumb(
                card.medium_bundle, (128, 128), True, CardArtCoordinates.MEDIUM.value
            )
            card.unity_file = True

    def data(self, index, role):
        if role == Qt.DisplayRole:
            return shorten(
                self.assets[index.row()].name,
                width=20,
                placeholder="...",
                replace_whitespace=False,
            )

        if role == Qt.DecorationRole:
            return self.assets[index.row()].thumb
