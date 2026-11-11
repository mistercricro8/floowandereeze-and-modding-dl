from abc import abstractmethod
from typing import override

from PySide6 import QtCore
from sqlalchemy.orm import Mapped

from database.models import UnityAsset
from database.objects import session


class AssetListModel(QtCore.QAbstractListModel):
    def __init__(self, assets, database_model):
        super().__init__()
        self.assets: list[UnityAsset] = assets
        self.db_model: UnityAsset = database_model
        self.thumbs = None

    @abstractmethod
    def refresh(self):
        pass

    @override
    def rowCount(self, index):
        return len(self.assets)

    def set_backup_state(self, asset_id: Mapped[int], has_backup: bool):
        session.query(self.db_model).filter(self.db_model.id == asset_id).update(
            {"has_backup": has_backup}
        )

    def reset_backups(self):
        session.query(self.db_model).update({"has_backup": False})
