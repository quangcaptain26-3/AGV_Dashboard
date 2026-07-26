"""Phan tich dung do bat thuong cua AGV tu cac file log .txt.

Tai cau truc tu ptich_agv/abnormalAnalyse.py:
  - Giu nguyen regex + quy tac phat hien bat thuong (nguong, loai tru, thang may).
  - KHONG dung datetime.now(): ngay duoc SUY RA tu ten thu muc / ten file log.
  - KHONG di chuyen/xoa log (doc tai cho).
  - Chi dung thu vien chuan (tuong thich Python 3.8).
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

from .config import Settings


# --- Regex (giu nguyen tu ban goc) --------------------------------------------

TIMESTAMP_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3})")

CHARGE_START_PATTERN = re.compile(r"(\d{4})标记自动充电(\d+)")
CHARGE_END_PATTERN = re.compile(r"(\d{4})充电结束")
CHARGE_RELEASE_PATTERN = re.compile(r"(\d{4})缓存释放，充电桩释放\d+")

TASK_ASSIGN_PATTERN = re.compile(r"任务([\w-]+)分配给(\d{4})号车")
TASK_FINISH_PATTERN = re.compile(r"(\d{4})车辆状态修改为NONE，FINISH")

POINT_ARRIVAL_PATTERN = re.compile(r"(\d{4})目标点[：:](\d+)")

# Chuoi khoa nhanh truoc khi chay regex (giam search tren moi dong)
_KW_CHARGE_START = "标记自动充电"
_KW_CHARGE_END = "充电结束"
_KW_CHARGE_RELEASE = "缓存释放"
_KW_TASK_ASSIGN = "分配给"
_KW_TASK_FINISH = "FINISH"
_KW_POINT = "目标点"

# So gio mau so mac dinh khi tinh ty le bat thuong (giong ban goc: 24H * so_xe)
DEFAULT_DENOM_HOURS = 24.0

_FOLDER_DATE_RE = re.compile(r"(\d{8})")
_FILE_DATE_RE = re.compile(r"Log(\d{8})\d{2}", re.IGNORECASE)


# --- Mo hinh du lieu ----------------------------------------------------------

@dataclass
class AbnormalRecord:
    car_id: str
    point_id: str
    arrival_time: datetime
    stay_sec: float

    @property
    def stay_min(self) -> float:
        return round(self.stay_sec / 60.0, 2)


@dataclass
class ShiftResult:
    label: str                       # "day" / "night"
    start: datetime
    end: datetime
    records: List[AbnormalRecord] = field(default_factory=list)
    seen_cars: Set[str] = field(default_factory=set)

    @property
    def all_cars(self) -> List[str]:
        cars = set(self.seen_cars)
        for r in self.records:
            cars.add(r.car_id)
        return sorted(cars)

    @property
    def car_count(self) -> int:
        return len(self.all_cars)

    @property
    def abnormal_count(self) -> int:
        return len(self.records)

    @property
    def abnormal_hours(self) -> float:
        return sum(r.stay_sec for r in self.records) / 3600.0

    @property
    def shift_hours(self) -> float:
        return round((self.end - self.start).total_seconds() / 3600.0, 2)

    def abnormal_rate(self, denom_hours: float = DEFAULT_DENOM_HOURS) -> float:
        cars = self.car_count
        if cars <= 0 or denom_hours <= 0:
            return 0.0
        return round(self.abnormal_hours / (denom_hours * cars) * 100.0, 2)

    def abnormal_by_car(self) -> Dict[str, List[AbnormalRecord]]:
        grouped: Dict[str, List[AbnormalRecord]] = defaultdict(list)
        for r in self.records:
            grouped[r.car_id].append(r)
        for car in grouped:
            grouped[car].sort(key=lambda x: x.arrival_time)
        return dict(grouped)


@dataclass
class DayResult:
    base_date: date
    folder: Path
    day: ShiftResult
    night: ShiftResult
    log_file_count: int = 0
    task_stats: Optional[object] = None  # DayTaskStats từ tasks.py (tránh circular import)
    api_log_stats: Optional[object] = None  # DayApiLogStats từ task_api_log.py
    has_agv_log: bool = True  # False nếu ngày chỉ có CSV/API, không có folder Log

    @property
    def all_cars(self) -> List[str]:
        return sorted(set(self.day.all_cars) | set(self.night.all_cars))

    @property
    def car_count(self) -> int:
        return len(self.all_cars)

    @property
    def abnormal_count(self) -> int:
        return self.day.abnormal_count + self.night.abnormal_count

    @property
    def abnormal_hours(self) -> float:
        return self.day.abnormal_hours + self.night.abnormal_hours

    def abnormal_rate(self, denom_hours: float = DEFAULT_DENOM_HOURS) -> float:
        cars = self.car_count
        if cars <= 0 or denom_hours <= 0:
            return 0.0
        return round(self.abnormal_hours / (denom_hours * cars) * 100.0, 2)

    @property
    def utilization(self) -> float:
        ts = self.task_stats
        if ts is None:
            return 0.0
        return float(getattr(ts, "utilization_all", 0.0) or 0.0)

    @property
    def task_count(self) -> int:
        ts = self.task_stats
        if ts is None:
            return 0
        return int(getattr(ts, "task_count", 0) or 0)

    @property
    def timeout_count(self) -> int:
        ts = self.task_stats
        if ts is None:
            return 0
        return int(getattr(ts, "timeout_count", 0) or 0)

    @property
    def api_create_count(self) -> int:
        api = self.api_log_stats
        if api is None:
            return 0
        return int(getattr(api, "create_count", 0) or 0)

    @property
    def api_poll_count(self) -> int:
        api = self.api_log_stats
        if api is None:
            return 0
        return int(getattr(api, "poll_count", 0) or 0)

    @property
    def api_error_count(self) -> int:
        api = self.api_log_stats
        if api is None:
            return 0
        return int(getattr(api, "api_error_count", 0) or 0)

    @property
    def weekday(self) -> int:
        """0 = Thu Hai ... 5 = Thu Bay, 6 = Chu Nhat."""
        return self.base_date.weekday()

    @property
    def is_saturday(self) -> bool:
        return self.base_date.weekday() == 5

    @property
    def iso_week(self) -> Tuple[int, int]:
        iso = self.base_date.isocalendar()
        return (iso[0], iso[1])   # (nam ISO, tuan ISO)

    @property
    def year_month(self) -> Tuple[int, int]:
        return (self.base_date.year, self.base_date.month)


# --- Suy ra ngay & tim file log ------------------------------------------------

def detect_base_date(folder: Path) -> Optional[date]:
    """Suy ra ngay goc cua thu muc log.

    Uu tien lay tu ten thu muc (vd 'Log20260710' -> 2026-07-10).
    Neu khong duoc thi lay ngay nho nhat tu ten cac file 'Log{YYYYMMDD}{HH}.txt'.
    """
    folder = Path(folder)

    m = _FOLDER_DATE_RE.search(folder.name)
    if m:
        parsed = _parse_yyyymmdd(m.group(1))
        if parsed:
            return parsed

    dates: List[date] = []
    for f in folder.glob("Log*.txt"):
        fm = _FILE_DATE_RE.search(f.stem)
        if fm:
            parsed = _parse_yyyymmdd(fm.group(1))
            if parsed:
                dates.append(parsed)
    if dates:
        return min(dates)

    return None


def _parse_yyyymmdd(text: str) -> Optional[date]:
    try:
        return datetime.strptime(text, "%Y%m%d").date()
    except ValueError:
        return None


def get_log_files(folder: Path) -> List[Path]:
    """Tra ve tat ca file log .txt trong thu muc (khong di chuyen)."""
    folder = Path(folder)
    if not folder.exists():
        return []
    files = [f for f in folder.glob("Log*.txt") if f.is_file()]
    files.sort(key=lambda x: x.name)
    return files


def calc_shift_ranges(base_date: date, settings: Settings):
    """Tinh moc thoi gian ngay/dem dua tren base_date (khong dung now())."""
    next_date = base_date + timedelta(days=1)

    d_hs, d_ms = settings.day_start
    d_he, d_me = settings.day_end
    n_hs, n_ms = settings.night_start
    n_he, n_me = settings.night_end

    day_start = datetime(base_date.year, base_date.month, base_date.day, d_hs, d_ms, 0)
    day_end = datetime(base_date.year, base_date.month, base_date.day, d_he, d_me, 59, 999999)
    night_start = datetime(base_date.year, base_date.month, base_date.day, n_hs, n_ms, 0)
    night_end = datetime(next_date.year, next_date.month, next_date.day, n_he, n_me, 59, 999999)

    return day_start, day_end, night_start, night_end


# --- Parse ---------------------------------------------------------------------

def parse_timestamp(line: str) -> Optional[datetime]:
    match = TIMESTAMP_PATTERN.match(line)
    if not match:
        return None
    ts_str = re.sub(r"\s+", " ", match.group(1).strip())
    try:
        return datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S.%f")
    except ValueError:
        return None


def _determine_shift(ts: datetime, day_range, night_range) -> Optional[str]:
    day_start, day_end = day_range
    night_start, night_end = night_range
    if day_start <= ts <= day_end:
        return "day"
    if night_start <= ts <= night_end:
        return "night"
    return None


def parse_folder(
    folder: Path,
    base_date: Optional[date],
    settings: Settings,
    progress_cb: Optional[Callable[[str], None]] = None,
    cancel_cb: Optional[Callable[[], bool]] = None,
) -> DayResult:
    """Phan tich mot thu muc log -> DayResult (ca ngay + ca dem).

    base_date=None -> tu dong suy ra tu thu muc/file.
    progress_cb(file_name): goi khi bat dau doc tung Log*.txt.
    cancel_cb(): True -> dung som, raise RuntimeError('cancelled').
    """
    folder = Path(folder)
    if base_date is None:
        base_date = detect_base_date(folder)
    if base_date is None:
        raise ValueError(
            "Khong suy ra duoc ngay tu thu muc '%s'. Ten thu muc/file phai chua YYYYMMDD."
            % folder
        )

    day_start, day_end, night_start, night_end = calc_shift_ranges(base_date, settings)
    day_range = (day_start, day_end)
    night_range = (night_start, night_end)

    log_files = get_log_files(folder)

    car_states: Dict[str, Dict] = defaultdict(lambda: {
        "is_charging": False,
        "is_task_active": False,
        "last_point": None,
        "last_point_time": None,
        "last_point_had_task": False,
    })

    shift_records: Dict[str, List[AbnormalRecord]] = {"day": [], "night": []}
    shift_seen: Dict[str, Set[str]] = {"day": set(), "night": set()}

    excluded = settings.excluded_points
    elevator = settings.elevator_points
    threshold_sec = settings.threshold_sec
    elevator_threshold_sec = settings.elevator_threshold_sec

    def check_abnormal(car_id: str, new_time: datetime, shift: Optional[str]) -> None:
        state = car_states[car_id]
        if state["last_point"] is None or state["last_point_time"] is None:
            return
        point_str = str(state["last_point"])
        if point_str in excluded:
            return
        limit = elevator_threshold_sec if point_str in elevator else threshold_sec
        stay = (new_time - state["last_point_time"]).total_seconds()
        if stay > limit and not state["is_charging"] and state["last_point_had_task"]:
            if shift in shift_records:
                shift_records[shift].append(AbnormalRecord(
                    car_id=car_id,
                    point_id=str(state["last_point"]),
                    arrival_time=state["last_point_time"],
                    stay_sec=stay,
                ))

    for log_file in log_files:
        if cancel_cb is not None and cancel_cb():
            raise RuntimeError("cancelled")
        if progress_cb is not None:
            progress_cb(log_file.name)
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    ts = parse_timestamp(line)
                    if not ts:
                        continue
                    if ts < day_start or ts > night_end:
                        continue

                    # Phan loai nhanh bang substring truoc khi regex
                    if _KW_CHARGE_START in line:
                        m = CHARGE_START_PATTERN.search(line)
                        if m:
                            car_states[m.group(1)]["is_charging"] = True
                        continue

                    if _KW_CHARGE_END in line:
                        m = CHARGE_END_PATTERN.search(line)
                        if m:
                            car_states[m.group(1)]["is_charging"] = False
                        continue

                    if _KW_CHARGE_RELEASE in line:
                        m = CHARGE_RELEASE_PATTERN.search(line)
                        if m:
                            car_states[m.group(1)]["is_charging"] = False
                        continue

                    if _KW_TASK_ASSIGN in line:
                        m = TASK_ASSIGN_PATTERN.search(line)
                        if m:
                            car_id = m.group(2)
                            if car_states[car_id]["is_charging"]:
                                car_states[car_id]["is_charging"] = False
                            car_states[car_id]["is_task_active"] = True
                        continue

                    if _KW_TASK_FINISH in line:
                        m = TASK_FINISH_PATTERN.search(line)
                        if m:
                            car_id = m.group(1)
                            car_states[car_id]["is_task_active"] = False
                            car_states[car_id]["last_point_had_task"] = False
                        continue

                    if _KW_POINT in line:
                        m = POINT_ARRIVAL_PATTERN.search(line)
                        if m:
                            car_id = m.group(1)
                            point_id = m.group(2)
                            shift = _determine_shift(ts, day_range, night_range)
                            if shift:
                                shift_seen[shift].add(car_id)
                            check_abnormal(car_id, ts, shift)
                            car_states[car_id]["last_point_had_task"] = (
                                car_states[car_id]["is_task_active"])
                            car_states[car_id]["last_point"] = point_id
                            car_states[car_id]["last_point_time"] = ts
                        continue
        except RuntimeError:
            raise
        except Exception as exc:  # noqa: BLE001 - bo qua file loi, tiep tuc
            print("Canh bao: doc file %s that bai: %s" % (log_file, exc))

    day_result = ShiftResult(
        label="day", start=day_start, end=day_end,
        records=shift_records["day"], seen_cars=shift_seen["day"],
    )
    night_result = ShiftResult(
        label="night", start=night_start, end=night_end,
        records=shift_records["night"], seen_cars=shift_seen["night"],
    )

    return DayResult(
        base_date=base_date,
        folder=folder,
        day=day_result,
        night=night_result,
        log_file_count=len(log_files),
        has_agv_log=True,
    )


def empty_day_result(base_date: date, settings: Settings,
                     folder: Optional[Path] = None) -> DayResult:
    """DayResult rỗng cho ngày chỉ có CSV/API (không có Log AGV)."""
    day_start, day_end, night_start, night_end = calc_shift_ranges(base_date, settings)
    return DayResult(
        base_date=base_date,
        folder=folder or Path("."),
        day=ShiftResult(label="day", start=day_start, end=day_end),
        night=ShiftResult(label="night", start=night_start, end=night_end),
        log_file_count=0,
        has_agv_log=False,
    )
