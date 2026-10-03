import sys
import os
import re
import json
import shutil
import subprocess
import threading
import queue
from datetime import datetime

import cv2

from PySide6.QtCore import (
    Qt, QTimer, QSize, QSizeF, QRect, QRectF, QPoint, QPointF, QEvent, Signal, QUrl,
    QPropertyAnimation, QEasingCurve, Property
)
from PySide6.QtGui import (
    QPixmap, QImage, QAction, QActionGroup, QIcon, QFont, QColor, QPainter, QPainterPath,
    QBrush, QLinearGradient, QPen, QPaintEvent, QMouseEvent
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QSlider, QVBoxLayout,
    QHBoxLayout, QFileDialog, QMessageBox, QMenu, QFrame,
    QGraphicsBlurEffect, QGraphicsDropShadowEffect,
    QProgressBar, QSpinBox, QDialog, QRadioButton, QLineEdit, QButtonGroup,
    QCheckBox, QComboBox, QScrollArea, QListWidget, QListWidgetItem
)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

if sys.platform == "win32":
    import ctypes
    from ctypes import windll, c_int, byref, sizeof

    try:
        ctypes.windll.kernel32.FreeConsole()
    except Exception:
        pass

    def apply_rounded_corners(hwnd):
        try:
            DWMWA_WINDOW_CORNER_PREFERENCE = 33
            windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, byref(c_int(2)), sizeof(c_int)
            )
        except Exception:
            pass

    def enable_acrylic(hwnd, dark=True):
        try:
            ACCENT_ENABLE_BLURBEHIND = 3
            ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
            class ACCENTPOLICY(ctypes.Structure):
                _fields_ = [
                    ("nAccentState", ctypes.c_int),
                    ("nFlags", ctypes.c_int),
                    ("nColor", ctypes.c_uint),
                    ("nAnimationId", ctypes.c_int),
                ]
            class WINCOMPATTRDATA(ctypes.Structure):
                _fields_ = [
                    ("nAttribute", ctypes.c_int),
                    ("pData", ctypes.c_void_p),
                    ("ulDataSize", ctypes.c_size_t),
                ]
            accent = ACCENTPOLICY()
            accent.nAccentState = ACCENT_ENABLE_ACRYLICBLURBEHIND
            accent.nFlags = 0
            # ABGR: alpha << 24 | blue << 16 | green << 8 | red
            if dark:
                accent.nColor = 0xCC0D0D18  # alpha 0xCC ~ 80%
            else:
                accent.nColor = 0xCCF2F2F7
            accent.nAnimationId = 0
            data = WINCOMPATTRDATA()
            data.nAttribute = 19
            data.pData = ctypes.pointer(accent)
            data.ulDataSize = ctypes.sizeof(accent)
            windll.user32.SetWindowCompositionAttribute(hwnd, byref(data))
        except Exception:
            pass
else:
    def apply_rounded_corners(hwnd):
        pass

    def enable_acrylic(hwnd, dark=True):
        pass


# ===================== DUAL PALETTES (Liquid Glass, Qt-compatible RGBA) =====================
PALETTES = {
    "dark": {
        "window_bg":      QColor(8, 8, 15, 255),       # deep black-blue
        "glass_bg":       QColor(26, 26, 46, 165),      # semi-transparent glass
        "glass_solid":    QColor(26, 26, 46, 220),
        "glass_hover":    QColor(42, 42, 68, 200),
        "glass_border":   QColor(255, 255, 255, 35),
        "fg":             QColor(234, 234, 244, 255),
        "fg_dim":         QColor(144, 144, 176, 255),
        "accent":         QColor(10, 132, 255, 255),
        "accent_hover":   QColor(64, 156, 255, 255),
        "accent_glow":    QColor(10, 132, 255, 90),
        "canvas_bg":      QColor(0, 0, 0, 30),
        "border":         QColor(58, 58, 92, 200),
        "thumb_bg":       QColor(20, 20, 35, 200),
        "thumb_selected": QColor(10, 132, 255, 220),
    },
}


CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
ICONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")

_DEFAULTS = {
    "save_folder": os.path.join(os.path.expanduser("~"), "Pictures", "FrameExtractor"),
    "save_format": "png",
    "jpg_quality": 95,
    "png_compression": 3,
    "filename_pattern": "{video}_frame_{frame}",
    "output_scale": 100,
    "open_folder_after_save": False,
    "rename_duplicates": True,
    "skip_frames": 10,
    "playback_speed": 1.0,
    "filmstrip_visible": True,
    "filmstrip_thumbs": 0,
    "recent_limit": 8,
    "batch_every": 30,
    "batch_mode": "frames",
    "recent_files": [],
}
config = {}


