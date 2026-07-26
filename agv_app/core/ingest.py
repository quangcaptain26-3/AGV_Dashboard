# -*- coding: utf-8 -*-
"""Phân loại & inventory 3 nguồn dữ liệu AGV Analyzer.

A. Thư mục log ngày (LogYYYYMMDD + Log*.txt)
B. Tasks CSV (YYYYMMDD.csv)
C. Tasks API logs (YYYYMMDD.log / debug_YYYYMMDD.log)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

_DATE8_RE = re.compile(r"^(\d{8})$")
_TASK_CSV_RE = re.compile(r"^(\d{8})\.csv$", re.IGNORECASE)
_API_LOG_RE = re.compile(r"^(?:debug_)?(\d{8})\.log$", re.IGNORECASE)
_AGV_FOLDER_RE = re.compile(r"^Log(\d{8})$", re.IGNORECASE)
_AGV_TXT_RE = re.compile(r"^Log(\d{8})\d{0,2}\.txt$", re.IGNORECASE)

# Giới hạn quét khi kéo folder cha lớn
DEFAULT_MAX_FILES = 8000
DEFAULT_MAX_DEPTH = 6


class DataKind(str, Enum):
    AGV_DAY_FOLDER = "agv_day"
    TASK_CSV = "task_csv"
    TASK_API_LOG = "task_api_log"
    UNKNOWN = "unknown"


KIND_LABEL_VI = {
    DataKind.AGV_DAY_FOLDER: "Log AGV ngày",
    DataKind.TASK_CSV: "Tasks CSV",
    DataKind.TASK_API_LOG: "Tasks API log",
    DataKind.UNKNOWN: "Không rõ",
}


def _parse_yyyymmdd(text: str) -> Optional[date]:
    try:
        return datetime.strptime(text, "%Y%m%d").date()
    except ValueError:
        return None


def is_task_csv_name(name: str) -> bool:
    return bool(_TASK_CSV_RE.match(name or ""))


def is_task_api_log_name(name: str) -> bool:
    return bool(_API_LOG_RE.match(name or ""))


def date_from_task_csv(path: Path) -> Optional[date]:
    m = _TASK_CSV_RE.match(Path(path).name)
    return _parse_yyyymmdd(m.group(1)) if m else None


def date_from_api_log(path: Path) -> Optional[date]:
    m = _API_LOG_RE.match(Path(path).name)
    return _parse_yyyymmdd(m.group(1)) if m else None


def _looks_like_agv_day_folder(path: Path) -> Tuple[bool, Optional[date]]:
    """Folder ngày AGV: tên LogYYYYMMDD hoặc chứa Log*.txt giờ."""
    path = Path(path)
    if not path.is_dir():
        return False, None

    m = _AGV_FOLDER_RE.match(path.name)
    if m:
        d = _parse_yyyymmdd(m.group(1))
        if d is not None:
            # Có Log*.txt thì chắc chắn; thiếu file vẫn nhận nếu tên đúng
            return True, d

    dates: List[date] = []
    try:
        for f in path.glob("Log*.txt"):
            if not f.is_file():
                continue
            fm = _AGV_TXT_RE.match(f.name)
            if fm:
                parsed = _parse_yyyymmdd(fm.group(1))
                if parsed:
                    dates.append(parsed)
    except OSError:
        return False, None
    if dates:
        return True, min(dates)
    return False, None


def _peek_api_log(path: Path, max_bytes: int = 4096) -> bool:
    """Xác nhận nội dung nhẹ: có taskCreate hoặc [poll ."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(max_bytes)
    except OSError:
        return False
    try:
        text = chunk.decode("utf-8", errors="ignore")
    except Exception:
        return False
    return ("taskCreate" in text) or ("[poll " in text) or ("/agvapi/" in text)


def classify_file(path: Path) -> Tuple[DataKind, Optional[date], str]:
    path = Path(path)
    if not path.is_file():
        return DataKind.UNKNOWN, None, "không phải file"

    name = path.name
    if is_task_csv_name(name):
        return DataKind.TASK_CSV, date_from_task_csv(path), "CSV nhiệm vụ"

    if is_task_api_log_name(name):
        d = date_from_api_log(path)
        note = "debug poll" if name.lower().startswith("debug_") else "API taskCreate/poll"
        # Path chứa /logs/ hoặc peek nội dung → chắc chắn C
        parts_lower = {p.lower() for p in path.parts}
        if "logs" in parts_lower or _peek_api_log(path):
            return DataKind.TASK_API_LOG, d, note
        # Vẫn nhận theo tên (YYYYMMDD.log)
        return DataKind.TASK_API_LOG, d, note

    # Log*.txt AGV → gợi ý folder cha (caller xử lý)
    if _AGV_TXT_RE.match(name) or (
        name.lower().startswith("log") and name.lower().endswith(".txt")
        and re.search(r"\d{8}", name)
    ):
        return DataKind.UNKNOWN, None, "file Log*.txt (dùng thư mục cha)"

    return DataKind.UNKNOWN, None, "không nhận diện"


def classify_path(path: Path) -> Tuple[DataKind, Optional[date], str]:
    """Phân loại một path (file hoặc folder ngày). Không quét đệ quy."""
    path = Path(path)
    if path.is_file():
        return classify_file(path)
    if path.is_dir():
        ok, d = _looks_like_agv_day_folder(path)
        if ok:
            return DataKind.AGV_DAY_FOLDER, d, "thư mục log ngày"
        return DataKind.UNKNOWN, None, "thư mục (cần quét con)"
    return DataKind.UNKNOWN, None, "không tồn tại"


@dataclass
class InventoryItem:
    kind: DataKind
    path: Path
    base_date: Optional[date] = None
    note: str = ""

    @property
    def kind_label(self) -> str:
        return KIND_LABEL_VI.get(self.kind, self.kind.value)

    @property
    def key(self) -> str:
        return "%s|%s" % (self.kind.value, str(Path(self.path).resolve()).lower())


@dataclass
class ScanResult:
    added: List[InventoryItem] = field(default_factory=list)
    skipped: int = 0
    unknown: List[Path] = field(default_factory=list)


@dataclass
class DataInventory:
    """Danh sách nguồn đã nhận — 3 loại, dedupe theo (kind, path resolve)."""

    items: List[InventoryItem] = field(default_factory=list)
    _keys: Set[str] = field(default_factory=set, repr=False)

    def clear(self) -> None:
        self.items.clear()
        self._keys.clear()

    def remove_at(self, index: int) -> Optional[InventoryItem]:
        if index < 0 or index >= len(self.items):
            return None
        item = self.items.pop(index)
        self._keys.discard(item.key)
        return item

    def remove_keys(self, keys: Iterable[str]) -> int:
        drop = set(keys)
        before = len(self.items)
        self.items = [it for it in self.items if it.key not in drop]
        self._keys = {it.key for it in self.items}
        return before - len(self.items)

    def _try_add(self, item: InventoryItem) -> bool:
        try:
            item.path = Path(item.path).resolve()
        except OSError:
            item.path = Path(item.path)
        if item.key in self._keys:
            return False
        self._keys.add(item.key)
        self.items.append(item)
        return True

    def add_item(self, kind: DataKind, path: Path, base_date: Optional[date] = None,
                 note: str = "") -> Optional[InventoryItem]:
        if kind == DataKind.UNKNOWN:
            return None
        item = InventoryItem(kind=kind, path=Path(path), base_date=base_date, note=note)
        if self._try_add(item):
            return item
        return None

    def discover(
        self,
        paths: Sequence[Path],
        *,
        max_depth: int = DEFAULT_MAX_DEPTH,
        max_files: int = DEFAULT_MAX_FILES,
    ) -> ScanResult:
        """Nhận path bất kỳ → phân loại / quét → thêm vào inventory."""
        result = ScanResult()
        file_budget = [max_files]

        for raw in paths:
            p = Path(raw)
            if not p.exists():
                result.unknown.append(p)
                continue
            self._discover_one(p, 0, max_depth, file_budget, result)

        return result

    def add_paths(self, paths: Sequence[Path], **kwargs) -> ScanResult:
        return self.discover(paths, **kwargs)

    def _discover_one(
        self,
        path: Path,
        depth: int,
        max_depth: int,
        file_budget: List[int],
        result: ScanResult,
    ) -> None:
        if file_budget[0] <= 0:
            return

        if path.is_file():
            file_budget[0] -= 1
            kind, d, note = classify_file(path)
            if kind == DataKind.UNKNOWN and note.startswith("file Log"):
                parent = path.parent
                ok, pd = _looks_like_agv_day_folder(parent)
                if ok:
                    item = self.add_item(DataKind.AGV_DAY_FOLDER, parent, pd, "từ file Log*.txt")
                    if item:
                        result.added.append(item)
                    else:
                        result.skipped += 1
                    return
            if kind != DataKind.UNKNOWN:
                item = self.add_item(kind, path, d, note)
                if item:
                    result.added.append(item)
                else:
                    result.skipped += 1
            else:
                result.unknown.append(path)
            return

        if not path.is_dir():
            result.unknown.append(path)
            return

        # Folder ngày AGV?
        ok, d = _looks_like_agv_day_folder(path)
        if ok:
            item = self.add_item(DataKind.AGV_DAY_FOLDER, path, d, "thư mục log ngày")
            if item:
                result.added.append(item)
            else:
                result.skipped += 1
            # Không quét sâu vào trong folder ngày
            return

        if depth >= max_depth:
            return

        try:
            entries = sorted(path.iterdir(), key=lambda x: x.name.lower())
        except OSError:
            return

        for child in entries:
            if file_budget[0] <= 0:
                break
            # Bỏ qua thư mục hệ thống / build phổ biến
            name_l = child.name.lower()
            if name_l in {".git", "__pycache__", "node_modules", "dist", "build", ".venv", "venv"}:
                continue
            self._discover_one(child, depth + 1, max_depth, file_budget, result)

    # --- Truy vấn theo loại ---------------------------------------------------

    def by_kind(self, kind: DataKind) -> List[InventoryItem]:
        return [it for it in self.items if it.kind == kind]

    def agv_folders(self) -> List[Path]:
        return [it.path for it in self.by_kind(DataKind.AGV_DAY_FOLDER)]

    def task_csv_paths(self) -> List[Path]:
        return [it.path for it in self.by_kind(DataKind.TASK_CSV)]

    def api_log_paths(self) -> List[Path]:
        return [it.path for it in self.by_kind(DataKind.TASK_API_LOG)]

    def counts(self) -> Dict[str, int]:
        return {
            "agv": len(self.by_kind(DataKind.AGV_DAY_FOLDER)),
            "csv": len(self.by_kind(DataKind.TASK_CSV)),
            "api": len(self.by_kind(DataKind.TASK_API_LOG)),
            "total": len(self.items),
        }

    def dates_by_kind(self) -> Dict[DataKind, Set[date]]:
        out: Dict[DataKind, Set[date]] = {
            DataKind.AGV_DAY_FOLDER: set(),
            DataKind.TASK_CSV: set(),
            DataKind.TASK_API_LOG: set(),
        }
        for it in self.items:
            if it.base_date is not None and it.kind in out:
                out[it.kind].add(it.base_date)
        return out

    def coverage_banner(self) -> str:
        """Cảnh báo thiếu nguồn trong khoảng ngày đã nạp."""
        dates = self.dates_by_kind()
        a, b, c = (
            dates[DataKind.AGV_DAY_FOLDER],
            dates[DataKind.TASK_CSV],
            dates[DataKind.TASK_API_LOG],
        )
        all_dates = a | b | c
        if not all_dates:
            return ""
        parts: List[str] = []
        csv_only = b - a
        if csv_only:
            parts.append("%d ngày có CSV nhưng thiếu Log AGV" % len(csv_only))
        api_only = c - a
        if api_only and not csv_only:
            parts.append("%d ngày có API log nhưng thiếu Log AGV" % len(api_only))
        elif api_only and csv_only != api_only:
            miss_api_agv = c - a
            if miss_api_agv:
                parts.append("%d ngày có API log thiếu Log AGV" % len(miss_api_agv))
        agv_no_csv = a - b
        if agv_no_csv and b:
            parts.append("%d ngày có Log AGV nhưng thiếu CSV" % len(agv_no_csv))
        csv_no_api = b - c
        if csv_no_api and c:
            parts.append("%d ngày có CSV nhưng thiếu API log" % len(csv_no_api))
        return " · ".join(parts)

    def badge_text(self) -> str:
        c = self.counts()
        return "Đã nhận %d CSV / %d API log / %d ngày AGV" % (
            c["csv"], c["api"], c["agv"])
