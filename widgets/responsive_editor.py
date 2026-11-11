"""Resizable editors retaining the Designer controls and crop workflows."""

from PySide6 import QtCore, QtWidgets

from widgets.asset_search import add_asset_search
from widgets.grip_splitter import GripSplitter
from widgets.inline_alert import attach_inline_alert


class ResponsiveEditor(QtCore.QObject):
    """Share editor sizing, result grids and saved splitter positions."""

    def __init__(self, page, view, key, ratio, search=False, header=None):
        super().__init__(page)
        self.page = page
        self.ratio = ratio
        self.settings = QtCore.QSettings("Floowandereeze", "DuelLinks")
        self.key = key
        root = page.verticalLayout
        root.setSpacing(8)
        root.setContentsMargins(12, 8, 12, 12)
        root.removeWidget(view)
        if header:
            root.removeItem(header)
            for index in reversed(range(header.count())):
                item_at = header.itemAt(index)
                if item_at is not None and item_at.spacerItem():
                    header.takeAt(index)
            header.insertWidget(0, QtWidgets.QLabel("Results", page))
            if key == "cards":
                header.setStretch(header.indexOf(page.searchEdit), 1)
                page.searchButton.setText("Search")
                page.searchButton.setAccessibleName("Search cards")
                page.searchButton.setToolTip("Search cards by name.")
        title = root.takeAt(0)
        editor = QtWidgets.QWidget(page)
        layout = QtWidgets.QVBoxLayout(editor)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)
        while root.count():
            item = root.takeAt(0)
            if item.widget():
                layout.addWidget(item.widget())
            elif item.layout():
                child_layout = item.layout()
                child_layout.setParent(None)
                layout.addLayout(child_layout)
            else:
                layout.addItem(item)
        root.addWidget(title.widget())
        attach_inline_alert(page, root)
        if key == "fields":
            page.horizontalLayout_6.setDirection(
                QtWidgets.QBoxLayout.Direction.RightToLeft
            )
        page.bundle.hide()
        self.preview_layout = None
        for widget, text in ((page.current, "Current"), (page._mode_stack, "Preview")):
            for parent_layout in editor.findChildren(QtWidgets.QBoxLayout):
                index = parent_layout.indexOf(widget)
                if index >= 0:
                    self.preview_layout = parent_layout
                    parent_layout.takeAt(index)
                    column = QtWidgets.QVBoxLayout()
                    column.setSpacing(4)
                    column.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
                    label = QtWidgets.QLabel(text, editor)
                    label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                    label.setStyleSheet("font-weight: 600;")
                    column.addWidget(label)
                    column.addWidget(widget, 0, QtCore.Qt.AlignmentFlag.AlignHCenter)
                    parent_layout.insertLayout(index, column)
                    break
        layout.addStretch(1)
        self.scroll = QtWidgets.QScrollArea(page)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.scroll.setWidget(editor)
        self.scroll.setAutoFillBackground(False)
        self.scroll.viewport().setAutoFillBackground(False)
        editor.setAutoFillBackground(False)
        self.scroll.setMinimumHeight(170)
        self.scroll.viewport().installEventFilter(self)
        results = QtWidgets.QWidget(page)
        results_layout = QtWidgets.QVBoxLayout(results)
        results_layout.setContentsMargins(0, 0, 0, 0)
        if header is None:
            header = QtWidgets.QHBoxLayout()
            header.addWidget(QtWidgets.QLabel("Results", page))
            header.addStretch()
        results_layout.addLayout(header)
        if search:
            add_asset_search(page, header, results_layout, key)
            if hasattr(page, "searchEdit"):
                if key == "fields":
                    page.searchEdit.setPlaceholderText("Search playmats by name...")
                    page.searchEdit.setToolTip(
                        "Type a playmat name and press Enter to search."
                    )
                elif key == "sleeves":
                    page.searchEdit.setPlaceholderText("Search sleeves by name...")
                    page.searchEdit.setToolTip(
                        "Type a sleeve name and press Enter to search."
                    )
                else:
                    page.searchEdit.setToolTip("Type a name and press Enter to search.")
            if hasattr(page, "searchButton"):
                if key == "fields":
                    page.searchButton.setToolTip("Search playmats by name.")
                elif key == "sleeves":
                    page.searchButton.setToolTip("Search sleeves by name.")
                else:
                    page.searchButton.setToolTip("Search items by name.")
        results_layout.addWidget(view, 1)
        results.setMinimumHeight(150)
        self.splitter = GripSplitter(QtCore.Qt.Orientation.Vertical, page)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.scroll)
        self.splitter.addWidget(results)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        root.addWidget(self.splitter, 1)
        state = self.settings.value(f"{key}/splitter")
        if state:
            self.splitter.restoreState(state)
        else:
            self.splitter.setSizes([400, 260])
        self.splitter.splitterMoved.connect(self.save_state)
        view.setViewMode(QtWidgets.QListView.ViewMode.IconMode)
        view.setFlow(QtWidgets.QListView.Flow.LeftToRight)
        view.setWrapping(True)
        view.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust)
        view.setMovement(QtWidgets.QListView.Movement.Static)
        view.setUniformItemSizes(True)
        view.setWordWrap(True)
        view.setSpacing(6)
        view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setToolTip("Select an item to view or edit.")
        icon = (
            QtCore.QSize(132, 66)
            if ratio > 1.5
            else QtCore.QSize(90, 132)
            if ratio < 1
            else QtCore.QSize(112, 112)
        )
        view.setIconSize(icon)
        view.setGridSize(QtCore.QSize(max(150, icon.width() + 16), icon.height() + 48))
        view.setStyleSheet(
            "QListView::item:selected {background: rgba(21,160,111,0.3); "
            "border: 1px solid #15a06f; border-radius: 4px;}"
        )
        for edit in editor.findChildren(QtWidgets.QLineEdit):
            if edit.objectName() != "borderEdit":
                edit.setPlaceholderText("Select or drop an image")
        for widget in (page.current, page.preview, page._mode_stack, page._crop_widget):
            widget.setMinimumSize(1, 1)
            widget.setMaximumSize(16777215, 16777215)
            widget.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Expanding,
            )
        QtCore.QTimer.singleShot(0, self.resize_images)

    def save_state(self, *_):
        self.settings.setValue(f"{self.key}/splitter", self.splitter.saveState())

    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.Type.Resize:
            self.resize_images()
        return super().eventFilter(watched, event)

    def resize_images(self):
        editor = self.scroll.widget()
        reserved = 0
        if editor and editor.layout():
            layout = editor.layout()
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if item.layout() is not None and item.layout() == self.preview_layout:
                    continue
                w = item.widget()
                if w and w.isVisible():
                    reserved += w.sizeHint().height() + layout.spacing()
                elif item.layout():
                    reserved += item.layout().sizeHint().height() + layout.spacing()
        reserved = max(160, reserved + 32)
        viewport_h = self.scroll.viewport().height()
        viewport_w = self.scroll.viewport().width()
        height = max(100, min(650, viewport_h - reserved))
        width = max(100, (viewport_w - 160) // 2)
        height = min(height, int(width / self.ratio))
        for widget in (self.page.current, self.page._mode_stack):
            widget.setFixedSize(max(64, int(height * self.ratio)), max(64, height))