def load_config():
    global config
    config = dict(_DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            config.update(data)
        except Exception:
            pass


def save_config():
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


load_config()


# ===================== GLASS WIDGETS =====================
class GlassPanel(QFrame):
    """Panel with REAL backdrop blur (liquid glass): captures the region of the
    parent canvas behind it, blurs it with QGraphicsBlurEffect, and paints the
    blurred snapshot under the translucent glass tint."""
    def __init__(self, parent=None, radius=14, blur_radius=24):
        super().__init__(parent)
        self._radius = radius
        self._bg_color = QColor(26, 26, 46, 165)
        self._blur_radius = blur_radius
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # Backdrop label: holds the blurred snapshot of what's behind the panel.
        # Stacked as the lowest child of the panel itself.
        self._backdrop = QLabel(self)
        self._backdrop.lower()
        self._backdrop.setScaledContents(False)
        self._backdrop.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._backdrop.setStyleSheet("background: transparent; border: none;")
        self._blur_effect = QGraphicsBlurEffect(self._backdrop)
        self._blur_effect.setBlurRadius(blur_radius)
        self._blur_effect.setBlurHints(QGraphicsBlurEffect.QualityHint)
        self._backdrop.setGraphicsEffect(self._blur_effect)
        self._source_canvas = None
        self._backdrop_pixmap = None
        self._update_pending = False

    def set_bg_color(self, color: QColor):
        self._bg_color = color
        self.update()

    def set_source_canvas(self, canvas: QWidget):
        """Register the video canvas whose content will be blurred behind this panel."""
        self._source_canvas = canvas

    def update_backdrop(self):
        """Capture the region of the source canvas behind this panel and refresh the blurred backdrop.
        Cheap when the canvas is empty; scales a cached pixmap."""
        if self._source_canvas is None:
            return
        # Determine the overlap region in canvas coordinates
        gp = self.mapTo(self._source_canvas, QPoint(0, 0))
        overlap = QRect(gp, self.size()).intersected(self._source_canvas.rect())
        if overlap.width() < 2 or overlap.height() < 2:
            self._backdrop.clear()
            return
        # Grab the pixels from the source canvas in that region
        pix = self._source_canvas.grab(overlap)
        if pix.isNull():
            return
        # Scale up slightly so blur edges don't show transparent border
        self._backdrop_pixmap = pix
        self._backdrop.setPixmap(pix)
        self._backdrop.setGeometry(self.rect())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._backdrop.setGeometry(self.rect())
        # ponytail: schedule backdrop refresh via timer to avoid paint recursion
        if self._source_canvas is not None:
            QTimer.singleShot(0, self.update_backdrop)

    def moveEvent(self, e):
        super().moveEvent(e)
        if self._source_canvas is not None:
            QTimer.singleShot(0, self.update_backdrop)

    def paintEvent(self, e: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect().adjusted(0, 0, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(QRectF(r.x(), r.y(), r.width(), r.height()), self._radius, self._radius)
        # Clip to rounded path so backdrop corners are also rounded
        p.setClipPath(path)
        # Backdrop is painted by the child QLabel; we just paint the glass tint on top
        p.fillPath(path, self._bg_color)
        # subtle top highlight (liquid glass refraction)
        grad = QLinearGradient(0, 0, 0, r.height())
        grad.setColorAt(0.0, QColor(255, 255, 255, 25))
        grad.setColorAt(0.15, QColor(255, 255, 255, 8))
        grad.setColorAt(0.5, QColor(255, 255, 255, 0))
        p.fillPath(path, QBrush(grad))
        # 1px inner border (refraction edge)
        p.setClipping(False)
        p.setPen(QPen(QColor(255, 255, 255, 35), 1))
        p.drawPath(path)


class GlassButton(QPushButton):
    """Rounded translucent button with glow on hover for accent variant."""
    def __init__(self, parent=None, text="", icon_name=None, accent=False, radius=10):
        super().__init__(parent)
        self._text = text
        self._accent = accent
        self._radius = radius
        self._bg_color = QColor(26, 26, 46, 165)
        self._hover_color = QColor(42, 42, 68, 200)
        self._fg_color = QColor(234, 234, 244, 255)
        self._accent_color = QColor(10, 132, 255, 255)
        self._accent_hover = QColor(64, 156, 255, 255)
        self._hovered = False
        self._has_icon = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setText(text)

        if icon_name:
            self.load_icon(icon_name)

        # Drop shadow / glow
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(16 if accent else 10)
        self._shadow.setOffset(0, 2)
        self._shadow.setColor(QColor(0, 0, 0, 90 if not accent else 0))
        if accent:
            self._shadow.setColor(QColor(10, 132, 255, 120))
            self._shadow.setBlurRadius(20)
            self._shadow.setOffset(0, 4)
        self.setGraphicsEffect(self._shadow)

        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMinimumHeight(34)

    def sizeHint(self):
        h = 34
        font = QFont("Segoe UI Variable Text", 9)
        if self._accent:
            font.setWeight(QFont.DemiBold)
        from PySide6.QtGui import QFontMetrics
        fm = QFontMetrics(font)
        text_w = fm.horizontalAdvance(self._text) if self._text else 0
        icon_w = self.iconSize().width() if self._has_icon else 0
        if icon_w and text_w:
            w = 12 + icon_w + 8 + text_w + 14
        elif icon_w:
            w = 38
        elif text_w:
            w = 16 + text_w + 16
        else:
            w = 38
        return QSize(w, h)

    def load_icon(self, name):
        path = os.path.join(ICONS_DIR, f"{name}.png")
        if os.path.exists(path):
            pix = QPixmap(path)
            if not pix.isNull():
                self.setIcon(QIcon(pix))
                self.setIconSize(QSize(18, 18))
                self._has_icon = True

    def set_colors(self, bg, hover, fg, accent=None, accent_hover=None):
        self._bg_color = bg
        self._hover_color = hover
        self._fg_color = fg
        if accent is not None:
            self._accent_color = accent
        if accent_hover is not None:
            self._accent_hover = accent_hover
        self.update()

    def enterEvent(self, e):
        self._hovered = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hovered = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect().adjusted(0, 0, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(QRectF(r.x(), r.y(), r.width(), r.height()), self._radius, self._radius)

        if self._accent:
            base = self._accent_hover if self._hovered else self._accent_color
            # glow gradient
            grad = QLinearGradient(0, 0, 0, r.height())
            grad.setColorAt(0.0, QColor(base.red(), base.green(), base.blue(), 255))
            grad.setColorAt(1.0, QColor(max(0, base.red()-30), max(0, base.green()-40), max(0, base.blue()-30), 255))
            p.fillPath(path, QBrush(grad))
            # top sheen
            sheen = QLinearGradient(0, 0, 0, r.height() // 2)
            sheen.setColorAt(0.0, QColor(255, 255, 255, 80))
            sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.fillPath(path, QBrush(sheen))
        else:
            base = self._hover_color if self._hovered else self._bg_color
            p.fillPath(path, base)
            # top sheen
            sheen = QLinearGradient(0, 0, 0, r.height() // 2)
            sheen.setColorAt(0.0, QColor(255, 255, 255, 30 if not self._hovered else 50))
            sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.fillPath(path, QBrush(sheen))

        # border
        p.setPen(QPen(QColor(255, 255, 255, 35 if not self._accent else 80), 1))
        p.drawPath(path)

        # icon + text
        text_color = QColor(255, 255, 255, 255) if self._accent else self._fg_color
        if not self.isEnabled():
            text_color = QColor(self._fg_color.red(), self._fg_color.green(), self._fg_color.blue(), 100)

        icon_rect_w = 0
        if self._has_icon and not self.icon().isNull():
            icon_size = self.iconSize()
            if self._text:
                icon_x = 12
            else:
                icon_x = (r.width() - icon_size.width()) // 2
            icon_y = (r.height() - icon_size.height()) // 2
            pix = self.icon().pixmap(icon_size)
            p.drawPixmap(icon_x, icon_y, pix)
            icon_rect_w = icon_size.width() + 8

        if self._text:
            p.setPen(QPen(text_color))
            font = QFont("Segoe UI Variable Text", 9)
            if self._accent:
                font.setWeight(QFont.DemiBold)
            if not self.isEnabled():
                font.setWeight(QFont.Normal)
            p.setFont(font)
            if self._has_icon:
                text_x = 12 + icon_rect_w
                text_rect = QRect(r.x() + text_x, r.y(), r.width() - text_x - 8, r.height())
                p.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self._text)
            else:
                text_rect = QRect(r.x() + 8, r.y(), r.width() - 16, r.height())
                p.drawText(text_rect, Qt.AlignVCenter | Qt.AlignCenter, self._text)


class ModeSwitch(QWidget):
    """Two-position animated switch for Capturas / Clips mode."""
    modeChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(160, 34)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self._clips = False
        self._thumb_w = 76
        self._thumb_x = 4
        self._bg_color = QColor(26, 26, 46, 220)
        self._hover_color = QColor(42, 42, 68, 230)
        self._fg_color = QColor(234, 234, 244, 255)
        self._dim_color = QColor(144, 144, 176, 255)
        self._accent_color = QColor(10, 132, 255, 255)
        self._hovered = False
        self._animation = QPropertyAnimation(self, b"thumbX", self)
        self._animation.setDuration(180)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)

    def sizeHint(self):
        return QSize(160, 34)

    def thumb_x(self):
        return self._thumb_x

    def set_thumb_x(self, value):
        self._thumb_x = int(value)
        self.update()

    thumbX = Property(int, thumb_x, set_thumb_x)

    def set_colors(self, bg, hover, fg, accent=None, accent_hover=None):
        self._bg_color = bg
        self._hover_color = hover
        self._fg_color = fg
        self._dim_color = QColor(fg.red(), fg.green(), fg.blue(), 150)
        if accent is not None:
            self._accent_color = accent
        self.update()

    def set_mode(self, clips, animate=True, emit=True):
        clips = bool(clips)
        self._clips = clips
        target = self.width() - self._thumb_w - 4 if clips else 4
        if animate:
            self._animation.stop()
            self._animation.setStartValue(self._thumb_x)
            self._animation.setEndValue(target)
            self._animation.start()
        else:
            self.set_thumb_x(target)
        if emit:
            self.modeChanged.emit(clips)

    def is_clips(self):
        return self._clips

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.set_mode(event.position().x() >= self.width() / 2)
        super().mousePressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect().adjusted(0, 0, -1, -1)
        track = QPainterPath()
        track.addRoundedRect(QRectF(r), 17, 17)
        p.fillPath(track, self._hover_color if self._hovered else self._bg_color)
        p.setPen(QPen(QColor(255, 255, 255, 45), 1))
        p.drawPath(track)

        left_rect = QRectF(4, 0, self._thumb_w, self.height())
        right_rect = QRectF(self.width() - self._thumb_w - 4, 0, self._thumb_w, self.height())
        font = QFont("Segoe UI Variable Text", 9)
        font.setWeight(QFont.DemiBold)
        p.setFont(font)
        p.setPen(self._dim_color if self._clips else self._fg_color)
        p.drawText(left_rect, Qt.AlignCenter, "Capturas")
        p.setPen(self._fg_color if self._clips else self._dim_color)
        p.drawText(right_rect, Qt.AlignCenter, "Clips")

        thumb = QPainterPath()
        thumb.addRoundedRect(QRectF(self._thumb_x, 3, self._thumb_w, self.height() - 6), 14, 14)
        p.fillPath(thumb, self._accent_color)
        p.setPen(QPen(QColor(255, 255, 255, 100), 1))
        p.drawPath(thumb)
        p.setPen(self._fg_color)
        p.drawText(left_rect if not self._clips else right_rect, Qt.AlignCenter,
                   "Clips" if self._clips else "Capturas")


class GlassSlider(QWidget):
    """Liquid glass slider: translucent trough, circular thumb with glow."""
    valueChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0
        self._min = 0
        self._max = 100
        self._dragging = False
        self._hovered = False
        self._bg = QColor(26, 26, 46, 165)
        self._border = QColor(255, 255, 255, 35)
        self._accent = QColor(10, 132, 255, 255)
        self._thumb = QColor(255, 255, 255, 255)
        self._glow = QColor(10, 132, 255, 120)
        self.setMouseTracking(True)
        self.setMinimumHeight(28)
        self.setFixedHeight(28)

        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(12)
        self._shadow.setOffset(0, 1)
        self._shadow.setColor(QColor(10, 132, 255, 80))
        self.setGraphicsEffect(self._shadow)

    def set_colors(self, bg, border, accent, glow):
        self._bg = bg
        self._border = border
        self._accent = accent
        self._glow = glow
        self.update()

    def setRange(self, mn, mx):
        self._min = mn
        self._max = mx
        self.update()

    def setValue(self, v):
        self._value = max(self._min, min(self._max, int(v)))
        self.update()

    def value(self):
        return self._value

    def _value_to_x(self, v):
        w = self.width()
        pad = 12
        if self._max == self._min:
            return pad
        return pad + (v - self._min) / (self._max - self._min) * (w - 2 * pad)

    def _x_to_value(self, x):
        w = self.width()
        pad = 12
        if w - 2 * pad <= 0:
            return self._min
        t = (x - pad) / (w - 2 * pad)
        t = max(0.0, min(1.0, t))
        return int(self._min + t * (self._max - self._min))

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w = self.width()
        h = self.height()

        # trough (glass)
        trough_rect = QRectF(8, h/2 - 3, w - 16, 6)
        path = QPainterPath()
        path.addRoundedRect(trough_rect, 3, 3)
        p.fillPath(path, self._bg)

        # filled portion
        x = self._value_to_x(self._value)
        if x > 8:
            fill_rect = QRectF(8, h/2 - 3, x - 8, 6)
            fpath = QPainterPath()
            fpath.addRoundedRect(fill_rect, 3, 3)
            p.fillPath(fpath, self._accent)

        # thumb with glow
        # outer glow
        if self._hovered or self._dragging:
            glow_rect = QRectF(x - 11, h/2 - 11, 22, 22)
            gpath = QPainterPath()
            gpath.addEllipse(glow_rect)
            p.fillPath(gpath, self._glow)
        # thumb itself
        thumb_rect = QRectF(x - 8, h/2 - 8, 16, 16)
        tpath = QPainterPath()
        tpath.addEllipse(thumb_rect)
        # white ring + accent fill
        p.fillPath(tpath, self._thumb)
        inner = QRectF(x - 6, h/2 - 6, 12, 12)
        ipath = QPainterPath()
        ipath.addEllipse(inner)
        p.fillPath(ipath, self._accent)

        # border on trough
        p.setPen(QPen(self._border, 1))
        p.drawPath(path)

    def enterEvent(self, e):
        self._hovered = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hovered = False
        self.update()
        super().leaveEvent(e)

    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.LeftButton:
            self._dragging = True
            self._value = self._x_to_value(e.position().x())
            self.valueChanged.emit(self._value)
            self.update()

    def mouseMoveEvent(self, e: QMouseEvent):
        if self._dragging:
            self._value = self._x_to_value(e.position().x())
            self.valueChanged.emit(self._value)
            self.update()

    def mouseReleaseEvent(self, e: QMouseEvent):
        self._dragging = False


class VideoCanvas(QWidget):
    """Canvas displaying the current video frame: wheel zoom, drag pan and
    aspect-ratio crop overlay for WYSIWYG captures."""
    MIN_ZOOM = 1.0
    MAX_ZOOM = 6.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = None
        self._scaled = None
        self._bg = QColor(0, 0, 0, 0)
        self._fg_dim = QColor(144, 144, 176, 255)
        self._accent = QColor(10, 132, 255, 255)
        self._zoom = 1.0
        self._pan = QPointF(0, 0)
        self._draw_rect = QRectF()
        self._panning = False
        self._pan_start = QPointF()
        self._crop_aspect = None
        self._crop_rect = None
        self._crop_drag = None
        self.setAcceptDrops(True)
        self.setMinimumSize(400, 300)
        self.setMouseTracking(True)

    def set_bg(self, color):
        self._bg = color
        self.update()

    def set_fg_dim(self, color):
        self._fg_dim = color
        self.update()

    def set_accent(self, color):
        self._accent = color
        self.update()

    def set_pixmap(self, pix: QPixmap):
        self._pixmap = pix
        self._scaled = None
        self.update()

    def clear_pixmap(self):
        self._pixmap = None
        self._scaled = None
        self.update()

    # ---------- ZOOM / VIEW ----------
    @property
    def zoom_level(self):
        return self._zoom

    def reset_view(self):
        self._zoom = 1.0
        self._pan = QPointF(0, 0)
        self._crop_aspect = None
        self._crop_rect = None
        self._scaled = None
        self.unsetCursor()
        self.update()

    def _fit_size(self):
        if self._pixmap is None or self._pixmap.isNull():
            return QSizeF(0, 0)
        return QSizeF(self._pixmap.size().scaled(self.size(), Qt.KeepAspectRatio))

    def _clamp_pan(self):
        base = self._fit_size()
        dw = base.width() * self._zoom
        dh = base.height() * self._zoom
        max_x = max(0.0, (dw - self.width()) / 2)
        max_y = max(0.0, (dh - self.height()) / 2)
        self._pan.setX(max(-max_x, min(max_x, self._pan.x())))
        self._pan.setY(max(-max_y, min(max_y, self._pan.y())))

    def wheelEvent(self, e):
        if self._pixmap is None or self._pixmap.isNull():
            return
        delta = e.angleDelta().y()
        if delta == 0:
            return
        factor = 1.25 if delta > 0 else 0.8
        new_zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, self._zoom * factor))
        if abs(new_zoom - self._zoom) < 1e-6:
            return
        base = self._fit_size()
        m = e.position()
        old_dw = base.width() * self._zoom
        old_dh = base.height() * self._zoom
        old_rx = (self.width() - old_dw) / 2 + self._pan.x()
        old_ry = (self.height() - old_dh) / 2 + self._pan.y()
        frac_x = (m.x() - old_rx) / old_dw if old_dw > 0 else 0.5
        frac_y = (m.y() - old_ry) / old_dh if old_dh > 0 else 0.5
        self._zoom = new_zoom
        if self._zoom <= self.MIN_ZOOM:
            self._pan = QPointF(0, 0)
        else:
            new_dw = base.width() * self._zoom
            new_dh = base.height() * self._zoom
            new_rx = m.x() - frac_x * new_dw
            new_ry = m.y() - frac_y * new_dh
            self._pan = QPointF(new_rx - (self.width() - new_dw) / 2,
                                new_ry - (self.height() - new_dh) / 2)
            self._clamp_pan()
        self._scaled = None
        self.update()

    def visible_frame_rect(self):
        """Visible region of the frame in frame pixels (for zoomed captures)."""
        if self._pixmap is None or self._pixmap.isNull() or self._draw_rect.isEmpty():
            return None
        pw, ph = self._pixmap.width(), self._pixmap.height()
        vis = self._draw_rect.intersected(QRectF(self.rect()))
        if vis.isEmpty():
            return None
        x = max(0, int((vis.x() - self._draw_rect.x()) / self._draw_rect.width() * pw))
        y = max(0, int((vis.y() - self._draw_rect.y()) / self._draw_rect.height() * ph))
        w = min(pw - x, int(vis.width() / self._draw_rect.width() * pw + 0.5))
        h = min(ph - y, int(vis.height() / self._draw_rect.height() * ph + 0.5))
        if w < 2 or h < 2:
            return None
        return (x, y, w, h)

    # ---------- CROP ----------
    def set_crop_aspect(self, aspect):
        """aspect: w/h float, or None to disable crop mode."""
        self._crop_aspect = aspect
        if aspect is None or self._pixmap is None or self._pixmap.isNull():
            self._crop_rect = None
        else:
            pw, ph = self._pixmap.width(), self._pixmap.height()
            if pw / ph >= aspect:
                ch = ph
                cw = ch * aspect
            else:
                cw = pw
                ch = cw / aspect
            self._crop_rect = QRectF((pw - cw) / 2, (ph - ch) / 2, cw, ch)
        self.update()

    def crop_frame_rect(self):
        if self._crop_rect is None or self._pixmap is None or self._pixmap.isNull():
            return None
        pw, ph = self._pixmap.width(), self._pixmap.height()
        r = self._crop_rect.intersected(QRectF(0, 0, pw, ph))
        x, y, w, h = int(r.x()), int(r.y()), int(r.width()), int(r.height())
        if w < 2 or h < 2:
            return None
        return (x, y, w, h)

    def _frame_to_widget(self, fx, fy):
        if self._pixmap is None or self._draw_rect.isEmpty():
            return QPointF()
        pw, ph = self._pixmap.width(), self._pixmap.height()
        return QPointF(self._draw_rect.x() + fx / pw * self._draw_rect.width(),
                       self._draw_rect.y() + fy / ph * self._draw_rect.height())

    def _widget_to_frame(self, pos):
        if self._pixmap is None or self._draw_rect.isEmpty():
            return QPointF()
        pw, ph = self._pixmap.width(), self._pixmap.height()
        return QPointF((pos.x() - self._draw_rect.x()) / self._draw_rect.width() * pw,
                       (pos.y() - self._draw_rect.y()) / self._draw_rect.height() * ph)

    def _crop_hit(self, pos):
        """('move', None) | ('resize', corner 0=TL 1=TR 2=BR 3=BL) | None"""
        if self._crop_rect is None:
            return None
        r = self._crop_rect
        for i, cf in enumerate((r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft())):
            wpt = self._frame_to_widget(cf.x(), cf.y())
            if abs(pos.x() - wpt.x()) <= 8 and abs(pos.y() - wpt.y()) <= 8:
                return ("resize", i)
        tl = self._frame_to_widget(r.x(), r.y())
        br = self._frame_to_widget(r.x() + r.width(), r.y() + r.height())
        if tl.x() <= pos.x() <= br.x() and tl.y() <= pos.y() <= br.y():
            return ("move", None)
        return None

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton or self._pixmap is None:
            return
        pos = e.position()
        if self._crop_rect is not None:
            hit = self._crop_hit(pos)
            if hit is not None:
                kind, corner = hit
                self._crop_drag = (kind, corner, self._widget_to_frame(pos), QRectF(self._crop_rect))
                return
        if self._zoom > 1.0:
            self._panning = True
            self._pan_start = pos
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self._crop_drag is not None:
            kind, corner, start_fp, orig = self._crop_drag
            fp = self._widget_to_frame(pos)
            pw, ph = self._pixmap.width(), self._pixmap.height()
            if kind == "move":
                nx = max(0.0, min(pw - orig.width(), orig.x() + (fp.x() - start_fp.x())))
                ny = max(0.0, min(ph - orig.height(), orig.y() + (fp.y() - start_fp.y())))
                self._crop_rect = QRectF(nx, ny, orig.width(), orig.height())
            else:
                aspect = self._crop_aspect
                oc = (orig.bottomRight(), orig.bottomLeft(), orig.topLeft(), orig.topRight())[corner]
                dw = abs(fp.x() - oc.x())
                dh = abs(fp.y() - oc.y())
                w = max(32.0, max(dw, dh * aspect))
                max_w = (pw - oc.x()) if fp.x() >= oc.x() else oc.x()
                max_h = (ph - oc.y()) if fp.y() >= oc.y() else oc.y()
                w = max(32.0, min(w, max_w, max_h * aspect))
                h = w / aspect
                x = oc.x() if fp.x() >= oc.x() else oc.x() - w
                y = oc.y() if fp.y() >= oc.y() else oc.y() - h
                self._crop_rect = QRectF(x, y, w, h)
            self.update()
            return
        if self._panning:
            self._pan += pos - self._pan_start
            self._pan_start = pos
            self._clamp_pan()
            self.update()
            return
        if self._crop_rect is not None:
            hit = self._crop_hit(pos)
            if hit and hit[0] == "resize":
                self.setCursor(Qt.SizeFDiagCursor if hit[1] in (0, 2) else Qt.SizeBDiagCursor)
            elif hit:
                self.setCursor(Qt.SizeAllCursor)
            else:
                self.unsetCursor()
        elif self._zoom > 1.0:
            self.setCursor(Qt.OpenHandCursor)
        else:
            self.unsetCursor()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._crop_drag = None
            if self._panning:
                self._panning = False
                self.unsetCursor()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton and self._zoom > 1.0:
            self._zoom = 1.0
            self._pan = QPointF(0, 0)
            self._scaled = None
            self.unsetCursor()
            self.update()

    # ---------- PAINT ----------
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        r = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(r, 12, 12)
        p.setClipPath(path)
        p.fillRect(self.rect(), self._bg)
        if self._pixmap and not self._pixmap.isNull():
            base = self._fit_size()
            dw = base.width() * self._zoom
            dh = base.height() * self._zoom
            key = (int(dw), int(dh))
            if self._scaled is None or self._scaled[1] != key:
                self._scaled = (
                    self._pixmap.scaled(QSize(max(1, int(dw)), max(1, int(dh))),
                                        Qt.IgnoreAspectRatio, Qt.SmoothTransformation),
                    key,
                )
            scaled = self._scaled[0]
            x = (self.width() - dw) / 2 + self._pan.x()
            y = (self.height() - dh) / 2 + self._pan.y()
            self._draw_rect = QRectF(x, y, dw, dh)
            p.drawPixmap(int(x), int(y), scaled)
            if self._crop_rect is not None:
                self._paint_crop_overlay(p)
            if self._zoom > 1.0:
                self._paint_zoom_badge(p)
        else:
            self._draw_rect = QRectF()
            p.setPen(QPen(self._fg_dim))
            f1 = QFont("Segoe UI Variable Display", 18, QFont.Bold)
            p.setFont(f1)
            p.drawText(self.rect(), Qt.AlignCenter, "Arrastra un video aqui\no haz clic en Abrir Video")
        p.end()

    def _paint_crop_overlay(self, p):
        cr = self._crop_rect
        tl = self._frame_to_widget(cr.x(), cr.y())
        br = self._frame_to_widget(cr.x() + cr.width(), cr.y() + cr.height())
        wrect = QRectF(tl, br)
        outer = QPainterPath()
        outer.addRect(QRectF(self.rect()))
        inner = QPainterPath()
        inner.addRect(wrect)
        p.fillPath(outer.subtracted(inner), QColor(0, 0, 0, 150))
        p.setPen(QPen(self._accent, 2))
        p.setBrush(Qt.NoBrush)
        p.drawRect(wrect)
        p.setPen(QPen(QColor(255, 255, 255, 230), 1))
        p.setBrush(QBrush(QColor(255, 255, 255, 230)))
        for cf in (wrect.topLeft(), wrect.topRight(), wrect.bottomRight(), wrect.bottomLeft()):
            p.drawRect(QRectF(cf.x() - 4, cf.y() - 4, 8, 8))

    def _paint_zoom_badge(self, p):
        text = f"{int(self._zoom * 100)}%"
        p.setFont(QFont("Segoe UI Variable Text", 8))
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(text) + 16
        th = fm.height() + 8
        bx = self.width() - tw - 10
        by = self.height() - th - 10
        path = QPainterPath()
        path.addRoundedRect(QRectF(bx, by, tw, th), 8, 8)
        p.fillPath(path, QColor(0, 0, 0, 140))
        p.setPen(QPen(QColor(255, 255, 255, 220)))
        p.drawText(QRectF(bx, by, tw, th), Qt.AlignCenter, text)

    # DnD
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path:
                self.window().open_video(path)


class FilmstripThumb(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected = False
        self._bg = QColor(20, 20, 35, 200)
        self._sel_bg = QColor(10, 132, 255, 220)
        self.setFixedSize(86, 52)
        self.setAlignment(Qt.AlignCenter)
        self.setScaledContents(False)
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(8)
        self._shadow.setOffset(0, 1)
        self._shadow.setColor(QColor(0, 0, 0, 100))
        self.setGraphicsEffect(self._shadow)

    def set_colors(self, bg, sel):
        self._bg = bg
        self._sel_bg = sel
        self.update()

    def set_selected(self, sel):
        self._selected = sel
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect().adjusted(0, 0, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(QRectF(r.x(), r.y(), r.width(), r.height()), 6, 6)
        if self._selected:
            p.fillPath(path, self._sel_bg)
            p.setPen(QPen(QColor(255, 255, 255, 120), 2))
        else:
            p.fillPath(path, self._bg)
            p.setPen(QPen(QColor(255, 255, 255, 35), 1))
        p.drawPath(path)
        super().paintEvent(e)


# ===================== VIDEO STATE (logic intact) =====================
cap = None
current_frame = None
current_frame_num = 0
total_frames = 0
bookmarks = []
video_fps = 0.0
video_w = 0
video_h = 0
is_playing = False
video_path = None
frame_cache = {}
cache_lock = threading.Lock()
cache_radius = 5

preload_queue = queue.Queue(maxsize=1)
preloader_stop_event = threading.Event()


def preloader_worker():
    local_cap = None
    local_video_path = None
    while not preloader_stop_event.is_set():
        try:
            center = preload_queue.get(timeout=0.5)
        except queue.Empty:
            continue
        if center is None:
            continue
        if video_path != local_video_path:
            if local_cap is not None:
                local_cap.release()
            local_cap = cv2.VideoCapture(video_path) if video_path else None
            local_video_path = video_path
        if local_cap is None or not local_cap.isOpened():
            continue
        start = max(0, center - cache_radius)
        end = min(total_frames - 1, center + cache_radius)
        local_cap.set(cv2.CAP_PROP_POS_FRAMES, start)
        for fn in range(start, end + 1):
            if preloader_stop_event.is_set() or video_path != local_video_path:
                break
            with cache_lock:
                have = fn in frame_cache
            ret, frame = local_cap.read()
            if not ret:
                break
            if not have:
                with cache_lock:
                    frame_cache[fn] = frame
        lower = max(0, center - cache_radius * 2)
        upper = min(total_frames - 1, center + cache_radius * 2)
        with cache_lock:
            for key in list(frame_cache.keys()):
                if key < lower or key > upper:
                    del frame_cache[key]
    if local_cap is not None:
        local_cap.release()


def cv2_to_qpixmap(frame):
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w = frame_rgb.shape[:2]
    img = QImage(frame_rgb.data, w, h, w * 3, QImage.Format_RGB888).copy()
    return QPixmap.fromImage(img)


def imwrite_params(fmt):
    if fmt == "jpg":
        return [cv2.IMWRITE_JPEG_QUALITY, int(config.get("jpg_quality", 95))]
    return [cv2.IMWRITE_PNG_COMPRESSION, int(config.get("png_compression", 3))]


def process_frame_for_export(frame, crop=None, scale_pct=100):
    if crop is not None:
        x, y, w, h = crop
        frame = frame[y:y + h, x:x + w]
    if scale_pct != 100:
        fh, fw = frame.shape[:2]
        new_w = max(1, int(fw * scale_pct / 100))
        new_h = max(1, int(fh * scale_pct / 100))
        frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
    return frame


def build_output_path(folder, pattern, video_stem, frame_num, ext, rename_dupes):
    name = (pattern or "{video}_frame_{frame}")
    name = name.replace("{video}", video_stem)
    name = name.replace("{frame}", f"{frame_num:05d}")
    name = name.replace("{fecha}", datetime.now().strftime("%Y%m%d_%H%M%S"))
    name = re.sub(r'[<>:"/\\|?*]', "_", name).strip() or f"frame_{frame_num:05d}"
    full_path = os.path.join(folder, f"{name}.{ext}")
    if rename_dupes:
        i = 1
        while os.path.exists(full_path):
            full_path = os.path.join(folder, f"{name}_{i}.{ext}")
            i += 1
    return full_path


def build_clip_output_path(folder, video_stem, start_frame, end_frame, rename_dupes):
    """Create a stable output name for an individual video clip."""
    name = f"{video_stem}_clip_{start_frame:05d}_{end_frame:05d}"
    full_path = os.path.join(folder, f"{name}.mp4")
    if rename_dupes:
        i = 1
        while os.path.exists(full_path):
            full_path = os.path.join(folder, f"{name}_{i}.mp4")
            i += 1
    return full_path


def ffmpeg_time(seconds):
    return f"{max(0.0, float(seconds)):.6f}"


# ===================== MAIN WINDOW =====================
class MainWindow(QMainWindow):
    _thumb_ready = Signal(QImage, int, str)
    _batch_progress = Signal(int, int, int)
    _batch_done = Signal(int)
    _clip_export_done = Signal(bool, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Frame Extractor")
        self.resize(980, 700)
        self.setMinimumSize(820, 580)
        self._palette = PALETTES["dark"]

        # Central widget (transparent for acrylic backdrop)
        central = QWidget(self)
        central.setObjectName("central")
        self.setCentralWidget(central)
        self.central_widget = central

        # Acrylic / rounded corners on Windows
        if sys.platform == "win32":
            self.setStyleSheet(f"QMainWindow {{ background: transparent; }}")
            QTimer.singleShot(50, self._apply_win_effects)

        # Icon
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # Build UI
        self._build_ui()
        self._apply_palette()

        # Worker-thread signals
        self._thumb_ready.connect(self._add_filmstrip_thumb)
        self._batch_progress.connect(self._on_batch_progress)
        self._batch_done.connect(self._on_batch_done)
        self._clip_export_done.connect(self._on_clip_export_done)
        self._batch_widgets = None
        self._clip_export_dialog = None
        self._clip_export_in_progress = False
        self._capture_mode = True
        self.clips = []
        self._pending_clip_start = None

        # Qt handles the audio stream while OpenCV keeps the frame-accurate canvas.
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(1.0)
        self.media_player = QMediaPlayer(self)
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.errorOccurred.connect(self._on_media_error)

        # Timer for playback
        self._play_timer = QTimer(self)
        self._play_timer.timeout.connect(self._play_tick)
        self._play_delay_timer = QTimer(self)
        self._play_delay_timer.setSingleShot(True)
        self._play_delay_timer.timeout.connect(self._do_deferred_seek)

        # Initial state
        threading.Thread(target=preloader_worker, daemon=True).start()
        self.filmstrip.setVisible(bool(config.get("filmstrip_visible", True)))
        self._layout_panels()
        QTimer.singleShot(100, self._draw_empty_state)

    def _apply_win_effects(self):
        try:
            hwnd = int(self.winId())
            apply_rounded_corners(hwnd)
            enable_acrylic(hwnd, dark=True)
        except Exception:
            pass

    # ---------- UI BUILD ----------
    def _build_ui(self):
        # Root layout: canvas fills, panels float via absolute positioning
        central = self.central_widget
        central.setStyleSheet("background: transparent;")

        # Video canvas (fills remaining window space)
        self.canvas = VideoCanvas(central)
        self.canvas.setGeometry(0, 0, self.width(), self.height())

        # Re-position panels on resize
        central.installEventFilter(self)

        # ---- TOP BAR (floating glass panel) ----
        self.top_bar = GlassPanel(central, radius=12)
        self.top_bar.setFixedHeight(78)

        self.open_btn = GlassButton(self.top_bar, text="Abrir Video", icon_name="open", accent=True)
        self.open_btn.setToolTip("Abrir video (Ctrl+O)")
        self.open_btn.clicked.connect(self.open_video)

        self.mode_btn = ModeSwitch(self.top_bar)
        self.mode_btn.setToolTip("Cambiar entre modo Capturas y modo Clips")
        self.mode_btn.modeChanged.connect(self.set_mode)

        self.crop_btn = GlassButton(self.top_bar, text="Recorte", icon_name="crop")
        self.crop_btn.setToolTip("Relación de aspecto y recorte")
        self.crop_btn.clicked.connect(self._show_crop_menu)
        self.crop_btn.setEnabled(False)

        self.batch_btn = GlassButton(self.top_bar, icon_name="batch")
        self.batch_btn.setToolTip("Extracción por lotes")
        self.batch_btn.clicked.connect(self.open_batch_dialog)
        self.batch_btn.setEnabled(False)

        self.settings_btn = GlassButton(self.top_bar, icon_name="settings")
        self.settings_btn.setToolTip("Configuración general")
        self.settings_btn.clicked.connect(self.open_settings)

        self.recent_btn = GlassButton(self.top_bar, icon_name="recent")
        self.recent_btn.setToolTip("Archivos recientes")
        self.recent_btn.clicked.connect(self._show_recent_menu)

        # Info labels (right side)
        self.file_label = QLabel("Archivo: —")
        self.file_label.setMaximumWidth(240)
        self.res_label = QLabel("Res.: —")
        self.fps_label = QLabel("FPS: —")
        self.frame_label = QLabel("Frame: —")
        self.time_label = QLabel("00:00:00 / 00:00:00")
        for lbl in (self.file_label, self.res_label, self.fps_label,
                    self.frame_label, self.time_label):
            lbl.setStyleSheet("background: transparent;")
            lbl.setFont(QFont("Segoe UI Variable Text", 9))

        # Layout top bar contents
        top_layout = QHBoxLayout(self.top_bar)
        top_layout.setContentsMargins(8, 4, 8, 4)
        top_layout.setSpacing(6)
        top_layout.addWidget(self.open_btn)
        top_layout.addWidget(self.crop_btn)
        top_layout.addWidget(self.batch_btn)
        top_layout.addWidget(self.settings_btn)
        top_layout.addWidget(self.recent_btn)
        top_layout.addStretch()
        top_layout.addWidget(self.file_label)
        top_layout.addWidget(self.res_label)
        top_layout.addWidget(self.fps_label)
        top_layout.addWidget(self.frame_label)
        top_layout.addWidget(self.time_label)

        # ---- SLIDER (floating) ----
        self.slider = GlassSlider(central)
        self.slider.valueChanged.connect(self.on_slider_change)

        # ---- BOOKMARKS bar (floating) ----
        self.bookmarks_bar = QWidget(central)
        self.bookmarks_bar.setFixedHeight(8)
        self.bookmarks_bar.setStyleSheet("background: transparent;")
        self.bookmarks_bar.paintEvent = self._paint_bookmarks_bar

        # ---- FILMSTRIP (floating) ----
        self.filmstrip = QWidget(central)
        self.filmstrip.setFixedHeight(55)
        self.filmstrip.setStyleSheet("background: transparent;")
        self.filmstrip_layout = QHBoxLayout(self.filmstrip)
        self.filmstrip_layout.setContentsMargins(8, 2, 8, 2)
        self.filmstrip_layout.setSpacing(3)
        self.filmstrip_layout.addStretch()
        self.filmstrip_thumbs = []
        self.filmstrip_frames = []

        # ---- BOTTOM BAR (floating glass panel) ----
        self.bottom_bar = GlassPanel(central, radius=12)
        self.bottom_bar.setFixedHeight(50)

        self.btn_first = GlassButton(self.bottom_bar, icon_name="first")
        self.btn_first.setToolTip("Primer frame (Home)")
        self.btn_first.clicked.connect(self.go_first)

        self.btn_prev = GlassButton(self.bottom_bar, icon_name="prev")
        self.btn_prev.setToolTip("Frame anterior (←)")
        self.btn_prev.clicked.connect(self.prev_frame)

        self.btn_play = GlassButton(self.bottom_bar, icon_name="play")
        self.btn_play.setToolTip("Reproducir / Pausar (Espacio)")
        self.btn_play.clicked.connect(self.play_pause)

        self.btn_next = GlassButton(self.bottom_bar, icon_name="next")
        self.btn_next.setToolTip("Frame siguiente (→)")
        self.btn_next.clicked.connect(self.next_frame)

        self.btn_last = GlassButton(self.bottom_bar, icon_name="last")
        self.btn_last.setToolTip("Último frame (End)")
        self.btn_last.clicked.connect(self.go_last)

        for b in (self.btn_first, self.btn_prev, self.btn_play,
                  self.btn_next, self.btn_last):
            b.setFixedWidth(38)
            b.setEnabled(False)

        self.bookmark_btn = GlassButton(self.bottom_bar, text=" 0", icon_name="bookmark")
        self.bookmark_btn.setToolTip("Añadir / quitar marcador (M)")
        self.bookmark_btn.clicked.connect(self.toggle_bookmark)
        self.bookmark_btn.setEnabled(False)

        self.export_bookmarks_btn = GlassButton(self.bottom_bar, icon_name="export")
        self.export_bookmarks_btn.setToolTip("Exportar todos los marcadores")
        self.export_bookmarks_btn.setFixedWidth(38)
        self.export_bookmarks_btn.clicked.connect(self.export_bookmarks)
        self.export_bookmarks_btn.setEnabled(False)

        self.open_folder_btn = GlassButton(self.bottom_bar, text="Abrir Carpeta", icon_name="folder")
        self.open_folder_btn.setToolTip("Abrir carpeta de capturas (Ctrl+E)")
        self.open_folder_btn.clicked.connect(self.open_save_folder)
        self.open_folder_btn.setEnabled(False)

        self.save_btn = GlassButton(self.bottom_bar, text="Guardar Frame", icon_name="save_btn", accent=True)
        self.save_btn.setToolTip("Guardar frame actual (Ctrl+S)")
        self.save_btn.clicked.connect(self.save_frame)
        self.save_btn.setEnabled(False)

        self.clip_start_btn = GlassButton(self.bottom_bar, text="Marcar inicio")
        self.clip_start_btn.setToolTip("Marcar el inicio de un clip en el frame actual (I)")
        self.clip_start_btn.clicked.connect(self.mark_clip_start)
        self.clip_start_btn.setEnabled(False)
        self.clip_start_btn.setVisible(False)

        self.clip_end_btn = GlassButton(self.bottom_bar, text="Marcar fin")
        self.clip_end_btn.setToolTip("Marcar el fin del clip en el frame actual (O)")
        self.clip_end_btn.clicked.connect(self.mark_clip_end)
        self.clip_end_btn.setEnabled(False)
        self.clip_end_btn.setVisible(False)

        self.clips_btn = GlassButton(self.bottom_bar, text="Clips (0)", accent=True)
        self.clips_btn.setToolTip("Ver, editar y exportar los clips marcados")
        self.clips_btn.clicked.connect(self.open_clips_dialog)
        self.clips_btn.setEnabled(False)
        self.clips_btn.setVisible(False)

        bbl = QHBoxLayout(self.bottom_bar)
        bbl.setContentsMargins(8, 4, 8, 4)
        bbl.setSpacing(6)
        bbl.addWidget(self.btn_first)
        bbl.addWidget(self.btn_prev)
        bbl.addWidget(self.btn_play)
        bbl.addWidget(self.btn_next)
        bbl.addWidget(self.btn_last)
        bbl.addWidget(self.clip_start_btn)
        bbl.addWidget(self.clip_end_btn)
        bbl.addStretch()
        bbl.addWidget(self.bookmark_btn)
        bbl.addWidget(self.export_bookmarks_btn)
        bbl.addWidget(self.clips_btn)
        bbl.addWidget(self.open_folder_btn)
        bbl.addWidget(self.save_btn)

        # ---- STATUS BAR (floating bottom strip) ----
        self.status_bar = GlassPanel(central, radius=8)
        self.status_bar.setFixedHeight(24)
        self.status_label = QLabel("Listo", self.status_bar)
        self.status_label.setStyleSheet("background: transparent;")
        self.status_label.setFont(QFont("Segoe UI Variable Text", 9))
        sl = QHBoxLayout(self.status_bar)
        sl.setContentsMargins(10, 2, 10, 2)
        sl.addWidget(self.status_label)
        sl.addStretch()

        # Position panels initially
        self._layout_panels()
        self.mode_btn.raise_()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._layout_panels()

    def eventFilter(self, obj, e):
        if obj is self.central_widget and e.type() == QEvent.Resize:
            self._layout_panels()
        return super().eventFilter(obj, e)

    def _layout_panels(self):
        w = self.central_widget.width()
        h = self.central_widget.height()
        if w < 100 or h < 100:
            return

        m = 10         # outer margin
        vid_m = 10     # video side margin
        g = 8          # gap between sections

        # Top bar
        top_h = 78
        top_y = m
        self.top_bar.setGeometry(m, top_y, w - 2 * m, top_h)
        mode_w = self.mode_btn.width()
        self.mode_btn.setGeometry((self.top_bar.width() - mode_w) // 2, 40, mode_w, 34)
        self.mode_btn.raise_()

        # Bottom section heights
        sb_h = 24
        bb_h = 50
        fs_h = 55 if self.filmstrip.isVisible() else 0
        bm_h = 8
        sl_h = 26

        # Position upwards from bottom of window
        sb_y = h - m - sb_h
        self.status_bar.setGeometry(m, sb_y, w - 2 * m, sb_h)

        bb_y = sb_y - 6 - bb_h
        self.bottom_bar.setGeometry(m, bb_y, w - 2 * m, bb_h)

        if self.filmstrip.isVisible():
            fs_y = bb_y - 6 - fs_h
            self.filmstrip.setGeometry(m, fs_y, w - 2 * m, fs_h)
            last_bottom_y = fs_y
        else:
            self.filmstrip.setGeometry(m, bb_y, w - 2 * m, 0)
            last_bottom_y = bb_y

        bm_y = last_bottom_y - 4 - bm_h
        self.bookmarks_bar.setGeometry(m + 6, bm_y, w - 2 * m - 12, bm_h)

        sl_y = bm_y - 2 - sl_h
        self.slider.setGeometry(m + 6, sl_y, w - 2 * m - 12, sl_h)

        # Video canvas fills exact remaining area
        vid_y = top_y + top_h + g
        vid_h = max(1, sl_y - g - vid_y)
        self.canvas.setGeometry(vid_m, vid_y, w - 2 * vid_m, vid_h)

    # ---------- THEME ----------
    def _apply_palette(self):
        p = self._palette
        self.canvas.set_bg(p["canvas_bg"])
        self.canvas.set_fg_dim(p["fg_dim"])
        self.top_bar.set_bg_color(p["glass_bg"])
        self.bottom_bar.set_bg_color(p["glass_bg"])
        self.status_bar.set_bg_color(p["glass_bg"])
        # Buttons
        for btn in (self.mode_btn, self.settings_btn, self.recent_btn, self.batch_btn, self.crop_btn,
                    self.btn_first, self.btn_prev, self.btn_play, self.btn_next, self.btn_last,
                    self.bookmark_btn, self.export_bookmarks_btn, self.open_folder_btn,
                    self.clip_start_btn, self.clip_end_btn):
            btn.set_colors(p["glass_bg"], p["glass_hover"], p["fg"])
        self.clips_btn.set_colors(p["glass_bg"], p["glass_hover"], p["fg"], p["accent"], p["accent_hover"])
        self.open_btn.set_colors(p["glass_bg"], p["glass_hover"], p["fg"], p["accent"], p["accent_hover"])
        self.save_btn.set_colors(p["glass_bg"], p["glass_hover"], p["fg"], p["accent"], p["accent_hover"])
        # Labels
        for lbl in (self.res_label, self.fps_label, self.time_label):
            lbl.setStyleSheet(f"color: rgb({p['fg'].red()},{p['fg'].green()},{p['fg'].blue()}); background: transparent;")
        self.frame_label.setStyleSheet(f"color: rgb({p['fg'].red()},{p['fg'].green()},{p['fg'].blue()}); background: transparent;")
        self.file_label.setStyleSheet(f"color: rgb({p['accent'].red()},{p['accent'].green()},{p['accent'].blue()}); background: transparent;")
        self.status_label.setStyleSheet(f"color: rgb({p['fg'].red()},{p['fg'].green()},{p['fg'].blue()}); background: transparent;")
        # Slider
        self.slider.set_colors(p["glass_bg"], p["glass_border"], p["accent"], p["accent_glow"])
        # Filmstrip thumbs
        for t in self.filmstrip_thumbs:
            t.set_colors(p["thumb_bg"], p["thumb_selected"])
        # Re-apply acrylic
        if sys.platform == "win32":
            QTimer.singleShot(30, self._apply_win_effects)
        self._draw_empty_state()
        self._draw_bookmarks()
        self._update_filmstrip_highlight()

    # ---------- RECENT MENU ----------
    def _show_recent_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(self._menu_stylesheet())
        recent = config.get("recent_files", [])
        if recent:
            for p in recent:
                act = QAction(os.path.basename(p), menu)
                act.triggered.connect(lambda checked=False, path=p: self.open_video(path))
                menu.addAction(act)
        else:
            act = QAction("No hay recientes", menu)
            act.setEnabled(False)
            menu.addAction(act)
        btn = self.recent_btn
        gp = btn.mapToGlobal(QPoint(0, btn.height()))
        menu.exec(gp)

    def _menu_stylesheet(self):
        p = self._palette
        return f"""
        QMenu {{
            background: rgba({p['glass_solid'].red()},{p['glass_solid'].green()},{p['glass_solid'].blue()}, 240);
            color: rgb({p['fg'].red()},{p['fg'].green()},{p['fg'].blue()});
            border: 1px solid rgba(255,255,255,40);
            border-radius: 8px;
            padding: 6px;
        }}
        QMenu::item {{
            padding: 6px 24px 6px 18px;
            border-radius: 4px;
        }}
        QMenu::item:selected {{
            background: rgba({p['accent'].red()},{p['accent'].green()},{p['accent'].blue()}, 180);
            color: white;
        }}
        """

    # ---------- CROP MENU ----------
    ASPECTS = [
        ("Original", None),
        ("1:1", 1.0),
        ("16:9", 16 / 9),
        ("9:16", 9 / 16),
        ("4:3", 4 / 3),
        ("3:4", 3 / 4),
        ("4:5", 4 / 5),
        ("2:3", 2 / 3),
    ]

    def _show_crop_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(self._menu_stylesheet())
        group = QActionGroup(menu)
        group.setExclusive(True)
        for label, aspect in self.ASPECTS:
            act = QAction(label, menu)
            act.setCheckable(True)
            act.setChecked(aspect == self._current_aspect)
            act.triggered.connect(lambda checked=False, a=aspect: self._set_crop_aspect(a))
            group.addAction(act)
            menu.addAction(act)
        gp = self.crop_btn.mapToGlobal(QPoint(0, self.crop_btn.height()))
        menu.exec(gp)

    def _set_crop_aspect(self, aspect):
        self._current_aspect = aspect
        self.canvas.set_crop_aspect(aspect)
        if aspect is None:
            self.status_label.setText("Listo")
        else:
            self.status_label.setText("Modo recorte: arrastra para mover, esquinas para redimensionar")

    # ---------- VIDEO FUNCTIONS (logic intact, Qt-flavored) ----------
    def open_video(self, path=None):
        global cap, total_frames, video_fps, video_w, video_h, current_frame, current_frame_num
        global video_path, frame_cache
        if path is None:
            path, _ = QFileDialog.getOpenFileName(
                self, "Abrir Video", "",
                "Video Files (*.mp4 *.avi *.mkv *.mov *.wmv);;All Files (*.*)"
            )
        if not path:
            return
        self.stop_playback()
        self.media_player.stop()
        if cap is not None:
            cap.release()
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            QMessageBox.warning(self, "Error", "No se pudo abrir el video.")
            return
        video_path = path
        abs_path = os.path.abspath(path)
        self.media_player.setSource(QUrl.fromLocalFile(abs_path))
        self.media_player.setPosition(0)
        recent = config.get("recent_files", [])
        if abs_path in recent:
            recent.remove(abs_path)
        recent.insert(0, abs_path)
        config["recent_files"] = recent[:int(config.get("recent_limit", 8))]
        save_config()
        self.canvas.reset_view()
        self._current_aspect = None
        self.status_label.setText("Listo")
        with cache_lock:
            frame_cache.clear()
        bookmarks.clear()
        self.clips.clear()
        self._pending_clip_start = None
        self._update_clips_button()
        self._update_bookmark_button()
        self._draw_bookmarks()
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        video_fps = cap.get(cv2.CAP_PROP_FPS)
        video_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        video_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        current_frame_num = 0
        self.file_label.setText(f"Archivo: {os.path.basename(path)}")
        self.res_label.setText(f"Res.: {video_w}x{video_h}")
        self.fps_label.setText(f"FPS: {video_fps:.2f}")
        self.slider.setRange(0, total_frames - 1 if total_frames > 1 else 0)
        self.slider.setValue(0)
        self.display_frame_at(0)
        self.update_frame_label(0)
        self.update_time_label(0)
        self.generate_filmstrip()
        self.enable_controls()

    def preload_cache(self, center):
        if video_path is None:
            return
        try:
            preload_queue.get_nowait()
        except queue.Empty:
            pass
        try:
            preload_queue.put_nowait(center)
        except queue.Full:
            pass

    def display_frame_at(self, frame_num):
        global current_frame, current_frame_num
        if cap is None:
            return
        with cache_lock:
            cached = frame_cache.get(frame_num)
        if cached is not None:
            current_frame = cached
            current_frame_num = frame_num
            self.canvas.set_pixmap(cv2_to_qpixmap(cached))
        else:
            if cap.get(cv2.CAP_PROP_POS_FRAMES) != frame_num:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            ret, frame = cap.read()
            if not ret:
                return
            current_frame = frame
            current_frame_num = frame_num
            self.canvas.set_pixmap(cv2_to_qpixmap(frame))
        if not is_playing:
            self.preload_cache(frame_num)
        self._update_filmstrip_highlight()
        self._update_bookmark_button()
        if not is_playing and video_fps > 0:
            self.media_player.setPosition(int(frame_num / video_fps * 1000))
        # Refresh blurred backdrops so glass panels reflect the new frame
        self._update_all_backdrops()

    def _update_all_backdrops(self):
        # ponytail: grab() forces a sync repaint; skip while playing (most expensive visual op)
        if is_playing:
            return
        if getattr(self, '_backdrop_timer_pending', False):
            return
        self._backdrop_timer_pending = True
        def _do():
            self._backdrop_timer_pending = False
            for panel in (self.top_bar, self.bottom_bar, self.status_bar):
                try:
                    panel.update_backdrop()
                except Exception:
                    pass
        QTimer.singleShot(50, _do)

    def update_frame_label(self, n):
        self.frame_label.setText(f"Frame: {n}/{total_frames - 1}" if total_frames > 0 else "Frame: —")

    def update_time_label(self, frame_number):
        def fmt(sec):
            if sec < 0: sec = 0
            h, rem = divmod(int(sec), 3600)
            m, s = divmod(rem, 60)
            return f"{h:02d}:{m:02d}:{s:02d}"
        if video_fps > 0 and total_frames > 0:
            cur = frame_number / video_fps
            tot = total_frames / video_fps
            self.time_label.setText(f"{fmt(cur)} / {fmt(tot)}")
        else:
            self.time_label.setText("00:00:00 / 00:00:00")

    def _on_media_error(self, error, error_string):
        if video_path and error_string:
            self.status_label.setText(f"Audio no disponible: {error_string}")

    def _set_media_position_for_current_frame(self):
        if video_fps > 0:
            self.media_player.setPosition(int(current_frame_num / video_fps * 1000))

    # Slider
    def on_slider_change(self, value):
        if cap is None:
            return
        if is_playing:
            self.stop_playback()
        frame_num = int(value)
        with cache_lock:
            cached = frame_cache.get(frame_num)
        if cached is not None:
            self.display_frame_at(frame_num)
            self.update_frame_label(frame_num)
            self.update_time_label(frame_num)
            return
        # Defer seek
        self._deferred_frame = frame_num
        self._play_delay_timer.start(30)

    def _do_deferred_seek(self):
        if is_playing:
            self.stop_playback()
        frame_num = getattr(self, "_deferred_frame", 0)
        self.display_frame_at(frame_num)
        self.update_frame_label(frame_num)
        self.update_time_label(frame_num)

    # Playback
    def _play_tick(self):
        if not is_playing or cap is None:
            return
        pos = current_frame_num + 1
        if pos >= total_frames:
            self.stop_playback()
            return
        self.display_frame_at(pos)
        self.slider.setValue(pos)
        self.update_frame_label(pos)
        self.update_time_label(pos)

    def play_pause(self):
        global is_playing
        if is_playing:
            self.stop_playback()
        else:
            if cap is None:
                return
            is_playing = True
            self.btn_play.load_icon("pause")
            speed = float(config.get("playback_speed", 1.0)) or 1.0
            delay = int(1000 / (video_fps * speed)) if video_fps > 0 else 33
            self.media_player.setPlaybackRate(speed)
            self._set_media_position_for_current_frame()
            self.media_player.play()
            self._play_timer.start(max(1, delay))

    def stop_playback(self):
        global is_playing
        if is_playing:
            is_playing = False
            self._play_timer.stop()
            self.media_player.pause()
            self.btn_play.load_icon("play")
            self._update_all_backdrops()

    def go_first(self):
        self.stop_playback()
        if cap is not None:
            self.display_frame_at(0)
            self.slider.setValue(0)
            self.update_frame_label(0)
            self.update_time_label(0)

    def go_last(self):
        self.stop_playback()
        if cap is not None:
            last = total_frames - 1
            self.display_frame_at(last)
            self.slider.setValue(last)
            self.update_frame_label(last)
            self.update_time_label(last)

    def prev_frame(self):
        self.stop_playback()
        if cap is not None:
            pos = max(0, current_frame_num - 1)
            self.display_frame_at(pos)
            self.slider.setValue(pos)
            self.update_frame_label(pos)
            self.update_time_label(pos)

    def next_frame(self):
        self.stop_playback()
        if cap is not None:
            pos = min(total_frames - 1, current_frame_num + 1)
            self.display_frame_at(pos)
            self.slider.setValue(pos)
            self.update_frame_label(pos)
            self.update_time_label(pos)

    def skip_back(self):
        self.stop_playback()
        if cap is not None:
            step = int(config.get("skip_frames", 10))
            pos = max(0, current_frame_num - step)
            self.display_frame_at(pos)
            self.slider.setValue(pos)
            self.update_frame_label(pos)
            self.update_time_label(pos)

    def skip_forward(self):
        self.stop_playback()
        if cap is not None:
            step = int(config.get("skip_frames", 10))
            pos = min(total_frames - 1, current_frame_num + step)
            self.display_frame_at(pos)
            self.slider.setValue(pos)
            self.update_frame_label(pos)
            self.update_time_label(pos)

    # Clips mode
    def toggle_mode(self):
        self.mode_btn.set_mode(not self._capture_mode)

    def set_mode(self, clips_mode):
        self.stop_playback()
        clips_mode = bool(clips_mode)
        self._capture_mode = not clips_mode

        if clips_mode:
            self._current_aspect = None
            self.canvas.set_crop_aspect(None)

        for widget in (self.crop_btn, self.batch_btn, self.bookmark_btn,
                       self.export_bookmarks_btn, self.save_btn):
            widget.setVisible(not clips_mode)
        for widget in (self.clip_start_btn, self.clip_end_btn, self.clips_btn):
            widget.setVisible(clips_mode)
        self._update_clips_button()
        self._draw_bookmarks()
        if clips_mode:
            self.status_label.setText("Modo Clips: marca inicio y fin para cada clip")
        else:
            self.status_label.setText("Modo Capturas")

    def _update_clips_button(self):
        if hasattr(self, "clips_btn"):
            self.clips_btn.setText(f"Clips ({len(self.clips)})")
            enabled = cap is not None and not self._clip_export_in_progress
            self.clips_btn.setEnabled(enabled)

    def mark_clip_start(self):
        if cap is None:
            return
        self.stop_playback()
        self._pending_clip_start = current_frame_num
        self._draw_bookmarks()
        self.status_label.setText(f"Inicio marcado en frame {current_frame_num}; marca ahora el fin")

    def mark_clip_end(self):
        if cap is None:
            return
        if self._pending_clip_start is None:
            QMessageBox.information(self, "Clip", "Primero marca el inicio del clip.")
            return
        self.stop_playback()
        start = min(self._pending_clip_start, current_frame_num)
        end = max(self._pending_clip_start, current_frame_num)
        if end <= start:
            QMessageBox.information(self, "Clip", "El fin debe estar después del inicio.")
            return
        self.clips.append({"start": start, "end": end})
        self.clips.sort(key=lambda item: (item["start"], item["end"]))
        self._pending_clip_start = None
        self._update_clips_button()
        self._draw_bookmarks()
        self.status_label.setText(f"Clip añadido: frames {start}–{end}. Puedes marcar otro.")

    def _format_clip_time(self, frame_num):
        if video_fps <= 0:
            return "00:00:00.000"
        total_ms = int(frame_num / video_fps * 1000)
        h, rem = divmod(total_ms, 3600000)
        m, rem = divmod(rem, 60000)
        s, ms = divmod(rem, 1000)
        return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"

    def _clip_list_text(self, index, clip):
        return (f"Clip {index}: {self._format_clip_time(clip['start'])}  →  "
                f"{self._format_clip_time(clip['end'] + 1)}  "
                f"(frames {clip['start']}–{clip['end']})")

    def open_clips_dialog(self):
        if cap is None:
            return
        self.stop_playback()
        dlg = QDialog(self)
        dlg.setWindowTitle("Clips del video")
        dlg.setModal(True)
        dlg.resize(680, 450)
        dlg.setStyleSheet(f"""
            QDialog {{
                background: rgba({self._palette['glass_solid'].red()},{self._palette['glass_solid'].green()},{self._palette['glass_solid'].blue()}, 245);
                border-radius: 14px;
            }}
            QLabel {{
                color: rgb({self._palette['fg'].red()},{self._palette['fg'].green()},{self._palette['fg'].blue()});
                background: transparent;
            }}
            QListWidget {{
                background: rgba({self._palette['glass_bg'].red()},{self._palette['glass_bg'].green()},{self._palette['glass_bg'].blue()}, 180);
                color: rgb({self._palette['fg'].red()},{self._palette['fg'].green()},{self._palette['fg'].blue()});
                border: 1px solid rgba(255,255,255,35);
                border-radius: 8px;
                padding: 4px;
            }}
        """)
        if sys.platform == "win32":
            try:
                hwnd = int(dlg.winId())
                enable_acrylic(hwnd, dark=True)
                apply_rounded_corners(hwnd)
            except Exception:
                pass

        v = QVBoxLayout(dlg)
        v.setContentsMargins(18, 18, 18, 18)
        v.setSpacing(10)
        title = QLabel("Selecciona clips para revisarlos o eliminarlos. Se exportarán con audio.")
        title.setWordWrap(True)
        v.addWidget(title)
        v.addWidget(QLabel("Carpeta donde guardar los clips:"))
        destination_row = QHBoxLayout()
        destination_path = QLineEdit(os.path.dirname(os.path.abspath(video_path)))
        destination_path.setReadOnly(True)
        destination_path.setStyleSheet(self._entry_stylesheet())
        destination_row.addWidget(destination_path, 1)
        browse_destination_btn = GlassButton(text="Cambiar...")
        browse_destination_btn.set_colors(self._palette["glass_bg"], self._palette["glass_hover"], self._palette["fg"])

        def choose_destination():
            folder = QFileDialog.getExistingDirectory(
                dlg, "Carpeta de destino para clips", destination_path.text()
            )
            if folder:
                destination_path.setText(os.path.abspath(folder))

        browse_destination_btn.clicked.connect(choose_destination)
        destination_row.addWidget(browse_destination_btn)
        v.addLayout(destination_row)
        clip_list = QListWidget()
        v.addWidget(clip_list, 1)

        def update_selection_buttons():
            delete_btn.setEnabled(bool(self.clips) and clip_list.currentRow() >= 0)
            clear_btn.setEnabled(bool(self.clips))
            individual_btn.setEnabled(bool(self.clips) and not self._clip_export_in_progress)
            combined_btn.setEnabled(bool(self.clips) and not self._clip_export_in_progress)

        def refresh_list():
            clip_list.blockSignals(True)
            clip_list.clear()
            for i, clip in enumerate(self.clips, 1):
                clip_list.addItem(self._clip_list_text(i, clip))
            clip_list.blockSignals(False)
            update_selection_buttons()

        delete_btn = GlassButton(text="Eliminar seleccionado")
        delete_btn.set_colors(self._palette["glass_bg"], self._palette["glass_hover"], self._palette["fg"])
        clear_btn = GlassButton(text="Borrar todos")
        clear_btn.set_colors(self._palette["glass_bg"], self._palette["glass_hover"], self._palette["fg"])
        individual_btn = GlassButton(text="Guardar clips individuales")
        individual_btn.set_colors(self._palette["glass_bg"], self._palette["glass_hover"], self._palette["fg"])
        combined_btn = GlassButton(text="Guardar video combinado", accent=True)
        combined_btn.set_colors(self._palette["glass_bg"], self._palette["glass_hover"], self._palette["fg"],
                                self._palette["accent"], self._palette["accent_hover"])
        close_btn = GlassButton(text="Cerrar")
        close_btn.set_colors(self._palette["glass_bg"], self._palette["glass_hover"], self._palette["fg"])

        def delete_selected():
            row = clip_list.currentRow()
            if 0 <= row < len(self.clips):
                del self.clips[row]
                self._update_clips_button()
                self._draw_bookmarks()
                refresh_list()

        def clear_all():
            self.clips.clear()
            self._update_clips_button()
            self._draw_bookmarks()
            refresh_list()

        delete_btn.clicked.connect(delete_selected)
        clear_btn.clicked.connect(clear_all)
        clip_list.currentRowChanged.connect(lambda _row: update_selection_buttons())
        individual_btn.clicked.connect(lambda: self._start_clip_export(False, dlg, destination_path.text()))
        combined_btn.clicked.connect(lambda: self._start_clip_export(True, dlg, destination_path.text()))
        close_btn.clicked.connect(dlg.reject)

        edit_row = QHBoxLayout()
        edit_row.addWidget(delete_btn)
        edit_row.addWidget(clear_btn)
        edit_row.addStretch()
        v.addLayout(edit_row)
        export_row = QHBoxLayout()
        export_row.addWidget(individual_btn)
        export_row.addWidget(combined_btn)
        v.addLayout(export_row)
        close_row = QHBoxLayout()
        close_row.addStretch()
        close_row.addWidget(close_btn)
        v.addLayout(close_row)

        dlg._export_buttons = (individual_btn, combined_btn)
        self._clip_export_dialog = dlg
        refresh_list()
        dlg.exec()
        if self._clip_export_dialog is dlg:
            self._clip_export_dialog = None

    def _start_clip_export(self, combined, dlg, destination):
        if self._clip_export_in_progress or not self.clips:
            return
        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            QMessageBox.warning(
                dlg, "FFmpeg no encontrado",
                "Para exportar clips con audio necesitas instalar FFmpeg y añadirlo al PATH del sistema."
            )
            return
        ffprobe_path = shutil.which("ffprobe") if combined else None
        if combined and not ffprobe_path:
            QMessageBox.warning(
                dlg, "FFprobe no encontrado",
                "La instalación de FFmpeg debe incluir ffprobe para crear el video combinado."
            )
            return

        clips = [dict(item) for item in self.clips]
        clips.sort(key=lambda item: (item["start"], item["end"]))
        source_path = video_path
        source_fps = float(video_fps)
        output_folder = os.path.abspath(destination.strip()) if destination.strip() else ""
        if not output_folder:
            QMessageBox.warning(dlg, "Carpeta no válida", "Selecciona una carpeta de destino para los clips.")
            return
        try:
            os.makedirs(output_folder, exist_ok=True)
        except OSError as exc:
            QMessageBox.critical(dlg, "Carpeta no disponible", f"No se pudo acceder a la carpeta de destino:\n{exc}")
            return
        stem = self._video_stem()
        rename = bool(config.get("rename_duplicates", True))
        if combined:
            base = f"{stem}_clips_combinados"
            output_path = os.path.join(output_folder, f"{base}.mp4")
            if rename:
                i = 1
                while os.path.exists(output_path):
                    output_path = os.path.join(output_folder, f"{base}_{i}.mp4")
                    i += 1
        else:
            output_path = None

        self._clip_export_in_progress = True
        for btn in getattr(dlg, "_export_buttons", ()):
            btn.setEnabled(False)
        self._update_clips_button()
        self.status_label.setText("Exportando clips con audio…")
        threading.Thread(
            target=self._run_clip_export,
            args=(ffmpeg_path, ffprobe_path, source_path, source_fps, clips, output_folder, stem, rename, combined, output_path),
            daemon=True,
        ).start()

    @staticmethod
    def _run_process(command):
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        return subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, creationflags=creationflags)

    def _run_clip_export(self, ffmpeg_path, ffprobe_path, source_path, source_fps, clips,
                         output_folder, stem, rename, combined, output_path):
        try:
            os.makedirs(output_folder, exist_ok=True)
            if combined:
                has_audio = self._has_audio_stream(ffprobe_path, source_path)
                filters = []
                concat_inputs = []
                for i, clip in enumerate(clips):
                    start_sec = clip["start"] / source_fps
                    end_sec = (clip["end"] + 1) / source_fps
                    filters.append(
                        f"[0:v:0]trim=start={ffmpeg_time(start_sec)}:end={ffmpeg_time(end_sec)},"
                        f"setpts=PTS-STARTPTS[v{i}]"
                    )
                    if has_audio:
                        filters.append(
                            f"[0:a:0]atrim=start={ffmpeg_time(start_sec)}:end={ffmpeg_time(end_sec)},"
                            f"asetpts=PTS-STARTPTS[a{i}]"
                        )
                        concat_inputs.extend((f"[v{i}]", f"[a{i}]"))
                    else:
                        concat_inputs.append(f"[v{i}]")
                if has_audio:
                    filters.append("".join(concat_inputs) + f"concat=n={len(clips)}:v=1:a=1[v][a]")
                else:
                    filters.append("".join(concat_inputs) + f"concat=n={len(clips)}:v=1:a=0[v]")
                command = [
                    ffmpeg_path, "-hide_banner", "-loglevel", "error", "-y",
                    "-i", source_path,
                    "-filter_complex", ";".join(filters),
                    "-map", "[v]",
                ]
                if has_audio:
                    command += ["-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
                command += [
                    "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", output_path,
                ]
                result = self._run_process(command)
                if result.returncode != 0:
                    raise RuntimeError(result.stderr.strip() or "FFmpeg no pudo crear el video combinado.")
                message = f"Video combinado guardado en:\n{output_path}"
            else:
                saved = []
                for clip in clips:
                    start_sec = clip["start"] / source_fps
                    duration = (clip["end"] - clip["start"] + 1) / source_fps
                    clip_path = build_clip_output_path(output_folder, stem, clip["start"], clip["end"], rename)
                    command = [
                        ffmpeg_path, "-hide_banner", "-loglevel", "error", "-y",
                        "-i", source_path,
                        "-ss", ffmpeg_time(start_sec),
                        "-t", ffmpeg_time(duration),
                        "-map", "0:v:0", "-map", "0:a:0?",
                        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                        "-movflags", "+faststart", clip_path,
                    ]
                    result = self._run_process(command)
                    if result.returncode != 0:
                        raise RuntimeError(result.stderr.strip() or "FFmpeg no pudo crear un clip.")
                    saved.append(clip_path)
                message = f"Se guardaron {len(saved)} clips en:\n{output_folder}"
            self._clip_export_done.emit(True, message)
        except Exception as exc:
            self._clip_export_done.emit(False, f"No se pudo exportar:\n{exc}")

    def _has_audio_stream(self, ffprobe_path, source_path):
        command = [
            ffprobe_path, "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=codec_type", "-of", "default=nw=1:nk=1", source_path,
        ]
        result = self._run_process(command)
        return result.returncode == 0 and result.stdout.strip() == "audio"

    def _on_clip_export_done(self, ok, message):
        self._clip_export_in_progress = False
        dlg = self._clip_export_dialog
        if dlg is not None:
            for btn in getattr(dlg, "_export_buttons", ()):
                btn.setEnabled(bool(self.clips))
        self._update_clips_button()
        self.status_label.setText("Exportación terminada" if ok else "Error al exportar clips")
        if dlg is not None:
            if ok:
                QMessageBox.information(dlg, "Exportación completada", message)
            else:
                QMessageBox.critical(dlg, "Error de exportación", message)

    # Save / folder
    def open_save_folder(self):
        save_folder = config.get("save_folder", "")
        if os.path.isdir(save_folder):
            os.startfile(save_folder)
        else:
            QMessageBox.warning(self, "Carpeta no encontrada", f"La carpeta no existe:\n{save_folder}")

    def _video_stem(self):
        if video_path:
            return os.path.splitext(os.path.basename(video_path))[0]
        return "video"

    def save_frame(self):
        global current_frame, current_frame_num
        if current_frame is None:
            QMessageBox.warning(self, "Sin Frame", "No hay ningun frame para guardar.")
            return
        fmt = config["save_format"]
        save_folder = config["save_folder"]
        os.makedirs(save_folder, exist_ok=True)
        crop = self.canvas.crop_frame_rect()
        if crop is None and self.canvas.zoom_level > 1.0:
            crop = self.canvas.visible_frame_rect()
        out = process_frame_for_export(current_frame, crop, int(config.get("output_scale", 100)))
        full_path = build_output_path(save_folder, config.get("filename_pattern", ""),
                                      self._video_stem(), current_frame_num, fmt,
                                      bool(config.get("rename_duplicates", True)))
        ok = cv2.imwrite(full_path, out, imwrite_params(fmt))
        if not ok:
            self.status_label.setText("Error al guardar el frame")
            return
        filename = os.path.basename(full_path)
        size_bytes = os.path.getsize(full_path)
        if size_bytes >= 1024 * 1024:
            size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            size_str = f"{size_bytes / 1024:.1f} KB"
        self.status_label.setText(f"✓ Frame guardado: {filename} ({size_str})")
        QTimer.singleShot(4000, lambda: self.status_label.setText("Listo"))
        if config.get("open_folder_after_save", False):
            try:
                os.startfile(save_folder)
            except Exception:
                pass

    # Bookmarks
    def toggle_bookmark(self, event=None):
        global current_frame_num
        if cap is None:
            return
        if current_frame_num in bookmarks:
            bookmarks.remove(current_frame_num)
        else:
            bookmarks.append(current_frame_num)
        self._update_bookmark_button()
        self._draw_bookmarks()

    def _update_bookmark_button(self):
        self.bookmark_btn.setText(f" {len(bookmarks)}")
        self.bookmark_btn.load_icon("bookmark_active" if current_frame_num in bookmarks else "bookmark")

    def _draw_bookmarks(self):
        self.bookmarks_bar.update()

    def _paint_bookmarks_bar(self, e):
        p = QPainter(self.bookmarks_bar)
        p.setRenderHint(QPainter.Antialiasing, True)
        w = self.bookmarks_bar.width()
        h = self.bookmarks_bar.height()
        if total_frames <= 1:
            return
        if not self._capture_mode:
            for clip in self.clips:
                x1 = int((clip["start"] / (total_frames - 1)) * w)
                x2 = int((clip["end"] / (total_frames - 1)) * w)
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(QColor(self._palette["accent"].red(),
                                         self._palette["accent"].green(),
                                         self._palette["accent"].blue(), 100)))
                p.drawRect(QRect(x1, 0, max(2, x2 - x1), h))
                p.setBrush(QBrush(self._palette["accent"]))
                p.drawRoundedRect(QRect(x1 - 2, 0, 4, h), 2, 2)
                p.drawRoundedRect(QRect(x2 - 2, 0, 4, h), 2, 2)
            if self._pending_clip_start is not None:
                x = int((self._pending_clip_start / (total_frames - 1)) * w)
                p.setBrush(QBrush(QColor(255, 196, 0, 230)))
                p.drawRoundedRect(QRect(x - 2, 0, 4, h), 2, 2)
            return
        for frame in bookmarks:
            x = int((frame / (total_frames - 1)) * w)
            p.setBrush(QBrush(self._palette["accent"]))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRect(x - 2, 0, 4, h), 2, 2)

    def export_bookmarks(self):
        if not bookmarks:
            QMessageBox.information(self, "Marcadores", "No hay frames marcados.")
            return
        fmt = config["save_format"]
        save_folder = config["save_folder"]
        os.makedirs(save_folder, exist_ok=True)
        saved = 0
        stem = self._video_stem()
        crop = self.canvas.crop_frame_rect()
        scale = int(config.get("output_scale", 100))
        pattern = config.get("filename_pattern", "")
        rename = bool(config.get("rename_duplicates", True))
        local_cap = cv2.VideoCapture(video_path)
        for frame_num in bookmarks:
            local_cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            ret, frame = local_cap.read()
            if not ret:
                continue
            out = process_frame_for_export(frame, crop, scale)
            full_path = build_output_path(save_folder, pattern, stem, frame_num, fmt, rename)
            cv2.imwrite(full_path, out, imwrite_params(fmt))
            saved += 1
        local_cap.release()
        QMessageBox.information(self, "Completado", f"Se exportaron {saved} frames a:\n{save_folder}")

    # Filmstrip
    def generate_filmstrip(self):
        global total_frames
        # Clear existing thumbs
        for t in self.filmstrip_thumbs:
            t.setParent(None)
            t.deleteLater()
        self.filmstrip_thumbs.clear()
        self.filmstrip_frames.clear()

        if total_frames <= 1 or video_path is None:
            return
        cfg_thumbs = int(config.get("filmstrip_thumbs", 0))
        if cfg_thumbs > 0:
            num_thumbs = cfg_thumbs
        else:
            num_thumbs = min(20, max(5, int(self.width() / 90)))
        step = max(1, total_frames // num_thumbs)

        path = video_path

        def worker():
            local_cap = cv2.VideoCapture(path)
            if not local_cap.isOpened():
                return
            for i in range(num_thumbs):
                fn = min(total_frames - 1, i * step)
                local_cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
                ret, frame = local_cap.read()
                if not ret:
                    break
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w = frame_rgb.shape[:2]
                scale = min(80 / w, 45 / h)
                new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
                resized = cv2.resize(frame_rgb, (new_w, new_h), interpolation=cv2.INTER_AREA)
                img = QImage(resized.data, new_w, new_h, new_w * 3, QImage.Format_RGB888).copy()
                self._thumb_ready.emit(img, fn, path)
            local_cap.release()

        threading.Thread(target=worker, daemon=True).start()

    def _add_filmstrip_thumb(self, img, frame_idx, path):
        if path != video_path:
            return
        thumb = FilmstripThumb(self.filmstrip)
        thumb.setPixmap(QPixmap.fromImage(img))
        thumb.set_colors(self._palette["thumb_bg"], self._palette["thumb_selected"])
        thumb.mousePressEvent = lambda e, f=frame_idx: self._filmstrip_click(f)
        # Insert before the trailing stretch
        self.filmstrip_layout.insertWidget(self.filmstrip_layout.count() - 1, thumb)
        self.filmstrip_thumbs.append(thumb)
        self.filmstrip_frames.append(frame_idx)
        self._update_filmstrip_highlight()

    def _filmstrip_click(self, frame_idx):
        self.stop_playback()
        self.display_frame_at(frame_idx)
        self.slider.setValue(frame_idx)
        self.update_frame_label(frame_idx)
        self.update_time_label(frame_idx)

    def _update_filmstrip_highlight(self):
        if not self.filmstrip_frames:
            return
        closest = 0
        mind = float('inf')
        for i, f in enumerate(self.filmstrip_frames):
            d = abs(f - current_frame_num)
            if d < mind:
                mind = d
                closest = i
        for i, t in enumerate(self.filmstrip_thumbs):
            t.set_selected(i == closest)

    def enable_controls(self):
        for b in (self.btn_first, self.btn_prev, self.btn_play, self.btn_next, self.btn_last,
                  self.save_btn, self.open_folder_btn, self.batch_btn, self.crop_btn,
                  self.bookmark_btn, self.export_bookmarks_btn):
            b.setEnabled(True)
        self.clip_start_btn.setEnabled(True)
        self.clip_end_btn.setEnabled(True)
        self._update_clips_button()

    # Empty state
    def _draw_empty_state(self):
        if current_frame is None:
            self.canvas.clear_pixmap()

    # ---------- SETTINGS DIALOG ----------
    def open_settings(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Configuracion")
        dlg.setModal(True)
        dlg.resize(500, 620)
        dlg.setStyleSheet(f"""
            QDialog {{
                background: rgba({self._palette['glass_solid'].red()},{self._palette['glass_solid'].green()},{self._palette['glass_solid'].blue()}, 245);
                border-radius: 14px;
            }}
            QLabel {{
                color: rgb({self._palette['fg'].red()},{self._palette['fg'].green()},{self._palette['fg'].blue()});
                background: transparent;
            }}
            QScrollArea, QScrollArea > QWidget > QWidget {{
                background: transparent;
                border: none;
            }}
        """)

        # acrylic
        if sys.platform == "win32":
            try:
                hwnd = int(dlg.winId())
                enable_acrylic(hwnd, dark=True)
                apply_rounded_corners(hwnd)
            except Exception:
                pass

        root = QVBoxLayout(dlg)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(10)

        scroll = QScrollArea(dlg)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        scroll.setWidget(inner)
        v = QVBoxLayout(inner)
        v.setContentsMargins(2, 2, 10, 2)
        v.setSpacing(8)
        root.addWidget(scroll, 1)

        fg_ss = (f"color: rgb({self._palette['fg'].red()},{self._palette['fg'].green()},{self._palette['fg'].blue()});"
                 f" background: transparent;")
        dim_ss = (f"color: rgb({self._palette['fg_dim'].red()},{self._palette['fg_dim'].green()},{self._palette['fg_dim'].blue()});"
                  f" background: transparent;")

        def section(text):
            lbl = QLabel(text)
            f = QFont("Segoe UI Variable Text", 10)
            f.setWeight(QFont.DemiBold)
            lbl.setFont(f)
            lbl.setStyleSheet(f"color: rgb({self._palette['accent'].red()},{self._palette['accent'].green()},{self._palette['accent'].blue()}); background: transparent;")
            v.addWidget(lbl)

        def mk_spin(mn, mx, val, suffix=""):
            sp = QSpinBox()
            sp.setRange(mn, mx)
            sp.setValue(int(val))
            if suffix:
                sp.setSuffix(suffix)
            sp.setStyleSheet(self._entry_stylesheet())
            return sp

        def mk_check(text, checked):
            c = QCheckBox(text)
            c.setChecked(bool(checked))
            c.setStyleSheet(fg_ss)
            c.setFont(QFont("Segoe UI Variable Text", 9))
            return c

        # ---- Archivos ----
        section("Archivos")
        v.addWidget(QLabel("Carpeta de guardado"))
        folder_row = QHBoxLayout()
        folder_var = QLineEdit(config.get("save_folder", ""))
        folder_var.setStyleSheet(self._entry_stylesheet())
        browse_btn = GlassButton(text="Examinar...")
        browse_btn.set_colors(self._palette["glass_bg"], self._palette["glass_hover"], self._palette["fg"])

        def browse():
            path = QFileDialog.getExistingDirectory(dlg, "Carpeta de guardado")
            if path:
                folder_var.setText(path)
        browse_btn.clicked.connect(browse)
        folder_row.addWidget(folder_var, 1)
        folder_row.addWidget(browse_btn)
        v.addLayout(folder_row)

        v.addWidget(QLabel("Formato"))
        radio_row = QHBoxLayout()
        png_radio = QRadioButton("PNG")
        jpg_radio = QRadioButton("JPG")
        for r in (png_radio, jpg_radio):
            r.setStyleSheet(fg_ss)
            r.setFont(QFont("Segoe UI Variable Text", 9))
        bg = QButtonGroup(dlg)
        bg.addButton(png_radio)
        bg.addButton(jpg_radio)
        if config.get("save_format") == "jpg":
            jpg_radio.setChecked(True)
        else:
            png_radio.setChecked(True)
        radio_row.addWidget(png_radio)
        radio_row.addWidget(jpg_radio)
        radio_row.addStretch()
        v.addLayout(radio_row)

        qual_lbl = QLabel("Calidad JPG")
        qual_scale = QSlider(Qt.Horizontal)
        qual_scale.setRange(1, 100)
        qual_scale.setValue(int(config.get("jpg_quality", 95)))
        qual_scale.setStyleSheet(self._slider_stylesheet())
        v.addWidget(qual_lbl)
        v.addWidget(qual_scale)

        comp_lbl = QLabel("Compresion PNG (0 = rapida, 9 = maxima)")
        comp_scale = QSlider(Qt.Horizontal)
        comp_scale.setRange(0, 9)
        comp_scale.setValue(int(config.get("png_compression", 3)))
        comp_scale.setStyleSheet(self._slider_stylesheet())
        v.addWidget(comp_lbl)
        v.addWidget(comp_scale)

        def toggle_format_opts():
            is_jpg = jpg_radio.isChecked()
            qual_lbl.setVisible(is_jpg)
            qual_scale.setVisible(is_jpg)
            comp_lbl.setVisible(not is_jpg)
            comp_scale.setVisible(not is_jpg)
        png_radio.toggled.connect(toggle_format_opts)
        jpg_radio.toggled.connect(toggle_format_opts)
        toggle_format_opts()

        v.addWidget(QLabel("Patron de nombre de archivo"))
        pattern_var = QLineEdit(config.get("filename_pattern", "{video}_frame_{frame}"))
        pattern_var.setStyleSheet(self._entry_stylesheet())
        pattern_var.setPlaceholderText("{video}_frame_{frame}")
        v.addWidget(pattern_var)
        hint = QLabel("Variables: {video} = nombre del video, {frame} = numero de frame, {fecha} = fecha y hora")
        hint.setStyleSheet(dim_ss)
        hint.setFont(QFont("Segoe UI Variable Text", 8))
        hint.setWordWrap(True)
        v.addWidget(hint)

        scale_row = QHBoxLayout()
        scale_row.addWidget(QLabel("Escalado de salida"))
        scale_row.addStretch()
        scale_spin = mk_spin(10, 100, config.get("output_scale", 100), " %")
        scale_row.addWidget(scale_spin)
        v.addLayout(scale_row)

        open_folder_chk = mk_check("Abrir la carpeta despues de guardar", config.get("open_folder_after_save", False))
        v.addWidget(open_folder_chk)
        rename_chk = mk_check("Renombrar si el archivo ya existe (no sobrescribir)", config.get("rename_duplicates", True))
        v.addWidget(rename_chk)

        # ---- Navegacion ----
        section("Navegacion y reproduccion")
        skip_row = QHBoxLayout()
        skip_row.addWidget(QLabel("Salto de frames (Shift + flechas)"))
        skip_row.addStretch()
        skip_spin = mk_spin(1, 600, config.get("skip_frames", 10))
        skip_row.addWidget(skip_spin)
        v.addLayout(skip_row)

        speed_row = QHBoxLayout()
        speed_row.addWidget(QLabel("Velocidad de reproduccion"))
        speed_row.addStretch()
        speed_combo = QComboBox()
        speed_combo.setStyleSheet(self._entry_stylesheet())
        speeds = [("0.25x", 0.25), ("0.5x", 0.5), ("0.75x", 0.75), ("1x (normal)", 1.0),
                  ("1.25x", 1.25), ("1.5x", 1.5), ("2x", 2.0)]
        cur_speed = float(config.get("playback_speed", 1.0))
        for i, (label, val) in enumerate(speeds):
            speed_combo.addItem(label, val)
            if abs(val - cur_speed) < 0.001:
                speed_combo.setCurrentIndex(i)
        if speed_combo.currentIndex() < 0:
            speed_combo.setCurrentIndex(3)
        speed_row.addWidget(speed_combo)
        v.addLayout(speed_row)

        # ---- Interfaz ----
        section("Interfaz")
        filmstrip_chk = mk_check("Mostrar tira de miniaturas", config.get("filmstrip_visible", True))
        v.addWidget(filmstrip_chk)
        thumbs_row = QHBoxLayout()
        thumbs_row.addWidget(QLabel("Numero de miniaturas (0 = automatico)"))
        thumbs_row.addStretch()
        thumbs_spin = mk_spin(0, 30, config.get("filmstrip_thumbs", 0))
        thumbs_row.addWidget(thumbs_spin)
        v.addLayout(thumbs_row)

        recent_row = QHBoxLayout()
        recent_row.addWidget(QLabel("Videos recientes (maximo)"))
        recent_row.addStretch()
        recent_spin = mk_spin(1, 20, config.get("recent_limit", 8))
        recent_row.addWidget(recent_spin)
        v.addLayout(recent_row)
        clear_recent_btn = GlassButton(text="Limpiar historial de recientes")
        clear_recent_btn.set_colors(self._palette["glass_bg"], self._palette["glass_hover"], self._palette["fg"])

        def clear_recent():
            config["recent_files"] = []
            save_config()
            clear_recent_btn.setEnabled(False)
        clear_recent_btn.clicked.connect(clear_recent)
        if not config.get("recent_files"):
            clear_recent_btn.setEnabled(False)
        v.addWidget(clear_recent_btn)

        v.addStretch()

        # ---- Buttons ----
        btn_row = QHBoxLayout()
        reset_btn = GlassButton(text="Restablecer")
        reset_btn.set_colors(self._palette["glass_bg"], self._palette["glass_hover"], self._palette["fg"])

        def reset_fields():
            folder_var.setText(_DEFAULTS["save_folder"])
            png_radio.setChecked(_DEFAULTS["save_format"] == "png")
            jpg_radio.setChecked(_DEFAULTS["save_format"] == "jpg")
            qual_scale.setValue(_DEFAULTS["jpg_quality"])
            comp_scale.setValue(_DEFAULTS["png_compression"])
            pattern_var.setText(_DEFAULTS["filename_pattern"])
            scale_spin.setValue(_DEFAULTS["output_scale"])
            open_folder_chk.setChecked(_DEFAULTS["open_folder_after_save"])
            rename_chk.setChecked(_DEFAULTS["rename_duplicates"])
            skip_spin.setValue(_DEFAULTS["skip_frames"])
            for i in range(speed_combo.count()):
                if abs(speed_combo.itemData(i) - _DEFAULTS["playback_speed"]) < 0.001:
                    speed_combo.setCurrentIndex(i)
                    break
            filmstrip_chk.setChecked(_DEFAULTS["filmstrip_visible"])
            thumbs_spin.setValue(_DEFAULTS["filmstrip_thumbs"])
            recent_spin.setValue(_DEFAULTS["recent_limit"])
        reset_btn.clicked.connect(reset_fields)

        btn_row.addWidget(reset_btn)
        btn_row.addStretch()
        cancel_btn = GlassButton(text="Cancelar")
        cancel_btn.set_colors(self._palette["glass_bg"], self._palette["glass_hover"], self._palette["fg"])
        cancel_btn.clicked.connect(dlg.reject)
        save_btn = GlassButton(text="Guardar", accent=True)
        save_btn.set_colors(self._palette["glass_bg"], self._palette["glass_hover"], self._palette["fg"],
                            self._palette["accent"], self._palette["accent_hover"])

        def save():
            config["save_folder"] = folder_var.text()
            config["save_format"] = "jpg" if jpg_radio.isChecked() else "png"
            config["jpg_quality"] = qual_scale.value()
            config["png_compression"] = comp_scale.value()
            config["filename_pattern"] = pattern_var.text().strip() or _DEFAULTS["filename_pattern"]
            config["output_scale"] = scale_spin.value()
            config["open_folder_after_save"] = open_folder_chk.isChecked()
            config["rename_duplicates"] = rename_chk.isChecked()
            config["skip_frames"] = skip_spin.value()
            config["playback_speed"] = float(speed_combo.currentData())
            config["filmstrip_visible"] = filmstrip_chk.isChecked()
            config["filmstrip_thumbs"] = thumbs_spin.value()
            config["recent_limit"] = recent_spin.value()
            config["recent_files"] = config.get("recent_files", [])[:recent_spin.value()]
            save_config()
            self._apply_interface_settings()
            dlg.accept()
        save_btn.clicked.connect(save)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        root.addLayout(btn_row)

        dlg.exec()

    def _apply_interface_settings(self):
        self.filmstrip.setVisible(bool(config.get("filmstrip_visible", True)))
        self._layout_panels()
        if video_path is not None and total_frames > 1:
            self.generate_filmstrip()

    def _entry_stylesheet(self):
        p = self._palette
        return f"""
            QLineEdit, QSpinBox, QComboBox {{
                background: rgba({p['glass_bg'].red()},{p['glass_bg'].green()},{p['glass_bg'].blue()}, 200);
                color: rgb({p['fg'].red()},{p['fg'].green()},{p['fg'].blue()});
                border: 1px solid rgba(255,255,255,40);
                border-radius: 6px;
                padding: 6px 10px;
                font: 9pt "Segoe UI Variable Text";
            }}
        """

    def _slider_stylesheet(self):
        p = self._palette
        return f"""
            QSlider::groove:horizontal {{
                background: rgba({p['glass_bg'].red()},{p['glass_bg'].green()},{p['glass_bg'].blue()}, 200);
                height: 6px;
                border-radius: 3px;
            }}
            QSlider::sub-page:horizontal {{
                background: rgb({p['accent'].red()},{p['accent'].green()},{p['accent'].blue()});
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: white;
                width: 16px;
                height: 16px;
                margin: -6px 0;
                border-radius: 8px;
            }}
        """

    # ---------- BATCH DIALOG ----------
    def open_batch_dialog(self):
        self.stop_playback()
        dlg = QDialog(self)
        dlg.setWindowTitle("Extraccion por Lotes")
        dlg.setModal(True)
        dlg.resize(420, 300)
        dlg.setStyleSheet(f"""
            QDialog {{
                background: rgba({self._palette['glass_solid'].red()},{self._palette['glass_solid'].green()},{self._palette['glass_solid'].blue()}, 245);
                border-radius: 14px;
            }}
            QLabel {{
                color: rgb({self._palette['fg'].red()},{self._palette['fg'].green()},{self._palette['fg'].blue()});
                background: transparent;
            }}
        """)
        if sys.platform == "win32":
            try:
                hwnd = int(dlg.winId())
                enable_acrylic(hwnd, dark=True)
                apply_rounded_corners(hwnd)
            except Exception:
                pass

        v = QVBoxLayout(dlg)
        v.setContentsMargins(18, 18, 18, 18)
        v.setSpacing(10)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Modo de extraccion"))
        mode_row.addStretch()
        mode_combo = QComboBox()
        mode_combo.setStyleSheet(self._entry_stylesheet())
        mode_combo.addItem("Cada N frames", "frames")
        mode_combo.addItem("Cada N segundos", "seconds")
        if config.get("batch_mode", "frames") == "seconds":
            mode_combo.setCurrentIndex(1)
        mode_row.addWidget(mode_combo)
        v.addLayout(mode_row)

        n_row = QHBoxLayout()
        n_lbl = QLabel()
        n_row.addWidget(n_lbl, 1)
        spin = QSpinBox()
        spin.setRange(1, 10000)
        spin.setValue(int(config.get("batch_every", 30)))
        spin.setStyleSheet(self._entry_stylesheet())
        n_row.addWidget(spin)
        v.addLayout(n_row)

        def update_n_lbl():
            if mode_combo.currentData() == "seconds":
                n_lbl.setText("Extraer 1 frame cada N segundos")
            else:
                n_lbl.setText("Extraer 1 frame cada N frames")
        mode_combo.currentIndexChanged.connect(lambda _i: update_n_lbl())
        update_n_lbl()

        v.addWidget(QLabel("Rango de frames (inicio - fin)"))
        range_row = QHBoxLayout()
        start_spin = QSpinBox()
        start_spin.setRange(0, max(0, total_frames - 1))
        start_spin.setValue(0)
        end_spin = QSpinBox()
        end_spin.setRange(0, max(0, total_frames - 1))
        end_spin.setValue(max(0, total_frames - 1))
        for sp in (start_spin, end_spin):
            sp.setStyleSheet(self._entry_stylesheet())
        range_row.addWidget(start_spin, 1)
        dash = QLabel("-")
        range_row.addWidget(dash)
        range_row.addWidget(end_spin, 1)
        v.addLayout(range_row)

        progress = QProgressBar()
        progress.setStyleSheet(self._slider_stylesheet())
        progress.setRange(0, 100)
        progress.setValue(0)
        v.addWidget(progress)
        status_lbl = QLabel("Listo")
        v.addWidget(status_lbl)
        v.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = GlassButton(text="Cancelar")
        cancel_btn.set_colors(self._palette["glass_bg"], self._palette["glass_hover"], self._palette["fg"])
        cancel_btn.clicked.connect(dlg.reject)
        start_btn = GlassButton(text="Iniciar", accent=True)
        start_btn.set_colors(self._palette["glass_bg"], self._palette["glass_hover"], self._palette["fg"],
                             self._palette["accent"], self._palette["accent_hover"])

        def start():
            if cap is None:
                return
            n = spin.value()
            if n < 1:
                return
            f_start = min(start_spin.value(), end_spin.value())
            f_end = max(start_spin.value(), end_spin.value())
            mode = mode_combo.currentData()
            config["batch_every"] = n
            config["batch_mode"] = mode
            save_config()
            spin.setEnabled(False)
            mode_combo.setEnabled(False)
            start_spin.setEnabled(False)
            end_spin.setEnabled(False)
            start_btn.setEnabled(False)
            cancel_btn.setEnabled(False)
            progress.setValue(0)
            crop = self.canvas.crop_frame_rect()
            scale = int(config.get("output_scale", 100))
            pattern = config.get("filename_pattern", "")
            rename = bool(config.get("rename_duplicates", True))

            def run():
                ext = config["save_format"]
                save_folder = config["save_folder"]
                os.makedirs(save_folder, exist_ok=True)
                saved = 0
                stem = self._video_stem()
                if mode == "seconds" and video_fps > 0:
                    step = max(1, int(round(n * video_fps)))
                else:
                    step = n
                span = max(1, f_end - f_start)
                local_cap = cv2.VideoCapture(video_path)
                i = f_start
                while i <= f_end:
                    local_cap.set(cv2.CAP_PROP_POS_FRAMES, i)
                    ret, frame = local_cap.read()
                    if ret:
                        out = process_frame_for_export(frame, crop, scale)
                        full_path = build_output_path(save_folder, pattern, stem, i, ext, rename)
                        cv2.imwrite(full_path, out, imwrite_params(ext))
                        saved += 1
                    pct = int((i - f_start) / span * 100)
                    self._batch_progress.emit(min(pct, 100), saved, i)
                    i += step
                local_cap.release()
                self._batch_done.emit(saved)

            self._batch_widgets = (progress, status_lbl, dlg)
            threading.Thread(target=run, daemon=True).start()

        start_btn.clicked.connect(start)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(start_btn)
        v.addLayout(btn_row)
        dlg.exec()

    def _on_batch_progress(self, pct, saved, idx):
        if not self._batch_widgets:
            return
        progress, status_lbl, _ = self._batch_widgets
        try:
            progress.setValue(pct)
            status_lbl.setText(f"Guardados: {saved}  ({idx}/{total_frames - 1})")
        except RuntimeError:
            self._batch_widgets = None

    def _on_batch_done(self, saved):
        widgets, self._batch_widgets = self._batch_widgets, None
        if not widgets:
            return
        progress, _, dlg = widgets
        try:
            progress.setValue(100)
            QMessageBox.information(dlg, "Completado", f"Extraccion finalizada.\n{saved} frames guardados en:\n{config['save_folder']}")
            dlg.accept()
        except RuntimeError:
            pass

    # ---------- KEYBOARD ----------
    def keyPressEvent(self, e):
        k = e.key()
        mod = e.modifiers()
        if k == Qt.Key_Space:
            if current_frame is not None:
                self.save_frame() if self._capture_mode else self.play_pause()
        elif k == Qt.Key_Left and mod & Qt.ShiftModifier:
            self.skip_back()
        elif k == Qt.Key_Right and mod & Qt.ShiftModifier:
            self.skip_forward()
        elif k == Qt.Key_Left:
            self.prev_frame()
        elif k == Qt.Key_Right:
            self.next_frame()
        elif k == Qt.Key_Home:
            self.go_first()
        elif k == Qt.Key_End:
            self.go_last()
        elif k == Qt.Key_I and not self._capture_mode:
            self.mark_clip_start()
        elif k == Qt.Key_O and not self._capture_mode:
            self.mark_clip_end()
        elif k == Qt.Key_M and self._capture_mode:
            self.toggle_bookmark()
        elif mod & Qt.ControlModifier:
            if k == Qt.Key_S:
                self.save_frame()
            elif k == Qt.Key_O:
                self.open_video()
            elif k == Qt.Key_E:
                self.open_save_folder()
        else:
            super().keyPressEvent(e)

    # ---------- CLOSE ----------
    def closeEvent(self, e):
        global cap
        preloader_stop_event.set()
        self.media_player.stop()
        if cap is not None:
            cap.release()
        save_config()
        super().closeEvent(e)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Frame Extractor")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
