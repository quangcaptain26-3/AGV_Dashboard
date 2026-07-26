# -*- coding: utf-8 -*-
"""Widget biểu đồ nhẹ vẽ bằng QPainter (không thêm thư viện ngoài).

Gồm:
  - KpiCard         : thẻ số liệu lớn (tiêu đề + giá trị + chú thích + màu nhấn).
  - BarChartWidget  : biểu đồ cột ngang + tooltip khi hover.
  - TrendChartWidget: biểu đồ đường theo ngày (xu hướng tỷ lệ bất thường).

Khuyến nghị Python 3.10 (tương thích 3.8–3.10) + PyQt5.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPen
from PyQt5.QtWidgets import QFrame, QLabel, QSizePolicy, QToolTip, QVBoxLayout, QWidget


EMPTY_TEXT = "Chưa có dữ liệu"


def _text_width(fm, text: str) -> int:
    try:
        return fm.horizontalAdvance(text)
    except AttributeError:  # PyQt5 rất cũ
        return fm.width(text)


class KpiCard(QFrame):
    """Thẻ hiển thị một chỉ số quan trọng (số to, dễ nhìn)."""

    def __init__(self, title: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._accent = "#2d7d46"
        self.setObjectName("KpiCard")
        self.setMinimumHeight(96)
        self.setMinimumWidth(160)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(3)

        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet("color:#5a5a5a; font-size:12px; font-weight:bold;")
        self.lbl_title.setWordWrap(True)

        self.lbl_value = QLabel("-")
        vf = QFont()
        vf.setPointSize(20)
        vf.setBold(True)
        self.lbl_value.setFont(vf)

        self.lbl_sub = QLabel("")
        self.lbl_sub.setStyleSheet("color:#808080; font-size:11px;")
        self.lbl_sub.setWordWrap(True)

        v.addWidget(self.lbl_title)
        v.addWidget(self.lbl_value)
        v.addWidget(self.lbl_sub)
        v.addStretch(1)

        self._apply_style()

    def _apply_style(self):
        self.setStyleSheet(
            "QFrame#KpiCard{background:#ffffff;border:1px solid #e3e3e3;"
            "border-top:4px solid %s;border-radius:8px;}" % self._accent
        )
        self.lbl_value.setStyleSheet("color:%s;" % self._accent)

    def set_value(self, value, subtitle: str = "", accent: Optional[str] = None):
        self.lbl_value.setText("" if value is None else str(value))
        self.lbl_sub.setText(subtitle or "")
        if accent:
            self._accent = accent
        self._apply_style()


class BarChartWidget(QWidget):
    """Biểu đồ cột ngang: dữ liệu là danh sách (nhãn, giá trị, màu?, tip?).

    Hover vào hàng → tooltip (modal nhỏ) hiện nhãn + giá trị / tip tùy chỉnh.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._data: List[Tuple[str, float, Optional[QColor]]] = []
        self._tips: List[str] = []
        self._suffix = ""
        self._default_color = QColor("#3a76d8")
        self._hover_idx: int = -1
        self._row_rects: List[QRectF] = []  # vùng hit-test từng hàng
        self.setMinimumHeight(170)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_Hover, True)

    def set_data(self, data, suffix: str = ""):
        """data: (nhãn, giá_trị) | (nhãn, giá_trị, màu) | (nhãn, giá_trị, màu, tip)."""
        norm: List[Tuple[str, float, Optional[QColor]]] = []
        tips: List[str] = []
        for item in data:
            tip = ""
            if len(item) >= 4 and item[3]:
                label, value, color, tip = item[0], item[1], item[2], item[3]
            elif len(item) >= 3:
                label, value, color = item[0], item[1], item[2]
            else:
                label, value, color = item[0], item[1], None
            norm.append((str(label), float(value), color))
            tips.append(str(tip) if tip else "")
        self._data = norm
        self._tips = tips
        self._suffix = suffix
        self._hover_idx = -1
        self._row_rects = []
        self.update()

    def leaveEvent(self, event):  # noqa: N802
        if self._hover_idx >= 0:
            self._hover_idx = -1
            self.update()
        QToolTip.hideText()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        idx = self._hit_test(event.pos().x(), event.pos().y())
        if idx != self._hover_idx:
            self._hover_idx = idx
            self.update()
        if idx >= 0:
            label, value, _color = self._data[idx]
            tip_extra = self._tips[idx] if idx < len(self._tips) else ""
            if tip_extra:
                tip = tip_extra
            else:
                tip = "%s\n%s%s" % (label, self._fmt(value), self._suffix)
            QToolTip.showText(event.globalPos(), tip, self)
            self.setCursor(Qt.PointingHandCursor)
        else:
            QToolTip.hideText()
            self.setCursor(Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    def _hit_test(self, mx: float, my: float) -> int:
        for i, r in enumerate(self._row_rects):
            if r.contains(mx, my):
                return i
        return -1

    def paintEvent(self, event):  # noqa: N802 (Qt API)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect().adjusted(10, 10, -10, -10)

        if not self._data:
            self._row_rects = []
            p.setPen(QColor("#9a9a9a"))
            p.drawText(rect, Qt.AlignCenter, EMPTY_TEXT)
            return

        fm = p.fontMetrics()
        row_h = rect.height() / len(self._data)
        bar_h = max(10.0, min(28.0, row_h - 8))

        max_label_w = max(_text_width(fm, d[0]) for d in self._data)
        max_label_w = min(max_label_w, int(rect.width() * 0.38))
        value_w = 74
        bar_x = rect.left() + max_label_w + 10
        bar_w_full = rect.right() - bar_x - value_w
        if bar_w_full < 20:
            bar_w_full = max(20, int(rect.width() * 0.4))

        max_val = max((d[1] for d in self._data), default=0.0) or 1.0
        text_color = QColor("#333333")
        self._row_rects = []

        for i, (label, value, color) in enumerate(self._data):
            cy = rect.top() + i * row_h + row_h / 2.0
            row_rect = QRectF(rect.left(), cy - row_h / 2.0, rect.width(), row_h)
            self._row_rects.append(row_rect)
            hovered = (i == self._hover_idx)

            if hovered:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(58, 118, 216, 28))
                p.drawRoundedRect(row_rect.adjusted(0, 1, 0, -1), 4, 4)

            # nhãn
            p.setPen(text_color)
            label_rect = QRectF(rect.left(), cy - row_h / 2.0, max_label_w, row_h)
            elided = fm.elidedText(label, Qt.ElideRight, max_label_w)
            p.drawText(label_rect, Qt.AlignVCenter | Qt.AlignLeft, elided)

            # nền cột
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#eef1f6"))
            p.drawRoundedRect(QRectF(bar_x, cy - bar_h / 2.0, bar_w_full, bar_h), 4, 4)

            # cột giá trị
            bw = (value / max_val) * bar_w_full if max_val else 0
            bw = max(2.0, bw)
            base = color if isinstance(color, QColor) else self._default_color
            if hovered:
                # sáng hơn một chút khi hover
                base = QColor(
                    min(255, base.red() + 30),
                    min(255, base.green() + 30),
                    min(255, base.blue() + 30))
            p.setBrush(base)
            p.drawRoundedRect(QRectF(bar_x, cy - bar_h / 2.0, bw, bar_h), 4, 4)

            # giá trị
            p.setPen(text_color)
            val_text = self._fmt(value) + self._suffix
            val_rect = QRectF(bar_x + bar_w_full + 4, cy - row_h / 2.0, value_w - 4, row_h)
            p.drawText(val_rect, Qt.AlignVCenter | Qt.AlignLeft, val_text)

        p.end()

    @staticmethod
    def _fmt(value: float) -> str:
        if abs(value - round(value)) < 1e-9:
            return str(int(round(value)))
        return "%.2f" % value


