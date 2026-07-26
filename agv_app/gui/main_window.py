# -*- coding: utf-8 -*-
"""Cửa sổ chính của ứng dụng Phân tích AGV (PyQt5).

Tính năng:
  - Thêm nhiều thư mục log (nút, chọn thư mục cha tự động quét, kéo-thả).
  - Phân tích trong luồng riêng (QThread) -> giao diện không treo.
  - Tab Tổng quan (dashboard KPI + biểu đồ) để "nhìn phát là ra tất cả".
  - Kết quả theo tab: Tổng quan / Ngày / Điểm / Xe / Model / Tuần / Tháng / API.
  - Cài đặt chỉnh sửa được (ngưỡng, thang máy, điểm loại trừ theo nhóm, giờ ca,
    số giờ mẫu số, ngưỡng màu, thư mục mặc định) và lưu ra point_settings.json.
  - Xuất Excel (công thức sống + biểu đồ) / CSV (kèm đầu vào + chú thích công thức).

Khuyến nghị Python 3.10 (tương thích 3.8–3.10) + PyQt5.
"""

from __future__ import annotations

import traceback
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from PyQt5.QtCore import QDate, Qt, QThread, QTime, pyqtSignal
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QAbstractItemView, QCheckBox, QDateEdit, QDoubleSpinBox, QFileDialog,
    QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QScrollArea, QSpinBox, QSplitter, QTableWidget,
    QTableWidgetItem, QTabWidget, QTimeEdit, QVBoxLayout, QWidget,
)

from ..core.abnormal import DayResult, detect_base_date
from ..core.config import Settings, app_dir, load_settings, save_settings
from ..core import aggregate, export
from ..core.ingest import DataInventory, DataKind, KIND_LABEL_VI
from ..core.pipeline import AnalyzeOutcome, CancelToken, default_workers, run_analyze
from ..core.task_api_log import DayApiLogStats
from ..core.tasks import (
    DayTaskStats,
    count_task_csv_files,
    find_log_day_folders,
    find_log_folders_for_dates,
    is_log_txt_file,
    is_task_csv_file,
    looks_like_task_log_dir,
    missing_dates_in_range,
    resolve_task_root_from_paths,
)
from .charts import BarChartWidget, KpiCard, TrendChartWidget

APP_TITLE = "Phân tích chất lượng AGV"
DETAIL_ROW_LIMIT = 500

COLOR_OK = QColor(198, 239, 206)      # xanh nhạt
COLOR_WARN = QColor(255, 235, 156)    # vàng nhạt
COLOR_BAD = QColor(255, 199, 206)     # đỏ nhạt
COLOR_SAT = QColor(221, 235, 247)     # xanh dương nhạt (Thứ Bảy)

# Màu đậm cho biểu đồ
BAR_OK = QColor(80, 170, 110)
BAR_WARN = QColor(240, 180, 60)
BAR_BAD = QColor(220, 80, 80)
BAR_ACCENT = QColor(58, 118, 216)
BAR_ACCENT2 = QColor(140, 100, 200)


def _item(text, center=True, color: Optional[QColor] = None, bold=False) -> QTableWidgetItem:
    it = QTableWidgetItem("" if text is None else str(text))
    if center:
        it.setTextAlignment(Qt.AlignCenter)
    if color is not None:
        it.setBackground(color)
    if bold:
        f = it.font()
        f.setBold(True)
        it.setFont(f)
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    return it


