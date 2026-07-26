# -*- coding: utf-8 -*-
"""Đọc Tasks Log CSV và tính tỷ lệ hoạt động (稼動率) + model / chu kỳ / timeout.

Port logic từ ptich_agv/reportAnalyse.py bằng stdlib (không dùng pandas).
Ngày neo theo base_date của thư mục log, không dùng datetime.now().
"""

from __future__ import annotations

import csv
import re
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .abnormal import calc_shift_ranges
from .config import Settings

_INVALID_CAR_IDS = frozenset({"0", "", "nan", "none", "null"})
_DATE_FILE_RE = re.compile(r"^(\d{8})\.csv$", re.IGNORECASE)

_DT_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M",
    "%Y/%m/%d %H:%M:%S",
)


@dataclass
class TaskRow:
    task_id: str
    car_id: str
    send_time: Optional[datetime]
    complete_time: Optional[datetime]
    duration_sec: float
    final_state: str
    model: str


@dataclass
class CarUtilRow:
    car_id: str
    task_count: int = 0
    total_sec: float = 0.0

    @property
    def total_hours(self) -> float:
        return round(self.total_sec / 3600.0, 4)


@dataclass
class ShiftUtilResult:
    """稼動率 một ca."""

    label: str  # "day" | "night"
    car_rows: List[CarUtilRow] = field(default_factory=list)
    utilization: float = 0.0
    car_count: int = 0
    shift_h: float = 0.0
    shift_sec: float = 0.0
    total_sec: float = 0.0
    task_count: int = 0

    @property
    def denom_sec(self) -> float:
        return self.shift_sec * self.car_count


@dataclass
class ModelStat:
    model: str
    task_count: int = 0
    total_sec: float = 0.0
    timeout_count: int = 0
    completed_count: int = 0
    duration_count: int = 0   # số task có duration > 0 (để tính TB)
    max_sec: float = 0.0
    min_sec: float = 0.0
    cars: Set[str] = field(default_factory=set)
    days_seen: Set[date] = field(default_factory=set)
    car_counts: Dict[str, int] = field(default_factory=dict)
    timeout_car_counts: Dict[str, int] = field(default_factory=dict)
    hour_counts: Dict[int, int] = field(default_factory=dict)
    last_seen: Optional[date] = None

    @property
    def avg_sec(self) -> float:
        n = self.duration_count if self.duration_count > 0 else self.task_count
        if n <= 0:
            return 0.0
        return round(self.total_sec / n, 1)

    @property
    def avg_min(self) -> float:
        return round(self.avg_sec / 60.0, 2) if self.avg_sec else 0.0

    @property
    def total_hours(self) -> float:
        return round(self.total_sec / 3600.0, 4)

    @property
    def timeout_rate(self) -> float:
        if self.task_count <= 0:
            return 0.0
        return round(self.timeout_count / self.task_count * 100.0, 1)

    @property
    def car_count(self) -> int:
        return len(self.cars)

    @property
    def day_seen_count(self) -> int:
        return len(self.days_seen)

    @property
    def max_min(self) -> float:
        return round(self.max_sec / 60.0, 1)

    @property
    def min_min(self) -> float:
        return round(self.min_sec / 60.0, 1) if self.duration_count else 0.0

    @property
    def per_day(self) -> float:
        n = self.day_seen_count
        if n <= 0:
            return 0.0
        return round(self.task_count / float(n), 2)

    @property
    def top_car(self) -> Tuple[str, int]:
        if not self.car_counts:
            return ("", 0)
        car_id, count = max(self.car_counts.items(), key=lambda kv: (kv[1], kv[0]))
        return (car_id, int(count))

    @property
    def top_car_share(self) -> float:
        if self.task_count <= 0:
            return 0.0
        _, count = self.top_car
        return round(100.0 * count / float(self.task_count), 1)

    @property
    def top_timeout_car(self) -> Tuple[str, int]:
        if not self.timeout_car_counts:
            return ("", 0)
        car_id, count = max(self.timeout_car_counts.items(), key=lambda kv: (kv[1], kv[0]))
        return (car_id, int(count))

    @property
    def top_timeout_share(self) -> float:
        if self.timeout_count <= 0:
            return 0.0
        _, count = self.top_timeout_car
        return round(100.0 * count / float(self.timeout_count), 1)


