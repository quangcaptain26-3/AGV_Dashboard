# -*- coding: utf-8 -*-
"""Pipeline phân tích nhiều ngày: song song, hủy, progress.

Dùng ThreadPoolExecutor (không ProcessPool) để tránh pickle trên Windows
và giữ PyInstaller đơn giản.

Hỗ trợ 3 nguồn qua DataInventory:
  A. Folder Log AGV ngày
  B. Tasks CSV
  C. Tasks API logs
"""

from __future__ import annotations

import os
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Set, Union

from .abnormal import DayResult, empty_day_result, parse_folder
from .config import Settings
from .ingest import DataInventory, DataKind
from .task_api_log import ApiLogIndex
from .tasks import TaskCsvIndex, analyse_day_tasks

ProgressCb = Callable[[int, int, str], None]  # done, total, message


@dataclass
class AnalyzeOutcome:
    """Kết quả một lần phân tích (có thể partial nếu bị hủy)."""

    results: List[DayResult] = field(default_factory=list)
    cancelled: bool = False
    errors: List[str] = field(default_factory=list)
    workers_used: int = 1


class CancelToken:
    """Cờ hủy an toàn giữa các thread."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def check(self) -> bool:
        """True nếu nên dừng."""
        return self._event.is_set()


def default_workers() -> int:
    cpu = os.cpu_count() or 2
    return max(1, min(4, cpu))


def _analyze_one_folder(
    folder: Path,
    settings: Settings,
    task_index: Optional[TaskCsvIndex],
    api_index: Optional[ApiLogIndex],
    cancel: Optional[CancelToken],
    file_progress: Optional[Callable[[str], None]],
) -> DayResult:
    if cancel is not None and cancel.check():
        raise RuntimeError("cancelled")

    def on_file(name: str) -> None:
        if file_progress:
            file_progress(name)

    def should_cancel() -> bool:
        return bool(cancel and cancel.check())

    dr = parse_folder(
        folder, None, settings,
        progress_cb=on_file,
        cancel_cb=should_cancel,
    )
    if cancel is not None and cancel.check():
        raise RuntimeError("cancelled")

    if task_index is not None:
        try:
            dr.task_stats = analyse_day_tasks(
                task_index.root, dr.base_date, settings, index=task_index)
        except Exception:
            pass

    if api_index is not None:
        try:
            dr.api_log_stats = api_index.stats_for(dr.base_date)
        except Exception:
            pass
    return dr


def _attach_csv_api(
    dr: DayResult,
    settings: Settings,
    task_index: Optional[TaskCsvIndex],
    api_index: Optional[ApiLogIndex],
) -> None:
    if task_index is not None and dr.task_stats is None:
        try:
            dr.task_stats = analyse_day_tasks(
                task_index.root, dr.base_date, settings, index=task_index)
        except Exception:
            pass
    if api_index is not None and dr.api_log_stats is None:
        try:
            dr.api_log_stats = api_index.stats_for(dr.base_date)
        except Exception:
            pass


def run_analyze(
    folders: Sequence[Path] = (),
    settings: Optional[Settings] = None,
    *,
    inventory: Optional[DataInventory] = None,
    task_root: Optional[Path] = None,
    workers: Optional[int] = None,
    cancel: Optional[CancelToken] = None,
    progress: Optional[ProgressCb] = None,
) -> AnalyzeOutcome:
    """Phân tích từ inventory (ưu tiên) hoặc list folder log + task_root (tương thích)."""
    if settings is None:
        settings = Settings()

    # Chuẩn hóa input → folders / csv paths / api paths
    agv_folders: List[Path] = []
    csv_paths: List[Path] = []
    api_paths: List[Path] = []

    if inventory is not None:
        agv_folders = list(inventory.agv_folders())
        csv_paths = list(inventory.task_csv_paths())
        api_paths = list(inventory.api_log_paths())
    else:
        agv_folders = [Path(f) for f in folders]
        if task_root is not None and Path(task_root).exists():
            # Legacy: index cả root CSV
            pass

    outcome = AnalyzeOutcome()
    n_workers = workers if workers is not None else default_workers()
    n_workers = max(1, n_workers)
    outcome.workers_used = n_workers

    # 1) Index CSV
    task_index: Optional[TaskCsvIndex] = None
    if csv_paths:
        if progress:
            progress(0, max(len(agv_folders), 1), "Đang index Tasks CSV (%d file)..." % len(csv_paths))
        task_index = TaskCsvIndex.from_paths(csv_paths)
        if progress:
            progress(0, max(len(agv_folders), 1),
                     "Tasks CSV: %d ngày" % len(task_index.by_date))
    elif task_root is not None and Path(task_root).exists():
        if progress:
            progress(0, max(len(agv_folders), 1), "Đang index Tasks Log...")
        task_index = TaskCsvIndex.build(Path(task_root))
        if progress:
            progress(0, max(len(agv_folders), 1),
                     "Tasks Log: %d file CSV" % len(task_index.by_date))

    # 2) Index API logs
    api_index: Optional[ApiLogIndex] = None
    if api_paths:
        if progress:
            progress(0, max(len(agv_folders), 1),
                     "Đang index Tasks API logs (%d file)..." % len(api_paths))
        api_index = ApiLogIndex.from_paths(api_paths)
        if progress:
            progress(0, max(len(agv_folders), 1),
                     "API logs: %d ngày" % len(api_index.by_date))

    # Tập ngày cần có kết quả = union A ∪ B ∪ C
    dates_from_agv: Dict[date, Path] = {}
    for folder in agv_folders:
        try:
            from .abnormal import detect_base_date
            d = detect_base_date(Path(folder))
            if d is not None:
                dates_from_agv[d] = Path(folder)
        except Exception:
            continue

    all_dates: Set[date] = set(dates_from_agv.keys())
    if task_index is not None:
        all_dates |= set(task_index.by_date.keys())
    if api_index is not None:
        all_dates |= set(api_index.by_date.keys())

    if not all_dates:
        return outcome

    # 3) Parse song song các folder AGV
    folder_list = list(agv_folders)
    total_folders = len(folder_list)
    by_date: Dict[date, DayResult] = {}
    done_count = 0
    lock = threading.Lock()

    def emit(msg: str) -> None:
        if progress:
            with lock:
                # total = folders + ngày CSV/API-only ước lượng
                progress(done_count, max(total_folders, 1), msg)

    if total_folders > 0:
        n_workers = max(1, min(n_workers, total_folders))
        outcome.workers_used = n_workers

        def work(idx: int, folder: Path):
            def file_cb(name: str) -> None:
                emit("Đang đọc Log AGV %s · %s" % (folder.name, name))

            try:
                dr = _analyze_one_folder(
                    folder, settings, task_index, api_index, cancel, file_cb)
                return idx, dr, None
            except RuntimeError as exc:
                if str(exc) == "cancelled":
                    return idx, None, "cancelled"
                return idx, None, str(exc)
            except Exception as exc:  # noqa: BLE001
                return idx, None, "%s: %s" % (folder.name, exc)

        if progress:
            progress(0, max(total_folders, 1),
                     "Bắt đầu phân tích %d ngày AGV (%d worker)..." % (total_folders, n_workers))

        with ThreadPoolExecutor(max_workers=n_workers) as pool:
            futures = {
                pool.submit(work, i, Path(folder)): i
                for i, folder in enumerate(folder_list)
            }
            for fut in as_completed(futures):
                if cancel is not None and cancel.check():
                    outcome.cancelled = True
                    for f2 in futures:
                        f2.cancel()
                    break
                try:
                    idx, dr, err = fut.result()
                except Exception as exc:  # noqa: BLE001
                    outcome.errors.append(str(exc))
                    with lock:
                        done_count += 1
                    continue

                with lock:
                    done_count += 1
                    cur = done_count

                if err == "cancelled":
                    outcome.cancelled = True
                    emit("Đã hủy — giữ kết quả đã xong")
                    continue
                if err:
                    outcome.errors.append(err)
                    emit("LỖI: %s" % err)
                    continue
                if dr is not None:
                    by_date[dr.base_date] = dr
                    extra = []
                    if dr.task_stats is not None and getattr(dr.task_stats, "has_data", False):
                        extra.append("稼動 %.2f%%" % dr.utilization)
                    if dr.api_log_stats is not None and getattr(dr.api_log_stats, "has_data", False):
                        extra.append("API create %d" % dr.api_create_count)
                    emit("Xong %s (%s) - %d BT%s  [%d/%d]" % (
                        Path(folder_list[idx]).name,
                        dr.base_date.isoformat(),
                        dr.abnormal_count,
                        (" | " + " | ".join(extra)) if extra else "",
                        cur, total_folders,
                    ))

    if cancel is not None and cancel.check():
        outcome.cancelled = True

    # 4) Ngày chỉ có CSV và/hoặc API — tạo DayResult rỗng + gắn stats
    csv_api_only = sorted(all_dates - set(by_date.keys()))
    if csv_api_only and not (cancel and cancel.check()):
        if progress:
            progress(done_count, max(total_folders, 1),
                     "Gắn Tasks CSV / API cho %d ngày không có Log AGV..." % len(csv_api_only))
        for d in csv_api_only:
            if cancel is not None and cancel.check():
                outcome.cancelled = True
                break
            dr = empty_day_result(d, settings)
            _attach_csv_api(dr, settings, task_index, api_index)
            by_date[d] = dr

    # 5) Ngày đã có AGV nhưng chưa gắn CSV/API (đã gắn trong _analyze_one) — OK
    # Đảm bảo ngày AGV cũng có API nếu index có (đã gắn)

    outcome.results = sorted(by_date.values(), key=lambda d: d.base_date)

    if task_index is not None:
        task_index.clear_cache()
    if api_index is not None:
        api_index.clear_cache()
    return outcome
