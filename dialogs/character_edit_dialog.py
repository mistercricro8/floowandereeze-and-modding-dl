"""Character editing dialog module."""

from pathlib import Path

from PIL.ImageQt import fromqimage
from pyqttoast import ToastPreset
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon, QPixmap
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
    QMessageBox,
    QPushButton,
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
from util.ui_util import show_toast
from widgets.crop_overlay_widget import CropOverlayWidget

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

        filter_label = QLabel("Filter by type:")
        left_layout.addWidget(filter_label)

        self.filter_combo = QComboBox()
        self.filter_combo.addItem("All Assets", "all")
        self.filter_combo.addItem("Duel Assets", "duel")
        self.filter_combo.addItem("Dialog Assets", "dialog")
        self.filter_combo.addItem("Miscellaneous", "misc")
        left_layout.addWidget(self.filter_combo)

        assets_label = QLabel("Character Assets:")
        left_layout.addWidget(assets_label)

        self.asset_list = QListWidget()
        self.asset_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.asset_list.setIconSize(QSize(64, 64))
        left_layout.addWidget(self.asset_list)
        selection_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("Select All")
        self.clear_selection_btn = QPushButton("Clear")
        selection_layout.addWidget(self.select_all_btn)
        selection_layout.addWidget(self.clear_selection_btn)
        left_layout.addLayout(selection_layout)
        self.selection_label = QLabel("0 assets selected")
        left_layout.addWidget(self.selection_label)
        selection_hint = QLabel("Use Ctrl or Shift to select multiple assets.")
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

        preview_label = QLabel("Asset Preview:")
        current_layout.addWidget(preview_label)

        self.current_preview = QLabel()
        self.current_preview.setFixedSize(256, 256)
        self.current_preview.setStyleSheet("border: 1px solid gray;")
        self.current_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.current_preview.setText("Select an asset to preview")
        current_layout.addWidget(self.current_preview, 0, Qt.AlignmentFlag.AlignHCenter)

        image_label = QLabel("Replacement Image:")
        right_layout.addWidget(image_label)

        image_layout = QHBoxLayout()
        self.image_path_edit = QLineEdit()
        self.image_path_edit.setReadOnly(True)
        self.image_path_edit.setPlaceholderText("No image selected")
        image_layout.addWidget(self.image_path_edit)

        self.select_image_btn = QPushButton("Select Image")
        image_layout.addWidget(self.select_image_btn)

        right_layout.addLayout(image_layout)

        fit_layout = QHBoxLayout()
        fit_layout.addWidget(QLabel("Fit Mode:"))

        self._stretch_btn = QPushButton("Stretch")
        self._stretch_btn.setCheckable(True)
        self._stretch_btn.setChecked(True)
        self._stretch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stretch_btn.setStyleSheet(_BTN_STYLE)

        self._crop_btn = QPushButton("Crop")
        self._crop_btn.setCheckable(True)
        self._crop_btn.setEnabled(False)
        self._crop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._crop_btn.setStyleSheet(_BTN_STYLE)
        self._crop_btn.setToolTip(
            "For multiple assets, each aspect ratio is fitted inside the "
            "shared crop area."
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
            "Preserve original transparent padding"
        )
        self.preserve_padding_checkbox.setChecked(True)
        self.preserve_padding_checkbox.setToolTip(
            "In Crop mode, fit to the original visible content and restore "
            "its transparent margins. Turn off to use the full texture area."
        )
        right_layout.addWidget(self.preserve_padding_checkbox)

        new_preview_label = QLabel("New Image Preview:")
        replacement_layout.addWidget(new_preview_label)

        self.new_preview = QLabel()
        self.new_preview.setFixedSize(256, 256)
        self.new_preview.setStyleSheet("border: 1px solid gray;")
        self.new_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.new_preview.setText("No image selected")

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

        self.extract_btn = QPushButton("Extract Asset")
        self.extract_btn.setEnabled(False)
        button_layout.addWidget(self.extract_btn)

        self.replace_btn = QPushButton("Replace Asset")
        self.replace_btn.setEnabled(False)
        button_layout.addWidget(self.replace_btn)

        self.restore_btn = QPushButton("Restore Asset")
        self.restore_btn.setEnabled(False)
        button_layout.addWidget(self.restore_btn)

        close_btn = QPushButton("Close")
        button_layout.addWidget(close_btn)

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
            return f"Dialog Expression {dialog_num}"

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
        self.selection_label.setText(f"{count} assets selected")
        for button, verb in (
            (self.extract_btn, "Extract"),
            (self.replace_btn, "Replace"),
            (self.restore_btn, "Restore"),
        ):
            button.setText(f"{verb} {count} Assets" if count > 1 else f"{verb} Asset")
        if items:
            current = self.asset_list.currentItem()
            self._on_asset_selected(current if current in items else items[0])
            return
        self.selected_asset_bundle = None
        self.service.bundle = None
        self._asset_ratio = None
        self.current_preview.setText("Select an asset to preview")
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
        except Exception:
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

    def _run_asset_action(self, title, action):
        """Apply an action to the selection and report partial failures together."""
        bundles = self._selected_bundles()
        if not bundles:
            return
        succeeded = 0
        errors = []
        image_path, crop_rect = self.service.image_path, self.service.crop_rect
        try:
            for bundle in bundles:
                self.service.bundle = bundle
                try:
                    action(bundle)
                    succeeded += 1
                except Exception as error:
                    errors.append(f"{bundle}: {error}")
                finally:
                    self.service.image_path = image_path
                    self.service.crop_rect = crop_rect
        finally:
            self.service.bundle = self.selected_asset_bundle

        for item in self.asset_list.selectedItems():
            _, bundle = item.data(Qt.ItemDataRole.UserRole)
            try:
                icon = fetch_bundle_thumb(bundle, None)
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
                pass
        if errors:
            QMessageBox.warning(
                self,
                title,
                f"Completed {succeeded} of {len(bundles)} assets.\n\n"
                + "\n".join(errors),
            )
        else:
            show_toast(
                self, title, f"Completed {succeeded} asset(s)", ToastPreset.SUCCESS_DARK
            )

    def _extract_asset(self):
        """Extract every selected asset to the characters folder."""
        self._run_asset_action("Character Extraction", self.service.extract_texture)

    def _replace_asset(self):
        """Replace selected assets using the same image and crop area."""
        if not self.service.image_path:
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

        self._run_asset_action("Character Replacement", replace)

    def _restore_asset(self):
        """Restore every selected asset that has a backup."""

        def restore(_bundle):
            if not self.service.restore_asset():
                raise FileNotFoundError("Asset backup not found")

        self._run_asset_action("Character Restore", restore)

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
