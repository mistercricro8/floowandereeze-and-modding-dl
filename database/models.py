"""
Database models for the application.
This module defines all SQLAlchemy models used to store application data,
including configuration, card data, and various UI assets.
"""

from typing import ClassVar

from PySide6.QtGui import QIcon
from sqlalchemy import JSON, Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.objects import base, engine
from util.enums import CharaAssetType


class UnityAsset:
    """
    Base class for Unity asset models.

    This class provides common fields for all Unity asset models:
    - id: Unique identifier
    - favorite: Whether the asset is marked as favorite
    - has_backup: Whether the asset has a backup

    Note: All child classes should have a `thumb: QIcon = QIcon()` attribute,
    but it's explicitly declared in children due to PyInstaller limitations.
    """

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    has_backup: Mapped[bool] = mapped_column(Boolean, default=False)


class AppConfig(base):
    """
    Application configuration model.

    Stores global application settings including:
    - Game path and background path
    - Version and crypto key
    - Mipmap settings and backup preferences
    - Background display mode
    """

    __tablename__ = "app_config"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    mipmap_count: Mapped[int] = mapped_column(Integer, default=10)
    game_path: Mapped[str] = mapped_column(String(610))
    background_path: Mapped[str] = mapped_column(String(610), nullable=True)
    version: Mapped[str] = mapped_column(String(100), nullable=True)
    crypto_key: Mapped[str] = mapped_column(String(100), nullable=True)
    packer: Mapped[str] = mapped_column(String(10), default="lz4")
    create_backup: Mapped[bool] = mapped_column(Boolean, default=True)
    background_mode: Mapped[str] = mapped_column(String(10), default="stretched")
    metadata_repository: Mapped[str] = mapped_column(
        Text, default="Nauder/floowandereeze-and-modding-etl-dl"
    )
    metadata_branch: Mapped[str] = mapped_column(String(255), default="")
    metadata_last_source: Mapped[str | None] = mapped_column(Text, nullable=True)


class SleeveModel(UnityAsset, base):
    """
    Model for card sleeve assets.

    Stores information about card sleeves including:
    - bundle: Unique identifier for the sleeve asset
    - thumb: Thumbnail icon for the sleeve
    """

    __tablename__ = "sleeve"

    name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    small_bundle: Mapped[str] = mapped_column(String(8), unique=True)
    medium_bundle: Mapped[str] = mapped_column(String(8), unique=True)
    thumb: QIcon = QIcon()


class CardModel(UnityAsset, base):
    """
    Model for card assets.

    Stores information about cards including:
    - name and description (original and modded)
    - bundle identifier
    - data index for Unity file
    - thumbnail icon
    """

    __tablename__ = "card"

    name: Mapped[str] = mapped_column(String(255))
    large_bundle: Mapped[str] = mapped_column(String(8), unique=True, nullable=True)
    medium_bundle: Mapped[str] = mapped_column(String(8), unique=True)
    small_bundle: Mapped[str] = mapped_column(String(8), unique=True)
    unity_file: ClassVar[bool] = False
    thumb: QIcon = QIcon()


class FieldModel(UnityAsset, base):
    """
    Model for field assets.

    Stores information about field assets including:
    - bundle identifier
    - position flags (bottom, flipped)
    - thumbnail icon
    """

    __tablename__ = "field"

    name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    small_bundle: Mapped[str] = mapped_column(String(8), unique=True)
    medium_bundle: Mapped[str] = mapped_column(String(8), unique=True)
    thumb: QIcon = QIcon()


