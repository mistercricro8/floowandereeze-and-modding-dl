"""Character editing dialog module."""

import logging
from pathlib import Path

from PIL.ImageQt import fromqimage
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QGuiApplication, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
)

from database.models import CharacterModel
from database.objects import session
from services.character_service import CharacterService
from unity.unity_utils import fetch_bundle_thumb
from util.constants import (
    APP_CONFIG,
    FIT_MODE_BUTTON_STYLE,
    IMAGE_EXTENSIONS,
    IMAGE_FILTER,
)
from util.enums import CharaAssetType
from util.image_utils import slugify
from util.ui_util import open_in_file_manager
from widgets.crop_overlay_widget import CropOverlayWidget
from widgets.inline_alert import attach_inline_alert, notify

logger = logging.getLogger(__name__)

_BTN_STYLE = FIT_MODE_BUTTON_STYLE


class CharacterEditDialog(QDialog):
    """Modal dialog for editing character assets."""

    def __init__(self, character: CharacterModel, parent=None):
        super().__init__(parent)
        self.character = character
        self.service = CharacterService()
        self.selected_asset_bundle: str | None = None

        self._crop_mode: bool = False
        self._asset_ratio: float | None = None

        self.setWindowTitle(f"Editing {character.name}")
        self.setModal(True)
        self.setAcceptDrops(True)

        self._setup_ui()
        self._populate_asset_list()
        self._connect_signals()
        self.adjustSize()

    def _setup_ui(self):
        """Setup the dialog UI layout."""
        layout = QVBoxLayout(self)

        attach_inline_alert(self, layout)

        header_layout = QHBoxLayout()

        self.character_icon = QLabel()
        self.character_icon.setFixedSize(32, 32)
        self.character_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if self.character.icon:
            icon = fetch_bundle_thumb(self.character.icon, None)
            if icon and icon.availableSizes():
                raw = icon.pixmap(icon.availableSizes()[0])
                self.character_icon.setPixmap(
                    raw.scaled(
                        32,
                        32,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        header_layout.addWidget(self.character_icon)

        title_label = QLabel(f"Editing {self.character.name}")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        left_frame = QFrame()
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_frame.setMinimumWidth(220)

        filter_label = QLabel("Filter by category:")
        left_layout.addWidget(filter_label)

        self.filter_combo = QComboBox()
        self.filter_combo.addItem("All Images", "all")
        self.filter_combo.addItem("Duel Artwork", "duel")
        self.filter_combo.addItem("Dialogue Expressions", "dialog")
        self.filter_combo.addItem("Miscellaneous", "misc")
        self.filter_combo.setToolTip(
            "Filter the list by category (duel, dialogue, or misc)."
        )
        left_layout.addWidget(self.filter_combo)

        assets_label = QLabel("Character Images:")
        left_layout.addWidget(assets_label)

        self.asset_list = QListWidget()
        self.asset_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.asset_list.setIconSize(QSize(64, 64))
        left_layout.addWidget(self.asset_list)

        self.asset_error_label = QLabel(self)
        self.asset_error_label.setObjectName("assetErrorLabel")
        self.asset_error_label.setStyleSheet("color: #a93226; font-size: 11px;")
        self.asset_error_label.setWordWrap(True)
        self.asset_error_label.setVisible(False)
        left_layout.addWidget(self.asset_error_label)

        selection_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.setToolTip("Select all character images in the list.")
        self.clear_selection_btn = QPushButton("Clear Selection")
        self.clear_selection_btn.setToolTip(
            "Deselect all character images in the list."
        )
        selection_layout.addWidget(self.select_all_btn)
        selection_layout.addWidget(self.clear_selection_btn)
        left_layout.addLayout(selection_layout)

        self.selection_label = QLabel("0 images selected")
        left_layout.addWidget(self.selection_label)
        selection_hint = QLabel("Use Ctrl or Shift to select multiple images.")
        selection_hint.setWordWrap(True)
        left_layout.addWidget(selection_hint)

        splitter.addWidget(left_frame)

        right_frame = QFrame()
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(0, 0, 0, 0)

        previews_layout = QHBoxLayout()
        current_layout = QVBoxLayout()
        replacement_layout = QVBoxLayout()
        previews_layout.addLayout(current_layout)
        previews_layout.addLayout(replacement_layout)
        right_layout.addLayout(previews_layout)

        preview_label = QLabel("Current Image:")
        current_layout.addWidget(preview_label)

        self.current_preview = QLabel()
        self.current_preview.setFixedSize(256, 256)
        self.current_preview.setStyleSheet("border: 1px solid gray;")
        self.current_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.current_preview.setText("Select an image to preview")
        current_layout.addWidget(self.current_preview, 0, Qt.AlignmentFlag.AlignHCenter)

        image_label = QLabel("Replacement Image:")
        right_layout.addWidget(image_label)

        image_layout = QHBoxLayout()
        self.image_path_edit = QLineEdit()
        self.image_path_edit.setReadOnly(True)
        self.image_path_edit.setPlaceholderText(
            "No replacement image selected (browse or drag & drop)..."
        )
        self.image_path_edit.setToolTip("Path to your replacement image file.")
        image_layout.addWidget(self.image_path_edit)

        self.select_image_btn = QPushButton("Select Image...")
        self.select_image_btn.setToolTip(
            "Browse your computer for a PNG or JPG replacement image."
        )
        self.select_image_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        image_layout.addWidget(self.select_image_btn)

        right_layout.addLayout(image_layout)

        self.image_error_label = QLabel(self)
        self.image_error_label.setObjectName("imageErrorLabel")
        self.image_error_label.setStyleSheet("color: #a93226; font-size: 11px;")
        self.image_error_label.setWordWrap(True)
        self.image_error_label.setVisible(False)
        right_layout.addWidget(self.image_error_label)

        fit_layout = QHBoxLayout()
        fit_layout.addWidget(QLabel("Fit Mode:"))

        self._stretch_btn = QPushButton("Stretch")
        self._stretch_btn.setCheckable(True)
        self._stretch_btn.setChecked(True)
        self._stretch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stretch_btn.setStyleSheet(_BTN_STYLE)
        self._stretch_btn.setToolTip(
            "Stretches the image to fit the game boundary completely."
        )

        self._crop_btn = QPushButton("Crop")
        self._crop_btn.setCheckable(True)
        self._crop_btn.setEnabled(False)
        self._crop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._crop_btn.setStyleSheet(_BTN_STYLE)
        self._crop_btn.setToolTip(
            "Preserves image proportions and lets you crop a specific area."
        )

        fit_layout.addWidget(self._stretch_btn)
        fit_layout.addWidget(self._crop_btn)
        fit_layout.addStretch()

        self._fit_group = QButtonGroup(self)
        self._fit_group.addButton(self._stretch_btn, 0)
        self._fit_group.addButton(self._crop_btn, 1)
        self._fit_group.setExclusive(True)

        right_layout.addLayout(fit_layout)

        self.preserve_padding_checkbox = QCheckBox(
            "Preserve original transparent margins"
        )
        self.preserve_padding_checkbox.setChecked(True)
        self.preserve_padding_checkbox.setToolTip(
            "Keeps transparent margins so dialogue expressions stay centered."
        )
        right_layout.addWidget(self.preserve_padding_checkbox)

        new_preview_label = QLabel("Replacement Preview:")
        replacement_layout.addWidget(new_preview_label)

        self.new_preview = QLabel()
        self.new_preview.setFixedSize(256, 256)
        self.new_preview.setStyleSheet("border: 1px solid gray;")
        self.new_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.new_preview.setText("No replacement image selected")

        self._crop_widget = CropOverlayWidget()
        self._crop_widget.setFixedSize(256, 256)
        self._crop_widget.crop_changed.connect(self._on_crop_changed)

        self._mode_stack = QStackedWidget()
        self._mode_stack.setFixedSize(256, 256)
        self._mode_stack.addWidget(self.new_preview)
        self._mode_stack.addWidget(self._crop_widget)

        replacement_layout.addWidget(self._mode_stack, 0, Qt.AlignmentFlag.AlignHCenter)

        right_layout.addStretch()

        splitter.addWidget(right_frame)
        splitter.setSizes([240, right_frame.sizeHint().width()])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

        layout.addWidget(splitter, 1)

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.extract_btn = QPushButton("Extract Image")
        self.extract_btn.setEnabled(False)
        self.extract_btn.setToolTip(
            "Extracts selected character images to images/characters/."
        )
        button_layout.addWidget(self.extract_btn)

        self.replace_btn = QPushButton("Apply Mod")
        self.replace_btn.setEnabled(False)
        self.replace_btn.setToolTip(
            "Applies your replacement image to game files. A backup is saved first."
        )
        button_layout.addWidget(self.replace_btn)

        self.restore_btn = QPushButton("Restore Original")
        self.restore_btn.setEnabled(False)
        self.restore_btn.setToolTip(
            "Restores selected character images back to original game artwork."
        )
        button_layout.addWidget(self.restore_btn)

        close_btn = QPushButton("Close")
        close_btn.setToolTip("Close the character editor.")
        button_layout.addWidget(close_btn)

        for btn in (self.extract_btn, self.replace_btn, self.restore_btn, close_btn):
            btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            btn.setMinimumWidth(btn.fontMetrics().horizontalAdvance(btn.text()) + 20)

        layout.addLayout(button_layout)

        close_btn.clicked.connect(self.accept)

    def _set_fit_mode(self, mode: str) -> None:
        self._crop_mode = mode == "crop"
        if self._crop_mode:
            if self.service.image_path:
                ratio = (
                    None
                    if len(self.asset_list.selectedItems()) > 1
                    else self._asset_ratio
                )
                self._crop_widget.set_image(self.service.image_path, ratio)
                self.service.crop_rect = self._crop_widget.get_crop_rect_normalized()
            self._mode_stack.setCurrentIndex(1)
        else:
            self.service.crop_rect = None
            self._mode_stack.setCurrentIndex(0)

    def _on_crop_changed(self) -> None:
        if self._crop_mode:
            self.service.crop_rect = self._crop_widget.get_crop_rect_normalized()

    def _on_padding_toggled(self, checked: bool) -> None:
        self.service.preserve_transparent_padding = checked
        self._on_selection_changed()

    def _load_image(self, path: str) -> None:
        self.image_path_edit.setText(path)
        self.service.image_path = path

        pixmap = QPixmap(path)
        self.new_preview.setPixmap(
            pixmap.scaled(
                256,
                256,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

        if self._crop_mode:
            ratio = (
                None if len(self.asset_list.selectedItems()) > 1 else self._asset_ratio
            )
            self._crop_widget.set_image(path, ratio)
            self.service.crop_rect = self._crop_widget.get_crop_rect_normalized()
            self._mode_stack.setCurrentIndex(1)
        else:
            self.service.crop_rect = None
            self._mode_stack.setCurrentIndex(0)

        self._update_replace_button_state()
        if not pixmap.isNull():
            self.image_error_label.clear()
            self.image_error_label.setVisible(False)
            notify(
                self,
                "info",
                "Image Selected",
                f"Loaded {Path(path).name} ({pixmap.width()}×{pixmap.height()})",
            )
        else:
            logger.warning("Failed to load image from %s", path)
            self.image_error_label.setText("Could not load image file.")
            self.image_error_label.setVisible(True)
            notify(
                self,
                "error",
                "Image Error",
                f"Could not load image: {Path(path).name}",
            )

    def _connect_signals(self):
        """Connect UI signals to their handlers."""
        self.filter_combo.currentTextChanged.connect(self._filter_assets)
        self.asset_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.asset_list.currentItemChanged.connect(
            lambda *_: self._on_selection_changed()
        )
        self.select_all_btn.clicked.connect(self.asset_list.selectAll)
        self.clear_selection_btn.clicked.connect(self.asset_list.clearSelection)
        self.select_image_btn.clicked.connect(self._select_image)
        self.extract_btn.clicked.connect(self._extract_asset)
        self.replace_btn.clicked.connect(self._replace_asset)
        self.restore_btn.clicked.connect(self._restore_asset)
        self._stretch_btn.clicked.connect(lambda: self._set_fit_mode("stretch"))
        self._crop_btn.clicked.connect(lambda: self._set_fit_mode("crop"))
        self.preserve_padding_checkbox.toggled.connect(self._on_padding_toggled)

    def _populate_asset_list(self):
        """Populate the asset list with character's available assets."""
        self.asset_list.clear()

        self.asset_data: list[tuple[CharaAssetType, str, str]] = []

        for asset_type in CharaAssetType:
            bundle = self.character.get_asset_bundle(asset_type)
            if bundle:
                self.asset_data.append(
                    (asset_type, bundle, self._get_asset_display_name(asset_type))
                )

        self._filter_assets()

    def _get_asset_display_name(self, asset_type: CharaAssetType) -> str:
        """Get a user-friendly display name for an asset type."""
        name_map = {
            CharaAssetType.ICON: "Character Icon",
            CharaAssetType.SELECT: "Selection Screen",
            CharaAssetType.WORLD: "World Map",
            CharaAssetType.EVENT: "Event Screen",
            CharaAssetType.CUTIN: "Cut-in Animation",
            CharaAssetType.VICTORY: "Victory Screen",
            CharaAssetType.DEFEAT: "Defeat Screen",
            CharaAssetType.VERSUS: "Versus Screen",
            CharaAssetType.SELECTED_LEGACY: "Selected (Legacy)",
            CharaAssetType.SELECTED_NEW: "Selected (New)",
            CharaAssetType.HOME_VICTORY: "Home Victory",
            CharaAssetType.HOME_SPECIAL: "Home Special",
            CharaAssetType.NAME_BIG: "Name (Large)",
            CharaAssetType.NAME_SMALL: "Name (Small)",
        }

        if asset_type.name.startswith("DUEL_"):
            duel_num = asset_type.name.split("_")[1]
            return f"Duel Animation {duel_num}"

        if asset_type.name.startswith("DIALOG_"):
            dialog_num = asset_type.name.split("_")[1]
            return f"Dialogue Expression {dialog_num}"

        return name_map.get(asset_type, asset_type.name.replace("_", " ").title())

    def _get_asset_category(self, asset_type: CharaAssetType) -> str:
        """Get the category of an asset type for filtering."""
        if asset_type.name.startswith("DUEL_"):
            return "duel"
        elif asset_type.name.startswith("DIALOG_"):
            return "dialog"
        else:
            return "misc"

    def _filter_assets(self):
        """Filter assets based on the selected filter."""
        self.asset_list.clear()
        filter_type = self.filter_combo.currentData()

        for asset_type, bundle, display_name in self.asset_data:
            if (
                filter_type == "all"
                or self._get_asset_category(asset_type) == filter_type
            ):
                item = QListWidgetItem(display_name)
                item.setData(Qt.ItemDataRole.UserRole, (asset_type, bundle))

                try:
                    item.setIcon(fetch_bundle_thumb(bundle, None))
                except Exception:
                    logger.exception("Failed to load icon for %s", bundle)
                    item.setIcon(QIcon())

                self.asset_list.addItem(item)

    def _selected_bundles(self) -> list[str]:
        """Return unique selected bundles in list order."""
        return list(
            dict.fromkeys(
                item.data(Qt.ItemDataRole.UserRole)[1]
                for item in self.asset_list.selectedItems()
            )
        )

    def _on_selection_changed(self):
        items = self.asset_list.selectedItems()
        count = len(items)
        self.selection_label.setText(
            f"{count} image{'s' if count != 1 else ''} selected"
        )
        for button, verb in (
            (self.extract_btn, "Extract"),
            (self.replace_btn, "Replace"),
            (self.restore_btn, "Restore"),
        ):
            button.setText(f"{verb} {count} Images" if count > 1 else f"{verb} Image")

        if count > 0:
            self.extract_btn.setToolTip(
                f"Extracts {count} selected character image{'s' if count != 1 else ''} to images/characters/."
            )
            self.restore_btn.setToolTip(
                f"Restores {count} selected character image{'s' if count != 1 else ''} back to original game art."
            )
            self.replace_btn.setToolTip(
                f"Replaces {count} selected character image{'s' if count != 1 else ''} in game files."
            )
            self.asset_error_label.clear()
            self.asset_error_label.setVisible(False)
        else:
            self.extract_btn.setToolTip(
                "Extracts selected character images to images/characters/."
            )
            self.restore_btn.setToolTip(
                "Restores selected character images back to original game artwork."
            )
            self.replace_btn.setToolTip(
                "Applies your replacement image to game files. A backup is saved first."
            )

        if items:
            current = self.asset_list.currentItem()
            self._on_asset_selected(current if current in items else items[0])
            return

        self.selected_asset_bundle = None
        self.service.bundle = None
        self._asset_ratio = None
        self.current_preview.setText("Select an image to preview")
        self.extract_btn.setEnabled(False)
        self.restore_btn.setEnabled(False)
        self._crop_btn.setEnabled(False)
        self._update_replace_button_state()

    def _on_asset_selected(self, item: QListWidgetItem):
        """Handle asset selection from the list."""
        _asset_type, bundle = item.data(Qt.ItemDataRole.UserRole)
        self.selected_asset_bundle = bundle
        self._asset_ratio = None

        try:
            icon = fetch_bundle_thumb(bundle, None)
            if icon and icon.availableSizes():
                raw = icon.pixmap(icon.availableSizes()[0])
                if not raw.isNull():
                    left, top, right, bottom = self.service.replacement_content_bounds(
                        bundle, fromqimage(raw.toImage())
                    )
                    self._asset_ratio = (right - left) / (bottom - top)
                self.current_preview.setPixmap(
                    raw.scaled(
                        256,
                        256,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
            else:
                self.current_preview.setText("Preview not available")
        except Exception:
            logger.exception("Failed to load preview for game file %s", bundle)
            self.current_preview.setText("Preview not available")

        multiple = len(self.asset_list.selectedItems()) > 1
        self._crop_btn.setEnabled(multiple or self._asset_ratio is not None)
        ratio = None if multiple else self._asset_ratio
        self._crop_widget.set_target_ratio(ratio, preserve_crop=multiple)
        if self._crop_mode:
            if self._asset_ratio is None and not multiple:
                self._stretch_btn.setChecked(True)
                self._set_fit_mode("stretch")
            else:
                self._on_crop_changed()

        self.extract_btn.setEnabled(True)
        self.restore_btn.setEnabled(True)

        self._update_replace_button_state()

        self.service.bundle = bundle

    def _select_image(self):
        """Open file dialog to select replacement image."""
        file, _ = QFileDialog.getOpenFileUrl(
            self, "Select Replacement Image", "", IMAGE_FILTER
        )

        if file and file.url():
            self._load_image(file.toLocalFile())

    def _update_replace_button_state(self):
        """Update the replace button enabled state."""
        has_image = bool(self.service.image_path)
        has_asset = bool(self.selected_asset_bundle)
        self.replace_btn.setEnabled(has_image and has_asset)

    def _run_asset_action(self, title: str, action):
        """Apply an action to the selection and report partial failures together."""
        bundles = self._selected_bundles()
        if not bundles:
            self.asset_error_label.setText("Select at least one image from the list.")
            self.asset_error_label.setVisible(True)
            notify(
                self,
                "warning",
                "Selection Required",
                "Please select at least one character image from the list.",
            )
            return

        self.asset_error_label.clear()
        self.asset_error_label.setVisible(False)

        succeeded = 0
        errors = []
        image_path, crop_rect = self.service.image_path, self.service.crop_rect
        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            for bundle in bundles:
                self.service.bundle = bundle
                try:
                    action(bundle)
                    succeeded += 1
                except Exception as error:
                    logger.exception(
                        "Failed to run action '%s' on game file '%s'", title, bundle
                    )
                    errors.append(f"{bundle} ({error})")
                finally:
                    self.service.image_path = image_path
                    self.service.crop_rect = crop_rect
        finally:
            self.service.bundle = self.selected_asset_bundle
            QGuiApplication.restoreOverrideCursor()

        for item in self.asset_list.selectedItems():
            _, bundle = item.data(Qt.ItemDataRole.UserRole)
            try:
                icon = fetch_bundle_thumb(bundle, None)
                if icon:
                    item.setIcon(icon)
                if (
                    bundle == self.selected_asset_bundle
                    and icon
                    and icon.availableSizes()
                ):
                    self.current_preview.setPixmap(
                        icon.pixmap(icon.availableSizes()[0]).scaled(
                            256,
                            256,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                    )
            except Exception:
                logger.exception("Failed to update thumbnail for %s", bundle)

        if errors:
            failed_str = ", ".join(errors)
            if succeeded > 0:
                logger.warning(
                    "%s completed partially: %d succeeded, %d failed",
                    title,
                    succeeded,
                    len(errors),
                )
                notify(
                    self,
                    "warning",
                    f"{title} Partial Success",
                    f"Completed {succeeded} of {len(bundles)} game files. Failed: {failed_str}",
                )
            else:
                logger.error(
                    "%s failed completely for %d game files: %s",
                    title,
                    len(bundles),
                    failed_str,
                )
                notify(
                    self,
                    "error",
                    f"{title} Failed",
                    f"Failed all {len(bundles)} game files: {failed_str}",
                )
        else:
            notify(
                self,
                "success",
                title,
                f"Successfully completed {succeeded} game file{'s' if succeeded != 1 else ''}.",
            )

    def _extract_asset(self):
        """Extract every selected image to the characters folder."""
        self._run_asset_action("Image Extraction", self.service.extract_texture)
        dest = Path("images/characters")
        if dest.is_dir():
            open_in_file_manager(dest)

    def _replace_asset(self):
        """Replace selected images using the same replacement image and crop."""
        if not self.service.image_path:
            self.image_error_label.setText("Select a replacement image first.")
            self.image_error_label.setVisible(True)
            notify(
                self,
                "warning",
                "Image Required",
                "Please select a replacement image before applying changes.",
            )
            return

        def replace(bundle):
            if APP_CONFIG.create_backup:
                backup = (
                    Path("backups") / self.service.subfolder / f"{slugify(bundle)}.png"
                )
                if not backup.is_file():
                    self.service.create_backup(bundle)
                self.character.has_backup = True
                session.commit()
            self.service.replace_bundle()

        self._run_asset_action("Apply Mod", replace)

    def _restore_asset(self):
        """Restore every selected image that has a backup."""

        def restore(_bundle):
            if not self.service.restore_asset():
                raise FileNotFoundError("Backup file not found")

        self._run_asset_action("Restore Original", restore)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Accept drag and drop of image files."""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(IMAGE_EXTENSIONS):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        """Handle drop event of an image file."""
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path.lower().endswith(IMAGE_EXTENSIONS):
                self._load_image(file_path)
                break
