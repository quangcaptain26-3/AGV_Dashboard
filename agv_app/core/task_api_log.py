# -*- coding: utf-8 -*-
"""Parser Tasks API logs (logs/*.log, debug_*.log).

Nguồn C — điều phối MES:
  - taskCreate: POST + JSON body (points, systemName, score)
  - poll (debug): raw JSON taskinfo
  - poll done (log thường): state=completed/timeout, dur=...
"""

from __future__ import annotations

import json
import re
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

_TS_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]")
_CREATE_RE = re.compile(r"POST\s+\S*taskCreate", re.IGNORECASE)
_POLL_RAW_RE = re.compile(
    r"\[poll\s+([^\]]+)\]\s+raw=(.+)$", re.IGNORECASE)
_POLL_DONE_RE = re.compile(
    r"\[poll\s+([^\]]+)\]\s+done,\s*state=(\w+),\s*dur=([\d.]+)s",
    re.IGNORECASE)
_API_LOG_NAME_RE = re.compile(r"^(?:debug_)?(\d{8})\.log$", re.IGNORECASE)


@dataclass
class TaskCreateEvent:
    ts: Optional[datetime]
    points: List[Tuple[str, str]] = field(default_factory=list)  # (point, action)
    system_name: str = ""
    score: Optional[float] = None
    source_file: str = ""


@dataclass
class PollEvent:
    ts: Optional[datetime]
    task_id: str
    state: str = ""
    car_id: str = ""
    points: List[str] = field(default_factory=list)
    state_code: Optional[int] = None
    duration_sec: Optional[float] = None
    kind: str = "raw"  # raw | done
    source_file: str = ""


@dataclass
class DayApiLogStats:
    """Thống kê điều phối API theo ngày lịch (file log)."""

    base_date: date
    create_count: int = 0
    poll_count: int = 0
    unique_tasks: int = 0
    assigned_car_count: int = 0  # poll có carId != 0/rỗng
    api_error_count: int = 0     # stateCode != 0
    top_points: List[Tuple[str, int]] = field(default_factory=list)
    creates: List[TaskCreateEvent] = field(default_factory=list, repr=False)
    source_files: List[str] = field(default_factory=list)
    has_data: bool = False

    @property
    def hot_point(self) -> str:
        return self.top_points[0][0] if self.top_points else ""

    @property
    def hot_point_count(self) -> int:
        return self.top_points[0][1] if self.top_points else 0


