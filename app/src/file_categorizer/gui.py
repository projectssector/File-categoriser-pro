"""Drag-and-drop GUI: categories, tags, folder picker, progress, reports, review."""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from file_categorizer.core.categories import CategoryStore
from file_categorizer.core.config_loader import load_config
from file_categorizer.core.db import Database
from file_categorizer.core.duplicates import (
    DuplicateGroup,
    group_summary,
    scan_duplicates,
)
from file_categorizer.core.hasher import hash_file
from file_categorizer.core.learning import (
    remember_entities_as_patterns,
    remember_note_keywords,
)
from file_categorizer.core.metadata_db import MetaField, MetaFile, MetadataDatabase
from file_categorizer.core.metadata_pipeline import MetadataPipeline
from file_categorizer.core.pipeline import (
    IMAGE_EXTS,
    VIDEO_EXTS,
    FilePipeline,
    safe_category_name,
    unique_destination,
)
from file_categorizer.core.report import Report

LIGHT_BUTTON_BG = "#e0e0e0"

LIGHT_QSS = """
QWidget { background: #f5f5f5; color: #1a1a1a; }
QPlainTextEdit, QTableWidget, QComboBox, QLineEdit { background: #ffffff; color: #1a1a1a; }
QComboBox QAbstractItemView { background: #ffffff; color: #1a1a1a; selection-background-color: #cde4ff; }
QHeaderView::section { background: #e6e6e6; color: #1a1a1a; border: 0; padding: 4px; }
QPushButton, QToolButton {
    background: #e0e0e0; color: #1a1a1a; border: 1px solid #b0b0b0;
    border-radius: 5px; padding: 5px 10px;
}
QPushButton:hover, QToolButton:hover { background: #cfcfcf; }
QPushButton:pressed, QToolButton:pressed { background: #bebebe; }
QPushButton:disabled { color: #9a9a9a; border-color: #d5d5d5; }
QPushButton#accentButton {
    background: #1a7f37; color: #ffffff; border: 1px solid #166b2e; font-weight: bold;
}
QPushButton#accentButton:hover { background: #15803d; }
QTabWidget::pane { border: 1px solid #c0c0c0; }
QTabBar::tab {
    background: #e0e0e0; color: #333333; padding: 7px 16px;
    border: 1px solid #c0c0c0; border-bottom: none;
    border-top-left-radius: 5px; border-top-right-radius: 5px;
}
QTabBar::tab:selected { background: #ffffff; color: #0a66c2; font-weight: bold; }
QTabBar::tab:hover:!selected { background: #d8d8d8; }
QGroupBox { border: 1px solid #c0c0c0; border-radius: 5px; margin-top: 10px; padding-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; color: #1a1a1a; }
QStatusBar { background: #ebebeb; color: #1a1a1a; }
QProgressBar {
    background: #e0e0e0; color: #1a1a1a; border: 1px solid #c0c0c0;
    border-radius: 3px; text-align: center;
}
QProgressBar::chunk { background: #1a7f37; border-radius: 3px; }
QMenu { background: #ffffff; color: #1a1a1a; border: 1px solid #c0c0c0; }
QMenu::item:selected { background: #cde4ff; }
QScrollBar:vertical { background: #ececec; width: 12px; }
QScrollBar::handle:vertical { background: #bbbbbb; border-radius: 6px; min-height: 24px; }
"""

DARK_QSS = """
QWidget { background: #1e1e1e; color: #e6e6e6; }
QPlainTextEdit, QTableWidget, QComboBox, QLineEdit { background: #28282b; color: #e6e6e6; }
QComboBox QAbstractItemView { background: #28282b; color: #e6e6e6; selection-background-color: #3d5a80; }
QHeaderView::section { background: #333337; color: #e6e6e6; border: 0; padding: 4px; }
QPushButton, QToolButton {
    background: #4a4a4f; color: #ffffff; border: 1px solid #6a6a70;
    border-radius: 5px; padding: 5px 10px;
}
QPushButton:hover, QToolButton:hover { background: #5a5a61; }
QPushButton:pressed, QToolButton:pressed { background: #3a3a3f; }
QPushButton:disabled { color: #9a9aa0; border-color: #4a4a4f; }
QPushButton#accentButton {
    background: #34a853; color: #ffffff; border: 1px solid #2c8f47; font-weight: bold;
}
QPushButton#accentButton:hover { background: #3cb963; }
QTabWidget::pane { border: 1px solid #48484d; }
QTabBar::tab {
    background: #2a2a2e; color: #c9c9cf; padding: 7px 16px;
    border: 1px solid #48484d; border-bottom: none;
    border-top-left-radius: 5px; border-top-right-radius: 5px;
}
QTabBar::tab:selected { background: #3a3a40; color: #ffffff; font-weight: bold; }
QTabBar::tab:hover:!selected { background: #33333a; }
QGroupBox { border: 1px solid #48484d; border-radius: 5px; margin-top: 10px; padding-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; color: #e6e6e6; }
QStatusBar { background: #161618; color: #e6e6e6; }
QProgressBar {
    background: #33333a; color: #ffffff; border: 1px solid #48484d;
    border-radius: 3px; text-align: center;
}
QProgressBar::chunk { background: #34a853; border-radius: 3px; }
QMenu { background: #2a2a2e; color: #e6e6e6; border: 1px solid #48484d; }
QMenu::item:selected { background: #3d5a80; }
QScrollBar:vertical { background: #232327; width: 12px; }
QScrollBar::handle:vertical { background: #5a5a61; border-radius: 6px; min-height: 24px; }
"""


def _available_geometry():
    """Return the usable area of the primary screen, or None if there is none."""
    app = QApplication.instance()
    screen = app.primaryScreen() if app is not None else None
    return screen.availableGeometry() if screen is not None else None


def fit_window_to_screen(
    window,
    width: int,
    height: int,
    min_width: int = 480,
    min_height: int = 360,
    margin: int = 40,
) -> None:
    """Size a top-level window so it never spills past the screen edges."""
    avail = _available_geometry()
    if avail is None:
        window.resize(width, height)
        return
    new_w = min(max(width, min_width), max(min_width, avail.width() - margin))
    new_h = min(max(height, min_height), max(min_height, avail.height() - margin))
    window.resize(new_w, new_h)
    frame = window.frameGeometry()
    frame.moveCenter(avail.center())
    window.move(frame.topLeft())


def clamp_window_to_screen(window, margin: int = 0) -> None:
    """Pull a window back inside the screen if it was restored off/over-sized."""
    avail = _available_geometry()
    if avail is None:
        return
    width = min(window.width(), max(320, avail.width() - margin))
    height = min(window.height(), max(240, avail.height() - margin))
    if (width, height) != (window.width(), window.height()):
        window.resize(width, height)
    frame = window.frameGeometry()
    if (
        not avail.contains(frame.topLeft())
        or frame.right() > avail.right()
        or frame.bottom() > avail.bottom()
    ):
        frame.moveCenter(avail.center())
        window.move(frame.topLeft())


class ClassifyWorker(QThread):
    progress = Signal(int, int, dict)
    finished_jobs = Signal(list)
    failed = Signal(str)

    def __init__(self, pipeline_factory, jobs, dry_run):
        super().__init__()
        self.pipeline_factory = pipeline_factory
        self.jobs = jobs
        self.dry_run = dry_run

    def run(self):
        try:
            pipeline = self.pipeline_factory()
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return

        results = []
        total = len(self.jobs)
        for index, (path, tags) in enumerate(self.jobs, 1):
            if self.isInterruptionRequested():
                break
            try:
                result = pipeline.process(path, dry_run=self.dry_run, user_tags=tags)
            except Exception as exc:
                result = {"path": str(path), "status": "error", "error": str(exc)}
            results.append(result)
            self.progress.emit(index, total, result)
        self.finished_jobs.emit(results)