class TrendChartWidget(QWidget):
    """Biểu đồ đường theo ngày (xu hướng). Dữ liệu: danh sách (nhãn, giá trị).

    thresholds: danh sách (giá trị, màu) để vẽ đường ngưỡng ngang (tốt/cảnh báo).
    Hover vào chấm → tooltip ngày + giá trị; nhãn X xoay chéo và tự thưa theo bề rộng.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._points: List[Tuple[str, float]] = []
        self._tips: List[str] = []  # tooltip đầy đủ khi hover (nếu có)
        self._suffix = ""
        self._thresholds: List[Tuple[float, QColor]] = []
        self._line_color = QColor("#2d7d46")
        self._hover_idx: int = -1
        self._dot_positions: List[Tuple[float, float]] = []  # (x, y) pixel sau lần vẽ
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_Hover, True)

    def set_data(self, points, suffix: str = "", thresholds=None):
        """points: (nhãn_trục, giá_trị) hoặc (nhãn_trục, giá_trị, tooltip)."""
        norm: List[Tuple[str, float]] = []
        tips: List[str] = []
        for item in points:
            if len(item) >= 3 and item[2]:
                label, value, tip = item[0], item[1], item[2]
            else:
                label, value, tip = item[0], item[1], ""
            norm.append((str(label), float(value)))
            tips.append(str(tip) if tip else "")
        self._points = norm
        self._tips = tips
        self._suffix = suffix
        self._thresholds = []
        for t in (thresholds or []):
            self._thresholds.append((float(t[0]), t[1]))
        self._hover_idx = -1
        self._dot_positions = []
        self.update()

    def leaveEvent(self, event):  # noqa: N802
        if self._hover_idx >= 0:
            self._hover_idx = -1
            self.update()
        QToolTip.hideText()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        idx = self._hit_test(event.pos().x(), event.pos().y())
        if idx != self._hover_idx:
            self._hover_idx = idx
            self.update()
        if idx >= 0:
            label, value = self._points[idx]
            tip_extra = self._tips[idx] if idx < len(self._tips) else ""
            if tip_extra:
                tip = "%s\n%s%s" % (tip_extra, self._fmt(value), self._suffix)
            else:
                tip = "%s\n%s%s" % (label, self._fmt(value), self._suffix)
            QToolTip.showText(event.globalPos(), tip, self)
            self.setCursor(Qt.PointingHandCursor)
        else:
            QToolTip.hideText()
            self.setCursor(Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    def _hit_test(self, mx: float, my: float, radius: float = 10.0) -> int:
        """Trả về index điểm gần chuột nhất trong bán kính, hoặc -1."""
        best = -1
        best_d2 = radius * radius
        for i, (x, y) in enumerate(self._dot_positions):
            d2 = (x - mx) ** 2 + (y - my) ** 2
            if d2 <= best_d2:
                best_d2 = d2
                best = i
        return best

    def paintEvent(self, event):  # noqa: N802 (Qt API)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect().adjusted(10, 12, -12, -10)

        if not self._points:
            self._dot_positions = []
            p.setPen(QColor("#9a9a9a"))
            p.drawText(rect, Qt.AlignCenter, EMPTY_TEXT)
            return

        fm = p.fontMetrics()
        left = rect.left() + 42
        # Chừa chỗ cho nhãn X xoay chéo (~45°)
        bottom = rect.bottom() - 48
        top = rect.top() + 8
        right = rect.right()
        plot_w = right - left
        plot_h = bottom - top
        if plot_w <= 10 or plot_h <= 10:
            return

        values = [v for _, v in self._points]
        max_val = max(values + [t[0] for t in self._thresholds] + [1.0])
        max_val *= 1.15

        # trục
        p.setPen(QPen(QColor("#c8c8c8"), 1))
        p.drawLine(int(left), int(top), int(left), int(bottom))
        p.drawLine(int(left), int(bottom), int(right), int(bottom))

        # nhãn trục Y (0 và max)
        p.setPen(QColor("#777777"))
        p.drawText(QRectF(rect.left(), bottom - 8, 38, 16), Qt.AlignRight | Qt.AlignVCenter, "0")
        p.drawText(QRectF(rect.left(), top - 8, 38, 16),
                   Qt.AlignRight | Qt.AlignVCenter, "%.1f" % max_val)

        # đường ngưỡng
        for value, color in self._thresholds:
            y = bottom - (value / max_val) * plot_h
            pen = QPen(color, 1, Qt.DashLine)
            p.setPen(pen)
            p.drawLine(int(left), int(y), int(right), int(y))

        n = len(self._points)
        if n == 1:
            xs = [left + plot_w / 2.0]
        else:
            xs = [left + plot_w * i / (n - 1) for i in range(n)]
        ys = [bottom - (v / max_val) * plot_h for v in values]
        self._dot_positions = list(zip(xs, ys))

        # vùng dưới đường (nhạt)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(45, 125, 70, 30))
        if n >= 2:
            from PyQt5.QtGui import QPolygonF
            from PyQt5.QtCore import QPointF
            poly = QPolygonF()
            poly.append(QPointF(xs[0], bottom))
            for x, y in zip(xs, ys):
                poly.append(QPointF(x, y))
            poly.append(QPointF(xs[-1], bottom))
            p.drawPolygon(poly)

        # đường nối
        p.setPen(QPen(self._line_color, 2))
        for i in range(n - 1):
            p.drawLine(int(xs[i]), int(ys[i]), int(xs[i + 1]), int(ys[i + 1]))

        # Chọn nhãn X: xoay -45°, thưa theo bề rộng (không chồng)
        # Ước lượng bề ngang chiếm chỗ của nhãn xoay ≈ 0.7 * text_width
        sample_lab = self._points[0][0] if self._points else "00-00"
        label_px = max(18, int(_text_width(fm, sample_lab) * 0.72))
        min_gap = label_px + 6
        max_labels = max(2, int(plot_w / min_gap))
        step = max(1, (n - 1) // max(1, max_labels - 1)) if n > 1 else 1
        label_idxs = set(range(0, n, step))
        label_idxs.add(0)
        label_idxs.add(n - 1)

        label_angle = -45
        for i, (label, value) in enumerate(self._points):
            x, y = xs[i], ys[i]
            hovered = (i == self._hover_idx)
            # điểm
            p.setPen(Qt.NoPen)
            if hovered:
                p.setBrush(QColor(255, 255, 255))
                p.drawEllipse(QRectF(x - 7, y - 7, 14, 14))
                p.setBrush(self._line_color)
                p.drawEllipse(QRectF(x - 5, y - 5, 10, 10))
            else:
                p.setBrush(self._line_color)
                p.drawEllipse(QRectF(x - 3.5, y - 3.5, 7, 7))

            if i in label_idxs:
                p.save()
                p.setPen(QColor("#555555"))
                font = p.font()
                font.setPointSize(max(8, font.pointSize() - 1))
                p.setFont(font)
                p.translate(x, bottom + 4)
                p.rotate(label_angle)
                lw = _text_width(p.fontMetrics(), label)
                p.drawText(QRectF(0, 0, lw + 4, p.fontMetrics().height() + 2),
                           Qt.AlignLeft | Qt.AlignTop, label)
                p.restore()

        # Gợi ý nhỏ góc phải
        if n >= 2:
            p.setPen(QColor("#9a9a9a"))
            hint = "Hover chấm để xem ngày"
            hw = _text_width(fm, hint)
            p.drawText(QRectF(right - hw - 2, top - 2, hw + 4, 14),
                       Qt.AlignRight | Qt.AlignVCenter, hint)

        p.end()

    @staticmethod
    def _fmt(value: float) -> str:
        if abs(value - round(value)) < 1e-9:
            return str(int(round(value)))
        return "%.2f" % value
