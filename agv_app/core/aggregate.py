# -*- coding: utf-8 -*-
"""Tổng hợp chất lượng AGV từ danh sách DayResult.

Tỷ lệ bất thường (%) của một kỳ:
    Sum(giờ bất thường của các ngày) / (denom_hours * tổng số xe-ngày) * 100
trong đó "xe-ngày" = tổng số xe hoạt động cộng dồn qua từng ngày (car_count mỗi ngày).
Cách này nhất quán với tỷ lệ từng ngày (denom_hours * số_xe) trong bản gốc.

Ngoài các tổng hợp theo kỳ (tuần / tháng), module còn cung cấp các phân tích
phục vụ báo cáo cho cấp quản lý:
  - aggregate_points : xếp hạng ĐIỂM hay kẹt.
  - aggregate_cars   : xếp hạng XE bất thường.
  - overall_summary  : KPI tổng thể (ngày/xe/tỷ lệ/điểm-xe tệ nhất...).
  - weekday_pattern  : mẫu bất thường theo thứ trong tuần.
  - daynight_split   : so sánh ca ngày và ca đêm.
  - severity_buckets : phân nhóm mức độ nặng theo thời gian dừng.
  - trend_series     : chuỗi tỷ lệ theo ngày (để vẽ biểu đồ).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional, Set, Tuple

from .abnormal import DayResult, DEFAULT_DENOM_HOURS
from .tasks import (
    DayTaskStats,
    ModelStat,
    aggregate_models,
    period_task_kpis,
    utilization_period,
)
from .task_api_log import DayApiLogStats, aggregate_api_kpis

WEEKDAY_VI = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]


def weekday_name(d: date) -> str:
    return WEEKDAY_VI[d.weekday()]


# --- Thống kê theo xe ----------------------------------------------------------

@dataclass
class CarStat:
    car_id: str
    abnormal_count: int = 0
    abnormal_hours: float = 0.0
    days_seen: Set[date] = field(default_factory=set)
    points: Set[str] = field(default_factory=set)
    point_counts: Dict[str, int] = field(default_factory=dict)
    day_count: int = 0
    night_count: int = 0
    max_stay_sec: float = 0.0
    max_stay_point: str = ""
    max_stay_at: Optional[date] = None
    hour_counts: Dict[int, int] = field(default_factory=dict)
    last_seen: Optional[date] = None

    @property
    def abnormal_min(self) -> float:
        return round(self.abnormal_hours * 60.0, 2)

    @property
    def avg_min(self) -> float:
        if self.abnormal_count <= 0:
            return 0.0
        return round(self.abnormal_hours * 60.0 / self.abnormal_count, 2)

    @property
    def max_min(self) -> float:
        return round(self.max_stay_sec / 60.0, 2)

    @property
    def day_seen_count(self) -> int:
        return len(self.days_seen)

    @property
    def point_count(self) -> int:
        return len(self.points)

    @property
    def hot_point(self) -> str:
        if not self.point_counts:
            return ""
        return max(self.point_counts.items(), key=lambda kv: (kv[1], kv[0]))[0]

    @property
    def hot_point_count(self) -> int:
        pt = self.hot_point
        return self.point_counts.get(pt, 0) if pt else 0

    @property
    def per_day(self) -> float:
        """Số lượt kẹt trung bình mỗi ngày có dữ liệu của xe này."""
        n = self.day_seen_count
        if n <= 0:
            return 0.0
        return round(self.abnormal_count / float(n), 2)

    @property
    def hot_point_share(self) -> float:
        """% lượt kẹt dồn vào điểm nóng nhất (0–100)."""
        if self.abnormal_count <= 0:
            return 0.0
        return round(100.0 * self.hot_point_count / float(self.abnormal_count), 1)


def aggregate_cars(days: List[DayResult]) -> List[CarStat]:
    """Cộng dồn số lần/giờ bất thường theo từng xe qua nhiều ngày."""
    stats: Dict[str, CarStat] = {}
    for d in days:
        for shift in (d.day, d.night):
            for rec in shift.records:
                cs = stats.get(rec.car_id)
                if cs is None:
                    cs = CarStat(car_id=rec.car_id)
                    stats[rec.car_id] = cs
                cs.abnormal_count += 1
                cs.abnormal_hours += rec.stay_sec / 3600.0
                cs.days_seen.add(d.base_date)
                cs.points.add(rec.point_id)
                cs.point_counts[rec.point_id] = cs.point_counts.get(rec.point_id, 0) + 1
                if rec.arrival_time is not None:
                    h = rec.arrival_time.hour
                    cs.hour_counts[h] = cs.hour_counts.get(h, 0) + 1
                if cs.last_seen is None or d.base_date > cs.last_seen:
                    cs.last_seen = d.base_date
                if shift.label == "day":
                    cs.day_count += 1
                else:
                    cs.night_count += 1
                if rec.stay_sec > cs.max_stay_sec:
                    cs.max_stay_sec = rec.stay_sec
                    cs.max_stay_point = rec.point_id
                    cs.max_stay_at = d.base_date
    result = list(stats.values())
    for cs in result:
        cs.abnormal_hours = round(cs.abnormal_hours, 4)
    result.sort(key=lambda x: (-x.abnormal_count, -x.abnormal_hours, x.car_id))
    return result


def car_priority(cs: CarStat, threshold_min: float,
                 latest_date: Optional[date],
                 stuck_per_100: Optional[float] = None,
                 fleet_avg_per_100: Optional[float] = None,
                 recent_days: int = 7) -> Tuple[str, float]:
    """Phân loại ưu tiên kiểm tra xe: (mức, điểm_số).

    Khi có Tasks CSV: chuẩn hoá theo Kẹt/100 task so với TB đội.
    Khi không: fallback giống point_priority (lượt/ngày + TB phút).
    """
    thresh = float(threshold_min) if threshold_min and threshold_min > 0 else 1.0
    per_day = float(cs.per_day)
    avg_min = float(cs.avg_min)
    recent = False
    if latest_date is not None and cs.last_seen is not None:
        recent = (latest_date - cs.last_seen).days <= int(recent_days)
    recency = 1.0 if recent else 0.4

    has_task_norm = (
        stuck_per_100 is not None
        and fleet_avg_per_100 is not None
        and float(fleet_avg_per_100) > 0
    )

    if has_task_norm:
        sp100 = float(stuck_per_100)
        fleet = float(fleet_avg_per_100)
        if recent and (sp100 >= 2.0 * fleet or avg_min >= 2.0 * thresh):
            level = "P1"
        elif recent or per_day >= 0.5:
            level = "P2"
        else:
            level = "P3"
        score = (sp100 / fleet) * (avg_min / thresh) * recency
    else:
        if recent and (per_day >= 1.0 or avg_min >= 2.0 * thresh):
            level = "P1"
        elif recent or per_day >= 0.5:
            level = "P2"
        else:
            level = "P3"
        score = per_day * (avg_min / thresh) * recency

    return (level, round(score, 3))


def car_detail_rows(
    days: List[DayResult], car_id: str, limit: int = 500
) -> List[Tuple[date, str, str, datetime, float]]:
    """Chi tiết từng lượt bất thường của một xe.

    Trả về list (ngày, ca, điểm, giờ_đến, phút_dừng) sắp xếp dừng dài trước.
    """
    rows: List[Tuple[date, str, str, datetime, float]] = []
    for d in days:
        for shift in (d.day, d.night):
            label = "Ca ngày" if shift.label == "day" else "Ca đêm"
            for rec in shift.records:
                if rec.car_id != car_id:
                    continue
                rows.append((d.base_date, label, rec.point_id, rec.arrival_time, rec.stay_min))
    rows.sort(key=lambda x: (-x[4], x[0], x[3]))
    return rows[:limit]


# --- Thống kê theo điểm --------------------------------------------------------

@dataclass
class PointStat:
    point_id: str
    abnormal_count: int = 0
    abnormal_hours: float = 0.0
    cars: Set[str] = field(default_factory=set)
    days_seen: Set[date] = field(default_factory=set)
    day_count: int = 0          # lượt thuộc ca ngày
    night_count: int = 0        # lượt thuộc ca đêm
    max_stay_sec: float = 0.0
    max_stay_car: str = ""
    max_stay_at: Optional[date] = None
    car_counts: Dict[str, int] = field(default_factory=dict)
    hour_counts: Dict[int, int] = field(default_factory=dict)
    last_seen: Optional[date] = None

    @property
    def abnormal_min(self) -> float:
        return round(self.abnormal_hours * 60.0, 2)

    @property
    def avg_min(self) -> float:
        if self.abnormal_count <= 0:
            return 0.0
        return round(self.abnormal_hours * 60.0 / self.abnormal_count, 2)

    @property
    def max_min(self) -> float:
        return round(self.max_stay_sec / 60.0, 2)

    @property
    def car_count(self) -> int:
        return len(self.cars)

    @property
    def day_seen_count(self) -> int:
        return len(self.days_seen)

    @property
    def per_day(self) -> float:
        """Số lượt kẹt trung bình mỗi ngày có dữ liệu tại điểm này."""
        n = self.day_seen_count
        if n <= 0:
            return 0.0
        return round(self.abnormal_count / float(n), 2)

    @property
    def top_car(self) -> Tuple[str, int]:
        """Xe gây nhiều lượt nhất tại điểm: (car_id, count)."""
        if not self.car_counts:
            return ("", 0)
        car_id, count = max(self.car_counts.items(), key=lambda kv: (kv[1], kv[0]))
        return (car_id, int(count))

    @property
    def top_car_share(self) -> float:
        """% lượt thuộc xe nhiều nhất (0–100)."""
        if self.abnormal_count <= 0:
            return 0.0
        _, count = self.top_car
        return round(100.0 * count / float(self.abnormal_count), 1)


def aggregate_points(days: List[DayResult]) -> List[PointStat]:
    """Cộng dồn bất thường theo từng ĐIỂM (điểm nào hay kẹt nhất)."""
    stats: Dict[str, PointStat] = {}
    for d in days:
        for shift in (d.day, d.night):
            for rec in shift.records:
                ps = stats.get(rec.point_id)
                if ps is None:
                    ps = PointStat(point_id=rec.point_id)
                    stats[rec.point_id] = ps
                ps.abnormal_count += 1
                ps.abnormal_hours += rec.stay_sec / 3600.0
                ps.cars.add(rec.car_id)
                ps.days_seen.add(d.base_date)
                ps.car_counts[rec.car_id] = ps.car_counts.get(rec.car_id, 0) + 1
                if rec.arrival_time is not None:
                    h = rec.arrival_time.hour
                    ps.hour_counts[h] = ps.hour_counts.get(h, 0) + 1
                if ps.last_seen is None or d.base_date > ps.last_seen:
                    ps.last_seen = d.base_date
                if shift.label == "day":
                    ps.day_count += 1
                else:
                    ps.night_count += 1
                if rec.stay_sec > ps.max_stay_sec:
                    ps.max_stay_sec = rec.stay_sec
                    ps.max_stay_car = rec.car_id
                    ps.max_stay_at = d.base_date
    result = list(stats.values())
    for ps in result:
        ps.abnormal_hours = round(ps.abnormal_hours, 4)
    result.sort(key=lambda x: (-x.abnormal_count, -x.abnormal_hours, x.point_id))
    return result


def point_priority(ps: PointStat, eff_threshold_min: float,
                   latest_date: Optional[date],
                   recent_days: int = 7) -> Tuple[str, float]:
    """Phân loại ưu tiên xử lý điểm: (mức, điểm_số).

    Mức: P1 = xử lý ngay, P2 = theo dõi, P3 = đã lắng.
    ``eff_threshold_min`` = ngưỡng phút hiệu dụng (thường hoặc thang máy).
    ``latest_date`` = ngày cuối trong khoảng dữ liệu (để tính «gần đây»).
    """
    thresh = float(eff_threshold_min) if eff_threshold_min and eff_threshold_min > 0 else 1.0
    per_day = float(ps.per_day)
    avg_min = float(ps.avg_min)
    recent = False
    if latest_date is not None and ps.last_seen is not None:
        recent = (latest_date - ps.last_seen).days <= int(recent_days)

    if recent and (per_day >= 1.0 or avg_min >= 2.0 * thresh):
        level = "P1"
    elif recent or per_day >= 0.5:
        level = "P2"
    else:
        level = "P3"

    score = per_day * (avg_min / thresh) * (1.0 if recent else 0.4)
    return (level, round(score, 3))


def point_detail_rows(
    days: List[DayResult], point_id: str, limit: int = 500
) -> List[Tuple[date, str, str, datetime, float]]:
    """Chi tiết từng lượt bất thường tại một điểm.

    Trả về list (ngày, ca, số_xe, giờ_đến, phút_dừng) sắp xếp dừng dài trước.
    """
    rows: List[Tuple[date, str, str, datetime, float]] = []
    for d in days:
        for shift in (d.day, d.night):
            label = "Ca ngày" if shift.label == "day" else "Ca đêm"
            for rec in shift.records:
                if rec.point_id != point_id:
                    continue
                rows.append((d.base_date, label, rec.car_id, rec.arrival_time, rec.stay_min))
    rows.sort(key=lambda x: (-x[4], x[0], x[3]))
    return rows[:limit]


# --- Tổng hợp theo kỳ ----------------------------------------------------------

@dataclass
class PeriodSummary:
    """Tóm tắt một kỳ (tuần / tháng)."""

    kind: str                       # 'week' | 'month'
    label: str                      # nhãn hiển thị, vd '2026-W28' hoặc '2026-07'
    days: List[DayResult] = field(default_factory=list)
    denom_hours: float = DEFAULT_DENOM_HOURS

    @property
    def num_days(self) -> int:
        return len(self.days)

    @property
    def date_start(self):
        return min(d.base_date for d in self.days) if self.days else None

    @property
    def date_end(self):
        return max(d.base_date for d in self.days) if self.days else None

    @property
    def abnormal_count(self) -> int:
        return sum(d.abnormal_count for d in self.days)

    @property
    def abnormal_hours(self) -> float:
        return sum(d.abnormal_hours for d in self.days)

    @property
    def car_days(self) -> int:
        """Tổng số xe-ngày (mẫu số quy đổi)."""
        return sum(d.car_count for d in self.days)

    @property
    def distinct_car_count(self) -> int:
        cars = set()
        for d in self.days:
            cars.update(d.all_cars)
        return len(cars)

    @property
    def abnormal_rate(self) -> float:
        if self.car_days <= 0 or self.denom_hours <= 0:
            return 0.0
        return round(self.abnormal_hours / (self.denom_hours * self.car_days) * 100.0, 2)

    @property
    def task_stats_list(self) -> List[DayTaskStats]:
        out: List[DayTaskStats] = []
        for d in self.days:
            ts = d.task_stats
            if isinstance(ts, DayTaskStats):
                out.append(ts)
        return out

    @property
    def utilization(self) -> float:
        return utilization_period(self.task_stats_list)

    @property
    def task_count(self) -> int:
        return sum(d.task_count for d in self.days)

    @property
    def timeout_count(self) -> int:
        return sum(d.timeout_count for d in self.days)

    @property
    def avg_cycle_sec(self) -> float:
        kpis = period_task_kpis(self.task_stats_list)
        return float(kpis.get("avg_cycle_sec", 0.0))

    def model_stats(self) -> List[ModelStat]:
        return aggregate_models(self.task_stats_list)

    def car_stats(self) -> List[CarStat]:
        return aggregate_cars(self.days)

    def point_stats(self) -> List[PointStat]:
        return aggregate_points(self.days)

    def sorted_days(self) -> List[DayResult]:
        return sorted(self.days, key=lambda d: d.base_date)


def weekly_summaries(day_results: List[DayResult],
                     denom_hours: float = DEFAULT_DENOM_HOURS) -> List[PeriodSummary]:
    """Gom theo tuần ISO (Thứ Hai - Chủ Nhật)."""
    groups: Dict[Tuple[int, int], List[DayResult]] = defaultdict(list)
    for d in day_results:
        groups[d.iso_week].append(d)

    summaries: List[PeriodSummary] = []
    for (iso_year, iso_week) in sorted(groups.keys()):
        days = sorted(groups[(iso_year, iso_week)], key=lambda d: d.base_date)
        summaries.append(PeriodSummary(
            kind="week",
            label="%d-W%02d" % (iso_year, iso_week),
            days=days,
            denom_hours=denom_hours,
        ))
    return summaries


def monthly_summaries(day_results: List[DayResult],
                      denom_hours: float = DEFAULT_DENOM_HOURS) -> List[PeriodSummary]:
    """Gom theo tháng dương lịch."""
    groups: Dict[Tuple[int, int], List[DayResult]] = defaultdict(list)
    for d in day_results:
        groups[d.year_month].append(d)

    summaries: List[PeriodSummary] = []
    for (year, month) in sorted(groups.keys()):
        days = sorted(groups[(year, month)], key=lambda d: d.base_date)
        summaries.append(PeriodSummary(
            kind="month",
            label="%04d-%02d" % (year, month),
            days=days,
            denom_hours=denom_hours,
        ))
    return summaries


# --- KPI tổng thể --------------------------------------------------------------

@dataclass
class OverallSummary:
    """KPI tổng thể của toàn bộ dữ liệu đã nạp - phục vụ dashboard cho sếp."""

    num_days: int = 0
    distinct_cars: int = 0
    car_days: int = 0
    abnormal_count: int = 0
    abnormal_hours: float = 0.0
    denom_hours: float = DEFAULT_DENOM_HOURS
    day_abnormal_hours: float = 0.0
    night_abnormal_hours: float = 0.0
    worst_day: Optional[DayResult] = None
    best_day: Optional[DayResult] = None
    top_car: Optional[CarStat] = None
    top_point: Optional[PointStat] = None
    utilization: float = 0.0
    task_count: int = 0
    timeout_count: int = 0
    avg_cycle_sec: float = 0.0
    top_models: List[ModelStat] = field(default_factory=list)
    # Điều phối API
    api_create_count: int = 0
    api_poll_count: int = 0
    api_unique_tasks: int = 0
    api_error_count: int = 0
    api_hot_point: str = ""
    api_hot_point_count: int = 0
    days_with_api: int = 0
    days_with_agv: int = 0
    days_with_csv: int = 0

    @property
    def abnormal_rate(self) -> float:
        if self.car_days <= 0 or self.denom_hours <= 0:
            return 0.0
        return round(self.abnormal_hours / (self.denom_hours * self.car_days) * 100.0, 2)

    @property
    def abnormal_minutes(self) -> float:
        return round(self.abnormal_hours * 60.0, 2)

    @property
    def avg_stay_min(self) -> float:
        if self.abnormal_count <= 0:
            return 0.0
        return round(self.abnormal_hours * 60.0 / self.abnormal_count, 2)

    @property
    def avg_abnormal_per_day(self) -> float:
        if self.num_days <= 0:
            return 0.0
        return round(self.abnormal_count / self.num_days, 2)


def overall_summary(day_results: List[DayResult],
                    denom_hours: float = DEFAULT_DENOM_HOURS) -> OverallSummary:
    if not day_results:
        return OverallSummary(denom_hours=denom_hours)

    distinct = set()
    for d in day_results:
        distinct.update(d.all_cars)

    cars = aggregate_cars(day_results)
    points = aggregate_points(day_results)

    worst = max(day_results, key=lambda d: d.abnormal_rate(denom_hours))
    best = min(day_results, key=lambda d: d.abnormal_rate(denom_hours))

    task_list: List[DayTaskStats] = []
    for d in day_results:
        if isinstance(d.task_stats, DayTaskStats):
            task_list.append(d.task_stats)
    kpis = period_task_kpis(task_list)

    api_list: List[DayApiLogStats] = []
    for d in day_results:
        api = d.api_log_stats
        if isinstance(api, DayApiLogStats) and api.has_data:
            api_list.append(api)
    api_kpis = aggregate_api_kpis(api_list)

    days_with_agv = sum(1 for d in day_results if getattr(d, "has_agv_log", True))
    days_with_csv = sum(
        1 for d in day_results
        if isinstance(d.task_stats, DayTaskStats) and d.task_stats.has_data
    )

    return OverallSummary(
        num_days=len(day_results),
        distinct_cars=len(distinct),
        car_days=sum(d.car_count for d in day_results),
        abnormal_count=sum(d.abnormal_count for d in day_results),
        abnormal_hours=round(sum(d.abnormal_hours for d in day_results), 4),
        denom_hours=denom_hours,
        day_abnormal_hours=round(sum(d.day.abnormal_hours for d in day_results), 4),
        night_abnormal_hours=round(sum(d.night.abnormal_hours for d in day_results), 4),
        worst_day=worst,
        best_day=best,
        top_car=cars[0] if cars else None,
        top_point=points[0] if points else None,
        utilization=float(kpis.get("utilization", 0.0)),
        task_count=int(kpis.get("task_count", 0)),
        timeout_count=int(kpis.get("timeout_count", 0)),
        avg_cycle_sec=float(kpis.get("avg_cycle_sec", 0.0)),
        top_models=aggregate_models(task_list)[:10],
        api_create_count=int(api_kpis.get("create_count", 0)),
        api_poll_count=int(api_kpis.get("poll_count", 0)),
        api_unique_tasks=int(api_kpis.get("unique_tasks", 0)),
        api_error_count=int(api_kpis.get("api_error_count", 0)),
        api_hot_point=str(api_kpis.get("hot_point", "") or ""),
        api_hot_point_count=int(api_kpis.get("hot_point_count", 0)),
        days_with_api=int(api_kpis.get("days_with_api", 0)),
        days_with_agv=days_with_agv,
        days_with_csv=days_with_csv,
    )


# --- Mẫu theo thứ trong tuần ---------------------------------------------------

@dataclass
class WeekdayStat:
    weekday: int                    # 0 = Thứ Hai ... 6 = Chủ Nhật
    name: str
    num_days: int = 0
    abnormal_count: int = 0
    abnormal_hours: float = 0.0
    car_days: int = 0
    denom_hours: float = DEFAULT_DENOM_HOURS

    @property
    def abnormal_rate(self) -> float:
        if self.car_days <= 0 or self.denom_hours <= 0:
            return 0.0
        return round(self.abnormal_hours / (self.denom_hours * self.car_days) * 100.0, 2)


def weekday_pattern(day_results: List[DayResult],
                    denom_hours: float = DEFAULT_DENOM_HOURS) -> List[WeekdayStat]:
    """Gộp theo thứ trong tuần (thứ mấy hay bất thường nhất)."""
    stats = [WeekdayStat(weekday=i, name=WEEKDAY_VI[i], denom_hours=denom_hours)
             for i in range(7)]
    for d in day_results:
        s = stats[d.base_date.weekday()]
        s.num_days += 1
        s.abnormal_count += d.abnormal_count
        s.abnormal_hours += d.abnormal_hours
        s.car_days += d.car_count
    for s in stats:
        s.abnormal_hours = round(s.abnormal_hours, 4)
    return stats


# --- So sánh ca ngày / ca đêm --------------------------------------------------

@dataclass
class ShiftAggregate:
    label: str                      # 'Ca ngày' | 'Ca đêm'
    abnormal_count: int = 0
    abnormal_hours: float = 0.0
    car_days: int = 0
    denom_hours: float = DEFAULT_DENOM_HOURS

    @property
    def abnormal_rate(self) -> float:
        if self.car_days <= 0 or self.denom_hours <= 0:
            return 0.0
        return round(self.abnormal_hours / (self.denom_hours * self.car_days) * 100.0, 2)

    @property
    def abnormal_min(self) -> float:
        return round(self.abnormal_hours * 60.0, 2)


def daynight_split(day_results: List[DayResult],
                   denom_hours: float = DEFAULT_DENOM_HOURS) -> List[ShiftAggregate]:
    """Trả về [ca ngày, ca đêm] đã cộng dồn toàn bộ dữ liệu."""
    day_agg = ShiftAggregate(label="Ca ngày", denom_hours=denom_hours)
    night_agg = ShiftAggregate(label="Ca đêm", denom_hours=denom_hours)
    for d in day_results:
        day_agg.abnormal_count += d.day.abnormal_count
        day_agg.abnormal_hours += d.day.abnormal_hours
        day_agg.car_days += d.day.car_count
        night_agg.abnormal_count += d.night.abnormal_count
        night_agg.abnormal_hours += d.night.abnormal_hours
        night_agg.car_days += d.night.car_count
    day_agg.abnormal_hours = round(day_agg.abnormal_hours, 4)
    night_agg.abnormal_hours = round(night_agg.abnormal_hours, 4)
    return [day_agg, night_agg]


# --- Phân nhóm mức độ nặng -----------------------------------------------------

@dataclass
class SeverityBucket:
    label: str
    min_minutes: float
    max_minutes: float              # float('inf') cho nhóm cuối
    count: int = 0
    abnormal_hours: float = 0.0

    @property
    def abnormal_min(self) -> float:
        return round(self.abnormal_hours * 60.0, 2)


def severity_buckets(day_results: List[DayResult]) -> List[SeverityBucket]:
    """Phân nhóm các lần bất thường theo thời gian dừng (mức độ nghiêm trọng)."""
    buckets = [
        SeverityBucket("Ngắn (< 20 phút)", 0, 20),
        SeverityBucket("Vừa (20 - 40 phút)", 20, 40),
        SeverityBucket("Dài (40 - 60 phút)", 40, 60),
        SeverityBucket("Rất dài (> 60 phút)", 60, float("inf")),
    ]
    for d in day_results:
        for shift in (d.day, d.night):
            for rec in shift.records:
                m = rec.stay_min
                for b in buckets:
                    if b.min_minutes <= m < b.max_minutes:
                        b.count += 1
                        b.abnormal_hours += rec.stay_sec / 3600.0
                        break
    for b in buckets:
        b.abnormal_hours = round(b.abnormal_hours, 4)
    return buckets


# --- Chuỗi xu hướng theo ngày --------------------------------------------------

def trend_series(day_results: List[DayResult],
                 denom_hours: float = DEFAULT_DENOM_HOURS) -> List[Tuple[date, float]]:
    """Danh sách (ngày, tỷ lệ bất thường %) theo thứ tự thời gian - để vẽ biểu đồ."""
    days = sorted(day_results, key=lambda d: d.base_date)
    return [(d.base_date, d.abnormal_rate(denom_hours)) for d in days]


def utilization_trend_series(day_results: List[DayResult]) -> List[Tuple[date, float]]:
    """Chuỗi (ngày, 稼動率 %) theo thời gian."""
    days = sorted(day_results, key=lambda d: d.base_date)
    return [(d.base_date, d.utilization) for d in days]


def api_create_trend_series(day_results: List[DayResult]) -> List[Tuple[date, float]]:
    """Chuỗi (ngày, số taskCreate) theo thời gian."""
    days = sorted(day_results, key=lambda d: d.base_date)
    return [(d.base_date, float(d.api_create_count)) for d in days]


def source_gap_messages(day_results: List[DayResult]) -> List[str]:
    """Banner thiếu nguồn trong kết quả đã phân tích."""
    if not day_results:
        return []
    has_agv = {d.base_date for d in day_results if getattr(d, "has_agv_log", True)}
    has_csv = {
        d.base_date for d in day_results
        if isinstance(d.task_stats, DayTaskStats) and d.task_stats.has_data
    }
    has_api = {
        d.base_date for d in day_results
        if isinstance(d.api_log_stats, DayApiLogStats) and d.api_log_stats.has_data
    }
    msgs: List[str] = []
    if has_csv and (has_csv - has_agv):
        msgs.append("%d ngày có CSV nhưng thiếu Log AGV" % len(has_csv - has_agv))
    if has_api and (has_api - has_agv):
        msgs.append("%d ngày có API log nhưng thiếu Log AGV" % len(has_api - has_agv))
    if has_agv and has_csv and (has_agv - has_csv):
        msgs.append("%d ngày có Log AGV nhưng thiếu CSV" % len(has_agv - has_csv))
    if has_csv and has_api and (has_csv - has_api):
        msgs.append("%d ngày có CSV nhưng thiếu API log" % len(has_csv - has_api))
    return msgs


def top_api_points(day_results: List[DayResult], limit: int = 15) -> List[Tuple[str, int]]:
    """Top điểm xuất hiện trong payload API (create + poll)."""
    from collections import defaultdict
    counts: Dict[str, int] = defaultdict(int)
    for d in day_results:
        api = d.api_log_stats
        if not isinstance(api, DayApiLogStats) or not api.has_data:
            continue
        for pt, n in api.top_points:
            counts[pt] += n
    return sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:limit]