@dataclass
class DayTaskStats:
    """Thống kê nhiệm vụ gắn với một ngày logic (base_date)."""

    base_date: date
    day: Optional[ShiftUtilResult] = None
    night: Optional[ShiftUtilResult] = None
    task_count: int = 0
    completed_count: int = 0
    timeout_count: int = 0
    avg_cycle_sec: float = 0.0
    p50_cycle_sec: float = 0.0
    models: List[ModelStat] = field(default_factory=list)
    source_files: List[str] = field(default_factory=list)
    has_data: bool = False
    # Giữ danh sách task trong cửa sổ ca để UI / Excel chi tiết
    rows: List[TaskRow] = field(default_factory=list, repr=False)

    @property
    def utilization_day(self) -> float:
        return self.day.utilization if self.day else 0.0

    @property
    def utilization_night(self) -> float:
        return self.night.utilization if self.night else 0.0

    @property
    def utilization_all(self) -> float:
        """稼動 cả ngày = tổng duration / tổng (shift_sec × car_count) các ca có dữ liệu."""
        total_sec = 0.0
        denom = 0.0
        for shift in (self.day, self.night):
            if shift is None or shift.car_count <= 0:
                continue
            total_sec += shift.total_sec
            denom += shift.denom_sec
        if denom <= 0:
            return 0.0
        return round(total_sec / denom * 100.0, 2)


