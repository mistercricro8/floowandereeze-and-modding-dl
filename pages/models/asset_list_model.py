"""Base model for asset lists with pagination and backup tracking."""

import logging
from abc import abstractmethod
from typing import override

from PySide6 import QtCore
from sqlalchemy.orm import Mapped

from database.models import UnityAsset
from database.objects import session

logger = logging.getLogger(__name__)

MAX_COMPLETION_NAMES: int = 2000


class AssetListModel(QtCore.QAbstractListModel):
    """Abstract list model providing on-demand lazy loading and pagination."""

    page_size: int = 200

    def __init__(self, assets, database_model):
        super().__init__()
        self.assets: list[UnityAsset] = list(assets) if assets else []
        self.db_model = database_model
        self.thumbs = None
        self._offset: int = len(self.assets)
        self._exhausted: bool = False
        self._fetching: bool = False

    @abstractmethod
    def _load(self, offset: int, limit: int) -> list[UnityAsset]:
        """Fetch a page of assets from the database. Subclasses must implement."""
        raise NotImplementedError

    def refresh(self):
        """Reset pagination offset and load the first page of assets."""
        self._fetching = False
        self.beginResetModel()
        self._offset = 0
        self._exhausted = False
        first_page = self._load(0, self.page_size)
        self.assets = list(first_page)
        self._offset = len(self.assets)
        self._exhausted = len(self.assets) < self.page_size
        self.endResetModel()

    @property
    def can_fetch_more(self) -> bool:
        """Check if additional pages can be fetched."""
        return not self._fetching and not self._exhausted

    @override
    def canFetchMore(self, parent=None) -> bool:
        """Qt model override for lazy pagination."""
        if parent is not None and parent.isValid():
            return False
        return self.can_fetch_more

    @override
    def fetchMore(self, parent=None) -> None:
        """Qt model override to load the next page of assets."""
        if parent is not None and parent.isValid():
            return
        if not self.can_fetch_more:
            return
        self._fetching = True
        try:
            next_page = self._load(self._offset, self.page_size)
            if not next_page:
                self._exhausted = True
                return
            start_row = len(self.assets)
            end_row = start_row + len(next_page) - 1
            self.beginInsertRows(parent or QtCore.QModelIndex(), start_row, end_row)
            self.assets.extend(next_page)
            self._offset += len(next_page)
            if len(next_page) < self.page_size:
                self._exhausted = True
            else:
                self._exhausted = False
            self.endInsertRows()
        finally:
            self._fetching = False

    @override
    def rowCount(self, parent=None) -> int:
        """Return the number of loaded rows, guarding against invalid parents."""
        if parent is not None and parent.isValid():
            return 0
        return len(self.assets)

    @override
    def data(
        self,
        index: QtCore.QModelIndex,
        role: int = QtCore.Qt.ItemDataRole.DisplayRole,
    ):
        """Guard against invalid indexes and return None."""
        if not index.isValid() or not (0 <= index.row() < len(self.assets)):
            return None
        return None

    def set_backup_state(self, asset_id: Mapped[int], has_backup: bool):
        """Update backup status for a given asset ID."""
        session.query(self.db_model).filter(self.db_model.id == asset_id).update(
            {"has_backup": has_backup}
        )

    def reset_backups(self):
        """Reset backup flags for all assets in the model table."""
        session.query(self.db_model).update({"has_backup": False})