def make_table(headers: List[str], stretch_last=True) -> QTableWidget:
    t = QTableWidget()
    t.setColumnCount(len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.setAlternatingRowColors(True)
    t.verticalHeader().setVisible(False)
    hh = t.horizontalHeader()
    hh.setSectionResizeMode(QHeaderView.ResizeToContents)
    if stretch_last:
        hh.setStretchLastSection(True)
    t.setSortingEnabled(False)
    return t


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    f = QFont()
    f.setPointSize(11)
    f.setBold(True)
    lbl.setFont(f)
    lbl.setStyleSheet("color:#1F4E79; margin-top:6px;")
    return lbl


# --- Worker phân tích ---------------------------------------------------------

class AnalyzeWorker(QThread):
    progress = pyqtSignal(int, int, str)     # done, total, message
    finished_ok = pyqtSignal(object)         # AnalyzeOutcome
    failed = pyqtSignal(str)

    def __init__(self, inventory: DataInventory, settings: Settings,
                 cancel: CancelToken, workers: Optional[int] = None):
        super().__init__()
        self._inventory = inventory
        self._settings = settings
        self._cancel = cancel
        self._workers = workers if workers is not None else default_workers()

    def run(self):
        try:
            def on_progress(done: int, total: int, message: str) -> None:
                self.progress.emit(done, total, message)

            outcome = run_analyze(
                settings=self._settings,
                inventory=self._inventory,
                workers=self._workers,
                cancel=self._cancel,
                progress=on_progress,
            )
            self.finished_ok.emit(outcome)
        except Exception:  # noqa: BLE001
            self.failed.emit(traceback.format_exc())


# --- Cửa sổ chính -------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1280, 820)
        self.setAcceptDrops(True)

        self._settings: Settings = load_settings()
        self._day_results: List[DayResult] = []
        self._inventory = DataInventory()
        self._worker: Optional[AnalyzeWorker] = None
        self._cancel: Optional[CancelToken] = None
        self._analyze_cancelled = False
        self._populated_tabs: set = set()
        self._rate_ok = self._settings.rate_ok
        self._rate_warn = self._settings.rate_warn
        self._point_stats_by_id: Dict = {}
        self._car_stats_by_id: Dict = {}
        self._car_fleet_avg_per_100: Optional[float] = None
        self._model_stats_by_id: Dict = {}
        self._model_fleet_timeout_rate: Optional[float] = None
        self._model_fleet_avg_sec: Optional[float] = None
        self._model_task_list = []
        self._months = []
        self._weeks = []

        self._build_ui()
        self._apply_settings_to_ui(self._settings)
        # Tránh QLineEdit/bảng "nuốt" sự kiện kéo-thả file CSV / folder
        for w in self.findChildren(QLineEdit):
            w.setAcceptDrops(False)
        for w in self.findChildren(QPlainTextEdit):
            w.setAcceptDrops(False)
        for w in self.findChildren(QAbstractItemView):
            w.setAcceptDrops(False)
        self.statusBar().showMessage(
            "Sẵn sàng. Kéo-thả Log AGV / Tasks CSV / API logs vào cửa sổ để bắt đầu.")

    # -- Màu theo tỷ lệ (ngưỡng động) -----------------------------------------

    def rate_color(self, rate: float) -> QColor:
        if rate >= self._rate_warn:
            return COLOR_BAD
        if rate >= self._rate_ok:
            return COLOR_WARN
        return COLOR_OK

    def rate_qcolor(self, rate: float) -> QColor:
        if rate >= self._rate_warn:
            return BAR_BAD
        if rate >= self._rate_ok:
            return BAR_WARN
        return BAR_OK

    # -- Xây dựng giao diện ---------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter, 1)

        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([440, 840])

        self.progress = QProgressBar()
        self.progress.setValue(0)
        root.addWidget(self.progress)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(110)
        self.log.setPlaceholderText("Nhật ký hoạt động...")
        root.addWidget(self.log)

    def _build_left_panel(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)

        self.left_tabs = QTabWidget()
        self.left_tabs.addTab(self._build_data_tab(), "Dữ liệu")
        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setWidget(self._build_settings_group())
        self.left_tabs.addTab(settings_scroll, "Cài đặt")
        v.addWidget(self.left_tabs, 1)

        self.lbl_job = QLabel("")
        self.lbl_job.setWordWrap(True)
        self.lbl_job.setStyleSheet("color:#1F4E79; font-size:11px;")
        v.addWidget(self.lbl_job)

        self.lbl_banner = QLabel("")
        self.lbl_banner.setWordWrap(True)
        self.lbl_banner.setVisible(False)
        self.lbl_banner.setStyleSheet(
            "background:#FFF3CD; color:#856404; padding:6px; border-radius:4px;")
        v.addWidget(self.lbl_banner)

        row_an = QHBoxLayout()
        self.b_analyze = QPushButton("PHÂN TÍCH")
        self.b_analyze.setMinimumHeight(40)
        self.b_analyze.setStyleSheet(
            "QPushButton{background:#2d7d46;color:white;font-weight:bold;border-radius:6px;font-size:14px;}"
            "QPushButton:hover{background:#35924f;}"
            "QPushButton:disabled{background:#9bbfa6;}")
        self.b_analyze.clicked.connect(self.on_analyze)
        self.b_cancel = QPushButton("Hủy")
        self.b_cancel.setMinimumHeight(40)
        self.b_cancel.setEnabled(False)
        self.b_cancel.setToolTip("Dừng phân tích; giữ kết quả các ngày đã xong")
        self.b_cancel.setStyleSheet(
            "QPushButton{background:#c0504d;color:white;font-weight:bold;border-radius:6px;}"
            "QPushButton:hover{background:#d0605d;}"
            "QPushButton:disabled{background:#c9a0a0;}")
        self.b_cancel.clicked.connect(self.on_cancel_analyze)
        row_an.addWidget(self.b_analyze, 3)
        row_an.addWidget(self.b_cancel, 1)
        v.addLayout(row_an)

        exp = QHBoxLayout()
        self.b_xlsx = QPushButton("Xuất Excel")
        self.b_xlsx.setToolTip("Xuất báo cáo Excel nhiều sheet, có công thức sống + biểu đồ")
        self.b_xlsx.clicked.connect(self.on_export_excel)
        self.b_xlsx.setEnabled(False)
        self.b_csv = QPushButton("Xuất CSV")
        self.b_csv.setToolTip("Xuất CSV kèm cột đầu vào và chú thích công thức")
        self.b_csv.clicked.connect(self.on_export_csv)
        self.b_csv.setEnabled(False)
        exp.addWidget(self.b_xlsx)
        exp.addWidget(self.b_csv)
        v.addLayout(exp)

        return w

    def _build_data_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 4, 4, 4)

        v.addWidget(_section_label("Nguồn dữ liệu (3 loại)"))

        self.lbl_inventory_badge = QLabel("Đã nhận 0 CSV / 0 API log / 0 ngày AGV")
        self.lbl_inventory_badge.setStyleSheet(
            "background:#eef5ff;border:1px solid #b8d0f0;border-radius:4px;"
            "padding:6px;color:#1F4E79;font-weight:bold;")
        v.addWidget(self.lbl_inventory_badge)

        self.folder_table = make_table(
            ["Loại", "Đường dẫn", "Ngày", "Ghi chú"], stretch_last=False)
        self.folder_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        # Alias cho code cũ tham chiếu inventory_table
        self.inventory_table = self.folder_table
        v.addWidget(self.folder_table, 1)

        btns = QHBoxLayout()
        b_add = QPushButton("Thêm…")
        b_add.setToolTip("Chọn file/folder bất kỳ — app tự phân loại A/B/C")
        b_add.clicked.connect(self.on_add_any)
        b_parent = QPushButton("Thêm thư mục cha")
        b_parent.setToolTip("Quét đệ quy: Log ngày + CSV + API logs")
        b_parent.clicked.connect(self.on_add_parent)
        btns.addWidget(b_add)
        btns.addWidget(b_parent)
        v.addLayout(btns)

        btns2 = QHBoxLayout()
        b_del = QPushButton("Xóa mục chọn")
        b_del.clicked.connect(self.on_remove_selected)
        b_clear = QPushButton("Xóa tất cả")
        b_clear.clicked.connect(self.on_clear_folders)
        b_rescan = QPushButton("Quét lại")
        b_rescan.setToolTip("Làm mới bảng từ inventory hiện tại")
        b_rescan.clicked.connect(self._refresh_inventory_table)
        btns2.addWidget(b_del)
        btns2.addWidget(b_clear)
        btns2.addWidget(b_rescan)
        v.addLayout(btns2)

        range_box = QGroupBox("Thêm Log AGV theo khoảng ngày")
        rf = QFormLayout(range_box)
        self.ed_range_parent = QLineEdit()
        self.ed_range_parent.setPlaceholderText("Thư mục cha chứa Log{YYYYMMDD}")
        b_rp = QPushButton("Chọn")
        b_rp.clicked.connect(self.on_pick_range_parent)
        row_rp = QHBoxLayout(); row_rp.setContentsMargins(0, 0, 0, 0)
        row_rp.addWidget(self.ed_range_parent); row_rp.addWidget(b_rp)
        wrp = QWidget(); wrp.setLayout(row_rp)
        rf.addRow("Thư mục gốc:", wrp)

        self.de_from = QDateEdit()
        self.de_from.setCalendarPopup(True)
        self.de_from.setDisplayFormat("yyyy-MM-dd")
        self.de_to = QDateEdit()
        self.de_to.setCalendarPopup(True)
        self.de_to.setDisplayFormat("yyyy-MM-dd")
        today = QDate.currentDate()
        self.de_from.setDate(today.addDays(-7))
        self.de_to.setDate(today)
        row_dt = QHBoxLayout(); row_dt.setContentsMargins(0, 0, 0, 0)
        row_dt.addWidget(self.de_from); row_dt.addWidget(QLabel("~")); row_dt.addWidget(self.de_to)
        wdt = QWidget(); wdt.setLayout(row_dt)
        rf.addRow("Từ ngày → Đến:", wdt)

        b_range = QPushButton("Quét & thêm theo khoảng")
        b_range.setToolTip("Chỉ thêm các thư mục Log có ngày nằm trong khoảng đã chọn")
        b_range.clicked.connect(self.on_add_date_range)
        rf.addRow(b_range)
        v.addWidget(range_box)

        # Tasks Log path vẫn giữ trên Cài đặt; badge CSV từ inventory
        self.ed_task_dir_data = QLineEdit()
        self.ed_task_dir_data.setVisible(False)
        self.lbl_task_status = QLabel("")
        self.lbl_task_status.setVisible(False)

        hint = QLabel(
            "Mẹo: kéo-thả một lần folder «Tasks Log 任务» (CSV + logs/*.log) "
            "và/hoặc Log20260711 — app tự phân loại 3 nguồn."
        )
        hint.setStyleSheet("color:#666; font-style:italic;")
        hint.setWordWrap(True)
        v.addWidget(hint)
        return w

    def _build_settings_group(self) -> QGroupBox:
        box = QGroupBox("Cài đặt phân tích")
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignRight)

        self.sp_threshold = QSpinBox()
        self.sp_threshold.setRange(1, 240)
        self.sp_threshold.setSuffix(" phút")
        self.sp_threshold.setToolTip("Dừng quá ngưỡng này (trừ khi đang sạc) mới tính bất thường")
        form.addRow("Ngưỡng bất thường:", self.sp_threshold)

        self.cb_elevator = QCheckBox("Áp dụng ngưỡng riêng cho thang máy")
        form.addRow(self.cb_elevator)

        self.sp_elevator = QSpinBox()
        self.sp_elevator.setRange(1, 240)
        self.sp_elevator.setSuffix(" phút")
        form.addRow("Ngưỡng thang máy:", self.sp_elevator)

        self.ed_elevator_pts = QLineEdit()
        self.ed_elevator_pts.setPlaceholderText("vd: 221, 1294, 223, 1767")
        form.addRow("Điểm thang máy:", self.ed_elevator_pts)

        self.te_excluded = QPlainTextEdit()
        self.te_excluded.setMaximumHeight(70)
        self.te_excluded.setPlaceholderText("Mỗi dòng: Tên nhóm: điểm1, điểm2\nvd: Home: 232, 1025, 259")
        self.te_excluded.setToolTip("Điểm liệt kê ở đây không tính bất thường dù dừng bao lâu")
        form.addRow("Điểm loại trừ:", self.te_excluded)

        self.te_day_start = QTimeEdit()
        self.te_day_start.setDisplayFormat("HH:mm")
        self.te_day_end = QTimeEdit()
        self.te_day_end.setDisplayFormat("HH:mm")
        row_day = QHBoxLayout()
        row_day.addWidget(self.te_day_start)
        row_day.addWidget(QLabel("~"))
        row_day.addWidget(self.te_day_end)
        wday = QWidget(); wday.setLayout(row_day)
        form.addRow("Ca ngày:", wday)

        self.te_night_start = QTimeEdit()
        self.te_night_start.setDisplayFormat("HH:mm")
        self.te_night_end = QTimeEdit()
        self.te_night_end.setDisplayFormat("HH:mm")
        row_night = QHBoxLayout()
        row_night.addWidget(self.te_night_start)
        row_night.addWidget(QLabel("~ (hôm sau)"))
        row_night.addWidget(self.te_night_end)
        wnight = QWidget(); wnight.setLayout(row_night)
        form.addRow("Ca đêm:", wnight)

        self.sp_denom = QDoubleSpinBox()
        self.sp_denom.setRange(1.0, 48.0)
        self.sp_denom.setDecimals(1)
        self.sp_denom.setSuffix(" giờ")
        self.sp_denom.setToolTip("Số giờ mẫu số khi tính tỷ lệ (mặc định 24, giống bản gốc)")
        form.addRow("Số giờ mẫu số:", self.sp_denom)

        self.sp_rate_ok = QDoubleSpinBox()
        self.sp_rate_ok.setRange(0.0, 100.0)
        self.sp_rate_ok.setDecimals(1)
        self.sp_rate_ok.setSuffix(" %")
        form.addRow("Ngưỡng màu Tốt (dưới):", self.sp_rate_ok)

        self.sp_rate_warn = QDoubleSpinBox()
        self.sp_rate_warn.setRange(0.0, 100.0)
        self.sp_rate_warn.setDecimals(1)
        self.sp_rate_warn.setSuffix(" %")
        form.addRow("Ngưỡng màu Cảnh báo:", self.sp_rate_warn)

        self.ed_log_dir = QLineEdit()
        b_log_dir = QPushButton("Chọn")
        b_log_dir.clicked.connect(self.on_pick_log_dir)
        row_log = QHBoxLayout(); row_log.setContentsMargins(0, 0, 0, 0)
        row_log.addWidget(self.ed_log_dir); row_log.addWidget(b_log_dir)
        wlog = QWidget(); wlog.setLayout(row_log)
        form.addRow("Thư mục log mặc định:", wlog)

        self.ed_out_dir = QLineEdit()
        b_out_dir = QPushButton("Chọn")
        b_out_dir.clicked.connect(self.on_pick_out_dir)
        row_out = QHBoxLayout(); row_out.setContentsMargins(0, 0, 0, 0)
        row_out.addWidget(self.ed_out_dir); row_out.addWidget(b_out_dir)
        wout = QWidget(); wout.setLayout(row_out)
        form.addRow("Thư mục xuất mặc định:", wout)

        self.ed_task_dir = QLineEdit()
        self.ed_task_dir.setPlaceholderText("Tasks Log 任务 (CSV nhiệm vụ)")
        self.ed_task_dir.editingFinished.connect(self._on_task_dir_edited)
        b_task_dir = QPushButton("Chọn")
        b_task_dir.clicked.connect(self.on_pick_task_dir)
        row_task = QHBoxLayout(); row_task.setContentsMargins(0, 0, 0, 0)
        row_task.addWidget(self.ed_task_dir); row_task.addWidget(b_task_dir)
        wtask = QWidget(); wtask.setLayout(row_task)
        form.addRow("Thư mục Tasks Log:", wtask)

        b_save = QPushButton("Lưu cài đặt vào point_settings.json")
        b_save.clicked.connect(self.on_save_settings)
        form.addRow(b_save)

        legend = QLabel("Màu tỷ lệ:  ● Tốt   ● Cảnh báo   ● Cao")
        legend.setStyleSheet("color:#555; font-size:11px;")
        form.addRow(legend)

        return box

    def _build_right_panel(self) -> QWidget:
        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self._on_result_tab_changed)

        self.tabs.addTab(self._build_dashboard_tab(), "Tổng quan")

        # Tab Theo ngày (báo cáo ngày: so sánh các ngày + báo cáo 1 ngày)
        self.tabs.addTab(self._build_day_tab(), "Theo ngày")
        self._clear_daily_detail("Chưa có dữ liệu — hãy nạp nguồn rồi bấm PHÂN TÍCH.")

        # Tab Theo điểm (báo cáo điểm cần xử lý)
        self.tabs.addTab(self._build_points_tab(), "Theo điểm")

        # Tab Theo xe (báo cáo xe cần kiểm tra)
        self.tabs.addTab(self._build_cars_tab(), "Theo xe")

        # Tab Theo model (báo cáo model cần chú ý — Tasks Log)
        self.tabs.addTab(self._build_models_tab(), "Theo model")

        # Tab Theo tuần (báo cáo tuần: so sánh nhiều tuần + báo cáo 1 tuần)
        self.tabs.addTab(self._build_week_tab(), "Theo tuần")

        # Tab Theo tháng (báo cáo tháng: so sánh nhiều tháng + báo cáo 1 tháng)
        self.tabs.addTab(self._build_month_tab(), "Theo tháng")

        # Tab Điều phối (API)
        self.tbl_api_days = make_table(
            ["Ngày", "taskCreate", "Poll", "Task unique", "Gán xe",
             "Lỗi API", "Điểm hot", "Số lần"])
        self.tbl_api_points = make_table(["Điểm", "Số lần (payload)"])
        self.tbl_api_cross = make_table(
            ["Ngày", "CSV task", "API create", "Chênh (CSV−API)", "Có CSV", "Có API"])
        self.chart_api_points = BarChartWidget()
        api_wrap = QWidget()
        api_lay = QVBoxLayout(api_wrap)
        api_lay.setContentsMargins(6, 6, 6, 6)
        api_lay.addWidget(_section_label("Điều phối theo ngày (Tasks API logs)"))
        api_lay.addWidget(self.tbl_api_days, 2)
        row_api = QHBoxLayout()
        col_ap = QVBoxLayout()
        col_ap.addWidget(_section_label("Top điểm trong payload"))
        col_ap.addWidget(self.chart_api_points)
        col_ap.addWidget(self.tbl_api_points, 1)
        row_api.addLayout(col_ap, 1)
        col_cx = QVBoxLayout()
        col_cx.addWidget(_section_label("Đối chiếu CSV ↔ API cùng ngày"))
        col_cx.addWidget(self.tbl_api_cross, 1)
        row_api.addLayout(col_cx, 1)
        api_lay.addLayout(row_api, 3)
        self.tabs.addTab(api_wrap, "Điều phối (API)")

        return self.tabs

    def _build_dashboard_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        scroll.setWidget(content)
        v = QVBoxLayout(content)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(8)

        title = QLabel("Báo cáo chất lượng hoạt động AGV")
        tf = QFont(); tf.setPointSize(15); tf.setBold(True)
        title.setFont(tf)
        title.setStyleSheet("color:#1F4E79;")
        v.addWidget(title)
        self.lbl_dash_sub = QLabel("Chưa có dữ liệu. Hãy thêm thư mục log và bấm PHÂN TÍCH.")
        self.lbl_dash_sub.setStyleSheet("color:#666; font-style:italic;")
        v.addWidget(self.lbl_dash_sub)

        # Hàng KPI chính
        kpi_grid = QGridLayout()
        kpi_grid.setSpacing(8)
        self.kpi_days = KpiCard("Số ngày phân tích")
        self.kpi_cars = KpiCard("Tổng số xe")
        self.kpi_events = KpiCard("Tổng lượt bất thường")
        self.kpi_hours = KpiCard("Tổng giờ bất thường")
        self.kpi_rate = KpiCard("Tỷ lệ bất thường CHUNG")
        for i, card in enumerate(
                [self.kpi_days, self.kpi_cars, self.kpi_events, self.kpi_hours, self.kpi_rate]):
            kpi_grid.addWidget(card, 0, i)
        v.addLayout(kpi_grid)

        # Hàng KPI Tasks Log / 稼動
        util_grid = QGridLayout()
        util_grid.setSpacing(8)
        self.kpi_util = KpiCard("Tỷ lệ hoạt động (稼動率)")
        self.kpi_tasks = KpiCard("Tổng số nhiệm vụ")
        self.kpi_timeout = KpiCard("Timeout")
        self.kpi_cycle = KpiCard("TB chu kỳ nhiệm vụ")
        for i, card in enumerate(
                [self.kpi_util, self.kpi_tasks, self.kpi_timeout, self.kpi_cycle]):
            util_grid.addWidget(card, 0, i)
        v.addLayout(util_grid)

        # Hàng KPI Tasks API logs
        api_grid = QGridLayout()
        api_grid.setSpacing(8)
        self.kpi_api_create = KpiCard("Lệnh taskCreate")
        self.kpi_api_poll = KpiCard("Poll / task unique")
        self.kpi_api_err = KpiCard("Lỗi API")
        self.kpi_api_hot = KpiCard("Điểm hot payload")
        for i, card in enumerate(
                [self.kpi_api_create, self.kpi_api_poll, self.kpi_api_err, self.kpi_api_hot]):
            api_grid.addWidget(card, 0, i)
        v.addLayout(api_grid)

        # Hàng điểm nhấn
        hl_grid = QGridLayout()
        hl_grid.setSpacing(8)
        self.kpi_worst = KpiCard("Ngày tệ nhất")
        self.kpi_best = KpiCard("Ngày tốt nhất")
        self.kpi_topcar = KpiCard("Xe cần chú ý nhất")
        self.kpi_toppoint = KpiCard("Điểm hay kẹt nhất")
        for i, card in enumerate(
                [self.kpi_worst, self.kpi_best, self.kpi_topcar, self.kpi_toppoint]):
            hl_grid.addWidget(card, 0, i)
        v.addLayout(hl_grid)

        # Biểu đồ xu hướng bất thường + 稼動 + taskCreate
        row_trend = QHBoxLayout()
        col_t1 = QVBoxLayout()
        col_t1.addWidget(_section_label("Xu hướng tỷ lệ bất thường theo ngày (%)"))
        self.chart_trend = TrendChartWidget()
        self.chart_trend.setMinimumHeight(200)
        col_t1.addWidget(self.chart_trend)
        row_trend.addLayout(col_t1, 1)
        col_t2 = QVBoxLayout()
        col_t2.addWidget(_section_label("Xu hướng tỷ lệ hoạt động (稼動率) (%)"))
        self.chart_util_trend = TrendChartWidget()
        self.chart_util_trend.setMinimumHeight(200)
        col_t2.addWidget(self.chart_util_trend)
        row_trend.addLayout(col_t2, 1)
        col_t3 = QVBoxLayout()
        col_t3.addWidget(_section_label("Xu hướng số lệnh taskCreate"))
        self.chart_api_trend = TrendChartWidget()
        self.chart_api_trend.setMinimumHeight(200)
        col_t3.addWidget(self.chart_api_trend)
        row_trend.addLayout(col_t3, 1)
        v.addLayout(row_trend)

        # Hai biểu đồ cạnh nhau: top điểm + top xe
        row2 = QHBoxLayout()
        col_a = QVBoxLayout()
        col_a.addWidget(_section_label("Top điểm hay kẹt (số lượt)"))
        self.chart_points = BarChartWidget()
        col_a.addWidget(self.chart_points)
        row2.addLayout(col_a, 1)
        col_b = QVBoxLayout()
        col_b.addWidget(_section_label("Top xe bất thường (số lượt)"))
        self.chart_cars = BarChartWidget()
        col_b.addWidget(self.chart_cars)
        row2.addLayout(col_b, 1)
        v.addLayout(row2)

        # Ca ngày/đêm + thứ trong tuần + mức độ nặng
        row3 = QHBoxLayout()
        col_c = QVBoxLayout()
        col_c.addWidget(_section_label("So sánh ca ngày / ca đêm (tỷ lệ %)"))
        self.chart_daynight = BarChartWidget()
        col_c.addWidget(self.chart_daynight)
        row3.addLayout(col_c, 1)
        col_d = QVBoxLayout()
        col_d.addWidget(_section_label("Mẫu theo thứ trong tuần (tỷ lệ %)"))
        self.chart_weekday = BarChartWidget()
        col_d.addWidget(self.chart_weekday)
        row3.addLayout(col_d, 1)
        v.addLayout(row3)

        v.addWidget(_section_label("Phân nhóm mức độ nặng (số lượt theo thời gian dừng)"))
        self.chart_severity = BarChartWidget()
        v.addWidget(self.chart_severity)

        v.addStretch(1)
        return scroll

    def _build_day_tab(self) -> QWidget:
        """Tab Theo ngày = báo cáo ngày: so sánh các ngày (trên) + báo cáo
        chi tiết một ngày đã chọn (dưới)."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        scroll.setWidget(content)
        v = QVBoxLayout(content)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(8)

        # --- Phần B: so sánh các ngày ----------------------------------------
        v.addWidget(_section_label("So sánh các ngày"))
        self.tbl_daily = make_table(
            ["Ngày", "Thứ", "Số xe", "Tổng bất thường", "Tỷ lệ ca ngày (%)",
             "Tỷ lệ ca đêm (%)", "Tỷ lệ cả ngày (%)", "稼動率 (%)", "Số task",
             "Timeout", "API create", "Số file"],
            stretch_last=False)
        self.tbl_daily.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tbl_daily.setMinimumHeight(180)
        self.tbl_daily.itemSelectionChanged.connect(self._on_daily_selected)
        self.chart_day_compare = BarChartWidget()
        self.chart_day_compare.setMinimumHeight(180)
        compare_row = QHBoxLayout()
        left_cmp = QVBoxLayout()
        left_cmp.addWidget(self.tbl_daily)
        right_cmp = QVBoxLayout()
        right_cmp.addWidget(_section_label("Ngày có tỷ lệ bất thường cao nhất (%)"))
        right_cmp.addWidget(self.chart_day_compare)
        compare_row.addLayout(left_cmp, 3)
        compare_row.addLayout(right_cmp, 2)
        v.addLayout(compare_row)

        # --- Phần A: báo cáo một ngày đã chọn --------------------------------
        self.lbl_day_title = QLabel("Báo cáo ngày — chọn một ngày ở bảng trên")
        tf = QFont(); tf.setPointSize(14); tf.setBold(True)
        self.lbl_day_title.setFont(tf)
        self.lbl_day_title.setStyleSheet("color:#1F4E79; margin-top:10px;")
        v.addWidget(self.lbl_day_title)

        self.lbl_day_verdict = QLabel("")
        self.lbl_day_verdict.setWordWrap(True)
        self.lbl_day_verdict.setStyleSheet(
            "padding:8px; border-radius:6px; background:#eef5ff; color:#1F4E79;")
        v.addWidget(self.lbl_day_verdict)

        kpi_grid = QGridLayout()
        kpi_grid.setSpacing(8)
        self.kpi_d_rate = KpiCard("Tỷ lệ bất thường")
        self.kpi_d_day = KpiCard("Ca ngày")
        self.kpi_d_night = KpiCard("Ca đêm")
        self.kpi_d_cars = KpiCard("Số xe")
        self.kpi_d_events = KpiCard("Tổng bất thường")
        self.kpi_d_util = KpiCard("Tỷ lệ hoạt động (稼動率)")
        self.kpi_d_tasks = KpiCard("Số nhiệm vụ")
        self.kpi_d_api = KpiCard("Điều phối API")
        for i, card in enumerate(
                [self.kpi_d_rate, self.kpi_d_day, self.kpi_d_night, self.kpi_d_cars]):
            kpi_grid.addWidget(card, 0, i)
        for i, card in enumerate(
                [self.kpi_d_events, self.kpi_d_util, self.kpi_d_tasks, self.kpi_d_api]):
            kpi_grid.addWidget(card, 1, i)
        v.addLayout(kpi_grid)

        charts_row = QHBoxLayout()
        col_pt = QVBoxLayout()
        col_pt.addWidget(_section_label("Điểm kẹt nhiều nhất trong ngày (số lượt)"))
        self.chart_day_points = BarChartWidget()
        self.chart_day_points.setMinimumHeight(170)
        col_pt.addWidget(self.chart_day_points)
        col_car = QVBoxLayout()
        col_car.addWidget(_section_label("Xe kẹt nhiều nhất trong ngày (số lượt)"))
        self.chart_day_cars = BarChartWidget()
        self.chart_day_cars.setMinimumHeight(170)
        col_car.addWidget(self.chart_day_cars)
        col_shift = QVBoxLayout()
        col_shift.addWidget(_section_label("Ca ngày / ca đêm (%)"))
        self.chart_day_shift = BarChartWidget()
        self.chart_day_shift.setMinimumHeight(170)
        col_shift.addWidget(self.chart_day_shift)
        charts_row.addLayout(col_pt, 2)
        charts_row.addLayout(col_car, 2)
        charts_row.addLayout(col_shift, 1)
        v.addLayout(charts_row)

        v.addWidget(_section_label("Bất thường theo giờ trong ngày (số lượt)"))
        self.chart_day_hours = BarChartWidget()
        self.chart_day_hours.setMinimumHeight(240)
        v.addWidget(self.chart_day_hours)

        self.lbl_daily_detail_title = _section_label("Chi tiết ngày đã chọn")
        v.addWidget(self.lbl_daily_detail_title)
        self.tbl_daily_detail = make_table(
            ["Ca", "Số xe", "Điểm", "Giờ đến", "Thời gian dừng (phút)"])
        self.tbl_daily_tasks = make_table(
            ["Ca", "Số xe", "Model", "Gửi lúc", "Hoàn thành",
             "Duration (phút)", "Trạng thái", "Task ID"])
        self.tbl_daily_api = make_table(
            ["Thời điểm", "systemName", "score", "Số điểm", "Lộ trình điểm"])
        self.daily_bottom = QTabWidget()
        self.daily_bottom.addTab(self.tbl_daily_detail, "Chi tiết bất thường")
        self.daily_bottom.addTab(self.tbl_daily_tasks, "Chi tiết Tasks Log")
        self.daily_bottom.addTab(self.tbl_daily_api, "API logs")
        self.daily_bottom.setMinimumHeight(300)
        v.addWidget(self.daily_bottom)

        v.addStretch(1)
        return scroll

    def _build_points_tab(self) -> QWidget:
        """Tab Theo điểm = báo cáo điểm cần xử lý (P1/P2/P3 + chẩn đoán)."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        scroll.setWidget(content)
        v = QVBoxLayout(content)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(8)

        title = QLabel("Báo cáo điểm hay kẹt")
        tf = QFont(); tf.setPointSize(14); tf.setBold(True)
        title.setFont(tf)
        title.setStyleSheet("color:#1F4E79;")
        v.addWidget(title)

        self.lbl_points_verdict = QLabel(
            "Chưa có dữ liệu. Hãy nạp Log AGV rồi bấm PHÂN TÍCH.")
        self.lbl_points_verdict.setWordWrap(True)
        self.lbl_points_verdict.setStyleSheet(
            "padding:8px; border-radius:6px; background:#eef5ff; color:#1F4E79;")
        v.addWidget(self.lbl_points_verdict)

        kpi_grid = QGridLayout()
        kpi_grid.setSpacing(8)
        self.kpi_pt_total = KpiCard("Số điểm có kẹt")
        self.kpi_pt_p1 = KpiCard("Cần xử lý ngay (P1)")
        self.kpi_pt_worst = KpiCard("Điểm nặng nhất")
        self.kpi_pt_focus = KpiCard("Mức tập trung top 5")
        for i, card in enumerate(
                [self.kpi_pt_total, self.kpi_pt_p1, self.kpi_pt_worst, self.kpi_pt_focus]):
            kpi_grid.addWidget(card, 0, i)
        v.addLayout(kpi_grid)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Tìm điểm:"))
        self.ed_point_filter = QLineEdit()
        self.ed_point_filter.setPlaceholderText("Nhập mã điểm để lọc bảng…")
        self.ed_point_filter.textChanged.connect(self._apply_point_filter)
        filter_row.addWidget(self.ed_point_filter, 1)
        v.addLayout(filter_row)

        charts_row = QHBoxLayout()
        left_c = QVBoxLayout(); right_c = QVBoxLayout()
        left_c.addWidget(_section_label("Xếp hạng theo số lượt (top 12)"))
        self.chart_points_tab = BarChartWidget()
        self.chart_points_tab.setMinimumHeight(160)
        left_c.addWidget(self.chart_points_tab)
        right_c.addWidget(_section_label("Xếp hạng theo tổng phút dừng (top 12)"))
        self.chart_points_time = BarChartWidget()
        self.chart_points_time.setMinimumHeight(160)
        right_c.addWidget(self.chart_points_time)
        charts_row.addLayout(left_c, 1)
        charts_row.addLayout(right_c, 1)
        v.addLayout(charts_row)

        self.lbl_points_title = _section_label(
            "Điểm xếp theo ưu tiên P1 → P2 → P3")
        v.addWidget(self.lbl_points_title)
        self.tbl_points = make_table(
            ["Ưu tiên", "Điểm", "Loại", "Số lượt", "Lượt/ngày", "Số xe", "Số ngày",
             "Ca ngày", "Ca đêm", "Tổng (phút)", "TB (phút)", "Max (phút)",
             "Max tại (xe · ngày)", "Lần cuối"],
            stretch_last=False)
        self.tbl_points.horizontalHeader().setSectionResizeMode(12, QHeaderView.Stretch)
        self.tbl_points.setMinimumHeight(220)
        self.tbl_points.itemSelectionChanged.connect(self._on_point_selected)
        v.addWidget(self.tbl_points)

        self.lbl_point_detail_title = _section_label("Chi tiết điểm đã chọn")
        v.addWidget(self.lbl_point_detail_title)
        self.lbl_point_diag = QLabel("Chọn một điểm ở bảng trên để xem chẩn đoán.")
        self.lbl_point_diag.setWordWrap(True)
        self.lbl_point_diag.setStyleSheet(
            "padding:8px; border-radius:6px; background:#f7f7f7; color:#333;")
        v.addWidget(self.lbl_point_diag)

        detail_charts = QHBoxLayout()
        col_car = QVBoxLayout()
        col_car.addWidget(_section_label("Phân bố lượt theo xe (top 10)"))
        self.chart_point_cars = BarChartWidget()
        self.chart_point_cars.setMinimumHeight(150)
        col_car.addWidget(self.chart_point_cars)
        col_hour = QVBoxLayout()
        col_hour.addWidget(_section_label("Phân bố lượt theo giờ đến"))
        self.chart_point_hours = BarChartWidget()
        self.chart_point_hours.setMinimumHeight(150)
        col_hour.addWidget(self.chart_point_hours)
        detail_charts.addLayout(col_car, 1)
        detail_charts.addLayout(col_hour, 1)
        v.addLayout(detail_charts)

        self.tbl_point_detail = make_table(
            ["Ngày", "Ca", "Số xe", "Giờ đến", "Thời gian dừng (phút)"])
        self.tbl_point_detail.setMinimumHeight(180)
        v.addWidget(self.tbl_point_detail)
        self._table_note(
            self.tbl_point_detail,
            "Chọn một điểm ở bảng trên để xem từng lượt dừng")

        v.addStretch(1)
        return scroll

    def _build_cars_tab(self) -> QWidget:
        """Tab Theo xe = báo cáo xe cần kiểm tra (P1/P2/P3 + Kẹt/100 task)."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        scroll.setWidget(content)
        v = QVBoxLayout(content)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(8)

        title = QLabel("Báo cáo xe hay kẹt")
        tf = QFont(); tf.setPointSize(14); tf.setBold(True)
        title.setFont(tf)
        title.setStyleSheet("color:#1F4E79;")
        v.addWidget(title)

        self.lbl_cars_verdict = QLabel(
            "Chưa có dữ liệu. Hãy nạp Log AGV rồi bấm PHÂN TÍCH.")
        self.lbl_cars_verdict.setWordWrap(True)
        self.lbl_cars_verdict.setStyleSheet(
            "padding:8px; border-radius:6px; background:#eef5ff; color:#1F4E79;")
        v.addWidget(self.lbl_cars_verdict)

        kpi_grid = QGridLayout()
        kpi_grid.setSpacing(8)
        self.kpi_car_total = KpiCard("Số xe có kẹt")
        self.kpi_car_p1 = KpiCard("Cần kiểm tra ngay (P1)")
        self.kpi_car_worst = KpiCard("Xe đáng lo nhất")
        self.kpi_car_fleet = KpiCard("Kẹt/100 task TB đội")
        for i, card in enumerate(
                [self.kpi_car_total, self.kpi_car_p1, self.kpi_car_worst, self.kpi_car_fleet]):
            kpi_grid.addWidget(card, 0, i)
        v.addLayout(kpi_grid)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Tìm xe:"))
        self.ed_car_filter = QLineEdit()
        self.ed_car_filter.setPlaceholderText("Nhập mã xe để lọc bảng…")
        self.ed_car_filter.textChanged.connect(self._apply_car_filter)
        filter_row.addWidget(self.ed_car_filter, 1)
        v.addLayout(filter_row)

        charts_row = QHBoxLayout()
        left_c = QVBoxLayout(); right_c = QVBoxLayout()
        left_c.addWidget(_section_label("Xếp hạng theo số lượt (top 12)"))
        self.chart_cars_tab = BarChartWidget()
        self.chart_cars_tab.setMinimumHeight(160)
        left_c.addWidget(self.chart_cars_tab)
        right_c.addWidget(_section_label("Xếp hạng theo tổng phút dừng (top 12)"))
        self.chart_cars_time = BarChartWidget()
        self.chart_cars_time.setMinimumHeight(160)
        right_c.addWidget(self.chart_cars_time)
        charts_row.addLayout(left_c, 1)
        charts_row.addLayout(right_c, 1)
        v.addLayout(charts_row)

        self.lbl_cars_title = _section_label(
            "Xe xếp theo ưu tiên P1 → P2 → P3")
        v.addWidget(self.lbl_cars_title)
        self.tbl_cars = make_table(
            ["Ưu tiên", "Số xe", "Số lượt", "Lượt/ngày", "Số task", "Giờ chạy việc",
             "Kẹt/100 task", "Số ngày", "Số điểm", "Điểm hay kẹt",
             "Ca ngày", "Ca đêm", "Tổng (phút)", "TB (phút)", "Max (phút)",
             "Max tại (điểm · ngày)", "Lần cuối"],
            stretch_last=False)
        self.tbl_cars.horizontalHeader().setSectionResizeMode(15, QHeaderView.Stretch)
        self.tbl_cars.setMinimumHeight(220)
        self.tbl_cars.itemSelectionChanged.connect(self._on_car_selected)
        v.addWidget(self.tbl_cars)

        self.lbl_car_detail_title = _section_label("Chi tiết xe đã chọn")
        v.addWidget(self.lbl_car_detail_title)
        self.lbl_car_diag = QLabel("Chọn một xe ở bảng trên để xem chẩn đoán.")
        self.lbl_car_diag.setWordWrap(True)
        self.lbl_car_diag.setStyleSheet(
            "padding:8px; border-radius:6px; background:#f7f7f7; color:#333;")
        v.addWidget(self.lbl_car_diag)

        detail_charts = QHBoxLayout()
        col_pt = QVBoxLayout()
        col_pt.addWidget(_section_label("Phân bố lượt theo điểm (top 10)"))
        self.chart_car_points = BarChartWidget()
        self.chart_car_points.setMinimumHeight(150)
        col_pt.addWidget(self.chart_car_points)
        col_hour = QVBoxLayout()
        col_hour.addWidget(_section_label("Phân bố lượt theo giờ đến"))
        self.chart_car_hours = BarChartWidget()
        self.chart_car_hours.setMinimumHeight(150)
        col_hour.addWidget(self.chart_car_hours)
        detail_charts.addLayout(col_pt, 1)
        detail_charts.addLayout(col_hour, 1)
        v.addLayout(detail_charts)

        self.tbl_car_detail = make_table(
            ["Ngày", "Ca", "Điểm", "Giờ đến", "Thời gian dừng (phút)"])
        self.tbl_car_detail.setMinimumHeight(180)
        v.addWidget(self.tbl_car_detail)
        self._table_note(
            self.tbl_car_detail,
            "Chọn một xe ở bảng trên để xem từng lượt dừng")

        v.addStretch(1)
        return scroll

    def _build_models_tab(self) -> QWidget:
        """Tab Theo model = báo cáo model cần chú ý (timeout + chu kỳ vs TB đội)."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        scroll.setWidget(content)
        v = QVBoxLayout(content)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(8)

        title = QLabel("Báo cáo model (Tasks Log)")
        tf = QFont(); tf.setPointSize(14); tf.setBold(True)
        title.setFont(tf)
        title.setStyleSheet("color:#1F4E79;")
        v.addWidget(title)

        self.lbl_models_verdict = QLabel(
            "Chưa có dữ liệu. Hãy nạp Tasks CSV rồi bấm PHÂN TÍCH.")
        self.lbl_models_verdict.setWordWrap(True)
        self.lbl_models_verdict.setStyleSheet(
            "padding:8px; border-radius:6px; background:#eef5ff; color:#1F4E79;")
        v.addWidget(self.lbl_models_verdict)

        kpi_grid = QGridLayout()
        kpi_grid.setSpacing(8)
        self.kpi_md_total = KpiCard("Số model")
        self.kpi_md_p1 = KpiCard("Cần chú ý (P1)")
        self.kpi_md_worst = KpiCard("Model đáng lo nhất")
        self.kpi_md_timeout = KpiCard("% timeout TB")
        for i, card in enumerate(
                [self.kpi_md_total, self.kpi_md_p1, self.kpi_md_worst, self.kpi_md_timeout]):
            kpi_grid.addWidget(card, 0, i)
        v.addLayout(kpi_grid)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Tìm model:"))
        self.ed_model_filter = QLineEdit()
        self.ed_model_filter.setPlaceholderText("Nhập tên model để lọc bảng…")
        self.ed_model_filter.textChanged.connect(self._apply_model_filter)
        filter_row.addWidget(self.ed_model_filter, 1)
        v.addLayout(filter_row)

        charts_row = QHBoxLayout()
        left_c = QVBoxLayout(); right_c = QVBoxLayout()
        left_c.addWidget(_section_label("Xếp hạng theo số task (top 12)"))
        self.chart_models = BarChartWidget()
        self.chart_models.setMinimumHeight(160)
        left_c.addWidget(self.chart_models)
        right_c.addWidget(_section_label("Xếp hạng theo tổng giờ chạy (top 12)"))
        self.chart_models_hours = BarChartWidget()
        self.chart_models_hours.setMinimumHeight(160)
        right_c.addWidget(self.chart_models_hours)
        charts_row.addLayout(left_c, 1)
        charts_row.addLayout(right_c, 1)
        v.addLayout(charts_row)

        self.lbl_models_title = _section_label(
            "Model xếp theo ưu tiên P1 → P2 → P3")
        v.addWidget(self.lbl_models_title)
        self.tbl_models = make_table(
            ["Ưu tiên", "Model", "Số task", "% tổng", "Task/ngày", "Số ngày", "Số xe",
             "Tổng giờ", "TB (phút)", "Min (phút)", "Max (phút)",
             "Timeout", "% timeout", "Lần cuối"],
            stretch_last=False)
        self.tbl_models.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tbl_models.setMinimumHeight(220)
        self.tbl_models.itemSelectionChanged.connect(self._on_model_selected)
        v.addWidget(self.tbl_models)

        self.lbl_model_detail_title = _section_label("Chi tiết model đã chọn")
        v.addWidget(self.lbl_model_detail_title)
        self.lbl_model_diag = QLabel("Chọn một model ở bảng trên để xem chẩn đoán.")
        self.lbl_model_diag.setWordWrap(True)
        self.lbl_model_diag.setStyleSheet(
            "padding:8px; border-radius:6px; background:#f7f7f7; color:#333;")
        v.addWidget(self.lbl_model_diag)

        detail_charts = QHBoxLayout()
        col_car = QVBoxLayout()
        col_car.addWidget(_section_label("Phân bố task theo xe (top 10)"))
        self.chart_model_cars = BarChartWidget()
        self.chart_model_cars.setMinimumHeight(150)
        col_car.addWidget(self.chart_model_cars)
        col_hour = QVBoxLayout()
        col_hour.addWidget(_section_label("Phân bố task theo giờ"))
        self.chart_model_hours = BarChartWidget()
        self.chart_model_hours.setMinimumHeight(150)
        col_hour.addWidget(self.chart_model_hours)
        detail_charts.addLayout(col_car, 1)
        detail_charts.addLayout(col_hour, 1)
        v.addLayout(detail_charts)

        self.tbl_model_detail = make_table(
            ["Ngày", "Ca", "Số xe", "Gửi lúc", "Hoàn thành",
             "Duration (phút)", "Trạng thái"],
            stretch_last=False)
        self.tbl_model_detail.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents)
        self.tbl_model_detail.setMinimumHeight(180)
        v.addWidget(self.tbl_model_detail)
        self._table_note(
            self.tbl_model_detail,
            "Chọn một model ở bảng trên để xem từng task")

        v.addStretch(1)
        return scroll

    def _build_week_tab(self) -> QWidget:
        """Tab Theo tuần = báo cáo tuần: so sánh nhiều tuần (trên) + báo cáo
        chi tiết một tuần đã chọn (dưới)."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        scroll.setWidget(content)
        v = QVBoxLayout(content)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(8)

        v.addWidget(_section_label("So sánh các tuần (Thứ Hai – Chủ Nhật)"))
        self.tbl_week = make_table(
            ["Tuần (ISO)", "Từ ngày", "Đến ngày", "Ngày có Log AGV", "Số xe",
             "Tổng bất thường", "Tỷ lệ bất thường (%)", "稼動率 (%)", "Số task", "Timeout"],
            stretch_last=False)
        self.tbl_week.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tbl_week.setMinimumHeight(150)
        self.tbl_week.itemSelectionChanged.connect(self._on_week_selected)
        self.chart_week_compare = BarChartWidget()
        self.chart_week_compare.setMinimumHeight(150)
        compare_row = QHBoxLayout()
        left_cmp = QVBoxLayout()
        left_cmp.addWidget(self.tbl_week)
        right_cmp = QVBoxLayout()
        right_cmp.addWidget(_section_label("Tỷ lệ bất thường theo tuần (%)"))
        right_cmp.addWidget(self.chart_week_compare)
        compare_row.addLayout(left_cmp, 3)
        compare_row.addLayout(right_cmp, 2)
        v.addLayout(compare_row)

        self.lbl_week_title = QLabel("Báo cáo tuần — chọn một tuần ở bảng trên")
        tf = QFont(); tf.setPointSize(14); tf.setBold(True)
        self.lbl_week_title.setFont(tf)
        self.lbl_week_title.setStyleSheet("color:#1F4E79; margin-top:10px;")
        v.addWidget(self.lbl_week_title)

        self.lbl_week_verdict = QLabel("")
        self.lbl_week_verdict.setWordWrap(True)
        self.lbl_week_verdict.setStyleSheet(
            "padding:8px; border-radius:6px; background:#eef5ff; color:#1F4E79;")
        v.addWidget(self.lbl_week_verdict)

        kpi_grid = QGridLayout()
        kpi_grid.setSpacing(8)
        self.kpi_w_days = KpiCard("Ngày có Log AGV")
        self.kpi_w_cars = KpiCard("Số xe")
        self.kpi_w_events = KpiCard("Tổng bất thường")
        self.kpi_w_rate = KpiCard("Tỷ lệ bất thường")
        self.kpi_w_util = KpiCard("Tỷ lệ hoạt động (稼動率)")
        self.kpi_w_tasks = KpiCard("Số nhiệm vụ")
        self.kpi_w_timeout = KpiCard("Timeout")
        self.kpi_w_worst = KpiCard("Ngày tệ nhất")
        for i, card in enumerate(
                [self.kpi_w_days, self.kpi_w_cars, self.kpi_w_events, self.kpi_w_rate]):
            kpi_grid.addWidget(card, 0, i)
        for i, card in enumerate(
                [self.kpi_w_util, self.kpi_w_tasks, self.kpi_w_timeout, self.kpi_w_worst]):
            kpi_grid.addWidget(card, 1, i)
        v.addLayout(kpi_grid)

        v.addWidget(_section_label("Xu hướng tỷ lệ bất thường theo ngày trong tuần (%)"))
        self.chart_week_trend = TrendChartWidget()
        self.chart_week_trend.setMinimumHeight(200)
        v.addWidget(self.chart_week_trend)

        v.addWidget(_section_label("Các ngày trong tuần (chỉ ngày có Log AGV / Tasks CSV)"))
        self.tbl_week_detail = make_table(
            ["Ngày", "Thứ", "Số xe", "Tổng bất thường", "Tỷ lệ cả ngày (%)",
             "稼動率 (%)", "Số task"],
            stretch_last=True)
        self.tbl_week_detail.setMinimumHeight(200)
        v.addWidget(self.tbl_week_detail)

        v.addStretch(1)
        return scroll

    def _build_month_tab(self) -> QWidget:
        """Tab Theo tháng = báo cáo tháng: so sánh nhiều tháng (trên) + báo cáo
        chi tiết một tháng đã chọn (dưới)."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        scroll.setWidget(content)
        v = QVBoxLayout(content)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(8)

        # --- Phần B: so sánh nhiều tháng -------------------------------------
        v.addWidget(_section_label("So sánh các tháng"))
        self.tbl_month = make_table(
            ["Tháng", "Ngày có Log AGV", "Số xe", "Tổng bất thường",
             "Tỷ lệ bất thường (%)", "稼動率 (%)", "Số task", "Timeout"],
            stretch_last=False)
        self.tbl_month.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tbl_month.setMinimumHeight(150)
        self.tbl_month.itemSelectionChanged.connect(self._on_month_selected)
        self.chart_month_compare = BarChartWidget()
        self.chart_month_compare.setMinimumHeight(150)
        compare_row = QHBoxLayout()
        left_cmp = QVBoxLayout()
        left_cmp.addWidget(self.tbl_month)
        right_cmp = QVBoxLayout()
        right_cmp.addWidget(_section_label("Tỷ lệ bất thường theo tháng (%)"))
        right_cmp.addWidget(self.chart_month_compare)
        compare_row.addLayout(left_cmp, 3)
        compare_row.addLayout(right_cmp, 2)
        v.addLayout(compare_row)

        # --- Phần A: báo cáo một tháng đã chọn -------------------------------
        self.lbl_month_title = QLabel("Báo cáo tháng — chọn một tháng ở bảng trên")
        tf = QFont(); tf.setPointSize(14); tf.setBold(True)
        self.lbl_month_title.setFont(tf)
        self.lbl_month_title.setStyleSheet("color:#1F4E79; margin-top:10px;")
        v.addWidget(self.lbl_month_title)

        self.lbl_month_verdict = QLabel("")
        self.lbl_month_verdict.setWordWrap(True)
        self.lbl_month_verdict.setStyleSheet(
            "padding:8px; border-radius:6px; background:#eef5ff; color:#1F4E79;")
        v.addWidget(self.lbl_month_verdict)

        kpi_grid = QGridLayout()
        kpi_grid.setSpacing(8)
        self.kpi_m_days = KpiCard("Ngày có Log AGV")
        self.kpi_m_cars = KpiCard("Số xe")
        self.kpi_m_events = KpiCard("Tổng bất thường")
        self.kpi_m_rate = KpiCard("Tỷ lệ bất thường")
        self.kpi_m_util = KpiCard("Tỷ lệ hoạt động (稼動率)")
        self.kpi_m_tasks = KpiCard("Số nhiệm vụ")
        self.kpi_m_timeout = KpiCard("Timeout")
        self.kpi_m_worst = KpiCard("Ngày tệ nhất")
        for i, card in enumerate(
                [self.kpi_m_days, self.kpi_m_cars, self.kpi_m_events, self.kpi_m_rate]):
            kpi_grid.addWidget(card, 0, i)
        for i, card in enumerate(
                [self.kpi_m_util, self.kpi_m_tasks, self.kpi_m_timeout, self.kpi_m_worst]):
            kpi_grid.addWidget(card, 1, i)
        v.addLayout(kpi_grid)

        v.addWidget(_section_label("Xu hướng tỷ lệ bất thường theo ngày trong tháng (%)"))
        self.chart_month_trend = TrendChartWidget()
        self.chart_month_trend.setMinimumHeight(200)
        v.addWidget(self.chart_month_trend)

        v.addWidget(_section_label("Các ngày trong tháng (chỉ ngày có Log AGV / Tasks CSV)"))
        self.tbl_month_detail = make_table(
            ["Ngày", "Thứ", "Số xe", "Tổng bất thường", "Tỷ lệ cả ngày (%)",
             "稼動率 (%)", "Số task"],
            stretch_last=True)
        self.tbl_month_detail.setMinimumHeight(200)
        v.addWidget(self.tbl_month_detail)

        v.addStretch(1)
        return scroll

    # -- Cài đặt <-> giao diện ------------------------------------------------

    def _apply_settings_to_ui(self, s: Settings):
        self.sp_threshold.setValue(s.threshold_min)
        self.sp_elevator.setValue(s.elevator_threshold_min)
        self.cb_elevator.setChecked(bool(s.elevator_points))
        self.ed_elevator_pts.setText(", ".join(sorted(s.elevator_points)))
        self.te_excluded.setPlainText(self._format_excluded_groups(s.excluded_groups))
        self.te_day_start.setTime(QTime(s.day_start[0], s.day_start[1]))
        self.te_day_end.setTime(QTime(s.day_end[0], s.day_end[1]))
        self.te_night_start.setTime(QTime(s.night_start[0], s.night_start[1]))
        self.te_night_end.setTime(QTime(s.night_end[0], s.night_end[1]))
        self.sp_denom.setValue(s.denom_hours)
        self.sp_rate_ok.setValue(s.rate_ok)
        self.sp_rate_warn.setValue(s.rate_warn)
        self.ed_log_dir.setText(s.default_log_dir)
        self.ed_out_dir.setText(s.default_output_dir)
        self._set_task_log_dir(s.task_log_dir or "", refresh=True, log=False)
        # Nạp sẵn Tasks Log từ cài đặt vào inventory (nếu chưa có)
        if s.task_log_dir and Path(s.task_log_dir).is_dir():
            if self._inventory.counts()["csv"] <= 0:
                self._ingest_paths([Path(s.task_log_dir)], log=False)
        if s.default_log_dir and not self.ed_range_parent.text().strip():
            self.ed_range_parent.setText(s.default_log_dir)
        self._rate_ok = s.rate_ok
        self._rate_warn = s.rate_warn

    @staticmethod
    def _format_excluded_groups(groups: Dict[str, List[str]]) -> str:
        lines = []
        for name, pts in groups.items():
            lines.append("%s: %s" % (name, ", ".join(str(p) for p in pts)))
        return "\n".join(lines)

    @staticmethod
    def _parse_points(text: str):
        out = set()
        for part in text.replace(";", ",").split(","):
            part = part.strip()
            if part:
                out.add(part)
        return out

    def _parse_excluded_groups(self, text: str) -> Dict[str, List[str]]:
        groups: Dict[str, List[str]] = {}
        for idx, line in enumerate(text.splitlines()):
            line = line.strip()
            if not line:
                continue
            if ":" in line:
                name, rest = line.split(":", 1)
                name = name.strip() or ("Nhóm %d" % (idx + 1))
            else:
                name, rest = ("Loại trừ", line)
            pts = [p.strip() for p in rest.replace(";", ",").split(",") if p.strip()]
            if pts:
                groups[name] = pts
        return groups

    def _read_settings_from_ui(self) -> Settings:
        elevator_pts = (self._parse_points(self.ed_elevator_pts.text())
                        if self.cb_elevator.isChecked() else set())
        groups = self._parse_excluded_groups(self.te_excluded.toPlainText())
        s = Settings(
            threshold_min=self.sp_threshold.value(),
            elevator_threshold_min=self.sp_elevator.value(),
            excluded_groups=groups,
            elevator_points=elevator_pts,
            day_start=(self.te_day_start.time().hour(), self.te_day_start.time().minute()),
            day_end=(self.te_day_end.time().hour(), self.te_day_end.time().minute()),
            night_start=(self.te_night_start.time().hour(), self.te_night_start.time().minute()),
            night_end=(self.te_night_end.time().hour(), self.te_night_end.time().minute()),
            denom_hours=self.sp_denom.value(),
            rate_ok=self.sp_rate_ok.value(),
            rate_warn=self.sp_rate_warn.value(),
            default_log_dir=self.ed_log_dir.text().strip(),
            default_output_dir=self.ed_out_dir.text().strip(),
            task_log_dir=self._current_task_log_dir(),
        )
        return s

    def _current_task_log_dir(self) -> str:
        """Đường dẫn Tasks Log hiện tại (ưu tiên ô tab Dữ liệu)."""
        data = ""
        if hasattr(self, "ed_task_dir_data"):
            data = self.ed_task_dir_data.text().strip()
        settings = self.ed_task_dir.text().strip() if hasattr(self, "ed_task_dir") else ""
        return data or settings

    def _set_task_log_dir(self, path: str, refresh: bool = True, log: bool = True) -> None:
        """Gắn / cập nhật thư mục Tasks Log trên cả 2 tab."""
        path = (path or "").strip()
        if hasattr(self, "ed_task_dir_data"):
            self.ed_task_dir_data.blockSignals(True)
            self.ed_task_dir_data.setText(path)
            self.ed_task_dir_data.blockSignals(False)
        if hasattr(self, "ed_task_dir"):
            self.ed_task_dir.blockSignals(True)
            self.ed_task_dir.setText(path)
            self.ed_task_dir.blockSignals(False)
        if refresh:
            self._refresh_task_status()
        if log and path:
            self._log("Tasks Log: %s" % path)

    def _on_task_dir_edited(self) -> None:
        sender = self.sender()
        text = ""
        if sender is not None:
            text = sender.text().strip()
        else:
            text = self._current_task_log_dir()
        self._set_task_log_dir(text, refresh=True, log=False)

    def _refresh_task_status(self) -> None:
        if not hasattr(self, "lbl_task_status"):
            return
        path = self._current_task_log_dir()
        if not path:
            self.lbl_task_status.setText(
                "Chưa gắn Tasks Log — kéo-thả folder «Tasks Log 任务» hoặc file "
                "YYYYMMDD.csv (vd 20260702.csv) vào cửa sổ."
            )
            self.lbl_task_status.setStyleSheet("color:#856404;")
            return
        root = Path(path)
        if not root.is_dir():
            self.lbl_task_status.setText(
                "Đường dẫn không tồn tại: %s" % path
            )
            self.lbl_task_status.setStyleSheet("color:#a94442;")
            return
        n = count_task_csv_files(root)
        if n <= 0:
            self.lbl_task_status.setText(
                "Thư mục đã chọn nhưng không thấy file YYYYMMDD.csv:\n%s" % path
            )
            self.lbl_task_status.setStyleSheet("color:#a94442;")
            return
        self.lbl_task_status.setText(
            "Đã gắn Tasks Log — tìm thấy %d file CSV (YYYYMMDD.csv).\n%s" % (n, path)
        )
        self.lbl_task_status.setStyleSheet("color:#2d7d46;")

    # -- Quản lý inventory ----------------------------------------------------

    def _refresh_inventory_table(self) -> None:
        self.folder_table.setRowCount(0)
        for it in self._inventory.items:
            r = self.folder_table.rowCount()
            self.folder_table.insertRow(r)
            kind_it = _item(it.kind_label)
            if it.kind == DataKind.AGV_DAY_FOLDER:
                kind_it.setBackground(COLOR_SAT)
            elif it.kind == DataKind.TASK_CSV:
                kind_it.setBackground(COLOR_OK)
            elif it.kind == DataKind.TASK_API_LOG:
                kind_it.setBackground(QColor(230, 220, 250))
            self.folder_table.setItem(r, 0, kind_it)
            path_it = _item(str(it.path), center=False)
            path_it.setData(Qt.UserRole, it.key)
            path_it.setToolTip(str(it.path))
            self.folder_table.setItem(r, 1, path_it)
            d = it.base_date
            self.folder_table.setItem(r, 2, _item(d.isoformat() if d else "—"))
            self.folder_table.setItem(r, 3, _item(it.note or "", center=False))
        if hasattr(self, "lbl_inventory_badge"):
            self.lbl_inventory_badge.setText(self._inventory.badge_text())
        # Đồng bộ task_log_dir từ CSV đã nhận (cho settings)
        csvs = self._inventory.task_csv_paths()
        if csvs:
            root = resolve_task_root_from_paths(csvs)
            if root is not None:
                self._set_task_log_dir(str(root), refresh=False, log=False)

    def _ingest_paths(self, paths: List[Path], log: bool = True) -> int:
        scan = self._inventory.add_paths(paths)
        self._refresh_inventory_table()
        n = len(scan.added)
        if log and n:
            c = self._inventory.counts()
            self._log(
                "Đã thêm %d mục (tổng: %d CSV / %d API / %d AGV). Bỏ qua trùng: %d"
                % (n, c["csv"], c["api"], c["agv"], scan.skipped)
            )
        return n

    def _existing_folders(self):
        """Tương thích: tập path folder AGV đã có."""
        return set(self._inventory.agv_folders())

    def _add_folder_row(self, folder: Path):
        folder = Path(folder)
        before = self._inventory.counts()["agv"]
        self._inventory.add_paths([folder])
        self._refresh_inventory_table()
        return self._inventory.counts()["agv"] > before

    def _selected_dates(self) -> List[date]:
        dates: List[date] = []
        for it in self._inventory.by_kind(DataKind.AGV_DAY_FOLDER):
            if it.base_date:
                dates.append(it.base_date)
        return dates

    def _guess_log_parents(self) -> List[Path]:
        parents: List[Path] = []
        seen = set()
        for folder in self._inventory.agv_folders():
            p = Path(folder).parent
            key = str(p)
            if key not in seen and p.is_dir():
                seen.add(key)
                parents.append(p)
        rp = self.ed_range_parent.text().strip()
        if rp and Path(rp).is_dir() and rp not in seen:
            parents.append(Path(rp))
        ld = self.ed_log_dir.text().strip()
        if ld and Path(ld).is_dir() and ld not in seen:
            parents.append(Path(ld))
        return parents

    def _suggest_missing_days(self, interactive: bool = True) -> int:
        """Gợi ý / bổ sung ngày thiếu trong khoảng đã chọn. Trả về số folder thêm.

        Khoảng ngày được chọn có thể “lủng” (nghỉ, chưa copy log…) — không chặn
        phân tích. Chỉ hỏi khi thực sự tìm thấy thư mục log có thể bổ sung.
        """
        selected = self._selected_dates()
        missing = missing_dates_in_range(selected)
        if not missing:
            return 0

        parents = self._guess_log_parents()
        found: Dict[date, Path] = {}
        for parent in parents:
            found.update(find_log_folders_for_dates(parent, missing))

        found_dates = sorted(found.keys())
        not_found = [d for d in missing if d not in found]
        missing_txt = ", ".join(d.isoformat() for d in missing[:12]) + (
            "…" if len(missing) > 12 else "")
        not_found_txt = ", ".join(d.isoformat() for d in not_found[:12]) + (
            "…" if len(not_found) > 12 else "")

        if not found_dates:
            # Cho phép khoảng ngày tùy ý — chỉ ghi nhật ký, không popup chặn.
            self._log(
                "Khoảng đã chọn thiếu %d ngày (bỏ qua, không chặn): %s"
                % (len(missing), missing_txt))
            if not_found:
                self._log("Không tìm thấy thư mục cho: %s" % not_found_txt)
            return 0

        msg_lines = [
            "Phát hiện %d ngày thiếu trong khoảng đã chọn:" % len(missing),
            missing_txt,
            "\nTìm thấy thư mục log cho %d ngày: %s"
            % (len(found_dates),
               ", ".join(d.isoformat() for d in found_dates[:12])
               + ("…" if len(found_dates) > 12 else "")),
        ]
        if not_found:
            msg_lines.append("\nKhông tìm thấy thư mục cho: %s" % not_found_txt)

        if interactive:
            reply = QMessageBox.question(
                self, "Bổ sung ngày thiếu?",
                "\n".join(msg_lines) + "\n\nThêm các thư mục tìm được ngay?"
                "\n(Chọn No để giữ nguyên danh sách hiện tại.)",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                self._log("Người dùng bỏ qua bổ sung %d ngày thiếu." % len(found_dates))
                return 0

        added = 0
        for d in found_dates:
            if self._add_folder_row(found[d]):
                added += 1
                self._log("Đã bổ sung ngày thiếu %s: %s" % (d.isoformat(), found[d].name))
        return added

    def on_add_any(self):
        start = self.ed_log_dir.text().strip() or ""
        folder = QFileDialog.getExistingDirectory(
            self, "Chọn thư mục / nguồn dữ liệu (tự phân loại)", start)
        if folder:
            n = self._ingest_paths([Path(folder)])
            if n:
                self._suggest_missing_days(interactive=True)
            else:
                self._log("Không thêm được mục mới từ: %s" % folder)

    def on_add_folder(self):
        self.on_add_any()

    def on_add_parent(self):
        start = self.ed_log_dir.text().strip() or ""
        parent = QFileDialog.getExistingDirectory(
            self, "Chọn thư mục cha (quét Log + CSV + API logs)", start)
        if not parent:
            return
        parent_path = Path(parent)
        self.ed_range_parent.setText(str(parent_path))
        n = self._ingest_paths([parent_path])
        self._log("Quét thư mục cha: thêm %d mục từ %s" % (n, parent))
        if n == 0:
            QMessageBox.information(
                self, "Thông báo",
                "Không nhận diện được Log AGV / Tasks CSV / API logs trong thư mục này.")
        else:
            self._suggest_missing_days(interactive=True)

    def on_pick_range_parent(self):
        start = (self.ed_range_parent.text().strip()
                 or self.ed_log_dir.text().strip() or "")
        folder = QFileDialog.getExistingDirectory(
            self, "Chọn thư mục gốc chứa Log{ngày}", start)
        if folder:
            self.ed_range_parent.setText(folder)

    def on_add_date_range(self):
        parent_txt = self.ed_range_parent.text().strip() or self.ed_log_dir.text().strip()
        if not parent_txt:
            QMessageBox.warning(self, "Thiếu thư mục gốc",
                                "Hãy chọn thư mục cha chứa các Log{YYYYMMDD}.")
            return
        parent = Path(parent_txt)
        if not parent.is_dir():
            QMessageBox.warning(self, "Không hợp lệ", "Thư mục gốc không tồn tại.")
            return

        q_from = self.de_from.date()
        q_to = self.de_to.date()
        d_from = date(q_from.year(), q_from.month(), q_from.day())
        d_to = date(q_to.year(), q_to.month(), q_to.day())
        if d_to < d_from:
            d_from, d_to = d_to, d_from

        wanted: List[date] = []
        cur = d_from
        while cur <= d_to:
            wanted.append(cur)
            cur += timedelta(days=1)

        found = find_log_folders_for_dates(parent, wanted)
        added = 0
        for d in wanted:
            path = found.get(d)
            if path is None:
                continue
            if self._add_folder_row(path):
                added += 1
        missing = [d for d in wanted if d not in found]
        self._log(
            "Khoảng %s → %s: thêm %d thư mục, thiếu file: %d ngày"
            % (d_from.isoformat(), d_to.isoformat(), added, len(missing))
        )
        if missing:
            self._log("Không có Log cho: %s"
                      % ", ".join(d.isoformat() for d in missing[:20]))
        if added == 0:
            QMessageBox.information(
                self, "Thông báo",
                "Không tìm thấy thư mục Log trong khoảng đã chọn tại:\n%s" % parent)

    def on_remove_selected(self):
        rows = sorted({i.row() for i in self.folder_table.selectedIndexes()}, reverse=True)
        keys = []
        for r in rows:
            it = self.folder_table.item(r, 1)
            if it is not None:
                key = it.data(Qt.UserRole)
                if key:
                    keys.append(key)
        if keys:
            self._inventory.remove_keys(keys)
            self._refresh_inventory_table()
            self._log("Đã xóa %d mục khỏi inventory." % len(keys))

    def on_clear_folders(self):
        self._inventory.clear()
        self._refresh_inventory_table()
        self._log("Đã xóa toàn bộ nguồn dữ liệu.")

    def on_pick_log_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục log mặc định",
                                                  self.ed_log_dir.text().strip() or "")
        if folder:
            self.ed_log_dir.setText(folder)
            if not self.ed_range_parent.text().strip():
                self.ed_range_parent.setText(folder)

    def on_pick_out_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục xuất mặc định",
                                                  self.ed_out_dir.text().strip() or "")
        if folder:
            self.ed_out_dir.setText(folder)

    def on_pick_task_dir(self):
        start = self._current_task_log_dir()
        folder = QFileDialog.getExistingDirectory(
            self, "Chọn thư mục Tasks Log (CSV + có thể kèm logs/)", start or "")
        if not folder:
            return
        root = Path(folder)
        n = self._ingest_paths([root])
        if n == 0 and not looks_like_task_log_dir(root):
            QMessageBox.warning(
                self, "Không thấy dữ liệu Tasks",
                "Thư mục không chứa YYYYMMDD.csv hoặc logs/*.log:\n%s" % folder)
        self._set_task_log_dir(str(root), refresh=False, log=True)

    def on_clear_task_dir(self) -> None:
        # Xóa chỉ mục CSV khỏi inventory
        keys = [it.key for it in self._inventory.by_kind(DataKind.TASK_CSV)]
        self._inventory.remove_keys(keys)
        self._set_task_log_dir("", refresh=False, log=False)
        self._refresh_inventory_table()
        self._log("Đã bỏ Tasks CSV khỏi inventory.")

    # -- Kéo thả --------------------------------------------------------------

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls()
                 if url.toLocalFile()]
        paths = [p for p in paths if p.exists()]
        if not paths:
            event.acceptProposedAction()
            return

        before = self._inventory.counts()
        n = self._ingest_paths(paths)
        after = self._inventory.counts()

        if n:
            self._suggest_missing_days(interactive=True)
            self.statusBar().showMessage(self._inventory.badge_text(), 8000)
        else:
            QMessageBox.information(
                self, "Không nhận diện được",
                "Hãy kéo-thả:\n"
                "• Thư mục LogYYYYMMDD / file Log*.txt\n"
                "• Thư mục Tasks Log 任务 (CSV YYYYMMDD + logs/*.log)\n"
                "• File YYYYMMDD.csv hoặc YYYYMMDD.log / debug_*.log\n\n"
                "Hiện có: %d CSV / %d API / %d AGV"
                % (before["csv"], before["api"], before["agv"])
            )
        event.acceptProposedAction()
        _ = after  # silence lint

    # -- Phân tích ------------------------------------------------------------

    def on_analyze(self):
        # Gợi ý ngày thiếu trước khi chạy
        self._suggest_missing_days(interactive=True)

        counts = self._inventory.counts()
        if counts["total"] <= 0:
            QMessageBox.warning(
                self, "Chưa có dữ liệu",
                "Hãy kéo-thả hoặc thêm ít nhất một nguồn:\n"
                "Log AGV ngày / Tasks CSV / Tasks API logs.")
            return

        self._settings = self._read_settings_from_ui()
        self._rate_ok = self._settings.rate_ok
        self._rate_warn = self._settings.rate_warn

        # Nếu settings có task_log_dir nhưng inventory chưa có CSV → nạp thêm
        task_dir = self._settings.task_log_dir
        if task_dir and Path(task_dir).is_dir() and counts["csv"] <= 0:
            self._ingest_paths([Path(task_dir)], log=True)
            counts = self._inventory.counts()

        if counts["agv"] <= 0 and counts["csv"] <= 0 and counts["api"] <= 0:
            QMessageBox.warning(self, "Chưa có dữ liệu", "Inventory trống sau khi quét.")
            return

        if counts["agv"] <= 0 and (counts["csv"] > 0 or counts["api"] > 0):
            reply = QMessageBox.question(
                self, "Không có Log AGV",
                "Inventory chỉ có Tasks CSV / API logs — bất thường sẽ = 0.\n"
                "Vẫn phân tích KPI nhiệm vụ / điều phối?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if reply != QMessageBox.Yes:
                return

        self._analyze_cancelled = False
        self._cancel = CancelToken()
        self.b_analyze.setEnabled(False)
        self.b_cancel.setEnabled(True)
        self.b_xlsx.setEnabled(False)
        self.b_csv.setEnabled(False)
        self.progress.setValue(0)
        self._set_banner("")
        n_workers = default_workers()
        self.lbl_job.setText(
            "Đang phân tích · %d AGV / %d CSV / %d API · %d worker"
            % (counts["agv"], counts["csv"], counts["api"], n_workers))
        self._log(
            "=== Bắt đầu phân tích inventory: %d AGV + %d CSV + %d API (%d worker) ==="
            % (counts["agv"], counts["csv"], counts["api"], n_workers))

        self._worker = AnalyzeWorker(
            self._inventory, self._settings, self._cancel, n_workers)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_analyze_done)
        self._worker.failed.connect(self._on_analyze_failed)
        self._worker.start()

    def on_cancel_analyze(self):
        if self._cancel is not None:
            self._cancel.cancel()
            self._analyze_cancelled = True
            self.b_cancel.setEnabled(False)
            self.lbl_job.setText("Đang hủy… giữ kết quả đã xong")
            self._log("Người dùng yêu cầu HỦY phân tích.")

    def _set_banner(self, text: str) -> None:
        if text:
            self.lbl_banner.setText(text)
            self.lbl_banner.setVisible(True)
        else:
            self.lbl_banner.setText("")
            self.lbl_banner.setVisible(False)

    def _on_progress(self, done: int, total: int, message: str):
        pct = int(done / total * 100) if total else 0
        self.progress.setValue(pct)
        self._log(message)
        self.lbl_job.setText("[%d/%d] %s" % (done, total, message))
        self.statusBar().showMessage(message)

    def _on_analyze_failed(self, tb: str):
        self.b_analyze.setEnabled(True)
        self.b_cancel.setEnabled(False)
        self.lbl_job.setText("")
        self._log("LỖI NGHIÊM TRỌNG:\n" + tb)
        QMessageBox.critical(self, "Lỗi", "Phân tích thất bại:\n" + tb)

    def _on_analyze_done(self, outcome: object):
        if isinstance(outcome, AnalyzeOutcome):
            results = outcome.results
            cancelled = outcome.cancelled or self._analyze_cancelled
            errors = outcome.errors
            workers = outcome.workers_used
        else:
            # Tương thích nếu emit List[DayResult] cũ
            results = list(outcome) if outcome else []
            cancelled = self._analyze_cancelled
            errors = []
            workers = 1

        self._day_results = sorted(results, key=lambda d: d.base_date)
        self.b_analyze.setEnabled(True)
        self.b_cancel.setEnabled(False)
        self.b_xlsx.setEnabled(bool(results))
        self.b_csv.setEnabled(bool(results))
        self.progress.setValue(100 if not cancelled else max(self.progress.value(), 1))
        self._populated_tabs = set()
        self._populate_visible_tab(force=True)

        missing_task = sum(
            1 for d in self._day_results
            if d.task_stats is None or not getattr(d.task_stats, "has_data", False)
        )

        banner_parts = []
        if cancelled:
            banner_parts.append(
                "Phân tích đã HỦY — đang hiển thị %d ngày đã xử lý xong."
                % len(self._day_results))
        banner_parts.extend(aggregate.source_gap_messages(self._day_results))
        if missing_task and self._inventory.counts()["csv"] > 0:
            banner_parts.append(
                "%d/%d ngày thiếu Tasks CSV (稼動 có thể trống)."
                % (missing_task, len(self._day_results) or 1))
        if errors:
            banner_parts.append("%d lỗi khi đọc (xem nhật ký)." % len(errors))
            for e in errors[:5]:
                self._log("Lỗi: %s" % e)
        inv_banner = self._inventory.coverage_banner()
        if inv_banner and inv_banner not in " | ".join(banner_parts):
            banner_parts.append(inv_banner)
        self._set_banner("  |  ".join(banner_parts))

        tag = " (HỦY — partial)" if cancelled else ""
        self._log("=== Hoàn tất%s: %d ngày, %d worker ==="
                  % (tag, len(results), workers))
        self.lbl_job.setText(
            "Xong%s: %d ngày · %d worker" % (tag, len(results), workers))
        self.statusBar().showMessage(
            "Hoàn tất%s: %d ngày dữ liệu." % (tag, len(results)))
        self.tabs.setCurrentIndex(0)

    # -- Đổ dữ liệu vào bảng --------------------------------------------------

    def _populate_all(self):
        """Đổ tất cả tab (dùng khi cần force full refresh)."""
        self._populated_tabs = set()
        for i in range(self.tabs.count()):
            self._populate_tab_index(i)
            self._populated_tabs.add(i)

    def _on_result_tab_changed(self, index: int):
        if not self._day_results:
            return
        self._populate_tab_index(index)

    def _populate_visible_tab(self, force: bool = False):
        idx = self.tabs.currentIndex()
        if force:
            self._populated_tabs.discard(idx)
        self._populate_tab_index(idx)

    def _populate_tab_index(self, index: int):
        if index in self._populated_tabs:
            return
        # Map theo thứ tự tab đã tạo
        loaders = [
            self._populate_dashboard,   # 0 Tổng quan
            self._populate_daily,       # 1 Theo ngày
            self._populate_points,      # 2 Theo điểm
            self._populate_cars,        # 3 Theo xe
            self._populate_models,      # 4 Theo model
            self._populate_weekly,      # 5 Theo tuần
            self._populate_monthly,     # 6 Theo tháng
            self._populate_api,         # 7 Điều phối (API)
        ]
        if 0 <= index < len(loaders):
            loaders[index]()
            self._populated_tabs.add(index)

    def _denom(self) -> float:
        return self._settings.denom_hours

    def _populate_dashboard(self):
        days = self._day_results
        denom = self._denom()
        if not days:
            return
        summ = aggregate.overall_summary(days, denom)

        d0 = min(d.base_date for d in days).isoformat()
        d1 = max(d.base_date for d in days).isoformat()
        self.lbl_dash_sub.setText(
            "Khoảng dữ liệu: %s → %s   |   Mẫu số: %g giờ/ngày   |   "
            "AGV %d · CSV %d · API %d ngày   |   稼動 %.2f%%   |   %d task"
            % (d0, d1, denom, summ.days_with_agv, summ.days_with_csv,
               summ.days_with_api, summ.utilization, summ.task_count))

        rate = summ.abnormal_rate
        rate_accent = self._accent_hex(rate)
        self.kpi_days.set_value(summ.num_days, "ngày dữ liệu", "#3a76d8")
        self.kpi_cars.set_value(summ.distinct_cars, "xe khác nhau", "#8c64c8")
        self.kpi_events.set_value(summ.abnormal_count,
                                  "TB %.1f lượt/ngày" % summ.avg_abnormal_per_day, "#d88a3a")
        self.kpi_hours.set_value("%.1f" % (summ.abnormal_hours),
                                 "TB dừng %.1f phút/lượt" % summ.avg_stay_min, "#d88a3a")
        self.kpi_rate.set_value("%.2f%%" % rate, "toàn bộ dữ liệu", rate_accent)

        self.kpi_util.set_value("%.2f%%" % summ.utilization,
                                "từ Tasks Log (completed)", "#2d7d46")
        self.kpi_tasks.set_value(summ.task_count, "nhiệm vụ trong cửa sổ ca", "#3a76d8")
        self.kpi_timeout.set_value(summ.timeout_count, "final_state = timeout",
                                   "#c0504d" if summ.timeout_count else "#2d7d46")
        cycle_min = summ.avg_cycle_sec / 60.0 if summ.avg_cycle_sec else 0.0
        self.kpi_cycle.set_value(
            "%.0fs" % summ.avg_cycle_sec if summ.avg_cycle_sec else "-",
            "≈ %.1f phút/task" % cycle_min if summ.avg_cycle_sec else "chưa có dữ liệu",
            "#8c64c8")

        self.kpi_api_create.set_value(
            summ.api_create_count, "lệnh POST taskCreate", "#3a76d8")
        self.kpi_api_poll.set_value(
            summ.api_poll_count,
            "%d task unique" % summ.api_unique_tasks, "#8c64c8")
        self.kpi_api_err.set_value(
            summ.api_error_count, "stateCode ≠ 0",
            "#c0504d" if summ.api_error_count else "#2d7d46")
        self.kpi_api_hot.set_value(
            summ.api_hot_point or "-",
            "%d lần trong payload" % summ.api_hot_point_count if summ.api_hot_point else "chưa có API log",
            "#d88a3a")

        if summ.worst_day:
            wr = summ.worst_day.abnormal_rate(denom)
            self.kpi_worst.set_value(summ.worst_day.base_date.isoformat(),
                                     "%s - %.2f%%" % (aggregate.weekday_name(summ.worst_day.base_date), wr),
                                     self._accent_hex(wr))
        if summ.best_day:
            br = summ.best_day.abnormal_rate(denom)
            self.kpi_best.set_value(summ.best_day.base_date.isoformat(),
                                    "%s - %.2f%%" % (aggregate.weekday_name(summ.best_day.base_date), br),
                                    self._accent_hex(br))
        if summ.top_car:
            self.kpi_topcar.set_value("Xe %s" % summ.top_car.car_id,
                                      "%d lượt - %.1f phút" % (summ.top_car.abnormal_count,
                                                               summ.top_car.abnormal_min),
                                      "#c0504d")
        if summ.top_point:
            self.kpi_toppoint.set_value("Điểm %s" % summ.top_point.point_id,
                                        "%d lượt - %d xe" % (summ.top_point.abnormal_count,
                                                             summ.top_point.car_count),
                                        "#c0504d")

        # Xu hướng bất thường — đủ điểm để hover; nhãn X tự thưa + xoay trong chart
        series = aggregate.trend_series(days, denom)
        points = [
            (d.strftime("%m-%d"), v,
             "%s (%s)" % (d.isoformat(), aggregate.weekday_name(d)))
            for d, v in series
        ]
        self.chart_trend.set_data(points, suffix="%",
                                  thresholds=[(self._rate_ok, BAR_WARN), (self._rate_warn, BAR_BAD)])

        # Xu hướng 稼動
        util_series = aggregate.utilization_trend_series(days)
        util_points = [
            (d.strftime("%m-%d"), v,
             "%s (%s)" % (d.isoformat(), aggregate.weekday_name(d)))
            for d, v in util_series
        ]
        self.chart_util_trend.set_data(util_points, suffix="%")

        # Xu hướng taskCreate
        api_series = aggregate.api_create_trend_series(days)
        api_points = [
            (d.strftime("%m-%d"), v,
             "%s (%s)" % (d.isoformat(), aggregate.weekday_name(d)))
            for d, v in api_series
        ]
        self.chart_api_trend.set_data(api_points, suffix="")

        # Top điểm / top xe
        top_points = aggregate.aggregate_points(days)[:10]
        self.chart_points.set_data(
            [("Điểm %s" % p.point_id, p.abnormal_count, BAR_ACCENT) for p in top_points])
        top_cars = aggregate.aggregate_cars(days)[:10]
        self.chart_cars.set_data(
            [("Xe %s" % c.car_id, c.abnormal_count, BAR_ACCENT2) for c in top_cars])

        # Ca ngày / đêm
        dn = aggregate.daynight_split(days, denom)
        self.chart_daynight.set_data(
            [(a.label, a.abnormal_rate, self.rate_qcolor(a.abnormal_rate)) for a in dn], suffix="%")

        # Thứ trong tuần (chỉ hiện các thứ có dữ liệu)
        wp = [s for s in aggregate.weekday_pattern(days, denom) if s.num_days > 0]
        self.chart_weekday.set_data(
            [(s.name, s.abnormal_rate, self.rate_qcolor(s.abnormal_rate)) for s in wp], suffix="%")

        # Mức độ nặng
        buckets = aggregate.severity_buckets(days)
        sev_colors = [BAR_OK, BAR_WARN, QColor(230, 130, 60), BAR_BAD]
        self.chart_severity.set_data(
            [(b.label, b.count, sev_colors[i]) for i, b in enumerate(buckets)])

    def _accent_hex(self, rate: float) -> str:
        if rate >= self._rate_warn:
            return "#c0504d"
        if rate >= self._rate_ok:
            return "#e0a030"
        return "#2d7d46"

    @staticmethod
    def _downsample_series(points, max_points: int = 20):
        """Giữ tối đa max_points điểm cho chart tháng (đều theo chỉ số)."""
        if len(points) <= max_points:
            return points
        step = max(1, len(points) // max_points)
        out = points[::step]
        if out[-1] != points[-1]:
            out.append(points[-1])
        return out[:max_points + 1]

    def _populate_daily(self):
        t = self.tbl_daily
        t.setRowCount(0)
        denom = self._denom()
        worst = []
        for d in self._day_results:
            r = t.rowCount(); t.insertRow(r)
            has_agv = getattr(d, "has_agv_log", True) and d.car_count > 0
            day_rate = d.day.abnormal_rate(denom)
            night_rate = d.night.abnormal_rate(denom)
            full_rate = d.abnormal_rate(denom)
            util = d.utilization
            sat = d.is_saturday
            warn = None if has_agv else COLOR_WARN
            t.setItem(r, 0, _item(d.base_date.isoformat(),
                                  color=COLOR_SAT if sat else warn))
            t.setItem(r, 1, _item(aggregate.weekday_name(d.base_date),
                                  color=COLOR_SAT if sat else warn))
            t.setItem(r, 2, _item(d.car_count if has_agv else "-", color=warn))
            t.setItem(r, 3, _item(d.abnormal_count if has_agv else "-", color=warn))
            t.setItem(r, 4, _item(day_rate if has_agv else "-",
                                  color=self.rate_color(day_rate) if has_agv else warn))
            t.setItem(r, 5, _item(night_rate if has_agv else "-",
                                  color=self.rate_color(night_rate) if has_agv else warn))
            t.setItem(r, 6, _item(full_rate if has_agv else "-",
                                  color=self.rate_color(full_rate) if has_agv else warn))
            t.setItem(r, 7, _item(util if util else "-"))
            t.setItem(r, 8, _item(d.task_count if d.task_count else "-"))
            t.setItem(r, 9, _item(d.timeout_count if d.timeout_count else "-"))
            t.setItem(r, 10, _item(d.api_create_count if d.api_create_count else "-"))
            t.setItem(r, 11, _item(d.log_file_count if has_agv else "-"))
            t.item(r, 0).setData(Qt.UserRole, d)
            if has_agv:
                worst.append((full_rate, d))

        worst.sort(key=lambda x: (-x[0], x[1].base_date))
        self.chart_day_compare.set_data(
            [(d.base_date.strftime("%m-%d"), rate, self.rate_qcolor(rate),
              "%s (%s)\nTỷ lệ bất thường %.2f%%\n%d lượt · %d xe"
              % (d.base_date.isoformat(), aggregate.weekday_name(d.base_date),
                 rate, d.abnormal_count, d.car_count))
             for rate, d in worst[:10]],
            suffix="%")

        if t.rowCount():
            # Mặc định xem ngày mới nhất CÓ Log AGV (bảng xếp tăng dần theo ngày);
            # ngày chỉ có CSV/API không đo được bất thường nên không mở đầu tiên.
            default_row = t.rowCount() - 1
            for r in range(t.rowCount() - 1, -1, -1):
                d = t.item(r, 0).data(Qt.UserRole)
                if getattr(d, "has_agv_log", True) and d.car_count > 0:
                    default_row = r
                    break
            t.selectRow(default_row)
            self._on_daily_selected()
        else:
            self._clear_daily_detail("Không có ngày nào trong kết quả phân tích")

    @staticmethod
    def _table_note(table: QTableWidget, text: str) -> None:
        """Xoá bảng và đặt một dòng ghi chú trải hết chiều ngang."""
        table.setRowCount(0)
        table.clearSpans()
        r = table.rowCount(); table.insertRow(r)
        table.setItem(r, 0, _item(text, center=False, color=COLOR_WARN))
        table.setSpan(r, 0, 1, max(1, table.columnCount()))

    def _clear_daily_detail(self, reason: str) -> None:
        """Không có ngày nào được chọn → nói rõ lý do thay vì để bảng trống."""
        for tbl in (self.tbl_daily_detail, self.tbl_daily_tasks, self.tbl_daily_api):
            self._table_note(tbl, "(%s)" % reason)
        for i, name in enumerate(("Chi tiết bất thường", "Chi tiết Tasks Log", "API logs")):
            self.daily_bottom.setTabText(i, name)
        if hasattr(self, "lbl_daily_detail_title"):
            self.lbl_daily_detail_title.setText("Chi tiết ngày đã chọn")
        self._fill_day_report(None)

    def _fill_detail_records(self, table: QTableWidget, day: DayResult):
        table.setRowCount(0)
        table.clearSpans()
        shown = 0
        total = day.abnormal_count
        truncated = False
        if total <= 0:
            self._table_note(
                table,
                "(Ngày %s: không có lượt dừng vượt ngưỡng %d phút — "
                "hoặc ngày này chỉ có Tasks CSV / API, chưa nạp Log AGV)"
                % (day.base_date.isoformat(), self._settings.threshold_min))
            return
        for shift in (day.day, day.night):
            label = "Ca ngày" if shift.label == "day" else "Ca đêm"
            by_car = shift.abnormal_by_car()
            for car_id in sorted(by_car.keys()):
                for rec in by_car[car_id]:
                    if shown >= DETAIL_ROW_LIMIT:
                        truncated = True
                        break
                    r = table.rowCount(); table.insertRow(r)
                    table.setItem(r, 0, _item(label))
                    table.setItem(r, 1, _item(car_id))
                    table.setItem(r, 2, _item("Điểm %s" % rec.point_id))
                    table.setItem(r, 3, _item(rec.arrival_time.strftime("%H:%M:%S")))
                    table.setItem(r, 4, _item(rec.stay_min))
                    shown += 1
                if truncated:
                    break
            if truncated:
                break
        if truncated:
            r = table.rowCount(); table.insertRow(r)
            remain = max(0, total - shown)
            it = _item(
                "… còn %d dòng — xem Excel để đủ chi tiết" % remain,
                center=False, color=COLOR_WARN)
            table.setItem(r, 0, it)
            table.setSpan(r, 0, 1, 5)

    def _fill_task_rows(self, table: QTableWidget, day: DayResult) -> None:
        """Đổ chi tiết Tasks Log của một ngày (giới hạn DETAIL_ROW_LIMIT)."""
        table.setRowCount(0)
        table.clearSpans()
        ts = day.task_stats if isinstance(day.task_stats, DayTaskStats) else None
        if ts is None or not ts.rows:
            self._table_note(
                table,
                "(Không có Tasks Log cho ngày %s — kiểm tra Cài đặt › Thư mục Tasks Log "
                "có file %s.csv không)"
                % (day.base_date.isoformat(), day.base_date.strftime("%Y%m%d")))
            return

        from ..core.abnormal import calc_shift_ranges
        day_start, day_end, night_start, night_end = calc_shift_ranges(
            day.base_date, self._settings)
        from ..core.tasks import shift_label_for_task

        shown = 0
        total = len(ts.rows)
        truncated = False
        for tr in ts.rows:
            if shown >= DETAIL_ROW_LIMIT:
                truncated = True
                break
            shift = shift_label_for_task(
                tr.complete_time, day_start, day_end, night_start, night_end)
            label = "Ca ngày" if shift == "day" else ("Ca đêm" if shift == "night" else "")
            r = table.rowCount(); table.insertRow(r)
            table.setItem(r, 0, _item(label))
            table.setItem(r, 1, _item(tr.car_id))
            table.setItem(r, 2, _item(tr.model))
            table.setItem(r, 3, _item(
                tr.send_time.strftime("%H:%M:%S") if tr.send_time else ""))
            table.setItem(r, 4, _item(
                tr.complete_time.strftime("%H:%M:%S") if tr.complete_time else ""))
            table.setItem(r, 5, _item(round(tr.duration_sec / 60.0, 2)))
            table.setItem(r, 6, _item(tr.final_state))
            table.setItem(r, 7, _item(tr.task_id, center=False))
            shown += 1
        if truncated:
            r = table.rowCount(); table.insertRow(r)
            remain = max(0, total - shown)
            it = _item(
                "… còn %d task — xem Excel sheet «Chi tiết Tasks Log»" % remain,
                center=False, color=COLOR_WARN)
            table.setItem(r, 0, it)
            table.setSpan(r, 0, 1, 8)

    def _selected_day(self, table: QTableWidget) -> Optional[DayResult]:
        rows = {i.row() for i in table.selectedIndexes()}
        if not rows:
            return None
        r = min(rows)
        it = table.item(r, 0)
        return it.data(Qt.UserRole) if it else None

    def _fill_day_report(self, day: Optional[DayResult]) -> None:
        """Đổ phần báo cáo (kết luận + KPI + biểu đồ) của ngày đã chọn."""
        cards = [self.kpi_d_rate, self.kpi_d_day, self.kpi_d_night, self.kpi_d_cars,
                 self.kpi_d_events, self.kpi_d_util, self.kpi_d_tasks, self.kpi_d_api]
        charts = [self.chart_day_points, self.chart_day_cars,
                  self.chart_day_shift, self.chart_day_hours]

        if day is None:
            self.lbl_day_title.setText("Báo cáo ngày — chọn một ngày ở bảng trên")
            self.lbl_day_verdict.setText("")
            self.lbl_day_verdict.setStyleSheet(
                "padding:8px; border-radius:6px; background:#eef5ff; color:#1F4E79;")
            for card in cards:
                card.set_value("-", "")
            for chart in charts:
                chart.set_data([])
            return

        denom = self._denom()
        has_agv = getattr(day, "has_agv_log", True) and day.car_count > 0
        rate = day.abnormal_rate(denom)
        day_rate = day.day.abnormal_rate(denom)
        night_rate = day.night.abnormal_rate(denom)
        util = day.utilization
        ts = day.task_stats if isinstance(day.task_stats, DayTaskStats) else None
        api = day.api_log_stats if isinstance(day.api_log_stats, DayApiLogStats) else None

        self.lbl_day_title.setText(
            "Báo cáo ngày %s (%s)"
            % (day.base_date.isoformat(), aggregate.weekday_name(day.base_date)))

        if has_agv:
            if rate >= self._rate_warn:
                status, bg, fg = "CẦN XỬ LÝ", "#f8d7da", "#9C0006"
            elif rate >= self._rate_ok:
                status, bg, fg = "CẦN CHÚ Ý", "#fff3cd", "#9C5700"
            else:
                status, bg, fg = "ỔN", "#d4edda", "#006100"
            self.lbl_day_verdict.setText(
                "%s — Tỷ lệ bất thường %.2f%% (ổn khi <%g%%, cần xử lý khi ≥%g%%) · "
                "%d lượt kẹt · %d xe · 稼動 %.2f%% · %d nhiệm vụ"
                % (status, rate, self._rate_ok, self._rate_warn,
                   day.abnormal_count, day.car_count, util, day.task_count))
            self.lbl_day_verdict.setStyleSheet(
                "padding:8px; border-radius:6px; background:%s; color:%s; font-weight:bold;"
                % (bg, fg))
        else:
            self.lbl_day_verdict.setText(
                "Ngày này chưa có Log AGV nên không đo được tỷ lệ bất thường · "
                "稼動 %.2f%% · %d nhiệm vụ · %d lệnh API (từ Tasks CSV / API log)"
                % (util, day.task_count, day.api_create_count))
            self.lbl_day_verdict.setStyleSheet(
                "padding:8px; border-radius:6px; background:#eef5ff; color:#1F4E79;")

        no_log_sub = "chưa nạp Log AGV"
        self.kpi_d_rate.set_value(
            "%.2f%%" % rate if has_agv else "-",
            "cả ngày (mẫu số %g giờ/xe)" % denom if has_agv else no_log_sub,
            self._accent_hex(rate) if has_agv else "#808080")
        self.kpi_d_day.set_value(
            "%.2f%%" % day_rate if has_agv else "-",
            ("%d lượt · %d xe" % (day.day.abnormal_count, day.day.car_count)
             if has_agv else no_log_sub),
            self._accent_hex(day_rate) if has_agv else "#808080")
        self.kpi_d_night.set_value(
            "%.2f%%" % night_rate if has_agv else "-",
            ("%d lượt · %d xe" % (day.night.abnormal_count, day.night.car_count)
             if has_agv else no_log_sub),
            self._accent_hex(night_rate) if has_agv else "#808080")
        self.kpi_d_cars.set_value(
            day.car_count if has_agv else "-",
            "xe xuất hiện trong Log AGV" if has_agv else no_log_sub,
            "#8c64c8" if has_agv else "#808080")
        self.kpi_d_events.set_value(
            day.abnormal_count if has_agv else "-",
            ("tổng %.0f phút dừng" % (day.abnormal_hours * 60.0)
             if has_agv else no_log_sub),
            "#d88a3a" if has_agv else "#808080")
        util_sub = "từ Tasks Log (completed)"
        if ts is not None and ts.has_data:
            util_sub = "ca ngày %.2f%% · ca đêm %.2f%%" % (
                ts.utilization_day, ts.utilization_night)
        self.kpi_d_util.set_value(
            "%.2f%%" % util if util else "-", util_sub, "#2d7d46")
        task_sub = "chưa có Tasks CSV"
        if ts is not None and ts.has_data:
            task_sub = "timeout %d · TB %.1f phút/nhiệm vụ" % (
                day.timeout_count, ts.avg_cycle_sec / 60.0)
        self.kpi_d_tasks.set_value(
            day.task_count if day.task_count else "-", task_sub, "#3a76d8")
        api_sub = "chưa có API log"
        if api is not None and api.has_data:
            api_sub = "%d poll · %d lỗi · hot %s" % (
                api.poll_count, api.api_error_count, api.hot_point or "-")
        self.kpi_d_api.set_value(
            day.api_create_count if day.api_create_count else "-",
            api_sub,
            "#c0504d" if (api is not None and api.api_error_count) else "#3a76d8")

        points = sorted(aggregate.aggregate_points([day]),
                        key=lambda p: (-p.abnormal_count, p.point_id))[:10]
        self.chart_day_points.set_data([
            ("Điểm %s" % p.point_id, p.abnormal_count, BAR_ACCENT,
             "Điểm %s\n%d lượt kẹt · tổng %.0f phút\n"
             "TB %.1f phút · Max %.1f phút\nXe nhiều nhất: %s (%d)"
             % (p.point_id, p.abnormal_count, p.abnormal_min,
                p.avg_min, p.max_min, p.top_car[0] or "-", p.top_car[1]))
            for p in points
        ])
        cars = sorted(aggregate.aggregate_cars([day]),
                      key=lambda c: (-c.abnormal_count, c.car_id))[:10]
        self.chart_day_cars.set_data([
            ("Xe %s" % c.car_id, c.abnormal_count, BAR_ACCENT2,
             "Xe %s\n%d lượt kẹt · tổng %.0f phút\n"
             "TB %.1f phút · Max %.1f phút\nĐiểm hay kẹt: %s (%d)"
             % (c.car_id, c.abnormal_count, c.abnormal_min,
                c.avg_min, c.max_min, c.hot_point or "-", c.hot_point_count))
            for c in cars
        ])
        if has_agv:
            self.chart_day_shift.set_data(
                [("Ca ngày", day_rate, self.rate_qcolor(day_rate),
                  "Ca ngày\nTỷ lệ bất thường %.2f%%\n%d lượt · %d xe"
                  % (day_rate, day.day.abnormal_count, day.day.car_count)),
                 ("Ca đêm", night_rate, self.rate_qcolor(night_rate),
                  "Ca đêm\nTỷ lệ bất thường %.2f%%\n%d lượt · %d xe"
                  % (night_rate, day.night.abnormal_count, day.night.car_count))],
                suffix="%")
        else:
            self.chart_day_shift.set_data([])

        hour_counts: Dict[int, int] = {}
        hour_mins: Dict[int, float] = {}
        for shift in (day.day, day.night):
            for rec in shift.records:
                h = rec.arrival_time.hour
                hour_counts[h] = hour_counts.get(h, 0) + 1
                hour_mins[h] = hour_mins.get(h, 0.0) + rec.stay_min
        self.chart_day_hours.set_data([
            ("%02dh" % h, hour_counts[h], BAR_ACCENT,
             "Khung giờ %02d:00–%02d:59\n%d lượt bất thường · tổng %.0f phút"
             % (h, h, hour_counts[h], hour_mins.get(h, 0.0)))
            for h in sorted(hour_counts)
        ])

    def _on_daily_selected(self):
        d = self._selected_day(self.tbl_daily)
        if not d:
            self._clear_daily_detail("Chọn một ngày ở bảng trên để xem chi tiết")
            return

        self._fill_day_report(d)
        self._fill_detail_records(self.tbl_daily_detail, d)
        self._fill_task_rows(self.tbl_daily_tasks, d)
        self._fill_api_rows(self.tbl_daily_api, d)

        ts = d.task_stats if isinstance(d.task_stats, DayTaskStats) else None
        api = d.api_log_stats if isinstance(d.api_log_stats, DayApiLogStats) else None
        n_task = len(ts.rows) if ts else 0
        n_api = len(api.creates) if api else 0
        self.daily_bottom.setTabText(0, "Chi tiết bất thường (%d)" % d.abnormal_count)
        self.daily_bottom.setTabText(1, "Chi tiết Tasks Log (%d)" % n_task)
        self.daily_bottom.setTabText(2, "API logs (%d)" % n_api)
        self.lbl_daily_detail_title.setText(
            "Chi tiết ngày %s (%s) — %d bất thường · %d task · %d lệnh API · %d file log"
            % (d.base_date.isoformat(), aggregate.weekday_name(d.base_date),
               d.abnormal_count, n_task, n_api, d.log_file_count))

    def _fill_api_rows(self, table: QTableWidget, day: DayResult) -> None:
        table.setRowCount(0)
        table.clearSpans()
        api = day.api_log_stats if isinstance(day.api_log_stats, DayApiLogStats) else None
        if api is None or not api.creates:
            self._table_note(
                table,
                "(Không có API taskCreate cho ngày %s — cần nạp logs/%s.log "
                "hoặc debug_%s.log)"
                % (day.base_date.isoformat(), day.base_date.strftime("%Y%m%d"),
                   day.base_date.strftime("%Y%m%d")))
            return
        shown = 0
        total = len(api.creates)
        for ev in api.creates:
            if shown >= DETAIL_ROW_LIMIT:
                break
            route = " → ".join(pt for pt, _a in ev.points) if ev.points else ""
            r = table.rowCount(); table.insertRow(r)
            table.setItem(r, 0, _item(
                ev.ts.strftime("%H:%M:%S") if ev.ts else ""))
            table.setItem(r, 1, _item(ev.system_name))
            table.setItem(r, 2, _item(ev.score if ev.score is not None else ""))
            table.setItem(r, 3, _item(len(ev.points)))
            table.setItem(r, 4, _item(route, center=False))
            shown += 1
        if shown < total:
            r = table.rowCount(); table.insertRow(r)
            table.setItem(r, 0, _item(
                "… còn %d lệnh — xem Excel «Chi tiết API taskCreate»" % (total - shown),
                center=False, color=COLOR_WARN))
            table.setSpan(r, 0, 1, 5)

    def _populate_api(self):
        days = self._day_results
        t = self.tbl_api_days
        t.setRowCount(0)
        for d in days:
            api = d.api_log_stats if isinstance(d.api_log_stats, DayApiLogStats) else None
            if api is None or not api.has_data:
                continue
            r = t.rowCount(); t.insertRow(r)
            t.setItem(r, 0, _item(d.base_date.isoformat()))
            t.setItem(r, 1, _item(api.create_count))
            t.setItem(r, 2, _item(api.poll_count))
            t.setItem(r, 3, _item(api.unique_tasks))
            t.setItem(r, 4, _item(api.assigned_car_count))
            t.setItem(r, 5, _item(api.api_error_count,
                                  color=COLOR_BAD if api.api_error_count else None))
            t.setItem(r, 6, _item(api.hot_point or "-"))
            t.setItem(r, 7, _item(api.hot_point_count if api.hot_point_count else "-"))

        top = aggregate.top_api_points(days, limit=15)
        tp = self.tbl_api_points
        tp.setRowCount(0)
        for pt, n in top:
            r = tp.rowCount(); tp.insertRow(r)
            tp.setItem(r, 0, _item(pt))
            tp.setItem(r, 1, _item(n))
        self.chart_api_points.set_data(
            [(pt, float(n), BAR_ACCENT) for pt, n in top[:12]])

        from ..core.task_api_log import csv_api_crosscheck
        cx = self.tbl_api_cross
        cx.setRowCount(0)
        for row in csv_api_crosscheck(days):
            r = cx.rowCount(); cx.insertRow(r)
            cx.setItem(r, 0, _item(row["date"].isoformat()))  # type: ignore[union-attr]
            cx.setItem(r, 1, _item(row["csv_task_count"]))
            cx.setItem(r, 2, _item(row["api_create_count"]))
            diff = int(row["diff_csv_minus_api"])  # type: ignore[arg-type]
            cx.setItem(r, 3, _item(diff, color=COLOR_WARN if abs(diff) > 5 else None))
            cx.setItem(r, 4, _item("Có" if row["has_csv"] else "Không"))
            cx.setItem(r, 5, _item("Có" if row["has_api"] else "Không"))

    def _point_eff_threshold(self, point_id: str) -> float:
        """Ngưỡng phút hiệu dụng: thang máy dùng elevator_threshold, còn lại threshold thường."""
        elev = getattr(self._settings, "elevator_points", set()) or set()
        if str(point_id) in {str(p) for p in elev}:
            return float(self._settings.elevator_threshold_min)
        return float(self._settings.threshold_min)

    def _populate_points(self):
        days = self._day_results
        stats = aggregate.aggregate_points(days)
        elev = {str(p) for p in (getattr(self._settings, "elevator_points", set()) or set())}
        latest = max((d.base_date for d in days), default=None) if days else None

        ranked = []
        for ps in stats:
            thresh = self._point_eff_threshold(ps.point_id)
            level, score = aggregate.point_priority(ps, thresh, latest)
            ranked.append((level, score, ps))
        order = {"P1": 0, "P2": 1, "P3": 2}
        ranked.sort(key=lambda x: (order.get(x[0], 9), -x[1], -x[2].abnormal_count))

        t = self.tbl_points
        t.setRowCount(0)
        self._point_stats_by_id = {}
        total_events = sum(ps.abnormal_count for ps in stats) or 0
        p1_list = [ps for level, _, ps in ranked if level == "P1"]
        p1_events = sum(ps.abnormal_count for ps in p1_list)

        for level, score, ps in ranked:
            r = t.rowCount(); t.insertRow(r)
            is_elev = str(ps.point_id) in elev
            kind = "Thang máy" if is_elev else "Thường"
            accent = COLOR_BAD if level == "P1" else (COLOR_WARN if level == "P2" else None)
            max_at = "-"
            if ps.max_stay_car and ps.max_stay_at:
                max_at = "Xe %s · %s" % (ps.max_stay_car, ps.max_stay_at.isoformat())
            elif ps.max_stay_car:
                max_at = "Xe %s" % ps.max_stay_car
            last = ps.last_seen.isoformat() if ps.last_seen else "-"

            t.setItem(r, 0, _item(level, color=accent, bold=True))
            t.setItem(r, 1, _item("Điểm %s" % ps.point_id, color=accent))
            t.setItem(r, 2, _item(kind, color=COLOR_SAT if is_elev else None))
            t.setItem(r, 3, _item(ps.abnormal_count))
            t.setItem(r, 4, _item(ps.per_day))
            t.setItem(r, 5, _item(ps.car_count))
            t.setItem(r, 6, _item(ps.day_seen_count))
            t.setItem(r, 7, _item(ps.day_count))
            t.setItem(r, 8, _item(ps.night_count))
            t.setItem(r, 9, _item(ps.abnormal_min))
            t.setItem(r, 10, _item(ps.avg_min, color=accent))
            t.setItem(r, 11, _item(ps.max_min, color=accent))
            t.setItem(r, 12, _item(max_at, center=False))
            t.setItem(r, 13, _item(last))
            t.item(r, 0).setData(Qt.UserRole, ps.point_id)
            t.item(r, 1).setData(Qt.UserRole, ps.point_id)
            self._point_stats_by_id[ps.point_id] = (level, score, ps)

        # KPI + kết luận
        top5 = sorted(stats, key=lambda p: -p.abnormal_count)[:5]
        top5_share = (100.0 * sum(p.abnormal_count for p in top5) / total_events
                      if total_events else 0.0)
        worst = ranked[0][2] if ranked else None

        self.kpi_pt_total.set_value(len(stats), "điểm có lượt kẹt", "#3a76d8")
        self.kpi_pt_p1.set_value(
            len(p1_list),
            "%d%% tổng lượt" % (round(100.0 * p1_events / total_events) if total_events else 0),
            "#c0504d" if p1_list else "#2d7d46")
        if worst:
            self.kpi_pt_worst.set_value(
                "Điểm %s" % worst.point_id,
                "%d lượt · TB %.1f phút · lần cuối %s"
                % (worst.abnormal_count, worst.avg_min,
                   worst.last_seen.isoformat() if worst.last_seen else "-"),
                "#c0504d")
        else:
            self.kpi_pt_worst.set_value("-", "chưa có dữ liệu", "#808080")
        self.kpi_pt_focus.set_value(
            "%.0f%%" % top5_share, "top 5 điểm / tổng lượt kẹt",
            "#d88a3a" if top5_share >= 50 else "#2d7d46")

        thr = self._settings.threshold_min
        elev_thr = self._settings.elevator_threshold_min
        excl_parts = []
        for name, pts in (self._settings.excluded_groups or {}).items():
            if pts:
                excl_parts.append("%s (%d)" % (name, len(pts)))
        excl_txt = ", ".join(excl_parts) if excl_parts else "không"
        if p1_list and worst:
            share = round(100.0 * p1_events / total_events) if total_events else 0
            verdict = (
                "Có %d điểm cần xử lý ngay (P1), chiếm %d%% tổng lượt kẹt; "
                "nặng nhất: Điểm %s — %d lượt, TB %.1f phút, lần cuối %s."
                % (len(p1_list), share, worst.point_id, worst.abnormal_count,
                   worst.avg_min,
                   worst.last_seen.isoformat() if worst.last_seen else "-"))
            bg, fg = "#f8d7da", "#9C0006"
        elif stats:
            verdict = (
                "Không có điểm P1 — tình hình ổn hoặc các điểm kẹt đã lắng. "
                "Tổng %d điểm có lượt kẹt trong khoảng đã chọn." % len(stats))
            bg, fg = "#d4edda", "#006100"
        else:
            verdict = "Không có bất thường theo điểm — cần Log AGV trong khoảng đã chọn."
            bg, fg = "#eef5ff", "#1F4E79"
        self.lbl_points_verdict.setText(
            "%s\n«kẹt» = dừng quá %d phút (trừ sạc); thang máy %d phút. "
            "Điểm loại trừ: %s. Ưu tiên: P1 xử lý ngay · P2 theo dõi · P3 đã lắng."
            % (verdict, thr, elev_thr, excl_txt))
        self.lbl_points_verdict.setStyleSheet(
            "padding:8px; border-radius:6px; background:%s; color:%s;" % (bg, fg))

        self.lbl_points_title.setText(
            "Điểm xếp theo ưu tiên P1 → P2 → P3 (%d điểm) — tô đỏ = P1, vàng = P2"
            % len(stats))
        self.chart_points_tab.set_data(
            [("Điểm %s" % p.point_id, p.abnormal_count, BAR_ACCENT) for p in stats[:12]])
        by_time = sorted(stats, key=lambda x: (-x.abnormal_min, -x.abnormal_count))[:12]
        self.chart_points_time.set_data(
            [("Điểm %s" % p.point_id, p.abnormal_min, BAR_BAD) for p in by_time],
            suffix=" phút")

        self._apply_point_filter()
        if t.rowCount():
            # Chọn dòng P1 đầu tiên còn hiện (sau filter), không thì dòng 0
            sel = 0
            for r in range(t.rowCount()):
                if not t.isRowHidden(r):
                    sel = r
                    break
            t.selectRow(sel)
            self._on_point_selected()
        else:
            self._clear_point_detail_empty()

    def _clear_point_detail_empty(self):
        self._table_note(
            self.tbl_point_detail,
            "(Không có bất thường theo điểm — cần Log AGV trong khoảng đã chọn)")
        self.lbl_point_detail_title.setText("Chi tiết điểm đã chọn")
        self.lbl_point_diag.setText("Chưa có điểm để chẩn đoán.")
        self.chart_point_cars.set_data([])
        self.chart_point_hours.set_data([])

    def _apply_point_filter(self):
        """Ẩn/hiện dòng bảng điểm theo ô tìm (không tính lại số liệu)."""
        needle = (self.ed_point_filter.text() or "").strip().lower()
        t = self.tbl_points
        for r in range(t.rowCount()):
            it = t.item(r, 1)  # cột Điểm
            text = (it.text() if it else "").lower()
            pid = ""
            if it is not None:
                raw = it.data(Qt.UserRole)
                pid = str(raw).lower() if raw is not None else ""
            show = (not needle) or (needle in text) or (needle in pid)
            t.setRowHidden(r, not show)

    def _on_point_selected(self):
        rows = {i.row() for i in self.tbl_points.selectedIndexes()}
        if not rows:
            return
        row = min(rows)
        if self.tbl_points.isRowHidden(row):
            return
        it = self.tbl_points.item(row, 0)
        if it is None:
            it = self.tbl_points.item(row, 1)
        point_id = it.data(Qt.UserRole) if it else None
        if not point_id:
            return

        packed = getattr(self, "_point_stats_by_id", {}).get(point_id)
        ps = packed[2] if packed else None
        level = packed[0] if packed else "?"

        # Chẩn đoán lỗi điểm / lỗi xe
        if ps is None:
            self.lbl_point_diag.setText("Không có thống kê cho điểm %s." % point_id)
            self.chart_point_cars.set_data([])
            self.chart_point_hours.set_data([])
        else:
            top_car, top_cnt = ps.top_car
            share = ps.top_car_share
            hour_peak = ""
            if ps.hour_counts:
                h, hc = max(ps.hour_counts.items(), key=lambda kv: (kv[1], kv[0]))
                hour_peak = "tập trung %02dh-%02dh (%d lượt)" % (h, (h + 1) % 24, hc)
            is_elev = str(point_id) in {
                str(p) for p in (getattr(self._settings, "elevator_points", set()) or set())}
            kind = "thang máy" if is_elev else "điểm thường"
            if share >= 60.0 and top_car:
                diag = (
                    "Xe %s gây %.0f%% số lượt tại điểm này (%d/%d) — "
                    "nghiêng về lỗi xe hơn lỗi điểm."
                    % (top_car, share, top_cnt, ps.abnormal_count))
                bg = "#fff3cd"
            else:
                diag = (
                    "Lượt kẹt rải trên %d xe — nghiêng về lỗi điểm (%s)."
                    % (ps.car_count, kind))
                bg = "#eef5ff"
            if hour_peak:
                diag += " · " + hour_peak
            diag = "[%s] Điểm %s — %s" % (level, point_id, diag)
            self.lbl_point_diag.setText(diag)
            self.lbl_point_diag.setStyleSheet(
                "padding:8px; border-radius:6px; background:%s; color:#333;" % bg)

            # Phân bố theo xe
            cars_sorted = sorted(
                ps.car_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
            car_bars = []
            for cid, cnt in cars_sorted:
                color = BAR_BAD if (cid == top_car and share >= 60.0) else BAR_ACCENT2
                car_bars.append(("Xe %s" % cid, cnt, color))
            self.chart_point_cars.set_data(car_bars)

            # Phân bố theo giờ (chỉ giờ có dữ liệu, sắp theo giờ)
            hours_sorted = sorted(ps.hour_counts.items(), key=lambda kv: kv[0])
            self.chart_point_hours.set_data(
                [("%02dh" % h, cnt, BAR_ACCENT) for h, cnt in hours_sorted])

        detail = aggregate.point_detail_rows(
            self._day_results, point_id, limit=DETAIL_ROW_LIMIT)
        t = self.tbl_point_detail
        t.setRowCount(0)
        t.clearSpans()
        if not detail:
            self._table_note(t, "(Không có lượt chi tiết cho điểm %s)" % point_id)
            self.lbl_point_detail_title.setText("Chi tiết điểm %s" % point_id)
            return
        thr = self._point_eff_threshold(point_id)
        for base_d, shift, car, arrival, stay in detail:
            r = t.rowCount(); t.insertRow(r)
            accent = COLOR_BAD if stay >= 2 * thr else (
                COLOR_WARN if stay >= thr else None)
            t.setItem(r, 0, _item(base_d.isoformat()))
            t.setItem(r, 1, _item(shift))
            t.setItem(r, 2, _item(car))
            t.setItem(r, 3, _item(arrival.strftime("%H:%M:%S") if arrival else ""))
            t.setItem(r, 4, _item(stay, color=accent))
        self.lbl_point_detail_title.setText(
            "Chi tiết lượt tại Điểm %s — %d lượt (sắp xếp dừng dài trước, tối đa %d)"
            % (point_id, len(detail), DETAIL_ROW_LIMIT))

    def _populate_cars(self):
        from ..core.tasks import DayTaskStats, aggregate_car_utilization

        days = self._day_results
        stats = aggregate.aggregate_cars(days)
        latest = max((d.base_date for d in days), default=None) if days else None
        thr = float(self._settings.threshold_min)

        day_stats = [d.task_stats for d in days if isinstance(d.task_stats, DayTaskStats)]
        car_util = {cu.car_id: cu for cu in aggregate_car_utilization(day_stats)}

        # Kẹt/100 task theo xe + TB đội (chỉ xe có task)
        stuck_map: Dict[str, Optional[float]] = {}
        fleet_events = 0
        fleet_tasks = 0
        for cs in stats:
            cu = car_util.get(cs.car_id)
            tc = int(cu.task_count) if cu is not None else 0
            if tc > 0:
                stuck_map[cs.car_id] = round(100.0 * cs.abnormal_count / float(tc), 2)
                fleet_events += cs.abnormal_count
                fleet_tasks += tc
            else:
                stuck_map[cs.car_id] = None
        fleet_avg = (100.0 * fleet_events / float(fleet_tasks)) if fleet_tasks > 0 else None
        self._car_fleet_avg_per_100 = fleet_avg

        ranked = []
        for cs in stats:
            sp100 = stuck_map.get(cs.car_id)
            level, score = aggregate.car_priority(
                cs, thr, latest,
                stuck_per_100=sp100 if fleet_avg else None,
                fleet_avg_per_100=fleet_avg)
            ranked.append((level, score, cs, sp100))
        order = {"P1": 0, "P2": 1, "P3": 2}
        ranked.sort(key=lambda x: (order.get(x[0], 9), -x[1], -x[2].abnormal_count))

        t = self.tbl_cars
        t.setRowCount(0)
        self._car_stats_by_id = {}
        p1_list = [cs for level, _, cs, _ in ranked if level == "P1"]

        for level, score, cs, sp100 in ranked:
            r = t.rowCount(); t.insertRow(r)
            accent = COLOR_BAD if level == "P1" else (COLOR_WARN if level == "P2" else None)
            cu = car_util.get(cs.car_id)
            task_count = int(cu.task_count) if cu is not None else 0
            work_hours = cu.total_hours if cu is not None else 0.0
            hot = ("Điểm %s (%d)" % (cs.hot_point, cs.hot_point_count)
                   if cs.hot_point else "-")
            max_at = "-"
            if cs.max_stay_point and cs.max_stay_at:
                max_at = "Điểm %s · %s" % (cs.max_stay_point, cs.max_stay_at.isoformat())
            elif cs.max_stay_point:
                max_at = "Điểm %s" % cs.max_stay_point
            last = cs.last_seen.isoformat() if cs.last_seen else "-"

            t.setItem(r, 0, _item(level, color=accent, bold=True))
            t.setItem(r, 1, _item(cs.car_id, color=accent))
            t.setItem(r, 2, _item(cs.abnormal_count))
            t.setItem(r, 3, _item(cs.per_day))
            t.setItem(r, 4, _item(task_count if task_count else "-"))
            t.setItem(r, 5, _item("%.2f" % work_hours if task_count else "-"))
            t.setItem(r, 6, _item(sp100 if sp100 is not None else "-", color=accent))
            t.setItem(r, 7, _item(cs.day_seen_count))
            t.setItem(r, 8, _item(cs.point_count))
            t.setItem(r, 9, _item(hot, center=False))
            t.setItem(r, 10, _item(cs.day_count))
            t.setItem(r, 11, _item(cs.night_count))
            t.setItem(r, 12, _item(cs.abnormal_min))
            t.setItem(r, 13, _item(cs.avg_min, color=accent))
            t.setItem(r, 14, _item(cs.max_min, color=accent))
            t.setItem(r, 15, _item(max_at, center=False))
            t.setItem(r, 16, _item(last))
            t.item(r, 0).setData(Qt.UserRole, cs.car_id)
            t.item(r, 1).setData(Qt.UserRole, cs.car_id)
            self._car_stats_by_id[cs.car_id] = {
                "level": level, "score": score, "stat": cs,
                "stuck_per_100": sp100, "task_count": task_count,
                "work_hours": work_hours,
            }

        # Xe đáng lo nhất: stuck_per_100 cao nhất, task_count >= 20
        worry = None
        if fleet_avg is not None:
            candidates = [
                (cs, sp100, car_util.get(cs.car_id))
                for level, score, cs, sp100 in ranked
                if sp100 is not None and car_util.get(cs.car_id)
                and int(car_util[cs.car_id].task_count) >= 20
            ]
            if candidates:
                worry = max(candidates, key=lambda x: (x[1], x[0].abnormal_count))

        most_events = max(stats, key=lambda c: c.abnormal_count) if stats else None
        most_tasks = None
        if car_util:
            most_tasks = max(car_util.values(), key=lambda c: (c.task_count, c.total_sec))

        self.kpi_car_total.set_value(len(stats), "xe có lượt kẹt", "#3a76d8")
        self.kpi_car_p1.set_value(
            len(p1_list), "theo ưu tiên P1",
            "#c0504d" if p1_list else "#2d7d46")
        if worry:
            w_cs, w_sp, _ = worry
            self.kpi_car_worst.set_value(
                "Xe %s" % w_cs.car_id,
                "%.1f lượt/100 task · %d lượt · lần cuối %s"
                % (w_sp, w_cs.abnormal_count,
                   w_cs.last_seen.isoformat() if w_cs.last_seen else "-"),
                "#c0504d")
        elif ranked:
            top = ranked[0][2]
            self.kpi_car_worst.set_value(
                "Xe %s" % top.car_id,
                "%d lượt · TB %.1f phút (chưa chuẩn hoá task)"
                % (top.abnormal_count, top.avg_min),
                "#d88a3a")
        else:
            self.kpi_car_worst.set_value("-", "chưa có dữ liệu", "#808080")
        if fleet_avg is not None:
            self.kpi_car_fleet.set_value(
                "%.1f" % fleet_avg, "trên các xe có Tasks CSV", "#8c64c8")
        else:
            self.kpi_car_fleet.set_value(
                "-", "cần nạp Tasks CSV để so sánh công bằng", "#808080")

        # Kết luận
        if not stats:
            verdict = "Không có bất thường theo xe — cần Log AGV trong khoảng đã chọn."
            bg, fg = "#eef5ff", "#1F4E79"
        elif fleet_avg is not None:
            parts = ["Có %d xe cần kiểm tra ngay (P1)." % len(p1_list)
                     if p1_list else "Không có xe P1."]
            if most_events and most_tasks and most_events.car_id == most_tasks.car_id:
                parts.append(
                    "Xe %s nhiều lượt nhất (%d) và cũng chạy nhiều nhất (%d task)."
                    % (most_events.car_id, most_events.abnormal_count, most_tasks.task_count))
            elif most_events and most_tasks:
                parts.append(
                    "Xe %s nhiều lượt nhất (%d) nhưng Xe %s chạy nhiều nhất (%d task)."
                    % (most_events.car_id, most_events.abnormal_count,
                       most_tasks.car_id, most_tasks.task_count))
            if worry:
                w_cs, w_sp, w_cu = worry
                parts.append(
                    "Đáng lo là Xe %s: %.1f lượt/100 task so với TB đội %.1f."
                    % (w_cs.car_id, w_sp, fleet_avg))
            verdict = " ".join(parts)
            bg, fg = ("#f8d7da", "#9C0006") if p1_list else ("#d4edda", "#006100")
        else:
            verdict = (
                "Đang xếp theo lượt/ngày (chưa có Tasks CSV) — "
                "nạp Tasks CSV để so sánh công bằng bằng Kẹt/100 task. "
                "Có %d xe P1 trong %d xe có kẹt."
                % (len(p1_list), len(stats)))
            bg, fg = ("#fff3cd", "#9C5700") if p1_list else ("#eef5ff", "#1F4E79")

        self.lbl_cars_verdict.setText(
            "%s\n«kẹt» = dừng quá %d phút (trừ sạc). "
            "Kẹt/100 task chỉ có khi đã nạp Tasks CSV. "
            "Ưu tiên: P1 kiểm tra ngay · P2 theo dõi · P3 đã lắng."
            % (verdict, int(thr)))
        self.lbl_cars_verdict.setStyleSheet(
            "padding:8px; border-radius:6px; background:%s; color:%s;" % (bg, fg))

        mode_note = ("theo Kẹt/100 task" if fleet_avg is not None
                     else "theo lượt/ngày — chưa có Tasks CSV")
        self.lbl_cars_title.setText(
            "Xe xếp theo ưu tiên P1 → P2 → P3 (%d xe, %s) — tô đỏ = P1, vàng = P2"
            % (len(stats), mode_note))
        self.chart_cars_tab.set_data(
            [("Xe %s" % c.car_id, c.abnormal_count, BAR_ACCENT2) for c in stats[:12]])
        by_time = sorted(stats, key=lambda x: (-x.abnormal_min, -x.abnormal_count))[:12]
        self.chart_cars_time.set_data(
            [("Xe %s" % c.car_id, c.abnormal_min, BAR_BAD) for c in by_time],
            suffix=" phút")

        self._apply_car_filter()
        if t.rowCount():
            sel = 0
            for r in range(t.rowCount()):
                if not t.isRowHidden(r):
                    sel = r
                    break
            t.selectRow(sel)
            self._on_car_selected()
        else:
            self._clear_car_detail_empty()

    def _clear_car_detail_empty(self):
        self._table_note(
            self.tbl_car_detail,
            "(Không có bất thường theo xe — cần Log AGV trong khoảng đã chọn)")
        self.lbl_car_detail_title.setText("Chi tiết xe đã chọn")
        self.lbl_car_diag.setText("Chưa có xe để chẩn đoán.")
        self.chart_car_points.set_data([])
        self.chart_car_hours.set_data([])

    def _apply_car_filter(self):
        """Ẩn/hiện dòng bảng xe theo ô tìm (không tính lại số liệu)."""
        needle = (self.ed_car_filter.text() or "").strip().lower()
        t = self.tbl_cars
        for r in range(t.rowCount()):
            it = t.item(r, 1)  # cột Số xe
            text = (it.text() if it else "").lower()
            cid = ""
            if it is not None:
                raw = it.data(Qt.UserRole)
                cid = str(raw).lower() if raw is not None else ""
            show = (not needle) or (needle in text) or (needle in cid)
            t.setRowHidden(r, not show)

    def _on_car_selected(self):
        rows = {i.row() for i in self.tbl_cars.selectedIndexes()}
        if not rows:
            return
        row = min(rows)
        if self.tbl_cars.isRowHidden(row):
            return
        it = self.tbl_cars.item(row, 0)
        if it is None:
            it = self.tbl_cars.item(row, 1)
        car_id = it.data(Qt.UserRole) if it else None
        if not car_id:
            return

        packed = getattr(self, "_car_stats_by_id", {}).get(car_id)
        cs = packed["stat"] if packed else None
        level = packed["level"] if packed else "?"
        sp100 = packed.get("stuck_per_100") if packed else None
        task_count = packed.get("task_count", 0) if packed else 0
        fleet_avg = getattr(self, "_car_fleet_avg_per_100", None)

        if cs is None:
            self.lbl_car_diag.setText("Không có thống kê cho xe %s." % car_id)
            self.chart_car_points.set_data([])
            self.chart_car_hours.set_data([])
        else:
            share = cs.hot_point_share
            hot = cs.hot_point
            hour_peak = ""
            if cs.hour_counts:
                h, hc = max(cs.hour_counts.items(), key=lambda kv: (kv[1], kv[0]))
                hour_peak = "tập trung %02dh-%02dh (%d lượt)" % (h, (h + 1) % 24, hc)

            if share >= 60.0 and hot:
                diag = (
                    "%.0f%% lượt kẹt của xe này dồn ở Điểm %s — "
                    "nghiêng về lỗi điểm, kiểm tra điểm trước khi kiểm tra xe."
                    % (share, hot))
                bg = "#fff3cd"
            else:
                diag = (
                    "Lượt kẹt rải trên %d điểm — nghiêng về lỗi xe."
                    % cs.point_count)
                bg = "#eef5ff"

            ctx = []
            if task_count:
                if sp100 is not None and fleet_avg is not None:
                    ctx.append(
                        "chạy %d task, %.1f lượt/100 task (TB đội %.1f)"
                        % (task_count, sp100, fleet_avg))
                else:
                    ctx.append("chạy %d task" % task_count)
            if hour_peak:
                ctx.append(hour_peak)
            if ctx:
                diag += " · " + " · ".join(ctx)
            diag = "[%s] Xe %s — %s" % (level, car_id, diag)
            self.lbl_car_diag.setText(diag)
            self.lbl_car_diag.setStyleSheet(
                "padding:8px; border-radius:6px; background:%s; color:#333;" % bg)

            pts_sorted = sorted(
                cs.point_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
            pt_bars = []
            for pid, cnt in pts_sorted:
                color = BAR_BAD if (pid == hot and share >= 60.0) else BAR_ACCENT
                pt_bars.append(("Điểm %s" % pid, cnt, color))
            self.chart_car_points.set_data(pt_bars)

            hours_sorted = sorted(cs.hour_counts.items(), key=lambda kv: kv[0])
            self.chart_car_hours.set_data(
                [("%02dh" % h, cnt, BAR_ACCENT2) for h, cnt in hours_sorted])

        detail = aggregate.car_detail_rows(
            self._day_results, car_id, limit=DETAIL_ROW_LIMIT)
        t = self.tbl_car_detail
        t.setRowCount(0)
        t.clearSpans()
        if not detail:
            self._table_note(t, "(Không có lượt chi tiết cho xe %s)" % car_id)
            self.lbl_car_detail_title.setText("Chi tiết xe %s" % car_id)
            return
        for base_d, shift, point_id, arrival, stay in detail:
            r = t.rowCount(); t.insertRow(r)
            thr_pt = self._point_eff_threshold(point_id)
            accent = COLOR_BAD if stay >= 2 * thr_pt else (
                COLOR_WARN if stay >= thr_pt else None)
            t.setItem(r, 0, _item(base_d.isoformat()))
            t.setItem(r, 1, _item(shift))
            t.setItem(r, 2, _item("Điểm %s" % point_id))
            t.setItem(r, 3, _item(arrival.strftime("%H:%M:%S") if arrival else ""))
            t.setItem(r, 4, _item(stay, color=accent))
        self.lbl_car_detail_title.setText(
            "Chi tiết lượt của Xe %s — %d lượt (sắp xếp dừng dài trước, tối đa %d)"
            % (car_id, len(detail), DETAIL_ROW_LIMIT))

    def _populate_models(self):
        from ..core.tasks import DayTaskStats, aggregate_models, model_priority

        self._model_task_list = []
        for d in self._day_results:
            if isinstance(d.task_stats, DayTaskStats):
                self._model_task_list.append(d.task_stats)
        stats = aggregate_models(self._model_task_list)
        total_tasks = sum(m.task_count for m in stats) or 0
        total_timeout = sum(m.timeout_count for m in stats)
        total_dur_sec = sum(m.total_sec for m in stats)
        total_dur_n = sum(m.duration_count for m in stats)
        fleet_to = (100.0 * total_timeout / float(total_tasks)) if total_tasks else 0.0
        fleet_avg = (total_dur_sec / float(total_dur_n)) if total_dur_n else 0.0
        self._model_fleet_timeout_rate = fleet_to
        self._model_fleet_avg_sec = fleet_avg

        latest = None
        for m in stats:
            if m.last_seen is not None:
                if latest is None or m.last_seen > latest:
                    latest = m.last_seen
        if latest is None and self._day_results:
            latest = max(d.base_date for d in self._day_results)

        ranked = []
        for ms in stats:
            level, score = model_priority(ms, fleet_to, fleet_avg, latest)
            ranked.append((level, score, ms))
        order = {"P1": 0, "P2": 1, "P3": 2}
        ranked.sort(key=lambda x: (order.get(x[0], 9), -x[1], -x[2].task_count))

        t = self.tbl_models
        t.setRowCount(0)
        self._model_stats_by_id = {}
        p1_list = [ms for level, _, ms in ranked if level == "P1"]
        denom = total_tasks or 1

        for level, score, ms in ranked:
            r = t.rowCount(); t.insertRow(r)
            accent = COLOR_BAD if level == "P1" else (COLOR_WARN if level == "P2" else None)
            share = round(ms.task_count / float(denom) * 100.0, 1)
            last = ms.last_seen.isoformat() if ms.last_seen else "-"
            t.setItem(r, 0, _item(level, color=accent, bold=True))
            t.setItem(r, 1, _item(ms.model, center=False, color=accent))
            t.setItem(r, 2, _item(ms.task_count))
            t.setItem(r, 3, _item("%.1f%%" % share))
            t.setItem(r, 4, _item(ms.per_day))
            t.setItem(r, 5, _item(ms.day_seen_count))
            t.setItem(r, 6, _item(ms.car_count))
            t.setItem(r, 7, _item(ms.total_hours))
            t.setItem(r, 8, _item(ms.avg_min if ms.duration_count else "-"))
            t.setItem(r, 9, _item(ms.min_min if ms.duration_count else "-"))
            t.setItem(r, 10, _item(ms.max_min if ms.duration_count else "-"))
            t.setItem(r, 11, _item(ms.timeout_count,
                                   color=COLOR_BAD if ms.timeout_count else None))
            t.setItem(r, 12, _item("%.1f%%" % ms.timeout_rate, color=accent))
            t.setItem(r, 13, _item(last))
            t.item(r, 0).setData(Qt.UserRole, ms.model)
            t.item(r, 1).setData(Qt.UserRole, ms.model)
            self._model_stats_by_id[ms.model] = {
                "level": level, "score": score, "stat": ms, "share": share,
            }

        # Model đáng lo nhất: task_count >= 20, điểm số cao nhất
        worry = None
        candidates = [(score, ms) for level, score, ms in ranked if ms.task_count >= 20]
        if candidates:
            worry = max(candidates, key=lambda x: (x[0], x[1].timeout_rate, x[1].task_count))

        self.kpi_md_total.set_value(
            len(stats), "%d task tổng" % total_tasks, "#3a76d8")
        self.kpi_md_p1.set_value(
            len(p1_list), "theo ưu tiên P1",
            "#c0504d" if p1_list else "#2d7d46")
        if worry:
            w_score, w_ms = worry
            self.kpi_md_worst.set_value(
                w_ms.model[:22],
                "%d task · timeout %.1f%% · TB %.1f phút"
                % (w_ms.task_count, w_ms.timeout_rate, w_ms.avg_min),
                "#c0504d")
        elif ranked:
            top = ranked[0][2]
            self.kpi_md_worst.set_value(
                top.model[:22],
                "%d task · timeout %.1f%% (mẫu nhỏ)" % (top.task_count, top.timeout_rate),
                "#d88a3a")
        else:
            self.kpi_md_worst.set_value("-", "chưa có Tasks CSV", "#808080")
        self.kpi_md_timeout.set_value(
            "%.1f%%" % fleet_to if total_tasks else "-",
            "TB đội · chu kỳ TB %.1f phút" % (fleet_avg / 60.0) if fleet_avg else "TB đội",
            "#c0504d" if fleet_to >= 5 else "#2d7d46")

        if not stats:
            verdict = (
                "Không có Tasks Log — kiểm tra thư mục Tasks Log / file YYYYMMDD.csv.")
            bg, fg = "#eef5ff", "#1F4E79"
        elif p1_list and worry:
            w_score, w_ms = worry
            share = round(w_ms.task_count / float(denom) * 100.0, 1)
            verdict = (
                "Có %d model cần chú ý (P1). Model %s chiếm %.1f%% task nhưng "
                "%%timeout %.1f (TB đội %.1f); chu kỳ TB %.1f phút so với TB đội %.1f phút."
                % (len(p1_list), w_ms.model, share, w_ms.timeout_rate, fleet_to,
                   w_ms.avg_min, fleet_avg / 60.0 if fleet_avg else 0.0))
            bg, fg = "#f8d7da", "#9C0006"
        elif stats:
            verdict = (
                "Không có model P1 trong %d model · %d task. "
                "%%timeout TB đội %.1f · chu kỳ TB %.1f phút."
                % (len(stats), total_tasks, fleet_to,
                   fleet_avg / 60.0 if fleet_avg else 0.0))
            bg, fg = "#d4edda", "#006100"
        else:
            verdict = ""
            bg, fg = "#eef5ff", "#1F4E79"

        self.lbl_models_verdict.setText(
            "%s\nTimeout = final_state timeout. Ưu tiên so với TB đội: "
            "P1 chú ý ngay · P2 theo dõi · P3 ổn. Mẫu đáng tin khi ≥ 20 task."
            % verdict)
        self.lbl_models_verdict.setStyleSheet(
            "padding:8px; border-radius:6px; background:%s; color:%s;" % (bg, fg))

        self.lbl_models_title.setText(
            "Model xếp theo ưu tiên P1 → P2 → P3 (%d model · %d task) — "
            "tô đỏ = P1, vàng = P2"
            % (len(stats), total_tasks))
        self.chart_models.set_data(
            [(m.model[:18], m.task_count, BAR_ACCENT) for m in stats[:12]])
        by_hours = sorted(stats, key=lambda x: (-x.total_hours, -x.task_count))[:12]
        self.chart_models_hours.set_data(
            [(m.model[:18], m.total_hours, BAR_ACCENT2) for m in by_hours],
            suffix=" h")

        self._apply_model_filter()
        if t.rowCount():
            sel = 0
            for r in range(t.rowCount()):
                if not t.isRowHidden(r):
                    sel = r
                    break
            t.selectRow(sel)
            self._on_model_selected()
        else:
            self._clear_model_detail_empty()

    def _clear_model_detail_empty(self):
        self._table_note(
            self.tbl_model_detail,
            "(Không có Tasks Log — kiểm tra thư mục Tasks Log / file YYYYMMDD.csv)")
        self.lbl_model_detail_title.setText("Chi tiết model đã chọn")
        self.lbl_model_diag.setText("Chưa có model để chẩn đoán.")
        self.chart_model_cars.set_data([])
        self.chart_model_hours.set_data([])

    def _apply_model_filter(self):
        needle = (self.ed_model_filter.text() or "").strip().lower()
        t = self.tbl_models
        for r in range(t.rowCount()):
            it = t.item(r, 1)
            text = (it.text() if it else "").lower()
            mid = ""
            if it is not None:
                raw = it.data(Qt.UserRole)
                mid = str(raw).lower() if raw is not None else ""
            show = (not needle) or (needle in text) or (needle in mid)
            t.setRowHidden(r, not show)

    def _on_model_selected(self):
        from ..core.tasks import model_detail_rows
        rows = {i.row() for i in self.tbl_models.selectedIndexes()}
        if not rows:
            return
        row = min(rows)
        if self.tbl_models.isRowHidden(row):
            return
        it = self.tbl_models.item(row, 0)
        if it is None:
            it = self.tbl_models.item(row, 1)
        model = it.data(Qt.UserRole) if it else None
        if not model:
            return

        packed = getattr(self, "_model_stats_by_id", {}).get(model)
        ms = packed["stat"] if packed else None
        level = packed["level"] if packed else "?"
        fleet_to = getattr(self, "_model_fleet_timeout_rate", None) or 0.0
        fleet_avg = getattr(self, "_model_fleet_avg_sec", None) or 0.0
        fleet_avg_min = fleet_avg / 60.0 if fleet_avg else 0.0

        if ms is None:
            self.lbl_model_diag.setText("Không có thống kê cho model %s." % model)
            self.chart_model_cars.set_data([])
            self.chart_model_hours.set_data([])
        else:
            parts = []
            to_car, to_cnt = ms.top_timeout_car
            to_share = ms.top_timeout_share
            if ms.timeout_count and to_share >= 60.0 and to_car:
                parts.append(
                    "Xe %s gây %.0f%% timeout của model này (%d/%d) — "
                    "nghiêng về lỗi xe hơn lỗi model."
                    % (to_car, to_share, to_cnt, ms.timeout_count))
                bg = "#fff3cd"
            elif ms.avg_sec >= 1.5 * fleet_avg and fleet_avg > 0:
                parts.append(
                    "Chu kỳ TB %.1f phút cao hơn TB đội %.1f phút (×%.1f) — "
                    "chu kỳ bất thường."
                    % (ms.avg_min, fleet_avg_min,
                       ms.avg_sec / fleet_avg if fleet_avg else 0))
                bg = "#fff3cd"
            else:
                parts.append(
                    "Timeout %.1f%% (TB đội %.1f%%) · chu kỳ TB %.1f phút "
                    "(TB đội %.1f) — trong biên bình thường hoặc mẫu nhỏ."
                    % (ms.timeout_rate, fleet_to, ms.avg_min, fleet_avg_min))
                bg = "#eef5ff"

            if ms.hour_counts:
                h, hc = max(ms.hour_counts.items(), key=lambda kv: (kv[1], kv[0]))
                parts.append("tập trung %02dh-%02dh (%d task)" % (h, (h + 1) % 24, hc))

            diag = "[%s] %s — %s" % (level, model, " · ".join(parts))
            self.lbl_model_diag.setText(diag)
            self.lbl_model_diag.setStyleSheet(
                "padding:8px; border-radius:6px; background:%s; color:#333;" % bg)

            cars_sorted = sorted(
                ms.car_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
            car_bars = []
            for cid, cnt in cars_sorted:
                to_c = ms.timeout_car_counts.get(cid, 0)
                color = BAR_BAD if (cid == to_car and to_share >= 60.0 and to_c) else BAR_ACCENT2
                car_bars.append(("Xe %s" % cid, cnt, color))
            self.chart_model_cars.set_data(car_bars)

            hours_sorted = sorted(ms.hour_counts.items(), key=lambda kv: kv[0])
            self.chart_model_hours.set_data(
                [("%02dh" % h, cnt, BAR_ACCENT) for h, cnt in hours_sorted])

        task_list = getattr(self, "_model_task_list", [])
        detail = model_detail_rows(task_list, model, limit=DETAIL_ROW_LIMIT)
        t = self.tbl_model_detail
        t.setRowCount(0)
        t.clearSpans()
        if not detail:
            self._table_note(t, "(Không có task chi tiết cho model %s)" % model)
            self.lbl_model_detail_title.setText("Chi tiết model %s" % model)
            return
        warn_min = 2.0 * fleet_avg_min if fleet_avg_min > 0 else 30.0
        for base_d, shift, car, send, done, dur_min, state in detail:
            r = t.rowCount(); t.insertRow(r)
            accent = COLOR_BAD if state == "timeout" else (
                COLOR_WARN if dur_min >= warn_min else None)
            t.setItem(r, 0, _item(base_d.isoformat()))
            t.setItem(r, 1, _item(shift))
            t.setItem(r, 2, _item(car))
            t.setItem(r, 3, _item(send.strftime("%H:%M:%S") if send else ""))
            t.setItem(r, 4, _item(done.strftime("%H:%M:%S") if done else ""))
            t.setItem(r, 5, _item(dur_min, color=accent))
            t.setItem(r, 6, _item(state, color=COLOR_BAD if state == "timeout" else None))
        self.lbl_model_detail_title.setText(
            "Chi tiết task «%s» — %d dòng (duration dài trước, tối đa %d)"
            % (model, len(detail), DETAIL_ROW_LIMIT))

    @staticmethod
    def _agv_days(summary) -> list:
        """Các ngày có Log AGV thực sự (tránh 0 giả khi chỉ có CSV/API)."""
        return [d for d in summary.days
                if getattr(d, "has_agv_log", True) and d.car_count > 0]

    def _week_report_widgets(self) -> dict:
        return {
            "title": self.lbl_week_title,
            "verdict": self.lbl_week_verdict,
            "cards": [
                self.kpi_w_days, self.kpi_w_cars, self.kpi_w_events, self.kpi_w_rate,
                self.kpi_w_util, self.kpi_w_tasks, self.kpi_w_timeout, self.kpi_w_worst,
            ],
            "trend": self.chart_week_trend,
            "detail_tbl": self.tbl_week_detail,
        }

    def _month_report_widgets(self) -> dict:
        return {
            "title": self.lbl_month_title,
            "verdict": self.lbl_month_verdict,
            "cards": [
                self.kpi_m_days, self.kpi_m_cars, self.kpi_m_events, self.kpi_m_rate,
                self.kpi_m_util, self.kpi_m_tasks, self.kpi_m_timeout, self.kpi_m_worst,
            ],
            "trend": self.chart_month_trend,
            "detail_tbl": self.tbl_month_detail,
        }

    def _fill_period_report(self, summary, period_word: str, widgets: dict):
        """Đổ báo cáo chi tiết cho kỳ đã chọn (tuần/tháng)."""
        denom = self._denom()
        title = widgets["title"]
        verdict = widgets["verdict"]
        cards = widgets["cards"]
        trend = widgets["trend"]
        tbl = widgets["detail_tbl"]
        tbl.setRowCount(0)

        if not summary:
            title.setText("Báo cáo %s — chọn một %s ở bảng trên" % (period_word, period_word))
            verdict.setText("")
            for card in cards:
                card.set_value("-", "")
            trend.set_data([])
            return

        d0 = summary.date_start.isoformat() if summary.date_start else "-"
        d1 = summary.date_end.isoformat() if summary.date_end else "-"
        title.setText("Báo cáo %s %s  (%s → %s)" % (period_word, summary.label, d0, d1))

        days_agv = self._agv_days(summary)
        n_agv = len(days_agv)
        rate = summary.abnormal_rate
        util = summary.utilization

        if n_agv:
            if rate >= self._rate_warn:
                status, bg, fg = "CẦN XỬ LÝ", "#f8d7da", "#9C0006"
            elif rate >= self._rate_ok:
                status, bg, fg = "CẦN CHÚ Ý", "#fff3cd", "#9C5700"
            else:
                status, bg, fg = "ỔN", "#d4edda", "#006100"
            verdict.setText(
                "%s — Tỷ lệ bất thường %.2f%% (ổn khi <%g%%, cần xử lý khi ≥%g%%) · "
                "稼動 %.2f%% · %d nhiệm vụ · %d ngày có Log AGV"
                % (status, rate, self._rate_ok, self._rate_warn, util,
                   summary.task_count, n_agv))
            verdict.setStyleSheet(
                "padding:8px; border-radius:6px; background:%s; color:%s; font-weight:bold;"
                % (bg, fg))
        else:
            verdict.setText(
                "%s này chưa có Log AGV nên không đo được tỷ lệ bất thường · "
                "稼動 %.2f%% · %d nhiệm vụ (từ Tasks CSV)"
                % (period_word.capitalize(), util, summary.task_count))
            verdict.setStyleSheet(
                "padding:8px; border-radius:6px; background:#eef5ff; color:#1F4E79;")

        cards[0].set_value(
            "%d / %d" % (n_agv, summary.num_days), "ngày có Log AGV / tổng", "#3a76d8")
        cards[1].set_value(
            summary.distinct_car_count if n_agv else "-", "xe khác nhau", "#8c64c8")
        cards[2].set_value(
            summary.abnormal_count if n_agv else "-", "tổng lượt bất thường", "#d88a3a")
        cards[3].set_value(
            "%.2f%%" % rate if n_agv else "-", "toàn %s" % period_word,
            self._accent_hex(rate) if n_agv else "#808080")
        cards[4].set_value(
            "%.2f%%" % util if util else "-", "từ Tasks Log (completed)", "#2d7d46")
        cards[5].set_value(
            summary.task_count if summary.task_count else "-", "nhiệm vụ trong ca", "#3a76d8")
        cards[6].set_value(
            summary.timeout_count, "final_state = timeout",
            "#c0504d" if summary.timeout_count else "#2d7d46")
        if days_agv:
            worst = max(days_agv, key=lambda d: d.abnormal_rate(denom))
            wr = worst.abnormal_rate(denom)
            cards[7].set_value(
                worst.base_date.isoformat(),
                "%s · %.2f%%" % (aggregate.weekday_name(worst.base_date), wr),
                self._accent_hex(wr))
        else:
            cards[7].set_value("-", "chưa có Log AGV", "#808080")

        trend_days = sorted(days_agv, key=lambda d: d.base_date)
        points = [
            (d.base_date.strftime("%m-%d"), d.abnormal_rate(denom),
             "%s (%s)" % (d.base_date.isoformat(), aggregate.weekday_name(d.base_date)))
            for d in trend_days
        ]
        trend.set_data(
            points, suffix="%",
            thresholds=[(self._rate_ok, BAR_WARN), (self._rate_warn, BAR_BAD)])

        for d in summary.sorted_days():
            has_agv = getattr(d, "has_agv_log", True) and d.car_count > 0
            if not (has_agv or d.task_count > 0):
                continue
            r = tbl.rowCount(); tbl.insertRow(r)
            rate_d = d.abnormal_rate(denom)
            util_d = d.utilization
            warn = None if has_agv else COLOR_WARN
            base_color = COLOR_SAT if d.is_saturday else warn
            tbl.setItem(r, 0, _item(d.base_date.isoformat(), color=base_color))
            tbl.setItem(r, 1, _item(aggregate.weekday_name(d.base_date), color=base_color))
            tbl.setItem(r, 2, _item(d.car_count if has_agv else "-", color=warn))
            tbl.setItem(r, 3, _item(d.abnormal_count if has_agv else "-", color=warn))
            tbl.setItem(r, 4, _item(
                rate_d if has_agv else "-",
                color=self.rate_color(rate_d) if has_agv else warn))
            tbl.setItem(r, 5, _item(util_d if util_d else "-"))
            tbl.setItem(r, 6, _item(d.task_count if d.task_count else "-"))

    def _populate_weekly(self):
        self._weeks = aggregate.weekly_summaries(self._day_results, self._denom())
        table = self.tbl_week
        table.setRowCount(0)
        bars = []
        for s in self._weeks:
            r = table.rowCount(); table.insertRow(r)
            n_agv = len(self._agv_days(s))
            util = s.utilization
            rate = s.abnormal_rate
            table.setItem(r, 0, _item(s.label))
            table.setItem(r, 1, _item(s.date_start.isoformat() if s.date_start else "-"))
            table.setItem(r, 2, _item(s.date_end.isoformat() if s.date_end else "-"))
            table.setItem(r, 3, _item("%d / %d" % (n_agv, s.num_days)))
            table.setItem(r, 4, _item(s.distinct_car_count if n_agv else "-"))
            table.setItem(r, 5, _item(s.abnormal_count if n_agv else "-"))
            table.setItem(r, 6, _item(
                rate if n_agv else "-",
                color=self.rate_color(rate) if n_agv else None))
            table.setItem(r, 7, _item(util if util else "-"))
            table.setItem(r, 8, _item(s.task_count if s.task_count else "-"))
            table.setItem(r, 9, _item(s.timeout_count if s.timeout_count else "-"))
            table.item(r, 0).setData(Qt.UserRole, s)
            if n_agv:
                color = (BAR_BAD if rate >= self._rate_warn
                         else BAR_WARN if rate >= self._rate_ok else BAR_OK)
                bars.append((s.label, rate, color))
        self.chart_week_compare.set_data(bars, suffix="%")
        if table.rowCount():
            table.selectRow(table.rowCount() - 1)
        else:
            self._fill_period_report(None, "tuần", self._week_report_widgets())

    def _on_week_selected(self):
        rows = {i.row() for i in self.tbl_week.selectedIndexes()}
        if rows:
            it = self.tbl_week.item(min(rows), 0)
            self._fill_period_report(
                it.data(Qt.UserRole) if it else None, "tuần", self._week_report_widgets())
        else:
            self._fill_period_report(None, "tuần", self._week_report_widgets())

    def _populate_monthly(self):
        self._months = aggregate.monthly_summaries(self._day_results, self._denom())
        table = self.tbl_month
        table.setRowCount(0)
        bars = []
        for s in self._months:
            r = table.rowCount(); table.insertRow(r)
            n_agv = len(self._agv_days(s))
            util = s.utilization
            rate = s.abnormal_rate
            table.setItem(r, 0, _item(s.label))
            table.setItem(r, 1, _item("%d / %d" % (n_agv, s.num_days)))
            table.setItem(r, 2, _item(s.distinct_car_count if n_agv else "-"))
            table.setItem(r, 3, _item(s.abnormal_count if n_agv else "-"))
            table.setItem(r, 4, _item(
                rate if n_agv else "-",
                color=self.rate_color(rate) if n_agv else None))
            table.setItem(r, 5, _item(util if util else "-"))
            table.setItem(r, 6, _item(s.task_count if s.task_count else "-"))
            table.setItem(r, 7, _item(s.timeout_count if s.timeout_count else "-"))
            table.item(r, 0).setData(Qt.UserRole, s)
            if n_agv:
                color = (BAR_BAD if rate >= self._rate_warn
                         else BAR_WARN if rate >= self._rate_ok else BAR_OK)
                bars.append((s.label, rate, color))
        self.chart_month_compare.set_data(bars, suffix="%")
        if table.rowCount():
            table.selectRow(table.rowCount() - 1)
        else:
            self._fill_month_report(None)

    def _on_month_selected(self):
        rows = {i.row() for i in self.tbl_month.selectedIndexes()}
        if rows:
            it = self.tbl_month.item(min(rows), 0)
            self._fill_month_report(it.data(Qt.UserRole) if it else None)
        else:
            self._fill_month_report(None)

    def _fill_month_report(self, summary):
        """Đổ báo cáo chi tiết cho tháng đã chọn."""
        self._fill_period_report(summary, "tháng", self._month_report_widgets())

    # -- Xuất file ------------------------------------------------------------

    def _default_out_dir(self) -> Path:
        out = self.ed_out_dir.text().strip()
        if out and Path(out).exists():
            return Path(out)
        return app_dir()

    def on_export_excel(self):
        if not self._day_results:
            return
        default = str(self._default_out_dir() / "BaoCao_AGV.xlsx")
        path, _ = QFileDialog.getSaveFileName(self, "Lưu báo cáo Excel", default, "Excel (*.xlsx)")
        if not path:
            return
        try:
            export.export_full_report(
                self._day_results, Path(path),
                self._settings.threshold_min, self._settings.denom_hours,
                settings=self._settings)
            self._log("Đã xuất Excel: %s" % path)
            QMessageBox.information(
                self, "Thành công",
                "Đã xuất báo cáo (gồm bất thường + Tasks Log / 稼動 / model):\n%s" % path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Lỗi", "Xuất Excel thất bại:\n%s" % exc)

    def on_export_csv(self):
        if not self._day_results:
            return
        default = str(self._default_out_dir() / "TongQuan_AGV.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Lưu CSV tổng quan", default, "CSV (*.csv)")
        if not path:
            return
        try:
            export.export_summary_csv(
                self._day_results, Path(path), self._settings.denom_hours,
                settings=self._settings)
            self._log("Đã xuất CSV: %s" % path)
            QMessageBox.information(self, "Thành công", "Đã xuất CSV:\n%s" % path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Lỗi", "Xuất CSV thất bại:\n%s" % exc)

    def on_save_settings(self):
        s = self._read_settings_from_ui()
        try:
            path = save_settings(s)
            self._settings = s
            self._rate_ok = s.rate_ok
            self._rate_warn = s.rate_warn
            if self._day_results:
                self._populate_all()
            self._log("Đã lưu cài đặt: %s" % path)
            QMessageBox.information(self, "Thành công", "Đã lưu cài đặt vào:\n%s" % path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Lỗi", "Lưu cài đặt thất bại:\n%s" % exc)

    # -- Tiện ích -------------------------------------------------------------

    def _log(self, msg: str):
        self.log.appendPlainText(msg)