class MainWindow(QMainWindow):
    def __init__(self, config_path: str = "config/config.yaml"):
        super().__init__()
        self.setWindowTitle("File Categorizer")
        self.setMinimumSize(640, 480)
        self.setAcceptDrops(True)

        self.config_path = Path(config_path).resolve()
        self.root = self.config_path.parent.parent
        self.data_dir = self.root / "data"
        os.chdir(self.root)

        self.cfg = load_config(self.config_path)
        self.output_root = self._resolve(self.cfg.paths.get("output", "output"))
        self.categories = CategoryStore(self.data_dir / "categories.json")
        self._sync_categories()
        self.db = Database(self._resolve(self.cfg.paths.get("database", "data/cache.db")))
        self.pipeline: FilePipeline | MetadataPipeline | None = None
        self._mdb: MetadataDatabase | None = None
        self._meta_originals: list[dict] = []
        self.worker: ClassifyWorker | None = None
        self.report: Report | None = None
        self.last_results: list[dict] = []
        self.review_results: list[dict] = []
        self.review_index = 0
        self._duplicate_groups: list[DuplicateGroup] = []
        self._hashes: dict[str, str] = {}
        self._loading = False
        self._dark = False
        self._settings = self._read_settings()
        if self._settings.get("gemini_api_key"):
            os.environ["GEMINI_API_KEY"] = self._settings["gemini_api_key"]
        self._show_meta_details = bool(self._settings.get("show_metadata_details", True))
        self._show_teaching_notes = bool(self._settings.get("show_teaching_notes", True))

        self._build_ui()
        if self._restore_geometry():
            clamp_window_to_screen(self)
        else:
            fit_window_to_screen(self, 1120, 720, min_width=640, min_height=480)
        self._refresh_categories()
        self._apply_theme(bool(self._settings.get("dark", False)))
        self._load_queue()
        self._set_review_results([])
        if self.gemini_key():
            self._set_status("Ready. Add files or drop them onto the window.")
        else:
            self._set_status(
                "Ready. Local indexing (category, EXIF, duplicates) works now; "
                "add an API key only for extra Gemini extraction."
            )

    # ---- persistence -------------------------------------------------
    def _settings_path(self) -> Path:
        return self.data_dir / "settings.json"

    def _queue_path(self) -> Path:
        return self.data_dir / "queue.json"

    def _read_settings(self) -> dict:
        path = self._settings_path()
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_settings(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._settings_path().write_text(
            json.dumps(
                {
                    "dark": self._dark,
                    "gemini_api_key": self._settings.get("gemini_api_key", ""),
                    "window_geometry": self._settings.get("window_geometry", ""),
                    "auto_index": self._settings.get("auto_index", True),
                    "export_after_index": self._settings.get(
                        "export_after_index", True
                    ),
                    "show_review_panel": self._settings.get("show_review_panel", True),
                    "show_metadata_details": self._settings.get("show_metadata_details", True),
                    "show_teaching_notes": self._settings.get("show_teaching_notes", True),
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def _save_geometry(self) -> None:
        try:
            self._settings["window_geometry"] = (
                self.saveGeometry().toHex().data().decode("ascii")
            )
        except Exception:
            pass

    def _restore_geometry(self) -> bool:
        raw = self._settings.get("window_geometry")
        if not raw:
            return False
        try:
            data = QByteArray.fromHex(str(raw).encode("ascii"))
            return bool(self.restoreGeometry(data))
        except Exception:
            return False

    def gemini_key(self) -> str:
        key = os.environ.get("GEMINI_API_KEY") or self._settings.get("gemini_api_key", "")
        return str(key).strip()

    def save_gemini_key(self, key: str) -> None:
        key = (key or "").strip()
        self._settings["gemini_api_key"] = key
        if key:
            os.environ["GEMINI_API_KEY"] = key
        else:
            os.environ.pop("GEMINI_API_KEY", None)
        self._write_settings()
        self.pipeline = None
        if key:
            self.api_btn.setStyleSheet("")
            self._set_status("API key saved. It will be used for hard cases.")
        else:
            self._set_status("API key cleared. Gemini guessing is disabled.")

    def _save_queue(self) -> None:
        entries = []
        for row in range(self.queue.rowCount()):
            path_item = self.queue.item(row, 0)
            if path_item is None:
                continue
            entries.append({"path": path_item.text()})
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._queue_path().write_text(
            json.dumps(entries, indent=2), encoding="utf-8"
        )

    def _prune_queue_missing(self) -> int:
        """Drop queue rows whose file no longer exists on disk.

        Files the app successfully moved (or that were already gone) are removed
        so a later run does not try to re-process them and report them as
        unsupported.  Rows that still exist are kept so they can be retried.
        """
        removed = 0
        self._loading = True
        try:
            for row in range(self.queue.rowCount() - 1, -1, -1):
                item = self.queue.item(row, 0)
                if item is not None and not Path(item.text()).exists():
                    self.queue.removeRow(row)
                    removed += 1
        finally:
            self._loading = False
        if removed:
            self._save_queue()
        return removed

    def _load_queue(self) -> None:
        path = self._queue_path()
        if not path.exists():
            return
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(entries, list):
            return
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            file_path = entry.get("path")
            if not file_path:
                continue
            self._add_row(Path(file_path))
        if entries:
            self._set_status(
                f"Restored {self.queue.rowCount()} file(s) from last session."
            )

    # ---- helpers -----------------------------------------------------
    def _resolve(self, path: str | Path) -> Path:
        path = Path(path)
        return path if path.is_absolute() else (self.root / path)

    def _sync_categories(self) -> None:
        """Make the user's own categories the only ones the sorter uses.

        The sample categories shipped inside config.yaml are deliberately not
        merged in - otherwise they would reappear next to your own list (and
        produce duplicates). config.yaml categories are still honoured by the
        command-line tool.
        """
        self.cfg.raw["categories"] = {
            name: dict(spec) for name, spec in self.categories.all().items()
        }

    def _hash(self, path: Path) -> str:
        key = str(path)
        if key not in self._hashes:
            try:
                self._hashes[key] = hash_file(path, fast=True)
            except OSError:
                self._hashes[key] = ""
        return self._hashes[key]

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def _theme_icon(self, dark: bool) -> QIcon:
        size = 24
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        if dark:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#f5d76e"))
            painter.drawEllipse(7, 7, 10, 10)
            pen = QPen(QColor("#f5d76e"))
            pen.setWidth(2)
            painter.setPen(pen)
            for x1, y1, x2, y2 in (
                (12, 1, 12, 4), (12, 20, 12, 23), (1, 12, 4, 12),
                (20, 12, 23, 12), (4, 4, 6, 6), (18, 18, 20, 20),
                (4, 20, 6, 18), (20, 4, 18, 6),
            ):
                painter.drawLine(x1, y1, x2, y2)
        else:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#f5d76e"))
            painter.drawEllipse(3, 3, 17, 17)
            painter.setBrush(QColor(LIGHT_BUTTON_BG))
            painter.drawEllipse(10, 0, 17, 17)
        painter.end()
        return QIcon(pix)

    def _apply_theme(self, dark: bool) -> None:
        self._dark = dark
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(DARK_QSS if dark else LIGHT_QSS)
        self.theme_btn.setIcon(self._theme_icon(dark))
        self.theme_btn.setIconSize(QSize(22, 22))
        self.theme_btn.setToolTip("Switch to light mode" if dark else "Switch to dark mode")
        self._write_settings()

    def toggle_theme(self) -> None:
        self._apply_theme(not self._dark)

    def _open_settings(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Settings - API Key")
        form = QFormLayout(dialog)
        key_edit = QLineEdit(dialog)
        key_edit.setPlaceholderText("AIza... (your own Google Gemini key)")
        key_edit.setEchoMode(QLineEdit.Password)
        key_edit.setText(self.gemini_key())
        hint = QLabel(
            "Paste YOUR OWN Gemini API key - every user is expected to bring "
            "their own free key.\n\n"
            "Get one: https://aistudio.google.com/app/apikey  (free account)\n\n"
            "Without a key the sorter still categorizes using image patterns, "
            "but the Gemini guess on hard cases is skipped. The key is stored "
            "only on this computer, in data/settings.json."
        )
        hint.setWordWrap(True)
        form.addRow("Gemini API key:", key_edit)
        form.addRow(hint)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel, dialog
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        fit_window_to_screen(dialog, 460, 240, min_width=360, min_height=200)
        if dialog.exec() == QDialog.Accepted:
            self.save_gemini_key(key_edit.text())

    # ---- UI ----------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        outer = QVBoxLayout(central)

        header = QHBoxLayout()
        title = QLabel("File Categorizer")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch(1)
        self.api_btn = QPushButton("API Key")
        self.api_btn.clicked.connect(self._open_settings)
        header.addWidget(self.api_btn)
        self.theme_btn = QToolButton()
        self.theme_btn.setAutoRaise(True)
        self.theme_btn.clicked.connect(self.toggle_theme)
        header.addWidget(self.theme_btn)
        outer.addLayout(header)

        self.tabs = QTabWidget()
        self.classify_tab = QWidget()
        self.duplicates_tab = QWidget()
        self.report_tab = QWidget()
        self.spreadsheet_tab = QWidget()
        self.tabs.addTab(self.classify_tab, "Classify")
        self.tabs.addTab(self.duplicates_tab, "Duplicates")
        self.tabs.addTab(self.report_tab, "Log / Report")
        self.tabs.addTab(self.spreadsheet_tab, "Spreadsheet")
        outer.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

        self._build_classify_tab()
        self._build_duplicates_tab()
        self._build_report_tab()
        self._build_spreadsheet_tab()

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.status_label = QLabel()
        self.statusBar().addWidget(self.progress, 1)
        self.statusBar().addPermanentWidget(self.status_label, 3)

    def _build_classify_tab(self) -> None:
        layout = QVBoxLayout(self.classify_tab)

        toolbar = QHBoxLayout()
        for label, slot in (
            ("Add Files...", self.add_files),
            ("Add Folder...", self.add_folder),
            ("Remove Selected", self.remove_selected),
            ("Clear Queue", self.clear_queue),
        ):
            button = QPushButton(label)
            button.clicked.connect(slot)
            toolbar.addWidget(button)
        toolbar.addStretch(1)
        self.auto_index = QCheckBox("Auto-index added files")
        self.auto_index.setChecked(bool(self._settings.get("auto_index", True)))
        self.auto_index.setToolTip(
            "Read new files immediately: classify, extract image/EXIF data, "
            "and update the workbook. No manual tagging needed."
        )
        self.auto_index.toggled.connect(self._set_auto_index)
        toolbar.addWidget(self.auto_index)
        self.dry_run = QCheckBox("Index in place (don't move files)")
        toolbar.addWidget(self.dry_run)
        layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Horizontal)

        queue_box = QGroupBox("Upload queue (drop files/folders anywhere)")
        queue_layout = QVBoxLayout(queue_box)
        hint = QLabel(
            "Files are indexed automatically: category, dimensions, EXIF, "
            "GPS, capture date and duplicate checks are written to the workbook."
        )
        hint.setWordWrap(True)
        queue_layout.addWidget(hint)
        self.queue = QTableWidget(0, 2)
        self.queue.setHorizontalHeaderLabels(["File", "Status"])
        self.queue.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.queue.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        self.queue.setColumnWidth(1, 220)
        self.queue.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.queue.setDragDropMode(QAbstractItemView.NoDragDrop)
        self.queue.setAcceptDrops(False)
        self.queue.viewport().setAcceptDrops(False)
        self.queue.setEditTriggers(QAbstractItemView.NoEditTriggers)
        queue_layout.addWidget(self.queue)
        splitter.addWidget(queue_box)

        cat_box = QGroupBox("Categories (remembered between sessions)")
        cat_layout = QVBoxLayout(cat_box)
        self.category_table = QTableWidget(0, 2)
        self.category_table.setHorizontalHeaderLabels(["Category", "Scan cues"])
        self.category_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.category_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.category_table.setColumnWidth(0, 150)
        self.category_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.category_table.itemChanged.connect(self._on_category_item_changed)
        cat_layout.addWidget(self.category_table)
        cat_buttons = QHBoxLayout()
        add_cat = QPushButton("Add Category")
        add_cat.clicked.connect(self.add_category)
        del_cat = QPushButton("Delete Category")
        del_cat.clicked.connect(self.delete_category)
        cat_buttons.addWidget(add_cat)
        cat_buttons.addWidget(del_cat)
        cat_layout.addLayout(cat_buttons)
        splitter.addWidget(cat_box)
        splitter.setSizes([600, 380])
        layout.addWidget(splitter, 1)

        self.run_btn = QPushButton("Index & Sort")
        self.run_btn.setObjectName("accentButton")
        self.run_btn.setMinimumHeight(44)
        self.run_btn.clicked.connect(self.run_classify)
        layout.addWidget(self.run_btn)

    def _build_duplicates_tab(self) -> None:
        layout = QVBoxLayout(self.duplicates_tab)

        toolbar = QHBoxLayout()
        self.scan_dups_btn = QPushButton("Scan for Duplicates")
        self.scan_dups_btn.setObjectName("accentButton")
        self.scan_dups_btn.clicked.connect(self.scan_duplicates)
        self._dup_scan_progress = QProgressBar()
        self._dup_scan_progress.setRange(0, 0)
        self._dup_scan_progress.setVisible(False)
        self._dup_scan_progress.setFixedWidth(160)
        quarantine = QPushButton("Move Selected to Quarantine")
        quarantine.clicked.connect(self.quarantine_selected_duplicates)
        open_folder = QPushButton("Open Containing Folder")
        open_folder.clicked.connect(self.open_duplicate_folder)
        toolbar.addWidget(self.scan_dups_btn)
        toolbar.addWidget(self._dup_scan_progress)
        toolbar.addWidget(quarantine)
        toolbar.addWidget(open_folder)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.duplicate_summary = QLabel(
            "Click 'Scan for Duplicates' to compare exact hashes and image "
            "perceptual hashes. Nothing is deleted automatically."
        )
        self.duplicate_summary.setWordWrap(True)
        layout.addWidget(self.duplicate_summary)

        splitter = QSplitter(Qt.Vertical)
        groups_box = QGroupBox("Duplicate groups (choose one to inspect)")
        groups_layout = QVBoxLayout(groups_box)
        self.duplicate_table = QTableWidget(0, 5)
        self.duplicate_table.setHorizontalHeaderLabels(
            ["Group", "Kind", "Copies", "Reclaimable", "Keep"]
        )
        self.duplicate_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Interactive
        )
        self.duplicate_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Interactive
        )
        self.duplicate_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.Interactive
        )
        self.duplicate_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.Interactive
        )
        self.duplicate_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.Stretch
        )
        self.duplicate_table.setColumnWidth(0, 150)
        self.duplicate_table.setColumnWidth(1, 90)
        self.duplicate_table.setColumnWidth(2, 70)
        self.duplicate_table.setColumnWidth(3, 100)
        self.duplicate_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.duplicate_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.duplicate_table.itemSelectionChanged.connect(
            self._on_duplicate_group_selected
        )
        groups_layout.addWidget(self.duplicate_table)
        splitter.addWidget(groups_box)

        members_box = QGroupBox("Files in the selected group")
        members_layout = QVBoxLayout(members_box)
        self.duplicate_members = QTableWidget(0, 4)
        self.duplicate_members.setHorizontalHeaderLabels(
            ["Keep", "File", "Size", "Similarity"]
        )
        self.duplicate_members.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Interactive
        )
        self.duplicate_members.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        self.duplicate_members.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.Interactive
        )
        self.duplicate_members.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.Interactive
        )
        self.duplicate_members.setColumnWidth(0, 60)
        self.duplicate_members.setColumnWidth(2, 100)
        self.duplicate_members.setColumnWidth(3, 100)
        self.duplicate_members.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.duplicate_members.setEditTriggers(QAbstractItemView.NoEditTriggers)
        members_layout.addWidget(self.duplicate_members)
        splitter.addWidget(members_box)
        splitter.setSizes([260, 300])
        layout.addWidget(splitter, 1)

    @staticmethod
    def _format_bytes(value: int | None) -> str:
        size = float(value or 0)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024 or unit == "TB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def scan_duplicates(self, auto: bool = False) -> None:
        if not self._metadata_enabled():
            if not auto:
                QMessageBox.information(
                    self, "Metadata disabled",
                    "Enable metadata in config.yaml to index and scan duplicates.",
                )
            return
        if hasattr(self, "scan_dups_btn"):
            self.scan_dups_btn.setEnabled(False)
        if hasattr(self, "_dup_scan_progress"):
            self._dup_scan_progress.setVisible(True)
        if not auto:
            self._set_status("Scanning for similarities and duplicates...")
        try:
            self._duplicate_groups = scan_duplicates(self._metadata_db())
        except Exception as exc:
            self._duplicate_groups = []
            if not auto:
                QMessageBox.warning(self, "Duplicate scan failed", str(exc))
            if hasattr(self, "scan_dups_btn"):
                self.scan_dups_btn.setEnabled(True)
            if hasattr(self, "_dup_scan_progress"):
                self._dup_scan_progress.setVisible(False)
            return

        self.duplicate_table.setRowCount(0)
        for group in self._duplicate_groups:
            row = self.duplicate_table.rowCount()
            self.duplicate_table.insertRow(row)
            for col, value in enumerate((
                group.group_id,
                group.kind.title(),
                str(len(group.files)),
                self._format_bytes(group.reclaimable),
                Path(group.keep_path).name,
            )):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if col == 0:
                    item.setData(Qt.UserRole, group.group_id)
                self.duplicate_table.setItem(row, col, item)
        self.duplicate_members.setRowCount(0)

        summary = group_summary(self._duplicate_groups)
        if summary["groups"]:
            self.duplicate_summary.setText(
                f"{summary['groups']} duplicate group(s): "
                f"{summary['exact_groups']} exact, "
                f"{summary['perceptual_groups']} perceptual. "
                f"Reclaimable if you quarantine all but the keep copy: "
                f"{self._format_bytes(summary['reclaimable'])}. "
                "Nothing is deleted automatically."
            )
            if not auto:
                self._set_status(
                    f"Duplicate scan found {summary['groups']} group(s)."
                )
        else:
            self.duplicate_summary.setText(
                "No duplicate groups found. Exact copies need a full-hash "
                "match; perceptual groups need a stored pHash."
            )
            if not auto:
                self._set_status("Duplicate scan found no duplicates.")
        if hasattr(self, "scan_dups_btn"):
            self.scan_dups_btn.setEnabled(True)
        if hasattr(self, "_dup_scan_progress"):
            self._dup_scan_progress.setVisible(False)

    def _current_duplicate_group(self) -> DuplicateGroup | None:
        rows = self.duplicate_table.selectionModel().selectedRows()
        if not rows:
            return None
        group_id = self.duplicate_table.item(rows[0].row(), 0)
        if group_id is None:
            return None
        target = group_id.data(Qt.UserRole)
        return next(
            (g for g in self._duplicate_groups if g.group_id == target), None
        )

    def _on_duplicate_group_selected(self) -> None:
        group = self._current_duplicate_group()
        self.duplicate_members.setRowCount(0)
        if group is None:
            return
        for f in group.files:
            row = self.duplicate_members.rowCount()
            self.duplicate_members.insertRow(row)
            keep = QTableWidgetItem("keep" if f.is_keep else "")
            keep.setFlags(keep.flags() & ~Qt.ItemIsEditable)
            self.duplicate_members.setItem(row, 0, keep)
            path_item = QTableWidgetItem(f.file_path)
            path_item.setFlags(path_item.flags() & ~Qt.ItemIsEditable)
            path_item.setData(Qt.UserRole, f.file_path)
            path_item.setData(Qt.UserRole + 1, f.is_keep)
            path_item.setData(Qt.UserRole + 2, group.group_id)
            self.duplicate_members.setItem(row, 1, path_item)
            for col, value in enumerate((
                self._format_bytes(f.file_size),
                f"{f.similarity:.1%}" if f.similarity is not None else "-",
            ), start=2):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.duplicate_members.setItem(row, col, item)

    def quarantine_selected_duplicates(self) -> None:
        rows = self.duplicate_members.selectionModel().selectedRows()
        pending: list[tuple[Path, str]] = []
        for index in rows:
            item = self.duplicate_members.item(index.row(), 1)
            if item is None:
                continue
            if bool(item.data(Qt.UserRole + 1)):
                continue
            pending.append((
                Path(item.data(Qt.UserRole) or item.text()),
                str(item.data(Qt.UserRole + 2) or "duplicates"),
            ))
        if not pending:
            QMessageBox.information(
                self, "No duplicates selected",
                "Select one or more non-keep rows in the group first.",
            )
            return
        if QMessageBox.question(
            self,
            "Quarantine duplicates",
            f"Move {len(pending)} duplicate file(s) to "
            f"{self.output_root / 'duplicates_quarantine'}?\n\n"
            "They are moved, not deleted, so you can restore them.",
        ) != QMessageBox.Yes:
            return

        mdb = self._metadata_db()
        moved = 0
        for source, group_id in pending:
            try:
                target_dir = self.output_root / "duplicates_quarantine" / safe_category_name(group_id)
                target_dir.mkdir(parents=True, exist_ok=True)
                destination = unique_destination(target_dir / source.name)
                shutil.move(str(source), destination)
                mdb.move_location(str(source), str(destination))
                moved += 1
            except OSError as exc:
                self._set_status(f"Could not quarantine {source.name}: {exc}")
        self.scan_duplicates(auto=True)
        self._set_status(f"Quarantined {moved} duplicate file(s).")

    def open_duplicate_folder(self) -> None:
        rows = self.duplicate_members.selectionModel().selectedRows()
        target = None
        if rows:
            item = self.duplicate_members.item(rows[0].row(), 1)
            if item is not None:
                target = Path(item.data(Qt.UserRole) or item.text()).parent
        if target is None:
            group = self._current_duplicate_group()
            if group is not None:
                target = Path(group.keep_path).parent
        if target is None:
            self._set_status("Select a duplicate group or file first.")
            return
        self._open_external(str(target))

    def _build_report_tab(self) -> None:
        layout = QVBoxLayout(self.report_tab)
        toolbar = QHBoxLayout()
        gen = QPushButton("Generate Report")
        gen.clicked.connect(self.generate_report)
        save = QPushButton("Save Report As...")
        save.clicked.connect(self.save_report_as)
        toolbar.addWidget(gen)
        toolbar.addWidget(save)
        toolbar.addStretch(1)
        self.show_review_panel = QCheckBox("Show Metadata Review")
        self.show_review_panel.setChecked(
            bool(self._settings.get("show_review_panel", True))
        )
        self.show_review_panel.toggled.connect(self._toggle_review_panel)
        toolbar.addWidget(self.show_review_panel)
        layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Horizontal)
        self.report_edit = QPlainTextEdit()
        self.report_edit.setPlaceholderText(
            "Classification tables and logs will appear here."
        )
        self.report_edit.setLineWrapMode(QPlainTextEdit.NoWrap)
        splitter.addWidget(self.report_edit)
        review_scroll = QScrollArea()
        review_scroll.setWidgetResizable(True)
        review_scroll.setFrameShape(QFrame.NoFrame)
        review_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._review_scroll = review_scroll
        review_scroll.setWidget(self._build_review_panel())
        splitter.addWidget(review_scroll)
        self._report_splitter = splitter
        splitter.setSizes([640, 420])
        self._toggle_review_panel(self.show_review_panel.isChecked())
        layout.addWidget(splitter, 1)

    def _build_review_panel(self) -> QWidget:
        box = QGroupBox("Review & Teach")
        layout = QVBoxLayout(box)

        self.preview = QLabel("No image yet")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setFixedSize(360, 300)
        self.preview.setStyleSheet("border: 1px solid #888; background: #00000000; cursor: pointer;")
        self.preview.mousePressEvent = self._preview_clicked
        layout.addWidget(self.preview, 0, Qt.AlignHCenter)

        self.review_name = QLabel("-")
        self.review_name.setWordWrap(True)
        layout.addWidget(self.review_name)

        self.review_classified = QLabel("-")
        self.review_classified.setWordWrap(True)
        layout.addWidget(self.review_classified)

        meta_box = QGroupBox("Metadata Review & Teach (edit the Value column)")
        meta_layout = QVBoxLayout(meta_box)

        self.meta_expand = QToolButton()
        self.meta_expand.setText("Metadata Details")
        self.meta_expand.setCheckable(True)
        self.meta_expand.setChecked(bool(getattr(self, "_show_meta_details", True)))
        self.meta_expand.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.meta_expand.setArrowType(Qt.DownArrow)
        self.meta_expand.clicked.connect(self._toggle_meta_details)
        meta_layout.addWidget(self.meta_expand)

        self.meta_content = QWidget()
        meta_content_layout = QVBoxLayout(self.meta_content)
        meta_content_layout.setContentsMargins(0, 0, 0, 0)

        self.meta_table = QTableWidget(0, 5)
        self.meta_table.setHorizontalHeaderLabels(
            ["Field", "Value", "Source", "Conf", "Evidence"]
        )
        self.meta_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.meta_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.meta_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Interactive)
        self.meta_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Interactive)
        self.meta_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.meta_table.setColumnWidth(0, 130)
        self.meta_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.meta_table.setMinimumHeight(150)
        meta_content_layout.addWidget(self.meta_table)

        meta_btns = QHBoxLayout()
        for label, slot in (
            ("Run search", self.run_metadata_search),
            ("Approve & save", self.approve_metadata),
            ("Open URL", self.open_metadata_url),
            ("Export this row", self.export_current_row),
            ("Mark recorded", self.mark_already_recorded),
        ):
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            meta_btns.addWidget(btn)
        meta_btns.addStretch(1)
        meta_content_layout.addLayout(meta_btns)

        self.corr_label = QLabel("")
        self.corr_label.setWordWrap(True)
        meta_content_layout.addWidget(self.corr_label)
        meta_layout.addWidget(self.meta_content)
        self.meta_content.setVisible(self.meta_expand.isChecked())
        self.meta_expand.setArrowType(
            Qt.DownArrow if self.meta_expand.isChecked() else Qt.RightArrow
        )
        layout.addWidget(meta_box)

        self.notes_box = QGroupBox("Teaching notes (what to look for)")
        notes_layout = QVBoxLayout(self.notes_box)
        self.teach_notes = QPlainTextEdit()
        self.teach_notes.setPlaceholderText(
            "Teach it what matters for THIS image, e.g. "
            "'Naruto fan art - comment says ep. 12 by @artist_handle'. "
            "Words here train the sorter for similar images."
        )
        self.teach_notes.setMaximumHeight(70)
        notes_layout.addWidget(self.teach_notes)
        notes_row = QHBoxLayout()
        notes_row.addStretch(1)
        self.save_notes_btn = QPushButton("Save notes")
        self.save_notes_btn.clicked.connect(self.save_teach_notes)
        notes_row.addWidget(self.save_notes_btn)
        notes_layout.addLayout(notes_row)
        self.notes_box.setVisible(bool(getattr(self, "_show_teaching_notes", True)))
        layout.addWidget(self.notes_box)

        layout.addWidget(QLabel("What is it actually?"))
        self.actual_combo = QComboBox()
        self.actual_combo.setEditable(True)
        layout.addWidget(self.actual_combo)

        suggest_layout = QHBoxLayout()
        self.suggest_btn = QPushButton("Suggest New Category")
        self.suggest_btn.clicked.connect(self._suggest_new_category)
        self.add_new_cat_btn = QPushButton("Add New Category")
        self.add_new_cat_btn.clicked.connect(self._add_new_category_from_review)
        suggest_layout.addWidget(self.suggest_btn)
        suggest_layout.addWidget(self.add_new_cat_btn)
        layout.addLayout(suggest_layout)

        self.learn_btn = QPushButton("Save Correction & Learn")
        self.learn_btn.clicked.connect(self.save_correction)
        layout.addWidget(self.learn_btn)

        nav = QHBoxLayout()
        self.prev_btn = QPushButton("< Previous")
        self.prev_btn.clicked.connect(self.previous_image)
        self.next_btn = QPushButton("Next >")
        self.next_btn.clicked.connect(self.next_image)
        self.review_counter = QLabel("0 / 0")
        self.review_counter.setAlignment(Qt.AlignCenter)
        nav.addWidget(self.prev_btn)
        nav.addWidget(self.review_counter, 1)
        nav.addWidget(self.next_btn)
        layout.addLayout(nav)
        layout.addStretch(1)
        return box

    def _build_spreadsheet_tab(self) -> None:
        layout = QVBoxLayout(self.spreadsheet_tab)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("Workbook:"))
        self.workbook_edit = QLineEdit(self._default_workbook())
        path_row.addWidget(self.workbook_edit, 1)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self.browse_workbook)
        path_row.addWidget(browse)
        layout.addLayout(path_row)

        opts = QHBoxLayout()
        self.export_after_index_check = QCheckBox("Export after each index run")
        self.export_after_index_check.setChecked(
            bool(self._settings.get("export_after_index", True))
        )
        self.export_after_index_check.toggled.connect(self._set_export_after_index)
        opts.addWidget(self.export_after_index_check)
        self.auto_export_check = QCheckBox("Auto-export after each file")
        self.auto_export_check.setChecked(self._auto_export())
        self.auto_export_check.toggled.connect(self._set_auto_export)
        opts.addWidget(self.auto_export_check)
        opts.addStretch(1)
        export_btn = QPushButton("Export Now")
        export_btn.setObjectName("accentButton")
        export_btn.clicked.connect(self.export_spreadsheet)
        opts.addWidget(export_btn)
        layout.addLayout(opts)

        self.spreadsheet_preview = QPlainTextEdit()
        self.spreadsheet_preview.setReadOnly(True)
        self.spreadsheet_preview.setPlaceholderText(
            "Click 'Export Now' to write the workbook from the metadata tables."
        )
        layout.addWidget(self.spreadsheet_preview, 1)
        self._refresh_spreadsheet_preview()

    # ---- drag and drop ----------------------------------------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasUrls():
            event.ignore()
            return
        paths = [
            Path(url.toLocalFile())
            for url in event.mimeData().urls()
            if url.isLocalFile()
        ]
        event.acceptProposedAction()
        self.add_paths(paths)

    # ---- queue -------------------------------------------------------
    def add_paths(self, paths: list[Path]) -> None:
        files: list[Path] = []
        for path in paths:
            path = Path(path)
            if path.is_dir():
                files.extend(
                    sorted(
                        p
                        for p in path.rglob("*")
                        if p.is_file() and p.suffix.lower() in (IMAGE_EXTS | VIDEO_EXTS)
                    )
                )
            elif path.is_file() and path.suffix.lower() in (IMAGE_EXTS | VIDEO_EXTS):
                files.append(path)
        for file in files:
            self._add_row(file)
        if files:
            self._save_queue()
            self._set_status(f"Added {len(files)} file(s) to the queue.")
            if self.auto_index.isChecked():
                QTimer.singleShot(0, self.run_classify)

    def _add_row(self, path: Path) -> None:
        self._loading = True
        row = self.queue.rowCount()
        self.queue.insertRow(row)
        name_item = QTableWidgetItem(str(path))
        name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
        self.queue.setItem(row, 0, name_item)
        status_item = QTableWidgetItem("Queued")
        status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
        self.queue.setItem(row, 1, status_item)
        self._loading = False

    def _set_queue_status(self, path: str | Path, text: str) -> None:
        target = str(path)
        for row in range(self.queue.rowCount()):
            item = self.queue.item(row, 0)
            if item is not None and item.text() == target:
                status = self.queue.item(row, 1)
                if status is not None:
                    status.setText(text)
                return

    def add_files(self) -> None:
        pattern = " ".join(f"*{e}" for e in sorted(IMAGE_EXTS | VIDEO_EXTS))
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select images or videos", str(self.root), f"Media ({pattern})"
        )
        if files:
            self.add_paths([Path(f) for f in files])

    def add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select a folder", str(self.root))
        if folder:
            self.add_paths([Path(folder)])

    def remove_selected(self) -> None:
        rows = sorted({index.row() for index in self.queue.selectedIndexes()}, reverse=True)
        for row in rows:
            self.queue.removeRow(row)
        if rows:
            self._save_queue()

    def clear_queue(self) -> None:
        self.queue.setRowCount(0)
        self._save_queue()

    # ---- categories --------------------------------------------------
    def _refresh_categories(self) -> None:
        cats = self.categories.all()
        was_loading = self._loading
        self._loading = True
        self.category_table.blockSignals(True)
        self.actual_combo.blockSignals(True)
        try:
            self.category_table.setRowCount(0)
            for name in sorted(cats):
                spec = cats[name] or {}
                row = self.category_table.rowCount()
                self.category_table.insertRow(row)
                name_item = QTableWidgetItem(name)
                name_item.setData(Qt.UserRole, name)
                self.category_table.setItem(row, 0, name_item)
                cues = ", ".join(spec.get("scan_for", []))
                self.category_table.setItem(row, 1, QTableWidgetItem(cues))
            current = self.actual_combo.currentText()
            self.actual_combo.clear()
            self.actual_combo.addItems(sorted(cats))
            if current:
                self.actual_combo.setCurrentText(current)
        finally:
            self.actual_combo.blockSignals(False)
            self.category_table.blockSignals(False)
            self._loading = was_loading

    def _on_category_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading:
            return
        row = item.row()
        name_item = self.category_table.item(row, 0)
        if not name_item:
            return
        new_name = name_item.text().strip()
        if not new_name:
            self._refresh_categories()
            return
        original = name_item.data(Qt.UserRole)
        cues_item = self.category_table.item(row, 1)
        cues_text = cues_item.text() if cues_item else ""
        cues = [c.strip() for c in cues_text.split(",") if c.strip()]

        if original and original != new_name:
            if (
                self.categories.has(new_name)
                and original.casefold() != new_name.casefold()
            ):
                QMessageBox.warning(
                    self,
                    "Duplicate category",
                    f"Category '{new_name}' already exists.",
                )
                self._refresh_categories()
                return
            self.categories.remove(original)

        try:
            clean = self.categories.add(new_name, cues)
        except ValueError:
            self._refresh_categories()
            return
        self._sync_categories()
        self._refresh_categories()
        self._set_status(f"Category '{clean}' updated.")

    def add_category(self) -> None:
        name, ok = QInputDialog.getText(self, "New Category", "Category name:")
        if not ok or not name.strip():
            return
        cues_text, _ = QInputDialog.getMultiLineText(
            self, "Scan cues", "One visual cue per line (optional):"
        )
        cues = [c.strip() for c in cues_text.splitlines() if c.strip()]
        try:
            clean = self.categories.add(name, cues)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid category", str(exc))
            return
        self._sync_categories()
        self._refresh_categories()
        self._set_status(f"Category '{clean}' saved.")

    def delete_category(self) -> None:
        rows = {index.row() for index in self.category_table.selectedIndexes()}
        if not rows:
            QMessageBox.information(self, "No selection", "Select a category to delete.")
            return
        name = self.category_table.item(min(rows), 0).text()
        if QMessageBox.question(self, "Delete", f"Delete category '{name}'?") != QMessageBox.Yes:
            return
        self.categories.remove(name)
        self._sync_categories()
        self._refresh_categories()
        self._set_status(f"Category '{name}' deleted.")

    # ---- classification ---------------------------------------------
    def _metadata_enabled(self) -> bool:
        return bool(self.cfg.raw.get("metadata", {}).get("enabled", True))

    def _get_pipeline(self):
        if self.pipeline is None:
            if self._metadata_enabled():
                mdb = MetadataDatabase(
                    self.cfg.paths.get("database", "data/cache.db")
                )
                self.pipeline = MetadataPipeline(
                    self.cfg, self.db, mdb, gemini_key=self.gemini_key()
                )
            else:
                self.pipeline = FilePipeline(self.cfg, self.db)
        return self.pipeline

    def _collect_jobs(self) -> list[tuple[Path, None]]:
        jobs: list[tuple[Path, None]] = []
        for row in range(self.queue.rowCount()):
            path = Path(self.queue.item(row, 0).text())
            jobs.append((path, None))
        return jobs

    def run_classify(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        if self.queue.rowCount() == 0:
            QMessageBox.information(self, "Nothing to do", "Add images or a folder first.")
            return

        jobs = self._collect_jobs()
        self.run_btn.setEnabled(False)
        self.progress.setRange(0, 0)
        if self.gemini_key():
            self._set_status("Loading models and indexing...")
        else:
            self._set_status(
                "Loading models and indexing locally (no API key - OCR/EXIF "
                "only, Gemini guessing skipped)..."
            )

        self.progress_dialog = QProgressDialog(
            "Loading models and indexing...", "Cancel", 0, 0, self
        )
        self.progress_dialog.setWindowTitle("Working")
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.canceled.connect(self._cancel_worker)

        self.worker = ClassifyWorker(self._get_pipeline, jobs, self.dry_run.isChecked())
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_jobs.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _cancel_worker(self) -> None:
        if self.worker is not None:
            self.worker.requestInterruption()

    def _on_progress(self, index: int, total: int, result: dict) -> None:
        if self.progress.maximum() != total:
            self.progress.setRange(0, total)
            self.progress_dialog.setRange(0, total)
        self.progress.setValue(index)
        self.progress_dialog.setValue(index)
        name = Path(result.get("path", "")).name
        tag = result.get("tag", "")
        status = result.get("status", "")
        self._set_status(f"[{index}/{total}] {name} -> {status} {tag}".strip())
        if status == "duplicate":
            label = f"Duplicate of {Path(result.get('duplicate_of_path') or '').name}"
        elif status in ("classified", "nsfw"):
            label = f"Indexed: {tag}" if tag else "Indexed"
        elif status == "missing":
            label = "Missing (already moved)"
        else:
            label = status.title() or "Done"
        self._set_queue_status(result.get("path", ""), label)

    def _on_failed(self, message: str) -> None:
        self.run_btn.setEnabled(True)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress_dialog.close()
        self._set_status("Failed.")
        QMessageBox.critical(self, "Classification failed", message)

    def _on_finished(self, results: list[dict]) -> None:
        self.run_btn.setEnabled(True)
        self.last_results = results
        total = max(1, len(results))
        self.progress.setRange(0, total)
        self.progress.setValue(len(results))
        self.progress_dialog.close()

        self.report = self._build_report(results)
        self.report_edit.setPlainText(self.report.build())
        try:
            saved = self.report.save(self.output_root / "reports")
            self._set_status(f"Done. Report saved to {saved}")
        except OSError as exc:
            self._set_status(f"Done (could not save report: {exc})")
        self._set_review_results(results)
        self.tabs.setCurrentWidget(self.report_tab)

        # Remove files that were sorted (moved) or are gone, so the queue does
        # not re-list them on the next run as "unsupported"/"missing".
        pruned = self._prune_queue_missing()
        moved = sum(1 for r in results if r.get("status") in ("classified", "nsfw"))
        duplicates = sum(1 for r in results if r.get("status") == "duplicate")
        error = sum(1 for r in results if r.get("status") == "error")
        missing = sum(1 for r in results if r.get("status") == "missing")
        unsupported = sum(1 for r in results if r.get("status") == "unsupported")
        verb = "would index" if self.dry_run.isChecked() else "indexed"
        summary = f"Done. {moved} {verb}"
        if duplicates:
            summary += f", {duplicates} exact duplicate(s) left in place"
        if error:
            summary += f", {error} error(s)"
        if missing:
            summary += f", {missing} missing (already moved)"
        if unsupported:
            summary += f", {unsupported} unreadable"
        if pruned and not self.dry_run.isChecked():
            summary += f" - {pruned} cleared from queue"

        if self._metadata_enabled():
            self.scan_duplicates(auto=True)
            if self.export_after_index_check.isChecked():
                exported = self._export_workbook_silent()
                if exported:
                    summary += f"; workbook saved to {exported.name}"
        self._refresh_spreadsheet_preview()
        self._set_status(summary)

    def _build_report(self, results: list[dict]) -> Report:
        report = Report()
        for result in results:
            status = result.get("status")
            if status == "classified" or (status == "nsfw" and result.get("tag")):
                report.add(
                    result.get("path", ""),
                    result.get("tag", ""),
                    result.get("confidence", 0.0),
                    result.get("model", "") or ("nsfw" if status == "nsfw" else ""),
                    result.get("tags", []),
                )
            else:
                report.add(
                    result.get("path", ""),
                    result.get("status", "unknown"),
                    0.0,
                    result.get("error", ""),
                    result.get("tags", []),
                )
        return report

    def generate_report(self) -> None:
        if not self.last_results:
            self._set_status("No results yet. Run a classification first.")
            return
        self.report = self._build_report(self.last_results)
        self.report_edit.setPlainText(self.report.build())

    def save_report_as(self) -> None:
        text = self.report_edit.toPlainText()
        if not text.strip():
            self._set_status("Nothing to save.")
            return
        default = str(self.output_root / "reports" / "report.txt")
        path, _ = QFileDialog.getSaveFileName(self, "Save report", default, "Text files (*.txt)")
        if not path:
            return
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text, encoding="utf-8")
        self._set_status(f"Report saved to {path}")

    # ---- review & corrections ---------------------------------------
    def _result_path(self, result: dict) -> Path | None:
        moved = result.get("moved_to")
        if moved and Path(moved).exists():
            return Path(moved)
        original = Path(result.get("path", ""))
        return original if original.exists() else None

    @staticmethod
    def _format_metadata(result: dict) -> str:
        fields = result.get("metadata_fields") or []
        if not fields:
            return "(no metadata extracted)"
        lines = []
        for f in fields:
            name = f.get("field_name", "?")
            value = f.get("field_value", "")
            source = f.get("source", "")
            conf = f.get("confidence")
            conf_txt = f" ({conf:.0%})" if isinstance(conf, (int, float)) else ""
            src_txt = f" [{source}]" if source else ""
            lines.append(f"{name}: {value}{src_txt}{conf_txt}")
        return "\n".join(lines)

    # ---- metadata review & spreadsheet -------------------------------
    def _metadata_db(self) -> MetadataDatabase:
        if self._mdb is None:
            self._mdb = MetadataDatabase(self.cfg.paths.get("database", "data/cache.db"))
            self._mdb.init_schema()
        return self._mdb

    def _default_workbook(self) -> str:
        wb = self.cfg.raw.get("spreadsheet", {}).get(
            "workbook_path", "output/metadata.xlsx"
        )
        return str(self._resolve(wb))

    def _auto_export(self) -> bool:
        return bool(self.cfg.raw.get("spreadsheet", {}).get("auto_export", False))

    def _set_auto_export(self, on: bool) -> None:
        self.cfg.raw.setdefault("spreadsheet", {})["auto_export"] = bool(on)

    def _set_auto_index(self, on: bool) -> None:
        self._settings["auto_index"] = bool(on)
        self._write_settings()

    def _set_export_after_index(self, on: bool) -> None:
        self._settings["export_after_index"] = bool(on)
        self.cfg.raw.setdefault("spreadsheet", {})["export_after_index"] = bool(on)
        self._write_settings()

    def _export_workbook_silent(self) -> Path | None:
        if not self._metadata_enabled():
            return None
        from file_categorizer.core.spreadsheet import export_workbook

        path = self.workbook_edit.text().strip() or self._default_workbook()
        try:
            return export_workbook(self._metadata_db(), path)
        except Exception as exc:
            self._set_status(f"Indexed, but workbook export failed: {exc}")
            return None

    def _toggle_meta_details(self) -> None:
        expanded = self.meta_expand.isChecked()
        self.meta_content.setVisible(expanded)
        self.meta_expand.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        if hasattr(self, "_settings"):
            self._settings["show_metadata_details"] = bool(expanded)
            self._show_meta_details = bool(expanded)
            self._write_settings()

    def _toggle_teaching_notes(self, visible: bool | None = None) -> None:
        if hasattr(self, "notes_box"):
            if visible is None:
                visible = not self.notes_box.isVisible()
            self.notes_box.setVisible(bool(visible))
        if hasattr(self, "_settings"):
            self._settings["show_teaching_notes"] = bool(visible)
            self._show_teaching_notes = bool(visible)
            self._write_settings()

    def _toggle_review_panel(self, on: bool) -> None:
        if hasattr(self, "_review_scroll"):
            self._review_scroll.setVisible(on)
        self._settings["show_review_panel"] = bool(on)
        self._write_settings()
        if hasattr(self, "_report_splitter"):
            if on:
                sizes = self._report_splitter.sizes()
                if len(sizes) == 2 and sizes[1] == 0:
                    self._report_splitter.setSizes([640, 420])
            else:
                self._report_splitter.setSizes([1, 0])

    def _current_review_result(self) -> dict | None:
        if not self.review_results:
            return None
        return self.review_results[self.review_index]

    def _review_file_hash(self, result: dict) -> str:
        return result.get("file_hash") or self._hash(Path(result.get("path", "")))

    def _fill_meta_table(self, result: dict) -> None:
        fields = result.get("metadata_fields") or []
        self._meta_originals = list(fields)
        self.meta_table.setRowCount(0)
        for f in fields:
            row = self.meta_table.rowCount()
            self.meta_table.insertRow(row)
            name_item = QTableWidgetItem(str(f.get("field_name", "")))
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.meta_table.setItem(row, 0, name_item)
            self.meta_table.setItem(row, 1, QTableWidgetItem(str(f.get("field_value", ""))))
            src_item = QTableWidgetItem(str(f.get("source", "")))
            src_item.setFlags(src_item.flags() & ~Qt.ItemIsEditable)
            self.meta_table.setItem(row, 2, src_item)
            conf = f.get("confidence")
            conf_item = QTableWidgetItem(
                f"{conf:.0%}" if isinstance(conf, (int, float)) else ""
            )
            conf_item.setFlags(conf_item.flags() & ~Qt.ItemIsEditable)
            self.meta_table.setItem(row, 3, conf_item)
            ev_item = QTableWidgetItem(str(f.get("evidence", "")))
            ev_item.setFlags(ev_item.flags() & ~Qt.ItemIsEditable)
            self.meta_table.setItem(row, 4, ev_item)

        corrs = {f.get("correlation") for f in fields if f.get("correlation")}
        dup = result.get("metadata_duplicate") or {}
        sug = result.get("metadata_pattern_suggestion") or {}
        learned = result.get("metadata_learned") or []
        parts = []
        if corrs:
            parts.append("correlation: " + ", ".join(sorted(corrs)))
        if learned:
            parts.append("learned: " + ", ".join(sorted(learned)))
        if sug.get("category"):
            parts.append(
                f"memory suggests '{sug['category']}' (weight {sug['weight']:.1f})"
            )
        if dup.get("is_duplicate"):
            parts.append(
                f"duplicate ({dup.get('reason')}) of "
                f"{str(dup.get('duplicate_of'))[:12]}"
            )
        self.corr_label.setText("   |   ".join(parts))

    def _store_file_note(self, file_hash: str, note: str, result: dict | None = None) -> None:
        """Persist a teaching note to the classic notes table and the meta layer."""
        self.db.set_note(file_hash, note)
        mdb = self._metadata_db()
        row = mdb.get_file(file_hash)
        path = (result or {}).get("path") or (row["file_path"] if row else "")
        if row is None:
            mdb.upsert_file(MetaFile(
                file_hash=file_hash, file_path=path, category=result.get("tag") if result else None,
                notes=note or None,
            ))
        else:
            mdb.upsert_file(MetaFile(
                file_hash=file_hash, file_path=row["file_path"],
                original_path=row["original_path"], category=row["category"],
                subcategory=row["subcategory"], platform=row["platform"],
                moved_to=row["moved_to"], thumbnail_path=row["thumbnail_path"],
                needs_review=bool(row["needs_review"]), notes=note or row["notes"],
            ))
        if note:
            mdb.put_field(MetaField(
                file_hash=file_hash, field_name="notes", field_value=note,
                source="manual", confidence=1.0, evidence="user teaching note",
            ))

    def save_teach_notes(self) -> None:
        """Save the notes box for the current image and teach from its keywords."""
        result = self._current_review_result()
        if result is None:
            return
        file_hash = self._review_file_hash(result)
        note = self.teach_notes.toPlainText().strip()
        self._store_file_note(file_hash, note, result)

        existing = {f.get("field_name"): f for f in result.get("metadata_fields") or []}
        if note:
            existing["notes"] = {
                "field_name": "notes", "field_value": note,
                "source": "manual", "confidence": 1.0,
                "evidence": "user teaching note",
            }
        result["metadata_fields"] = list(existing.values())
        self._fill_meta_table(result)

        category = (self.actual_combo.currentText().strip()
                    or result.get("tag")
                    or ("NSFW" if result.get("status") == "nsfw" else ""))
        taught = remember_note_keywords(self.db, note, category) if note else 0
        self._set_status(
            f"Notes saved ({taught} keyword(s) learned)."
            if taught else "Notes saved."
        )

    def approve_metadata(self) -> None:
        result = self._current_review_result()
        if result is None:
            return
        file_hash = self._review_file_hash(result)
        mdb = self._metadata_db()
        entities = result.get("metadata_entities") or []
        edited = 0
        by_name: dict[str, str] = {}
        for row in range(self.meta_table.rowCount()):
            name = self.meta_table.item(row, 0).text()
            value = self.meta_table.item(row, 1).text()
            by_name[name] = value
            orig = self._meta_originals[row] if row < len(self._meta_originals) else {}
            wrong = orig.get("field_value", "")
            if value != wrong:
                mdb.add_field_correction(
                    name, value, wrong_value=wrong, file_hash=file_hash
                )
                # Generalise: the same field fix applies to future files that
                # share an entity, not just this exact file hash.
                for e in entities:
                    etype, evalue = e.get("entity_type"), e.get("entity_value")
                    if etype and evalue:
                        mdb.add_field_correction(
                            name, value, wrong_value=wrong,
                            entity_type=etype, entity_value=evalue,
                        )
                mdb.put_field(MetaField(
                    file_hash=file_hash, field_name=name, field_value=value,
                    source="manual", confidence=1.0, evidence="edited in review",
                ))
                edited += 1
        for f in result.get("metadata_fields") or []:
            if f.get("field_name") in by_name:
                f["field_value"] = by_name[f["field_name"]]

        # Confirming is also a teaching moment: save the note and remember
        # this file's entities for next time.
        category = result.get("tag") or (
            "NSFW" if result.get("status") == "nsfw" else ""
        )
        note = self.teach_notes.toPlainText().strip()
        if note:
            self._store_file_note(file_hash, note, result)
            remember_note_keywords(self.db, note, category)
        remembered = remember_entities_as_patterns(self.db, entities, category)
        extra = f" {remembered} entity memory." if remembered else ""
        self._set_status(
            (f"Approved. {edited} field edit(s) saved." if edited
             else "Approved. No changes to save.") + extra
        )

    def run_metadata_search(self) -> None:
        result = self._current_review_result()
        if result is None:
            return
        entities = result.get("metadata_entities") or []
        if not entities:
            self._set_status("No entities to search.")
            return
        from file_categorizer.core.enrichment import enrich_entity

        mdb = self._metadata_db()
        added = 0
        for e in entities:
            data = enrich_entity(
                e.get("entity_type"), e.get("entity_value"), self.cfg, mdb
            )
            if not data:
                continue
            for key, value in data.items():
                if value in (None, ""):
                    continue
                result.setdefault("metadata_fields", []).append({
                    "field_name": key, "field_value": str(value),
                    "source": "search", "confidence": 0.6,
                    "evidence": f"enrichment:{e.get('entity_type')}",
                })
                added += 1
        self._fill_meta_table(result)
        self._set_status(
            f"Search added {added} value(s)." if added else "Search found nothing new."
        )

    def open_metadata_url(self) -> None:
        url = None
        rows = sorted({i.row() for i in self.meta_table.selectedIndexes()})
        for row in (rows or range(self.meta_table.rowCount())):
            name = self.meta_table.item(row, 0).text().lower()
            value = self.meta_table.item(row, 1).text().strip()
            if value.startswith(("http://", "https://")):
                url = value
                break
            if name in ("url", "website", "entity_url") and value:
                url = value
                break
        if not url:
            self._set_status("No URL found in the metadata rows.")
            return
        self._open_external(url)

    def export_current_row(self) -> None:
        from file_categorizer.core.spreadsheet import export_workbook

        path = self.workbook_edit.text().strip() or self._default_workbook()
        try:
            out = export_workbook(self._metadata_db(), path)
        except Exception as exc:
            QMessageBox.warning(self, "Export failed", str(exc))
            return
        self._set_status(f"Exported to {out}")
        self._refresh_spreadsheet_preview()

    def mark_already_recorded(self) -> None:
        result = self._current_review_result()
        if result is None:
            return
        file_hash = self._review_file_hash(result)
        mdb = self._metadata_db()
        row = mdb.get_file(file_hash)
        marker = "marked as already recorded"
        if row is None:
            mdb.upsert_file(MetaFile(
                file_hash=file_hash, file_path=result.get("path", ""),
                category=result.get("tag"), needs_review=False, notes=marker,
            ))
        else:
            notes = f"{row['notes']}; {marker}" if row["notes"] else marker
            mdb.upsert_file(MetaFile(
                file_hash=file_hash, file_path=row["file_path"],
                original_path=row["original_path"], category=row["category"],
                subcategory=row["subcategory"], platform=row["platform"],
                moved_to=row["moved_to"], thumbnail_path=row["thumbnail_path"],
                needs_review=False, notes=notes,
            ))
        self._set_status("Marked as already recorded.")

    def browse_workbook(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Choose workbook", self.workbook_edit.text(),
            "Excel workbook (*.xlsx)",
        )
        if path:
            self.workbook_edit.setText(path)

    def export_spreadsheet(self) -> None:
        from file_categorizer.core.spreadsheet import export_workbook

        path = self.workbook_edit.text().strip() or self._default_workbook()
        try:
            out = export_workbook(self._metadata_db(), path)
        except Exception as exc:
            QMessageBox.warning(self, "Export failed", str(exc))
            return
        self._set_status(f"Exported workbook to {out}")
        self._refresh_spreadsheet_preview()

    def _refresh_spreadsheet_preview(self) -> None:
        mdb = self._metadata_db()
        files = mdb.all_files()
        lines = [
            f"Stored files:   {len(files)}",
            f"Known locations: {mdb.count_rows('meta_file_locations')}",
            f"Entities:       {len(mdb.all_entities())}",
            f"Extracted fields: {mdb.count_rows('meta_extracted_fields')}",
            f"Entity links:   {mdb.count_rows('meta_file_entities')}",
            f"Past exports:   {mdb.count_rows('meta_exports')}",
            "",
            "Most recent files:",
        ]
        for r in files[:15]:
            lines.append(
                f"  {str(r['file_hash'])[:12]}  {r['category'] or '?':<14}  "
                f"{Path(r['file_path']).name}"
            )
        if not files:
            lines.append("  (none yet)")
        self.spreadsheet_preview.setPlainText("\n".join(lines))

    def _open_external(self, target: str) -> None:
        try:
            if sys.platform == "win32":
                os.startfile(target)
            elif sys.platform == "darwin":
                import subprocess
                subprocess.run(["open", target], check=False)
            else:
                import subprocess
                subprocess.run(["xdg-open", target], check=False)
        except Exception as exc:
            QMessageBox.warning(self, "Cannot open", str(exc))

    def _set_review_results(self, results: list[dict]) -> None:
        self.review_results = [
            r for r in results if r.get("status") in ("classified", "nsfw")
        ]
        self.review_index = 0
        self._load_review()

    def _load_review(self) -> None:
        total = len(self.review_results)
        if total == 0:
            self.preview.setPixmap(QPixmap())
            self.preview.setText("No classified image yet")
            self.review_name.setText("-")
            self.review_classified.setText("-")
            self._fill_meta_table({})
            self.teach_notes.setPlainText("")
            self.review_counter.setText("0 / 0")
            self.learn_btn.setEnabled(False)
            self.prev_btn.setEnabled(False)
            self.next_btn.setEnabled(False)
            return

        self.review_index = max(0, min(self.review_index, total - 1))
        result = self.review_results[self.review_index]
        path = self._result_path(result)

        pixmap = QPixmap(str(path)) if path is not None else QPixmap()
        if pixmap.isNull():
            self.preview.setPixmap(QPixmap())
            if path is not None and path.suffix.lower() in VIDEO_EXTS:
                self.preview.setText("(video - no preview)")
            else:
                self.preview.setText("No preview available")
        else:
            self.preview.setPixmap(
                pixmap.scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )

        self.review_name.setText(Path(result.get("path", "")).name)
        is_nsfw = bool(result.get("nsfw")) or result.get("status") == "nsfw"
        display_tag = result.get("tag") or ("NSFW" if is_nsfw else "?")
        marker = " (explicit/NSFW)" if is_nsfw else ""
        self.review_classified.setText(
            f"Classified as: {display_tag}{marker} "
            f"({result.get('confidence', 0.0):.0%}) via {result.get('model', '') or 'nsfw'}"
        )
        self.actual_combo.setCurrentText(result.get("tag") or display_tag)
        self.teach_notes.setPlainText(self.db.get_note(self._review_file_hash(result)))
        self._fill_meta_table(result)
        self.review_counter.setText(f"{self.review_index + 1} / {total}")
        self.learn_btn.setEnabled(True)
        self.prev_btn.setEnabled(self.review_index > 0)
        self.next_btn.setEnabled(self.review_index < total - 1)
        self._set_status(f"Reviewing {self.review_index + 1} of {total}")

    def previous_image(self) -> None:
        if self.review_index > 0:
            self.review_index -= 1
            self._load_review()

    def next_image(self) -> None:
        if self.review_index < len(self.review_results) - 1:
            self.review_index += 1
            self._load_review()

    def save_correction(self) -> None:
        if not self.review_results:
            return
        result = self.review_results[self.review_index]
        actual = self.actual_combo.currentText().strip()
        if not actual:
            QMessageBox.information(self, "Missing value", "Type or pick the correct category.")
            return

        guessed = result.get("tag", "")
        self.db.add_correction(self._hash(Path(result["path"])), guessed, actual)

        # Persist the teaching note and learn from its keywords.
        note = self.teach_notes.toPlainText().strip()
        if note:
            self._store_file_note(self._review_file_hash(result), note, result)
        taught = remember_note_keywords(self.db, note, actual) if note else 0

        # Phase 6: remember this file's entities -> category for next time.
        remembered = remember_entities_as_patterns(
            self.db, result.get("metadata_entities") or [], actual
        )

        if not self.categories.has(actual):
            self.categories.add(actual)
            self._sync_categories()
            self._refresh_categories()

        if not self.dry_run.isChecked():
            path = self._result_path(result)
            if path is not None:
                if result.get("nsfw") or result.get("status") == "nsfw":
                    nsfw_name = Path(self.cfg.paths.get("nsfw", "NSFW")).name or "NSFW"
                    destination_dir = (
                        self.output_root / nsfw_name / safe_category_name(actual)
                    )
                else:
                    destination_dir = self.output_root / safe_category_name(actual)
                destination_dir.mkdir(parents=True, exist_ok=True)
                destination = unique_destination(destination_dir / path.name)
                if destination.resolve() != path.resolve():
                    try:
                        shutil.move(str(path), destination)
                        self._metadata_db().move_location(
                            str(path), str(destination)
                        )
                        result["moved_to"] = str(destination)
                    except OSError as exc:
                        self._set_status(f"Could not move file: {exc}")

        result["tag"] = actual
        result["model"] = "correction"
        result["confidence"] = 1.0

        self.report = self._build_report(self.last_results)
        self.report_edit.setPlainText(self.report.build())
        self.review_index = self.review_results.index(result)
        self._load_review()
        extra = f" ({remembered} entity memory)" if remembered else ""
        if taught:
            extra += f" ({taught} note keyword(s))"
        self._set_status(
            f"Learned: '{guessed}' -> '{actual}' for {Path(result['path']).name}{extra}"
        )

    def _preview_clicked(self, event) -> None:
        if not self.review_results:
            return
        result = self.review_results[self.review_index]
        path = self._result_path(result)
        if path is None:
            return
        try:
            import os
            import subprocess
            import sys

            if sys.platform == "win32":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.run(["open", str(path)], check=False)
            else:
                subprocess.run(["xdg-open", str(path)], check=False)
        except Exception as exc:
            QMessageBox.warning(self, "Cannot open image", str(exc))

    def _suggest_new_category(self) -> None:
        if not self.review_results:
            return
        result = self.review_results[self.review_index]
        name = Path(result.get("path", "")).name
        suggested = name.split('.')[0].replace('_', ' ').replace('-', ' ').title()
        suggested = ' '.join(suggested.split())
        if suggested and suggested not in self.actual_combo.items() if hasattr(self.actual_combo, 'items') else True:
            self.actual_combo.setCurrentText(suggested)

    def _add_new_category_from_review(self) -> None:
        current = self.actual_combo.currentText().strip()
        if not current:
            QMessageBox.information(self, "Missing name", "Enter a category name first.")
            return
        if self.categories.has(current):
            QMessageBox.information(self, "Exists", f"Category '{current}' already exists.")
            return
        try:
            clean = self.categories.add(current, [])
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid category", str(exc))
            return
        self._sync_categories()
        self._refresh_categories()
        self.actual_combo.setCurrentText(clean)
        self._set_status(f"Category '{clean}' added.")

    # ---- lifecycle ---------------------------------------------------
    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(3000)
        self._save_geometry()
        self._write_settings()
        self.db.close()
        super().closeEvent(event)


def run(config_path: str = "config/config.yaml"):
    app = QApplication(sys.argv)
    window = MainWindow(config_path)
    window.show()
    sys.exit(app.exec())