class CharacterAssets:
    """Character assets container with dynamic mapping from CharaAssetType
    enum values."""

    _ENUM_TO_ATTR = {
        CharaAssetType.ICON: "icon",
        CharaAssetType.SELECT: "select",
        CharaAssetType.DUEL_1: "duel_1",
        CharaAssetType.DUEL_2: "duel_2",
        CharaAssetType.DUEL_3: "duel_3",
        CharaAssetType.DUEL_4: "duel_4",
        CharaAssetType.DUEL_5: "duel_5",
        CharaAssetType.DUEL_6: "duel_6",
        CharaAssetType.DUEL_7: "duel_7",
        CharaAssetType.DUEL_8: "duel_8",
        CharaAssetType.DUEL_9: "duel_9",
        CharaAssetType.DUEL_10: "duel_10",
        CharaAssetType.DUEL_11: "duel_11",
        CharaAssetType.DUEL_12: "duel_12",
        CharaAssetType.DUEL_13: "duel_13",
        CharaAssetType.DUEL_14: "duel_14",
        CharaAssetType.DUEL_15: "duel_15",
        CharaAssetType.DUEL_16: "duel_16",
        CharaAssetType.DUEL_17: "duel_17",
        CharaAssetType.DUEL_18: "duel_18",
        CharaAssetType.DUEL_19: "duel_19",
        CharaAssetType.DUEL_20: "duel_20",
        CharaAssetType.DUEL_31: "duel_31",
        CharaAssetType.DUEL_32: "duel_32",
        CharaAssetType.DUEL_33: "duel_33",
        CharaAssetType.DUEL_34: "duel_34",
        CharaAssetType.DUEL_35: "duel_35",
        CharaAssetType.DUEL_36: "duel_36",
        CharaAssetType.DUEL_37: "duel_37",
        CharaAssetType.DUEL_38: "duel_38",
        CharaAssetType.DUEL_39: "duel_39",
        CharaAssetType.DUEL_40: "duel_40",
        CharaAssetType.DUEL_41: "duel_41",
        CharaAssetType.DUEL_42: "duel_42",
        CharaAssetType.WORLD: "world",
        CharaAssetType.EVENT: "event",
        CharaAssetType.DIALOG_0: "dialog_0",
        CharaAssetType.DIALOG_1: "dialog_1",
        CharaAssetType.DIALOG_2: "dialog_2",
        CharaAssetType.DIALOG_3: "dialog_3",
        CharaAssetType.DIALOG_4: "dialog_4",
        CharaAssetType.DIALOG_5: "dialog_5",
        CharaAssetType.DIALOG_6: "dialog_6",
        CharaAssetType.DIALOG_7: "dialog_7",
        CharaAssetType.DIALOG_8: "dialog_8",
        CharaAssetType.DIALOG_9: "dialog_9",
        CharaAssetType.DIALOG_10: "dialog_10",
        CharaAssetType.DIALOG_11: "dialog_11",
        CharaAssetType.DIALOG_12: "dialog_12",
        CharaAssetType.DIALOG_13: "dialog_13",
        CharaAssetType.DIALOG_14: "dialog_14",
        CharaAssetType.DIALOG_15: "dialog_15",
        CharaAssetType.DIALOG_16: "dialog_16",
        CharaAssetType.DIALOG_17: "dialog_17",
        CharaAssetType.DIALOG_18: "dialog_18",
        CharaAssetType.DIALOG_19: "dialog_19",
        CharaAssetType.DIALOG_20: "dialog_20",
        CharaAssetType.DIALOG_21: "dialog_21",
        CharaAssetType.DIALOG_22: "dialog_22",
        CharaAssetType.DIALOG_23: "dialog_23",
        CharaAssetType.DIALOG_24: "dialog_24",
        CharaAssetType.DIALOG_25: "dialog_25",
        CharaAssetType.DIALOG_26: "dialog_26",
        CharaAssetType.DIALOG_31: "dialog_31",
        CharaAssetType.DIALOG_32: "dialog_32",
        CharaAssetType.DIALOG_33: "dialog_33",
        CharaAssetType.DIALOG_34: "dialog_34",
        CharaAssetType.DIALOG_35: "dialog_35",
        CharaAssetType.DIALOG_36: "dialog_36",
        CharaAssetType.DIALOG_37: "dialog_37",
        CharaAssetType.DIALOG_38: "dialog_38",
        CharaAssetType.DIALOG_39: "dialog_39",
        CharaAssetType.DIALOG_40: "dialog_40",
        CharaAssetType.DIALOG_41: "dialog_41",
        CharaAssetType.DIALOG_42: "dialog_42",
        CharaAssetType.DIALOG_43: "dialog_43",
        CharaAssetType.DIALOG_44: "dialog_44",
        CharaAssetType.DIALOG_45: "dialog_45",
        CharaAssetType.SELECTED_LEGACY: "selected_legacy",
        CharaAssetType.SELECTED_NEW: "selected_new",
        CharaAssetType.HOME_VICTORY: "home_victory",
        CharaAssetType.HOME_SPECIAL: "home_special",
        CharaAssetType.NAME_BIG: "name_big",
        CharaAssetType.NAME_SMALL: "name_small",
        CharaAssetType.CUTIN: "cutin",
        CharaAssetType.VICTORY: "victory",
        CharaAssetType.DEFEAT: "defeat",
        CharaAssetType.VERSUS: "versus",
    }

    _VALUE_TO_ENUM = {asset_type.value: asset_type for asset_type in CharaAssetType}

    def __init__(self):
        """Initialize with all asset attributes set to None."""
        self.konami_id: int = 0
        self.series: str = ""

        for attr_name in self._ENUM_TO_ATTR.values():
            setattr(self, attr_name, None)

    def set_asset_by_string(self, asset_string: str, value: str | None) -> bool:
        """Args:
            asset_string: String to match against CharaAssetType values
            (e.g., "Chara001")
            value: Value to set for the matched asset
        Returns:
            True if match found and set, False otherwise
        """
        if asset_string in self._VALUE_TO_ENUM:
            enum_type = self._VALUE_TO_ENUM[asset_string]
            attr_name = self._ENUM_TO_ATTR[enum_type]
            setattr(self, attr_name, value)
            return True
        return False

    def get_asset_by_string(self, asset_string: str) -> str | None:
        """Get asset by matching the string against enum values.
        Args:
            asset_string: String to match against CharaAssetType values
        Returns:
            Asset value if found, None otherwise
        """
        if asset_string in self._VALUE_TO_ENUM:
            enum_type = self._VALUE_TO_ENUM[asset_string]
            attr_name = self._ENUM_TO_ATTR[enum_type]
            return getattr(self, attr_name)
        return None

    def set_asset_by_enum(self, asset_type: CharaAssetType, value: str | None) -> None:
        """Set asset by CharaAssetType enum."""
        attr_name = self._ENUM_TO_ATTR[asset_type]
        setattr(self, attr_name, value)

    def get_asset_by_enum(self, asset_type: CharaAssetType) -> str | None:
        """Get asset by CharaAssetType enum."""
        attr_name = self._ENUM_TO_ATTR[asset_type]
        return getattr(self, attr_name)

    @classmethod
    def get_supported_strings(cls) -> list[str]:
        """Get list of all supported asset strings."""
        return list(cls._VALUE_TO_ENUM.keys())

    def to_dict(self) -> dict:
        """Convert CharacterAssets to a dictionary for JSON serialization."""
        result = {}
        if hasattr(self, "konami_id"):
            result["konami_id"] = self.konami_id
        if hasattr(self, "series"):
            result["series"] = self.series

        for attr_name in self._ENUM_TO_ATTR.values():
            value = getattr(self, attr_name, None)
            if value is not None:
                result[attr_name] = value
        return result


