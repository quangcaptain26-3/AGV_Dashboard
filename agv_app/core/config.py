# -*- coding: utf-8 -*-
"""Cấu hình phân tích AGV.

- Chứa giá trị mặc định NHÚNG SẴN để app/.exe chạy được mà không cần file ngoài.
- Đọc thêm point_settings.json nếu có (ưu tiên file bên cạnh app, sau đó file bundle).
- resource_path(): hỗ trợ lấy file đã đóng gói trong PyInstaller (sys._MEIPASS).

Cấu hình gói trọn ý nghĩa của 3 file gốc:
  - point_settings.json  -> ngưỡng, điểm loại trừ (theo nhóm), thang máy.
  - abnormal_setting.ini -> giờ ca ngày/đêm, thư mục log.
  - report_setting.ini   -> thư mục xuất báo cáo, giờ ca.
Ngoài ra bổ sung: denom_hours (số giờ mẫu số), ngưỡng màu tốt/cảnh báo.

Khuyến nghị Python 3.10 (tương thích 3.8–3.10).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


# --- Giá trị mặc định (đồng bộ với ptich_agv/point_settings.json) --------------

DEFAULT_THRESHOLD_MIN = 12
DEFAULT_ELEVATOR_THRESHOLD_MIN = 3

# Giữ theo NHÓM giống bản gốc để dễ hiểu và chỉnh sửa (Home / Charging / ...).
DEFAULT_EXCLUDED_GROUPS: Dict[str, List[str]] = {
    "Home": ["232", "1025", "259"],
    "Charging": ["239"],
}
DEFAULT_ELEVATOR_POINTS = {"221", "1294", "223", "1767"}

# Ca làm việc mặc định: ngày 08:00-19:59, đêm 20:00-07:59 (qua ngày hôm sau)
DEFAULT_SHIFT = {
    "day_start": (8, 0),
    "day_end": (19, 59),
    "night_start": (20, 0),
    "night_end": (7, 59),
}

# Số giờ mẫu số khi tính tỷ lệ bất thường (giống bản gốc: 24H * số_xe).
DEFAULT_DENOM_HOURS = 24.0

# Ngưỡng màu hiển thị (%): dưới rate_ok = tốt (xanh), rate_ok..rate_warn = cảnh báo
# (vàng), trên rate_warn = xấu (đỏ).
DEFAULT_RATE_OK = 5.0
DEFAULT_RATE_WARN = 10.0

SETTINGS_FILENAME = "point_settings.json"


def resource_path(relative: str) -> Path:
    """Trả về đường dẫn tuyệt đối cho file tài nguyên.

    Hoạt động cả khi chạy .py lẫn khi đã đóng gói bằng PyInstaller
    (--onedir/--onefile).
    """
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / relative
    return Path(__file__).resolve().parent.parent / relative


def app_dir() -> Path:
    """Thư mục chứa app khi chạy (cạnh .exe hoặc cạnh package)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _fmt_hhmm(value: Tuple[int, int]) -> str:
    return "%02d:%02d" % (int(value[0]), int(value[1]))


def _parse_hhmm(text: str, fallback: Tuple[int, int]) -> Tuple[int, int]:
    try:
        parts = str(text).strip().split(":")
        return (int(parts[0]), int(parts[1]))
    except (ValueError, IndexError, AttributeError):
        return fallback


@dataclass
class Settings:
    """Cấu hình dùng cho một lần phân tích + hiển thị."""

    threshold_min: int = DEFAULT_THRESHOLD_MIN
    elevator_threshold_min: int = DEFAULT_ELEVATOR_THRESHOLD_MIN

    # Điểm loại trừ giữ theo NHÓM (nguồn sự thật); phần logic dùng excluded_points.
    excluded_groups: Dict[str, List[str]] = field(
        default_factory=lambda: {k: list(v) for k, v in DEFAULT_EXCLUDED_GROUPS.items()}
    )
    elevator_points: Set[str] = field(default_factory=lambda: set(DEFAULT_ELEVATOR_POINTS))

    day_start: Tuple[int, int] = DEFAULT_SHIFT["day_start"]
    day_end: Tuple[int, int] = DEFAULT_SHIFT["day_end"]
    night_start: Tuple[int, int] = DEFAULT_SHIFT["night_start"]
    night_end: Tuple[int, int] = DEFAULT_SHIFT["night_end"]

    denom_hours: float = DEFAULT_DENOM_HOURS
    rate_ok: float = DEFAULT_RATE_OK
    rate_warn: float = DEFAULT_RATE_WARN

    default_log_dir: str = ""
    default_output_dir: str = ""
    task_log_dir: str = ""

    @property
    def excluded_points(self) -> Set[str]:
        """Tập hợp điểm loại trừ (gộp mọi nhóm) dùng cho phần logic."""
        out: Set[str] = set()
        for points in self.excluded_groups.values():
            for p in points:
                out.add(str(p))
        return out

    @property
    def threshold_sec(self) -> float:
        return self.threshold_min * 60.0

    @property
    def elevator_threshold_sec(self) -> float:
        return self.elevator_threshold_min * 60.0

    def to_json_dict(self) -> Dict:
        """Xuất ra cấu trúc point_settings.json mở rộng (để lưu lại)."""
        return {
            "_comment": (
                "Cấu hình điểm đặc biệt + ca làm việc của AGV. "
                "Sửa file này không cần sửa code."
            ),
            "threshold_min": self.threshold_min,
            "denom_hours": self.denom_hours,
            "excluded_points": {
                k: list(v) for k, v in self.excluded_groups.items()
            },
            "elevator": {
                "threshold_min": self.elevator_threshold_min,
                "points": sorted(self.elevator_points),
            },
            "shift": {
                "day_start": _fmt_hhmm(self.day_start),
                "day_end": _fmt_hhmm(self.day_end),
                "night_start": _fmt_hhmm(self.night_start),
                "night_end": _fmt_hhmm(self.night_end),
            },
            "display": {
                "rate_ok": self.rate_ok,
                "rate_warn": self.rate_warn,
            },
            "paths": {
                "default_log_dir": self.default_log_dir,
                "default_output_dir": self.default_output_dir,
                "task_log_dir": self.task_log_dir,
            },
        }