def parse_dt_flexible(text: str) -> Optional[datetime]:
    """Parse thời gian linh hoạt (nhiều định dạng Tasks Log)."""
    if text is None:
        return None
    s = str(text).strip().strip('"').strip("'")
    if not s:
        return None
    # Chuẩn hóa khoảng trắng
    s = re.sub(r"\s+", " ", s)
    for fmt in _DT_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    # Thử bỏ phần mili-giây
    if "." in s:
        try:
            return datetime.strptime(s.split(".")[0], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    return None


def _detect_delimiter(sample: str) -> str:
    if "\t" in sample and sample.count("\t") >= sample.count(","):
        return "\t"
    return ","


def _open_csv(path: Path):
    """Mở CSV với encoding fallback."""
    for enc in ("utf-8-sig", "utf-8", "gbk", "cp1252"):
        try:
            f = open(path, "r", encoding=enc, newline="")
            f.read(256)
            f.seek(0)
            return f
        except (UnicodeDecodeError, OSError):
            try:
                f.close()
            except Exception:
                pass
    return open(path, "r", encoding="utf-8-sig", errors="replace", newline="")


def _normalize_header(name: str) -> str:
    return str(name or "").strip().strip('"').lower()


def _header_map(fieldnames: Optional[Sequence[str]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not fieldnames:
        return out
    for name in fieldnames:
        if name is None:
            continue
        out[_normalize_header(name)] = name
    return out


def _mapped_get(row: Dict[str, str], hmap: Dict[str, str], *keys: str) -> str:
    for k in keys:
        real = hmap.get(k.lower())
        if real is not None:
            return (row.get(real) or "").strip().strip('"')
    return ""


def read_task_csv(path: Path) -> List[TaskRow]:
    """Đọc một file YYYYMMDD.csv thành danh sách TaskRow."""
    path = Path(path)
    if not path.is_file():
        return []

    rows: List[TaskRow] = []
    with _open_csv(path) as f:
        sample = f.read(4096)
        f.seek(0)
        delim = _detect_delimiter(sample)
        reader = csv.DictReader(f, delimiter=delim)
        hmap = _header_map(reader.fieldnames)
        for raw in reader:
            if not raw:
                continue
            car_id = _mapped_get(raw, hmap, "carid", "car_id")
            duration_s = _mapped_get(raw, hmap, "duration_sec", "duration")
            state = _mapped_get(raw, hmap, "final_state", "state").lower()
            model = _mapped_get(raw, hmap, "model").strip().strip("\t")
            try:
                duration = float(duration_s) if duration_s else 0.0
            except ValueError:
                duration = 0.0

            rows.append(TaskRow(
                task_id=_mapped_get(raw, hmap, "taskid", "task_id"),
                car_id=car_id,
                send_time=parse_dt_flexible(_mapped_get(raw, hmap, "send_time", "sendtime")),
                complete_time=parse_dt_flexible(
                    _mapped_get(raw, hmap, "complete_time", "completetime")
                ),
                duration_sec=duration,
                final_state=state,
                model=model,
            ))
    return rows


@dataclass
class TaskCsvIndex:
    """Index CSV Tasks Log quét một lần + cache nội dung theo ngày."""

    root: Path
    by_date: Dict[date, Path] = field(default_factory=dict)
    _row_cache: Dict[date, List[TaskRow]] = field(default_factory=dict, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @classmethod
    def build(cls, root: Optional[Path]) -> "TaskCsvIndex":
        if root is None:
            return cls(root=Path("."))
        root = Path(root)
        idx = cls(root=root)
        if not root.exists():
            return idx

        # Thu thập ứng viên; ưu tiên gần root hơn khi trùng ngày
        candidates: List[Tuple[int, str, date, Path]] = []
        for p in root.rglob("*.csv"):
            if not p.is_file():
                continue
            m = _DATE_FILE_RE.match(p.name)
            if not m:
                continue
            try:
                d = datetime.strptime(m.group(1), "%Y%m%d").date()
            except ValueError:
                continue
            try:
                depth = len(p.relative_to(root).parts)
            except ValueError:
                depth = 99
            candidates.append((depth, str(p), d, p))

        candidates.sort(key=lambda t: (t[0], t[1]))
        for _depth, _s, d, p in candidates:
            if d not in idx.by_date:
                idx.by_date[d] = p
        return idx

    @classmethod
    def from_paths(cls, paths: Sequence[Path], root: Optional[Path] = None) -> "TaskCsvIndex":
        """Index từ danh sách file CSV cụ thể (inventory kéo-thả)."""
        path_list = [Path(p) for p in paths if Path(p).is_file() and is_task_csv_file(Path(p))]
        if root is None:
            if path_list:
                try:
                    root = Path(path_list[0]).resolve().parent
                except OSError:
                    root = Path(path_list[0]).parent
            else:
                root = Path(".")
        idx = cls(root=Path(root))
        # Ưu tiên path nông hơn (ít phần path hơn) khi trùng ngày
        candidates: List[Tuple[int, str, date, Path]] = []
        for p in path_list:
            m = _DATE_FILE_RE.match(p.name)
            if not m:
                continue
            try:
                d = datetime.strptime(m.group(1), "%Y%m%d").date()
            except ValueError:
                continue
            candidates.append((len(p.parts), str(p), d, p))
        candidates.sort(key=lambda t: (t[0], t[1]))
        for _depth, _s, d, p in candidates:
            if d not in idx.by_date:
                idx.by_date[d] = p
        return idx

    def path_for(self, d: date) -> Optional[Path]:
        return self.by_date.get(d)

    def rows_for(self, d: date) -> List[TaskRow]:
        """Đọc CSV một ngày, cache trong phiên analyze (thread-safe)."""
        with self._lock:
            if d in self._row_cache:
                return self._row_cache[d]
        path = self.by_date.get(d)
        if path is None:
            with self._lock:
                self._row_cache[d] = []
            return []
        rows = read_task_csv(path)
        with self._lock:
            self._row_cache[d] = rows
            return self._row_cache[d]

    def clear_cache(self) -> None:
        with self._lock:
            self._row_cache.clear()


def find_task_csv_files(root: Path, dates: Sequence[date],
                        index: Optional[TaskCsvIndex] = None) -> Dict[date, Path]:
    """Tìm file CSV theo ngày. Ưu tiên dùng TaskCsvIndex nếu có."""
    if index is not None:
        return {d: index.by_date[d] for d in dates if d in index.by_date}
    # Fallback: build tạm (một lần rglob)
    tmp = TaskCsvIndex.build(Path(root))
    return {d: tmp.by_date[d] for d in dates if d in tmp.by_date}


def load_task_rows_for_base_date(
    root: Path,
    base_date: date,
    index: Optional[TaskCsvIndex] = None,
) -> Tuple[List[TaskRow], List[str]]:
    """Load CSV cho base_date và ngày kế (ca đêm spill), giống reportAnalyse."""
    next_date = base_date + timedelta(days=1)
    if index is None:
        index = TaskCsvIndex.build(Path(root))

    rows: List[TaskRow] = []
    sources: List[str] = []
    for d in (base_date, next_date):
        path = index.path_for(d)
        if path is None:
            continue
        sources.append(str(path))
        rows.extend(index.rows_for(d))
    return rows, sources


def _valid_car(car_id: str) -> bool:
    return str(car_id or "").strip().lower() not in _INVALID_CAR_IDS


def _percentile_sorted(sorted_vals: List[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return round(sorted_vals[0], 1)
    k = (len(sorted_vals) - 1) * pct
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return round(sorted_vals[f], 1)
    return round(sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f), 1)


def utilization_by_shift(
    rows: Sequence[TaskRow],
    day_start: datetime,
    day_end: datetime,
    night_start: datetime,
    night_end: datetime,
) -> Dict[str, Optional[ShiftUtilResult]]:
    """
    稼動率 = tổng duration completed ÷ (thời lượng ca × số xe) × 100.
    Chỉ tính final_state == completed và carId hợp lệ.
    """
    completed = [
        r for r in rows
        if r.final_state == "completed"
        and _valid_car(r.car_id)
        and r.complete_time is not None
        and r.duration_sec > 0
    ]

    results: Dict[str, Optional[ShiftUtilResult]] = {"day": None, "night": None}
    ranges = {
        "day": (day_start, day_end),
        "night": (night_start, night_end),
    }

    for shift_key, (s_start, s_end) in ranges.items():
        shift_sec = (s_end - s_start).total_seconds()
        shift_h = round(shift_sec / 3600.0, 1)
        sdf = [
            r for r in completed
            if s_start <= r.complete_time <= s_end  # type: ignore[operator]
        ]
        if not sdf:
            results[shift_key] = None
            continue

        by_car: Dict[str, CarUtilRow] = {}
        for r in sdf:
            cid = str(r.car_id).strip()
            cu = by_car.get(cid)
            if cu is None:
                cu = CarUtilRow(car_id=cid)
                by_car[cid] = cu
            cu.task_count += 1
            cu.total_sec += r.duration_sec

        car_rows = sorted(by_car.values(), key=lambda x: x.car_id)
        car_count = len(car_rows)
        total_sec = sum(c.total_sec for c in car_rows)
        util = (total_sec / (shift_sec * car_count) * 100.0) if car_count and shift_sec else 0.0

        results[shift_key] = ShiftUtilResult(
            label=shift_key,
            car_rows=car_rows,
            utilization=round(util, 2),
            car_count=car_count,
            shift_h=shift_h,
            shift_sec=shift_sec,
            total_sec=round(total_sec, 1),
            task_count=sum(c.task_count for c in car_rows),
        )

    return results


def _model_stats(rows: Sequence[TaskRow], base_date: Optional[date] = None) -> List[ModelStat]:
    stats: Dict[str, ModelStat] = {}
    for r in rows:
        name = (r.model or "").strip() or "(không rõ)"
        ms = stats.get(name)
        if ms is None:
            ms = ModelStat(model=name)
            stats[name] = ms
        ms.task_count += 1
        if r.car_id and r.car_id not in _INVALID_CAR_IDS:
            cid = str(r.car_id).strip()
            ms.cars.add(cid)
            ms.car_counts[cid] = ms.car_counts.get(cid, 0) + 1
            if r.final_state == "timeout":
                ms.timeout_car_counts[cid] = ms.timeout_car_counts.get(cid, 0) + 1
        t = r.complete_time or r.send_time
        if t is not None:
            h = t.hour
            ms.hour_counts[h] = ms.hour_counts.get(h, 0) + 1
        if base_date is not None:
            ms.days_seen.add(base_date)
            if ms.last_seen is None or base_date > ms.last_seen:
                ms.last_seen = base_date
        if r.final_state == "completed":
            ms.completed_count += 1
        if r.final_state == "timeout":
            ms.timeout_count += 1
        if r.duration_sec > 0:
            ms.total_sec += r.duration_sec
            ms.duration_count += 1
            if r.duration_sec > ms.max_sec:
                ms.max_sec = r.duration_sec
            if ms.min_sec <= 0 or r.duration_sec < ms.min_sec:
                ms.min_sec = r.duration_sec
    result = list(stats.values())
    for ms in result:
        ms.total_sec = round(ms.total_sec, 1)
        ms.max_sec = round(ms.max_sec, 1)
        ms.min_sec = round(ms.min_sec, 1)
    result.sort(key=lambda x: (-x.task_count, -x.total_sec, x.model))
    return result


def analyse_day_tasks(
    root: Optional[Path],
    base_date: date,
    settings: Settings,
    index: Optional[TaskCsvIndex] = None,
) -> DayTaskStats:
    """Phân tích Tasks Log cho một ngày logic.

    Truyền TaskCsvIndex để tránh rglob lại mỗi ngày và tái sử dụng cache CSV.
    """
    stats = DayTaskStats(base_date=base_date)
    if index is None:
        if root is None or not Path(root).exists():
            return stats
        index = TaskCsvIndex.build(Path(root))

    rows, sources = load_task_rows_for_base_date(
        index.root if root is None else Path(root), base_date, index=index)
    stats.source_files = sources
    if not rows:
        return stats

    day_start, day_end, night_start, night_end = calc_shift_ranges(base_date, settings)

    # Chỉ giữ task có complete trong cửa sổ ngày logic
    window_rows = [
        r for r in rows
        if r.complete_time is not None and day_start <= r.complete_time <= night_end
    ]
    if not window_rows:
        # Vẫn có file nhưng không khớp cửa sổ ca
        stats.has_data = bool(sources)
        return stats

    stats.has_data = True
    stats.task_count = len(window_rows)
    stats.completed_count = sum(1 for r in window_rows if r.final_state == "completed")
    stats.timeout_count = sum(1 for r in window_rows if r.final_state == "timeout")
    stats.rows = list(window_rows)

    durations = sorted(
        r.duration_sec for r in window_rows
        if r.final_state == "completed" and r.duration_sec > 0
    )
    if durations:
        stats.avg_cycle_sec = round(sum(durations) / len(durations), 1)
        stats.p50_cycle_sec = _percentile_sorted(durations, 0.5)

    stats.models = _model_stats(window_rows, base_date=base_date)

    util = utilization_by_shift(window_rows, day_start, day_end, night_start, night_end)
    stats.day = util.get("day")
    stats.night = util.get("night")
    return stats


def aggregate_car_utilization(day_stats: Sequence[DayTaskStats]) -> List[CarUtilRow]:
    """Gộp 稼動 theo xe qua nhiều ngày (tổng task + tổng giây completed)."""
    by_car: Dict[str, CarUtilRow] = {}
    for ds in day_stats:
        for shift in (ds.day, ds.night):
            if shift is None:
                continue
            for cr in shift.car_rows:
                cu = by_car.get(cr.car_id)
                if cu is None:
                    cu = CarUtilRow(car_id=cr.car_id)
                    by_car[cr.car_id] = cu
                cu.task_count += cr.task_count
                cu.total_sec += cr.total_sec
    result = list(by_car.values())
    for cu in result:
        cu.total_sec = round(cu.total_sec, 1)
    result.sort(key=lambda x: (-x.total_sec, -x.task_count, x.car_id))
    return result


def shift_label_for_task(
    complete_time: Optional[datetime],
    day_start: datetime,
    day_end: datetime,
    night_start: datetime,
    night_end: datetime,
) -> str:
    if complete_time is None:
        return ""
    if day_start <= complete_time <= day_end:
        return "day"
    if night_start <= complete_time <= night_end:
        return "night"
    return ""


def is_log_txt_file(path: Path) -> bool:
    """File log AGV dạng LogYYYYMMDDHH.txt."""
    path = Path(path)
    if not path.is_file():
        return False
    name = path.name
    return bool(re.match(r"(?i)^Log\d{10}\.txt$", name) or (
        name.lower().startswith("log") and name.lower().endswith(".txt")
        and bool(re.search(r"\d{8}", name))
    ))


def find_log_day_folders(root: Path, max_depth: int = 3) -> List[Path]:
    """Tìm thư mục ngày log dưới root (độ sâu giới hạn)."""
    from .abnormal import detect_base_date, get_log_files

    root = Path(root)
    found: List[Path] = []
    seen = set()

    def walk(cur: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = list(cur.iterdir())
        except OSError:
            return
        # Chính cur có thể là folder ngày
        if detect_base_date(cur) is not None and get_log_files(cur):
            key = str(cur.resolve())
            if key not in seen:
                seen.add(key)
                found.append(cur)
            return  # không đi sâu vào trong folder ngày
        if depth == max_depth:
            return
        for sub in sorted(e for e in entries if e.is_dir()):
            walk(sub, depth + 1)

    if root.is_dir():
        walk(root, 0)
    return found


def utilization_period(day_stats: Sequence[DayTaskStats]) -> float:
    """稼動 kỳ = tổng duration / tổng (shift_sec × car_count) qua các ca có dữ liệu."""
    total_sec = 0.0
    denom = 0.0
    for ds in day_stats:
        for shift in (ds.day, ds.night):
            if shift is None or shift.car_count <= 0:
                continue
            total_sec += shift.total_sec
            denom += shift.denom_sec
    if denom <= 0:
        return 0.0
    return round(total_sec / denom * 100.0, 2)


def aggregate_models(day_stats: Sequence[DayTaskStats]) -> List[ModelStat]:
    """Gộp model qua nhiều ngày."""
    stats: Dict[str, ModelStat] = {}
    for ds in day_stats:
        for m in ds.models:
            ms = stats.get(m.model)
            if ms is None:
                ms = ModelStat(model=m.model)
                stats[m.model] = ms
            ms.task_count += m.task_count
            ms.total_sec += m.total_sec
            ms.timeout_count += m.timeout_count
            ms.completed_count += m.completed_count
            ms.duration_count += m.duration_count
            ms.cars.update(m.cars)
            ms.days_seen.update(m.days_seen)
            for cid, cnt in m.car_counts.items():
                ms.car_counts[cid] = ms.car_counts.get(cid, 0) + cnt
            for cid, cnt in m.timeout_car_counts.items():
                ms.timeout_car_counts[cid] = ms.timeout_car_counts.get(cid, 0) + cnt
            for h, cnt in m.hour_counts.items():
                ms.hour_counts[h] = ms.hour_counts.get(h, 0) + cnt
            if m.last_seen is not None:
                if ms.last_seen is None or m.last_seen > ms.last_seen:
                    ms.last_seen = m.last_seen
            if m.max_sec > ms.max_sec:
                ms.max_sec = m.max_sec
            if m.min_sec > 0 and (ms.min_sec <= 0 or m.min_sec < ms.min_sec):
                ms.min_sec = m.min_sec
    result = list(stats.values())
    for ms in result:
        ms.total_sec = round(ms.total_sec, 1)
        ms.max_sec = round(ms.max_sec, 1)
        ms.min_sec = round(ms.min_sec, 1)
    result.sort(key=lambda x: (-x.task_count, -x.total_sec, x.model))
    return result


def model_priority(ms: ModelStat, fleet_timeout_rate: float, fleet_avg_sec: float,
                   latest_date: Optional[date],
                   recent_days: int = 7,
                   min_tasks: int = 20) -> Tuple[str, float]:
    """Phân loại ưu tiên model: (mức, điểm_số).

    So sánh %timeout và chu kỳ TB với baseline đội (fleet).
    """
    recent = False
    if latest_date is not None and ms.last_seen is not None:
        recent = (latest_date - ms.last_seen).days <= int(recent_days)
    recency = 1.0 if recent else 0.4
    enough = ms.task_count >= int(min_tasks)

    to_rate = float(ms.timeout_rate)
    avg_sec = float(ms.avg_sec)
    fleet_to = max(float(fleet_timeout_rate), 0.0)
    fleet_avg = max(float(fleet_avg_sec), 0.0)

    p1_to = max(5.0, 2.0 * fleet_to) if fleet_to > 0 else 5.0
    p2_to = max(1.0, fleet_to) if fleet_to > 0 else 1.0
    p1_cycle = 2.0 * fleet_avg if fleet_avg > 0 else float("inf")
    p2_cycle = 1.5 * fleet_avg if fleet_avg > 0 else float("inf")

    if enough and recent and (to_rate >= p1_to or avg_sec >= p1_cycle):
        level = "P1"
    elif (recent
          or to_rate >= p2_to
          or (enough and avg_sec >= p2_cycle)):
        level = "P2"
    else:
        level = "P3"

    score = (
        (to_rate / max(fleet_to, 0.1) + avg_sec / max(fleet_avg, 1.0))
        * recency
        * (1.0 if enough else 0.5)
    )
    return (level, round(score, 3))


def model_detail_rows(
    day_stats: Sequence[DayTaskStats], model: str, limit: int = 500
) -> List[Tuple[date, str, str, Optional[datetime], Optional[datetime], float, str]]:
    """Chi tiết task của một model.

    Trả về (ngày, ca, số_xe, gửi, hoàn thành, duration_phút, trạng thái)
    sắp xếp duration dài trước.
    """
    rows: List[Tuple[date, str, str, Optional[datetime], Optional[datetime], float, str]] = []
    for ds in day_stats:
        for tr in ds.rows:
            name = (tr.model or "").strip() or "(không rõ)"
            if name != model:
                continue
            shift = ""
            t = tr.complete_time or tr.send_time
            if t is not None:
                h = t.hour
                shift = "Ca ngày" if 8 <= h < 20 else "Ca đêm"
            rows.append((
                ds.base_date,
                shift,
                tr.car_id,
                tr.send_time,
                tr.complete_time,
                round(tr.duration_sec / 60.0, 2) if tr.duration_sec else 0.0,
                tr.final_state,
            ))
    rows.sort(key=lambda x: (-x[5], x[0], x[3] or datetime.min))
    return rows[:limit]


def period_task_kpis(day_stats: Sequence[DayTaskStats]) -> Dict[str, float]:
    """KPI task gộp: số task, timeout, avg cycle, 稼動."""
    task_count = sum(ds.task_count for ds in day_stats)
    timeout_count = sum(ds.timeout_count for ds in day_stats)
    completed = sum(ds.completed_count for ds in day_stats)
    # avg cycle có trọng số theo completed
    weighted = 0.0
    weight = 0
    for ds in day_stats:
        if ds.avg_cycle_sec > 0 and ds.completed_count > 0:
            weighted += ds.avg_cycle_sec * ds.completed_count
            weight += ds.completed_count
    avg_cycle = round(weighted / weight, 1) if weight else 0.0
    return {
        "task_count": float(task_count),
        "timeout_count": float(timeout_count),
        "completed_count": float(completed),
        "avg_cycle_sec": avg_cycle,
        "utilization": utilization_period(day_stats),
    }


def is_task_csv_file(path: Path) -> bool:
    """True nếu tên file dạng YYYYMMDD.csv (Tasks Log)."""
    path = Path(path)
    if not path.is_file():
        return False
    return bool(_DATE_FILE_RE.match(path.name))


def count_task_csv_files(root: Path, max_scan: int = 5000) -> int:
    """Đếm file YYYYMMDD.csv dưới root (giới hạn để UI nhanh)."""
    root = Path(root)
    if not root.is_dir():
        return 0
    n = 0
    try:
        for p in root.rglob("*.csv"):
            if is_task_csv_file(p):
                n += 1
                if n >= max_scan:
                    break
    except OSError:
        return n
    return n


def looks_like_task_log_dir(path: Path) -> bool:
    """Thư mục chứa (trực tiếp hoặc lồng) ít nhất một YYYYMMDD.csv."""
    path = Path(path)
    if not path.is_dir():
        return False
    # Nhanh: file CSV ngay dưới root
    try:
        for p in path.iterdir():
            if p.is_file() and is_task_csv_file(p):
                return True
    except OSError:
        return False
    # Chậm hơn: quét nông vài cấp
    return count_task_csv_files(path, max_scan=1) > 0


def resolve_task_root_from_paths(paths: Sequence[Path]) -> Optional[Path]:
    """Suy ra thư mục Tasks Log từ file/folder được kéo-thả hoặc chọn.

    - Folder chứa YYYYMMDD.csv -> chính folder đó
    - File YYYYMMDD.csv -> thư mục cha
    - Nhiều CSV cùng cha -> cha chung
    """
    roots: List[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_file() and is_task_csv_file(p):
            roots.append(p.parent.resolve())
        elif p.is_dir() and looks_like_task_log_dir(p):
            roots.append(p.resolve())
    if not roots:
        return None
    # Nếu mọi path cùng một root -> dùng root đó; không thì lấy cha chung nông nhất
    unique = sorted({str(r): r for r in roots}.values(), key=lambda x: str(x))
    if len(unique) == 1:
        return unique[0]
    # Cùng parent?
    parents = {r.parent for r in unique}
    if len(parents) == 1:
        return next(iter(parents))
    # Fallback: root có nhiều CSV nhất
    return max(unique, key=lambda r: count_task_csv_files(r, max_scan=200))


def default_task_log_dir() -> str:
    """Gợi ý thư mục Tasks Log: cạnh .exe, cwd, hoặc gốc repo khi dev."""
    import sys

    names = ("Tasks Log 任务", "Tasks Log", "TasksLog", "tasks_log")
    candidates: List[Path] = []

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir)
        candidates.append(exe_dir.parent)
    else:
        # agv_app/core/tasks.py -> repo root
        repo = Path(__file__).resolve().parent.parent.parent
        candidates.append(repo)
        candidates.append(Path(__file__).resolve().parent.parent)  # agv_app/

    try:
        candidates.append(Path.cwd())
    except OSError:
        pass

    seen = set()
    for base in candidates:
        try:
            base = base.resolve()
        except OSError:
            continue
        key = str(base)
        if key in seen:
            continue
        seen.add(key)
        for name in names:
            cand = base / name
            if cand.is_dir() and looks_like_task_log_dir(cand):
                return str(cand)
        # Chính base đã là Tasks Log (user copy CSV cạnh exe)
        if looks_like_task_log_dir(base):
            # Chỉ nhận nếu có ít nhất 1 YYYYMMDD.csv và không phải thư mục Log ngày
            if count_task_csv_files(base, max_scan=3) > 0:
                return str(base)
    return ""


def missing_dates_in_range(selected: Iterable[date]) -> List[date]:
    """Các ngày thiếu trong khoảng min..max của tập đã chọn."""
    dates = sorted(set(selected))
    if len(dates) < 2:
        return []
    start, end = dates[0], dates[-1]
    have: Set[date] = set(dates)
    missing: List[date] = []
    cur = start
    while cur <= end:
        if cur not in have:
            missing.append(cur)
        cur += timedelta(days=1)
    return missing


def find_log_folders_for_dates(
    parent: Path, dates: Sequence[date]
) -> Dict[date, Path]:
    """Tìm thư mục Log có base_date khớp trong parent."""
    from .abnormal import detect_base_date, get_log_files

    parent = Path(parent)
    wanted = set(dates)
    found: Dict[date, Path] = {}
    if not parent.is_dir():
        return found

    for sub in sorted(parent.iterdir()):
        if not sub.is_dir():
            continue
        d = detect_base_date(sub)
        if d is None or d not in wanted:
            continue
        if not get_log_files(sub):
            continue
        if d not in found:
            found[d] = sub
    return found