class CharacterModel(UnityAsset, base):
    """
    Model for character assets.

    Stores information about characters including:
    - name, konami_id, and series information
    - individual bundle columns for each CharaAssetType
    - thumbnail icon from the icon bundle
    """

    __tablename__ = "character"

    name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    konami_id: Mapped[int] = mapped_column(Integer, unique=True)
    series: Mapped[str] = mapped_column(String(255))

    icon: Mapped[str | None] = mapped_column(String(8), nullable=True)
    select: Mapped[str | None] = mapped_column(String(8), nullable=True)
    duel_1: Mapped[str | None] = mapped_column(String(8), nullable=True)
    duel_2: Mapped[str | None] = mapped_column(String(8), nullable=True)
    duel_3: Mapped[str | None] = mapped_column(String(8), nullable=True)
    duel_4: Mapped[str | None] = mapped_column(String(8), nullable=True)
    duel_5: Mapped[str | None] = mapped_column(String(8), nullable=True)
    duel_6: Mapped[str | None] = mapped_column(String(8), nullable=True)
    duel_7: Mapped[str | None] = mapped_column(String(8), nullable=True)
    duel_8: Mapped[str | None] = mapped_column(String(8), nullable=True)
    duel_9: Mapped[str | None] = mapped_column(String(8), nullable=True)
    duel_10: Mapped[str | None] = mapped_column(String(8), nullable=True)
    duel_11: Mapped[str | None] = mapped_column(String(8), nullable=True)
    duel_12: Mapped[str | None] = mapped_column(String(8), nullable=True)
    duel_13: Mapped[str | None] = mapped_column(String(8), nullable=True)
    duel_14: Mapped[str | None] = mapped_column(String(8), nullable=True)
    duel_15: Mapped[str | None] = mapped_column(String(8), nullable=True)
    duel_16: Mapped[str | None] = mapped_column(String(8), nullable=True)
    duel_17: Mapped[str | None] = mapped_column(String(8), nullable=True)
    duel_18: Mapped[str | None] = mapped_column(String(8), nullable=True)
    duel_19: Mapped[str | None] = mapped_column(String(8), nullable=True)
    duel_20: Mapped[str | None] = mapped_column(String(8), nullable=True)
    duel_31: Mapped[str | None] = mapped_column(String(8), nullable=True)
    duel_32: Mapped[str | None] = mapped_column(String(8), nullable=True)
    duel_33: Mapped[str | None] = mapped_column(String(8), nullable=True)
    duel_34: Mapped[str | None] = mapped_column(String(8), nullable=True)
    duel_35: Mapped[str | None] = mapped_column(String(8), nullable=True)
    duel_36: Mapped[str | None] = mapped_column(String(8), nullable=True)
    duel_37: Mapped[str | None] = mapped_column(String(8), nullable=True)
    duel_38: Mapped[str | None] = mapped_column(String(8), nullable=True)
    duel_39: Mapped[str | None] = mapped_column(String(8), nullable=True)
    duel_40: Mapped[str | None] = mapped_column(String(8), nullable=True)
    duel_41: Mapped[str | None] = mapped_column(String(8), nullable=True)
    duel_42: Mapped[str | None] = mapped_column(String(8), nullable=True)
    world: Mapped[str | None] = mapped_column(String(8), nullable=True)
    event: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_0: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_1: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_2: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_3: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_4: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_5: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_6: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_7: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_8: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_9: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_10: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_11: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_12: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_13: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_14: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_15: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_16: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_17: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_18: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_19: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_20: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_21: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_22: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_23: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_24: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_25: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_26: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_31: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_32: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_33: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_34: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_35: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_36: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_37: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_38: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_39: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_40: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_41: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_42: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_43: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_44: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dialog_45: Mapped[str | None] = mapped_column(String(8), nullable=True)
    selected_legacy: Mapped[str | None] = mapped_column(String(8), nullable=True)
    selected_new: Mapped[str | None] = mapped_column(String(8), nullable=True)
    home_victory: Mapped[str | None] = mapped_column(String(8), nullable=True)
    home_special: Mapped[str | None] = mapped_column(String(8), nullable=True)
    name_big: Mapped[str | None] = mapped_column(String(8), nullable=True)
    name_small: Mapped[str | None] = mapped_column(String(8), nullable=True)
    cutin: Mapped[str | None] = mapped_column(String(8), nullable=True)
    victory: Mapped[str | None] = mapped_column(String(8), nullable=True)
    defeat: Mapped[str | None] = mapped_column(String(8), nullable=True)
    versus: Mapped[str | None] = mapped_column(String(8), nullable=True)

    thumb: QIcon = QIcon()

    def get_asset_bundle(self, asset_type: CharaAssetType) -> str | None:
        """Get the bundle for a specific asset type."""
        attr_name = CharacterAssets._ENUM_TO_ATTR.get(asset_type)
        if attr_name:
            return getattr(self, attr_name, None)
        return None

    def set_asset_bundle(self, asset_type: CharaAssetType, bundle: str) -> None:
        """Set the bundle for a specific asset type."""
        attr_name = CharacterAssets._ENUM_TO_ATTR.get(asset_type)
        if attr_name:
            setattr(self, attr_name, bundle)


class CharacterAssetLayout(base):
    """Original texture layout, independent of replacement image transparency."""

    __tablename__ = "character_asset_layout"

    bundle: Mapped[str] = mapped_column(String, primary_key=True)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    bounds: Mapped[list[int]] = mapped_column(JSON)


base.metadata.create_all(engine)
