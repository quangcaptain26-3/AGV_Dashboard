# -*- coding: utf-8 -*-
"""Điểm khởi chạy ứng dụng Phân tích AGV.

Chạy khi phát triển:
    py -3.10 -m agv_app.main
    hoặc: py -3.10 agv_app/main.py

Khuyến nghị Python 3.10 (tương thích 3.8–3.10).
Được dùng làm entry script cho PyInstaller.
"""

import sys
from pathlib import Path

# Đảm bảo gói 'agv_app' import được dù chạy trực tiếp file hay đã đóng gói.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402


def main() -> int:
    # High-DPI phải bật trước khi tạo QApplication
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("AGV Analyzer")

    from agv_app.gui.main_window import MainWindow  # import muộn để bắt lỗi rõ ràng
    win = MainWindow()
    win.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
