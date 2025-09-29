# ui/review_viewer.py
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

# Prefer native PDF viewer
_pdf_ok = True
try:
    from PySide6.QtPdf import QPdfDocument
    from PySide6.QtPdfWidgets import QPdfView
except Exception:
    _pdf_ok = False
    from PySide6.QtWebEngineWidgets import QWebEngineView  # type: ignore


@dataclass
class ReviewItem:
    file: str
    lines: str  # e.g. "main.tex:10-11"
    message: str


@dataclass
class ReviewData:
    title: str                         # e.g. "LaTeX Review — paper-1"
    status: str                        # e.g. "Returned", "Approved", "Pending"
    pdf_path: Optional[str] = None     # absolute or file://
    diff_pdf_path: Optional[str] = None
    general_notes: Optional[str] = ""  # plain text or markdown-ish
    comments: Optional[List[str]] = None
    items: Optional[List[ReviewItem]] = None
    build_log: Optional[str] = ""
    sources: Optional[List[Tuple[str, str]]] = None  # (label, filepath)


def _status_color(status: str) -> str:
    s = status.strip().lower()
    if s.startswith("return"): return "#b45309"   # amber-700
    if s.startswith("approve"): return "#166534"  # green-700
    if s.startswith("pend"): return "#1f2937"     # gray-800
    if s.startswith("fail") or s.startswith("error"): return "#991b1b"  # red-800
    return "#334155"  # slate-700


