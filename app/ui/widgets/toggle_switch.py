"""Custom toggle switch widget — a small pill-shaped slider."""

from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtCore import Qt, Signal, QRectF, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QPainter, QColor


class ToggleSwitch(QWidget):
    toggled = Signal(bool)

    _TRACK_W = 40
    _TRACK_H = 20
    _KNOB_MARGIN = 2
    _KNOB_D = _TRACK_H - 2 * _KNOB_MARGIN  # 16px

    _COLOR_ON = QColor("#4ecca3")
    _COLOR_OFF = QColor("#3a3a5a")
    _KNOB_COLOR = QColor("#e0e0ec")

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self._checked = checked
        self._offset = float(self._on_pos() if checked else self._off_pos())
        self.setFixedSize(self._TRACK_W, self._TRACK_H)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.InOutQuad)

    def _on_pos(self) -> float:
        return float(self._TRACK_W - self._KNOB_MARGIN - self._KNOB_D)

    def _off_pos(self) -> float:
        return float(self._KNOB_MARGIN)

    # -- Animated property --------------------------------------------------
    def _get_offset(self) -> float:
        return self._offset

    def _set_offset(self, val: float):
        self._offset = val
        self.update()

    offset = Property(float, _get_offset, _set_offset)

    # -- Public API ---------------------------------------------------------
    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, on: bool, animate: bool = True):
        if on == self._checked:
            return
        self._checked = on
        target = self._on_pos() if on else self._off_pos()
        if animate:
            self._anim.stop()
            self._anim.setStartValue(self._offset)
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self._offset = target
            self.update()

    # -- Events -------------------------------------------------------------
    def mousePressEvent(self, event):
        self._checked = not self._checked
        target = self._on_pos() if self._checked else self._off_pos()
        self._anim.stop()
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(target)
        self._anim.start()
        self.toggled.emit(self._checked)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # Track
        track_color = self._COLOR_ON if self._checked else self._COLOR_OFF
        p.setPen(Qt.NoPen)
        p.setBrush(track_color)
        p.drawRoundedRect(
            QRectF(0, 0, self._TRACK_W, self._TRACK_H),
            self._TRACK_H / 2, self._TRACK_H / 2,
        )

        # Knob
        p.setBrush(self._KNOB_COLOR)
        p.drawEllipse(QRectF(self._offset, self._KNOB_MARGIN,
                              self._KNOB_D, self._KNOB_D))
        p.end()