def _parse_json_settings(data: Dict, base: Settings) -> Settings:
    """Cập nhật Settings từ dữ liệu JSON (không làm thay đổi base gốc).

    Tương thích ngược: file cũ chỉ có threshold_min/excluded_points/elevator vẫn nạp
    được; các khóa mới (shift/display/paths/denom_hours) thiếu thì dùng mặc định.
    """
    threshold_min = int(data.get("threshold_min", base.threshold_min))
    denom_hours = float(data.get("denom_hours", base.denom_hours))

    # --- Điểm loại trừ (giữ theo nhóm) ---
    excluded_groups: Dict[str, List[str]] = {}
    raw_excluded = data.get("excluded_points", {})
    if isinstance(raw_excluded, dict):
        for category, points in raw_excluded.items():
            if isinstance(category, str) and category.startswith("_"):
                continue
            if isinstance(points, list):
                excluded_groups[category] = [str(p) for p in points]
    elif isinstance(raw_excluded, list):
        excluded_groups["Khác"] = [str(p) for p in raw_excluded]
    if not excluded_groups:
        excluded_groups = {k: list(v) for k, v in base.excluded_groups.items()}

    # --- Thang máy ---
    elevator_data = data.get("elevator", {}) or {}
    elevator_threshold_min = int(
        elevator_data.get("threshold_min", base.elevator_threshold_min)
    )
    elevator_points: Set[str] = set(str(p) for p in elevator_data.get("points", []))
    if not elevator_points:
        elevator_points = set(base.elevator_points)

    # --- Giờ ca ---
    shift = data.get("shift", {}) or {}
    day_start = _parse_hhmm(shift.get("day_start", ""), base.day_start)
    day_end = _parse_hhmm(shift.get("day_end", ""), base.day_end)
    night_start = _parse_hhmm(shift.get("night_start", ""), base.night_start)
    night_end = _parse_hhmm(shift.get("night_end", ""), base.night_end)

    # --- Ngưỡng màu hiển thị ---
    display = data.get("display", {}) or {}
    rate_ok = float(display.get("rate_ok", base.rate_ok))
    rate_warn = float(display.get("rate_warn", base.rate_warn))

    # --- Thư mục mặc định ---
    paths = data.get("paths", {}) or {}
    default_log_dir = str(paths.get("default_log_dir", base.default_log_dir) or "")
    default_output_dir = str(paths.get("default_output_dir", base.default_output_dir) or "")
    task_log_dir = str(paths.get("task_log_dir", base.task_log_dir) or "")

    return Settings(
        threshold_min=threshold_min,
        elevator_threshold_min=elevator_threshold_min,
        excluded_groups=excluded_groups,
        elevator_points=elevator_points,
        day_start=day_start,
        day_end=day_end,
        night_start=night_start,
        night_end=night_end,
        denom_hours=denom_hours,
        rate_ok=rate_ok,
        rate_warn=rate_warn,
        default_log_dir=default_log_dir,
        default_output_dir=default_output_dir,
        task_log_dir=task_log_dir,
    )


def _candidate_settings_paths() -> List[Path]:
    """Danh sách vị trí tìm point_settings.json theo thứ tự ưu tiên."""
    paths: List[Path] = []
    # 1. Cạnh file .exe / package (người dùng có thể sửa)
    paths.append(app_dir() / SETTINGS_FILENAME)
    # 2. File đã đóng gói trong PyInstaller
    paths.append(resource_path(SETTINGS_FILENAME))
    # 3. Thư mục gốc dự án (khi phát triển)
    paths.append(Path(__file__).resolve().parent.parent.parent / "ptich_agv" / SETTINGS_FILENAME)
    return paths


def load_settings(explicit_path: Optional[str] = None) -> Settings:
    """Nạp Settings: bắt đầu từ mặc định, ghi đè bằng point_settings.json nếu tìm thấy."""
    settings = Settings()
    # Gợi ý Tasks Log cạnh repo khi chưa cấu hình
    try:
        from .tasks import default_task_log_dir
        settings.task_log_dir = default_task_log_dir()
    except Exception:
        pass

    search_paths: List[Path] = []
    if explicit_path:
        search_paths.append(Path(explicit_path))
    search_paths.extend(_candidate_settings_paths())

    for path in search_paths:
        try:
            if path and path.exists():
                with open(path, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                loaded = _parse_json_settings(data, settings)
                # Nếu JSON không có task_log_dir, giữ gợi ý mặc định
                if not loaded.task_log_dir and settings.task_log_dir:
                    loaded.task_log_dir = settings.task_log_dir
                return loaded
        except Exception:
            continue

    return settings


def save_settings(settings: Settings, path: Optional[Path] = None) -> Path:
    """Lưu Settings ra point_settings.json (mặc định cạnh app)."""
    if path is None:
        path = app_dir() / SETTINGS_FILENAME
    path = Path(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings.to_json_dict(), f, ensure_ascii=False, indent=2)
    return path