class ReviewDialog(QDialog):
    def __init__(self, review: ReviewData, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Review")
        self.setMinimumSize(1100, 740)
        self.review = review

        root = QVBoxLayout(self)
        # Header
        header = self._build_header()
        root.addWidget(header)

        # Splitter: left viewer, right tabs
        split = QSplitter(Qt.Horizontal, self)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(8)
        self.viewer = self._build_viewer()
        self.sidebar = self._build_sidebar()
        self.sidebar.setMinimumWidth(360)
        split.addWidget(self.viewer)
        split.addWidget(self.sidebar)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(8)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)

        # đặt tỉ lệ ban đầu 70/30 sau khi dialog show
        self._split = split
        QTimer.singleShot(0, lambda: self._split.setSizes([int(self.width()*0.6),
                                                        int(self.width()*0.4)]))
        root.addWidget(split)

        self._apply_styles()
        self._load_data()

    # ---------- UI pieces ----------
    def _build_header(self) -> QWidget:
        w = QWidget(self)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(12, 10, 12, 10)  # gọn hơn
        w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        w.setMaximumHeight(64)  # ← hạn chế chiều cao header

        title = QLabel(self.review.title)
        title.setObjectName("titleLabel")

        status = QLabel(self.review.status)
        status.setObjectName("statusBadge")
        status.setAlignment(Qt.AlignCenter)
        status.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        status.setFixedHeight(32)          # ← badge không còn cao
        status.setMinimumWidth(100)        # ← để chữ không bị dọc
        status.setStyleSheet(f"background:{_status_color(self.review.status)};")

        btnOpen = QPushButton("Open PDF")
        btnOpen.clicked.connect(self._open_pdf_external)
        btnDiff = QPushButton("Open Diff")
        btnDiff.setEnabled(bool(self.review.diff_pdf_path))
        btnDiff.clicked.connect(self._open_diff_external)

        lay.addWidget(title, 1)
        lay.addWidget(status, 0, Qt.AlignRight)
        lay.addSpacing(8)
        lay.addWidget(btnOpen, 0)
        lay.addWidget(btnDiff, 0)
        return w

    def _build_viewer(self) -> QWidget:
        container = QWidget(self)
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)

        # Toolbar
        tb = QToolBar()
        tb.setIconSize(tb.iconSize())  # default
        v.addWidget(tb)

        # Controls
        self.pageSpin = QSpinBox(); self.pageSpin.setMinimum(1); self.pageSpin.setMaximum(1)
        self.zoomSlider = QSlider(Qt.Horizontal); self.zoomSlider.setRange(25, 300); self.zoomSlider.setValue(110)
        self.searchBox = QLineEdit(); self.searchBox.setPlaceholderText("Find in document… (Enter)")

        actPrev = QAction("Prev", self); actPrev.setShortcut(QKeySequence(Qt.Key_K))
        actNext = QAction("Next", self); actNext.setShortcut(QKeySequence(Qt.Key_J))
        actZoomIn = QAction("Zoom +", self); actZoomIn.setShortcut(QKeySequence.ZoomIn)
        actZoomOut = QAction("Zoom –", self); actZoomOut.setShortcut(QKeySequence.ZoomOut)
        actFitWidth = QAction("Fit width", self); actFitWidth.setShortcut("W")
        actFitPage = QAction("Fit page", self); actFitPage.setShortcut("P")
        actRefresh = QAction("Refresh", self); actRefresh.setShortcut(QKeySequence.Refresh)

        for a in [actPrev, actNext, actZoomOut, actZoomIn, actFitWidth, actFitPage, actRefresh]:
            tb.addAction(a)
        tb.addSeparator()
        tb.addWidget(QLabel(" Page "))
        tb.addWidget(self.pageSpin)
        tb.addSeparator()
        tb.addWidget(QLabel(" Zoom "))
        tb.addWidget(self.zoomSlider)
        tb.addSeparator()
        tb.addWidget(self.searchBox)

        if _pdf_ok:
            self.doc = QPdfDocument(self)
            self.pdf = QPdfView(self)
            self.pdf.setPageMode(QPdfView.PageMode.SinglePage)
            self.pdf.setZoomMode(QPdfView.ZoomMode.Custom)
            v.addWidget(self.pdf, 1)

            # Wire actions
            actPrev.triggered.connect(self._prev_page)
            actNext.triggered.connect(self._next_page)
            actZoomIn.triggered.connect(lambda: self._bump_zoom(+10))
            actZoomOut.triggered.connect(lambda: self._bump_zoom(-10))
            actFitWidth.triggered.connect(lambda: self._set_zoom_mode("width"))
            actFitPage.triggered.connect(lambda: self._set_zoom_mode("page"))
            actRefresh.triggered.connect(self._reload_pdf)

            self.pageSpin.valueChanged.connect(self._goto_page)
            self.zoomSlider.valueChanged.connect(self._set_zoom)
            self.searchBox.returnPressed.connect(self._search_pdf)
        else:
            self.web = QWebEngineView(self)
            v.addWidget(self.web, 1)

            actPrev.setEnabled(False); actNext.setEnabled(False)
            actFitPage.setEnabled(False); actFitWidth.setEnabled(False)
            self.pageSpin.setEnabled(False); self.zoomSlider.setEnabled(False)
            self.searchBox.returnPressed.connect(self._search_html)
            actZoomIn.triggered.connect(lambda: self._bump_web_zoom(+0.1))
            actZoomOut.triggered.connect(lambda: self._bump_web_zoom(-0.1))
            actRefresh.triggered.connect(self._reload_web)

        return container

    def _build_sidebar(self) -> QWidget:
        side = QWidget(self)
        v = QVBoxLayout(side); v.setContentsMargins(8, 0, 0, 0)
        tabs = QTabWidget()
        self.tabs = tabs

        # Overview
        self.overview = QTextEdit(); self.overview.setReadOnly(True)
        tabs.addTab(self.overview, "Overview")

        # Comments
        self.comments = QListWidget()
        tabs.addTab(self.comments, "Comments")

        # Itemised
        self.items = QTreeWidget(); self.items.setHeaderLabels(["File:Line(s)", "Message"])
        tabs.addTab(self.items, "Itemised")

        # Build log
        self.buildLog = QTextEdit(); self.buildLog.setReadOnly(True); self.buildLog.setLineWrapMode(QTextEdit.NoWrap)
        tabs.addTab(self.buildLog, "Build log")

        # Sources
        self.srcTree = QTreeWidget(); self.srcTree.setHeaderLabels(["Source", "Path"])
        tabs.addTab(self.srcTree, "Source files")

        v.addWidget(tabs, 1)
        return side

    # ---------- data & behaviors ----------
    def _load_data(self):
        # PDF
        if self.review.pdf_path:
            if _pdf_ok:
                self.doc.load(self._as_url(self.review.pdf_path).toLocalFile())
                self.pdf.setDocument(self.doc)
                self.pageSpin.setMaximum(max(1, self.doc.pageCount()))
                self.pageSpin.setValue(1)
                self._set_zoom(self.zoomSlider.value())
            else:
                self.web.load(self._as_url(self.review.pdf_path))
        else:
            QMessageBox.information(self, "No PDF", "This review has no PDF attached.")

        # Overview
        status_mark = f'<span style="background:{_status_color(self.review.status)};color:#fff;border-radius:6px;padding:2px 6px">{self.review.status}</span>'
        notes = (self.review.general_notes or "").replace("\n", "<br>")
        self.overview.setHtml(f"<h3 style='margin-top:0'>{self.review.title}</h3>{status_mark}<hr>{notes}")

        # Comments
        self.comments.clear()
        for c in (self.review.comments or []):
            QListWidgetItem(c, self.comments)

        # Items
        self.items.clear()
        for it in (self.review.items or []):
            row = QTreeWidgetItem([f"{it.file}:{it.lines}", it.message])
            self.items.addTopLevelItem(row)

        # Build log
        self.buildLog.setPlainText(self.review.build_log or "")

        # Sources
        self.srcTree.clear()
        for label, path in (self.review.sources or []):
            self.srcTree.addTopLevelItem(QTreeWidgetItem([label, path]))

    # ---------- helpers ----------
    def _as_url(self, path: str) -> QUrl:
        return QUrl(path) if path.startswith("http") or path.startswith("file:") else QUrl.fromLocalFile(os.path.abspath(path))

    def _open_pdf_external(self):
        if self.review.pdf_path:
            QDesktopServices.openUrl(self._as_url(self.review.pdf_path))

    def _open_diff_external(self):
        if self.review.diff_pdf_path:
            QDesktopServices.openUrl(self._as_url(self.review.diff_pdf_path))

    # PDF controls (QtPdf)
    def _bump_zoom(self, delta: int):
        self.zoomSlider.setValue(max(self.zoomSlider.minimum(), min(self.zoomSlider.maximum(), self.zoomSlider.value() + delta)))

    def _set_zoom(self, val: int):
        if _pdf_ok:
            self.pdf.setZoomMode(QPdfView.ZoomMode.Custom)
            self.pdf.setZoomFactor(val / 100.0)

    def _set_zoom_mode(self, mode: str):
        if not _pdf_ok: return
        if mode == "width":
            self.pdf.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        else:
            self.pdf.setZoomMode(QPdfView.ZoomMode.FitInView)

    def _goto_page(self, p: int):
        if _pdf_ok and self.doc:
            self.pdf.setPage(p - 1)

    def _prev_page(self):
        self.pageSpin.setValue(max(1, self.pageSpin.value() - 1))

    def _next_page(self):
        self.pageSpin.setValue(min(self.pageSpin.maximum(), self.pageSpin.value() + 1))

    def _reload_pdf(self):
        if _pdf_ok and self.review.pdf_path:
            cur = self.pageSpin.value()
            self.doc.load(self._as_url(self.review.pdf_path).toLocalFile())
            self.pageSpin.setMaximum(max(1, self.doc.pageCount()))
            self.pageSpin.setValue(min(cur, self.pageSpin.maximum()))

    # Web fallback controls
    def _bump_web_zoom(self, delta: float):
        if not _pdf_ok:
            self.web.setZoomFactor(self.web.zoomFactor() + delta)

    def _reload_web(self):
        if not _pdf_ok and self.review.pdf_path:
            self.web.load(self._as_url(self.review.pdf_path))

    def _search_pdf(self):
        # QtPdf chưa có search built-in; tuỳ phiên bản bạn có thể bỏ trống/hook qua text layer.
        QMessageBox.information(self, "Search", "Search is limited in native PDF view.\nConsider opening in external viewer (Ctrl+O).")

    def _search_html(self):
        if not _pdf_ok:
            self.web.findText("")

    def _apply_styles(self):
        self.setStyleSheet("""
        QDialog { background: #f8fafc; }
        #titleLabel { font-size: 18px; font-weight: 600; color: #0f172a; margin-right: 8px; }
        #statusBadge {
            color: white; padding: 4px 12px; border-radius: 16px;
            font-weight: 600; margin-right: 8px;
        }
        QToolBar { background:#ffffff; border-bottom:1px solid #e5e7eb; padding:4px; }
        QTabWidget::pane { border:1px solid #e5e7eb; background:white; }
        QTabBar::tab { padding:8px 12px; }
        QListWidget, QTreeWidget, QTextEdit { background:white; border:1px solid #e5e7eb; }
        """)


# --- Helper to open dialog from your app ---
def open_review_dialog(parent, review: ReviewData):
    dlg = ReviewDialog(review, parent)
    dlg.exec()