def date_from_api_log_name(path: Path) -> Optional[date]:
    m = _API_LOG_NAME_RE.match(Path(path).name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d").date()
    except ValueError:
        return None


def _parse_ts(line: str) -> Optional[datetime]:
    m = _TS_RE.match(line)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _extract_points_from_create(payload: dict) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    pts = payload.get("points") or []
    if not isinstance(pts, list):
        return out
    for item in pts:
        if isinstance(item, dict):
            pt = str(item.get("point", "") or "").strip()
            act = str(item.get("action", "") or "").strip()
            if pt:
                out.append((pt, act))
        elif item is not None:
            out.append((str(item).strip(), ""))
    return out


def _safe_json_loads(text: str) -> Optional[dict]:
    text = (text or "").strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def parse_task_api_log(path: Path) -> Tuple[List[TaskCreateEvent], List[PollEvent]]:
    """Stream parse một file API log → creates + polls."""
    path = Path(path)
    creates: List[TaskCreateEvent] = []
    polls: List[PollEvent] = []
    if not path.is_file():
        return creates, polls

    pending_ts: Optional[datetime] = None
    awaiting_json = False
    collecting_json = False
    json_buf: List[str] = []
    brace_depth = 0

    def flush_json() -> None:
        nonlocal collecting_json, json_buf, brace_depth, pending_ts, awaiting_json
        awaiting_json = False
        if not json_buf:
            collecting_json = False
            brace_depth = 0
            return
        payload = _safe_json_loads("\n".join(json_buf))
        collecting_json = False
        json_buf = []
        brace_depth = 0
        if payload is None:
            pending_ts = None
            return
        pts = _extract_points_from_create(payload)
        score = payload.get("score")
        try:
            score_f = float(score) if score is not None else None
        except (TypeError, ValueError):
            score_f = None
        creates.append(TaskCreateEvent(
            ts=pending_ts,
            points=pts,
            system_name=str(payload.get("systemName", "") or ""),
            score=score_f,
            source_file=str(path),
        ))
        pending_ts = None

    def start_json(fragment: str) -> None:
        nonlocal collecting_json, json_buf, brace_depth, awaiting_json
        awaiting_json = False
        collecting_json = True
        json_buf = [fragment]
        brace_depth = fragment.count("{") - fragment.count("}")
        if brace_depth <= 0:
            flush_json()

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for raw_line in f:
                line = raw_line.rstrip("\n\r")

                if collecting_json:
                    json_buf.append(line)
                    brace_depth += line.count("{") - line.count("}")
                    if brace_depth <= 0 and json_buf:
                        flush_json()
                    continue

                if awaiting_json:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    # JSON body có thể cùng dòng timestamp: "[...] {"
                    brace_idx = stripped.find("{")
                    if brace_idx >= 0:
                        # Lấy từ dấu { gốc trên dòng (giữ indent JSON)
                        raw_idx = line.find("{")
                        start_json(line[raw_idx:] if raw_idx >= 0 else stripped[brace_idx:])
                        continue
                    # Hủy chờ JSON nếu dòng không phải body
                    awaiting_json = False
                    pending_ts = None

                ts = _parse_ts(line)

                if _CREATE_RE.search(line):
                    pending_ts = ts
                    brace_idx = line.find("{")
                    if brace_idx >= 0:
                        start_json(line[brace_idx:])
                    else:
                        awaiting_json = True
                        collecting_json = False
                        json_buf = []
                        brace_depth = 0
                    continue

                m_raw = _POLL_RAW_RE.search(line)
                if m_raw:
                    task_id = m_raw.group(1).strip()
                    payload = _safe_json_loads(m_raw.group(2))
                    state = ""
                    car_id = ""
                    points: List[str] = []
                    state_code = None
                    if payload:
                        state_code = payload.get("stateCode")
                        try:
                            state_code = int(state_code) if state_code is not None else None
                        except (TypeError, ValueError):
                            state_code = None
                        info = payload.get("taskinfo") or {}
                        if isinstance(info, dict):
                            state = str(info.get("state", "") or "")
                            car_id = str(info.get("carId", "") or "").strip()
                            tid = str(info.get("taskId", "") or "").strip()
                            if tid:
                                task_id = tid
                            raw_pts = info.get("points") or []
                            if isinstance(raw_pts, list):
                                points = [str(x) for x in raw_pts]
                    polls.append(PollEvent(
                        ts=ts,
                        task_id=task_id,
                        state=state,
                        car_id=car_id,
                        points=points,
                        state_code=state_code,
                        kind="raw",
                        source_file=str(path),
                    ))
                    continue

                m_done = _POLL_DONE_RE.search(line)
                if m_done:
                    try:
                        dur = float(m_done.group(3))
                    except ValueError:
                        dur = None
                    polls.append(PollEvent(
                        ts=ts,
                        task_id=m_done.group(1).strip(),
                        state=m_done.group(2).strip(),
                        duration_sec=dur,
                        kind="done",
                        source_file=str(path),
                    ))
                    continue
    except OSError:
        return creates, polls

    if collecting_json and json_buf:
        flush_json()

    return creates, polls


def build_day_api_stats(
    base_date: date,
    creates: Sequence[TaskCreateEvent],
    polls: Sequence[PollEvent],
    source_files: Optional[Sequence[str]] = None,
) -> DayApiLogStats:
    point_counts: Dict[str, int] = defaultdict(int)
    for ev in creates:
        for pt, _act in ev.points:
            if pt:
                point_counts[pt] += 1
    for ev in polls:
        for pt in ev.points:
            if pt:
                point_counts[pt] += 1

    top = sorted(point_counts.items(), key=lambda x: (-x[1], x[0]))[:20]

    task_ids = set()
    assigned = 0
    errors = 0
    for ev in polls:
        if ev.task_id:
            task_ids.add(ev.task_id)
        cid = (ev.car_id or "").strip()
        if cid and cid not in {"0", "None", "none", "null"}:
            assigned += 1
        if ev.state_code is not None and ev.state_code != 0:
            errors += 1

    stats = DayApiLogStats(
        base_date=base_date,
        create_count=len(creates),
        poll_count=len(polls),
        unique_tasks=len(task_ids),
        assigned_car_count=assigned,
        api_error_count=errors,
        top_points=top,
        creates=list(creates),
        source_files=list(source_files or []),
        has_data=bool(creates or polls),
    )
    return stats


@dataclass
class ApiLogIndex:
    """Index file API log theo ngày + cache stats."""

    by_date: Dict[date, List[Path]] = field(default_factory=dict)
    _stats_cache: Dict[date, DayApiLogStats] = field(default_factory=dict, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @classmethod
    def from_paths(cls, paths: Iterable[Path]) -> "ApiLogIndex":
        idx = cls()
        for raw in paths:
            p = Path(raw)
            if not p.is_file():
                continue
            d = date_from_api_log_name(p)
            if d is None:
                continue
            idx.by_date.setdefault(d, [])
            # Dedup path
            resolved = None
            try:
                resolved = p.resolve()
            except OSError:
                resolved = p
            existing = {str(x.resolve()) if x.exists() else str(x) for x in idx.by_date[d]}
            key = str(resolved)
            if key not in existing:
                idx.by_date[d].append(p)
        return idx

    def dates(self) -> List[date]:
        return sorted(self.by_date.keys())

    def stats_for(self, d: date) -> Optional[DayApiLogStats]:
        with self._lock:
            if d in self._stats_cache:
                return self._stats_cache[d]
        paths = self.by_date.get(d) or []
        if not paths:
            return None
        all_creates: List[TaskCreateEvent] = []
        all_polls: List[PollEvent] = []
        sources: List[str] = []
        # Ưu tiên file không debug trước (taskCreate), rồi debug (poll raw)
        ordered = sorted(
            paths,
            key=lambda p: (1 if Path(p).name.lower().startswith("debug_") else 0, str(p)),
        )
        for p in ordered:
            creates, polls = parse_task_api_log(p)
            all_creates.extend(creates)
            all_polls.extend(polls)
            sources.append(str(p))
        stats = build_day_api_stats(d, all_creates, all_polls, sources)
        with self._lock:
            self._stats_cache[d] = stats
        return stats

    def clear_cache(self) -> None:
        with self._lock:
            self._stats_cache.clear()


def aggregate_api_kpis(day_stats: Sequence[DayApiLogStats]) -> Dict[str, float]:
    create_count = sum(s.create_count for s in day_stats if s and s.has_data)
    poll_count = sum(s.poll_count for s in day_stats if s and s.has_data)
    unique = sum(s.unique_tasks for s in day_stats if s and s.has_data)
    errors = sum(s.api_error_count for s in day_stats if s and s.has_data)
    assigned = sum(s.assigned_car_count for s in day_stats if s and s.has_data)
    point_counts: Dict[str, int] = defaultdict(int)
    for s in day_stats:
        if not s or not s.has_data:
            continue
        for pt, n in s.top_points:
            point_counts[pt] += n
    hot = ""
    hot_n = 0
    if point_counts:
        hot, hot_n = max(point_counts.items(), key=lambda x: (x[1], x[0]))
    return {
        "create_count": float(create_count),
        "poll_count": float(poll_count),
        "unique_tasks": float(unique),
        "api_error_count": float(errors),
        "assigned_car_count": float(assigned),
        "hot_point_count": float(hot_n),
        "days_with_api": float(sum(1 for s in day_stats if s and s.has_data)),
        "hot_point": hot,  # type: ignore[dict-item]
    }


def csv_api_crosscheck(
    day_results: Sequence[object],
) -> List[Dict[str, object]]:
    """Đối chiếu CSV task_count vs API create_count theo ngày."""
    rows: List[Dict[str, object]] = []
    for d in sorted(day_results, key=lambda x: getattr(x, "base_date")):
        base = getattr(d, "base_date", None)
        if base is None:
            continue
        csv_count = int(getattr(d, "task_count", 0) or 0)
        api = getattr(d, "api_log_stats", None)
        create_count = int(getattr(api, "create_count", 0) or 0) if api else 0
        poll_count = int(getattr(api, "poll_count", 0) or 0) if api else 0
        has_csv = bool(
            getattr(getattr(d, "task_stats", None), "has_data", False)
        )
        has_api = bool(getattr(api, "has_data", False)) if api else False
        if not has_csv and not has_api:
            continue
        diff = csv_count - create_count
        rows.append({
            "date": base,
            "csv_task_count": csv_count,
            "api_create_count": create_count,
            "api_poll_count": poll_count,
            "diff_csv_minus_api": diff,
            "has_csv": has_csv,
            "has_api": has_api,
        })
    return rows
