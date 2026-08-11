
import asyncio
# pyrefly: ignore [missing-import]
from livekit import agents
import contextlib
import cv2
import json
import logging
import math
import numpy as np
import os
import pickle
import platform
import psutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

from prompts import VARIANT_NAME

# Windows audio control imports
try:
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    WINDOWS_AUDIO_AVAILABLE = True
except ImportError:
    WINDOWS_AUDIO_AVAILABLE = False
    print("⚠️ pycaw not available. Install with: pip install pycaw")

from dotenv import find_dotenv, load_dotenv, set_key
from livekit import rtc
from livekit.agents import AgentServer, WorkerOptions, cli as agents_cli
from livekit.agents.utils import images
from livekit.rtc import VideoBufferType
from PyQt5.QtCore import (
    QEasingCurve,
    QParallelAnimationGroup,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSequentialAnimationGroup,
    QSize,
    Qt,
    QTimer,
    pyqtProperty,
    pyqtSignal,
)
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QFont,
    QFontMetrics,
    QIcon,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
)
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from Mark_Voice_Assistant import Assistant, entrypoint
import traceback

# Conditional imports for face recognition


# ===== Windows Microphone Control Functions =====

def get_microphone_device():
    """Get the default microphone device endpoint."""
    if not WINDOWS_AUDIO_AVAILABLE:
        return None
    
    try:
        devices = AudioUtilities.GetMicrophone()
        if devices:
            interface = devices.Activate(
                IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            return cast(interface, POINTER(IAudioEndpointVolume))
    except Exception as e:
        print(f"❌ Error getting microphone device: {e}")
    return None

def mute_system_microphone():
    """Mute the system microphone at Windows level."""
    if not WINDOWS_AUDIO_AVAILABLE:
        print("⚠️ Windows audio control not available")
        return False
    
    try:
        mic = get_microphone_device()
        if mic:
            mic.SetMute(1, None)
            print("🔇 System microphone MUTED at Windows level")
            return True
    except Exception as e:
        print(f"❌ Error muting microphone: {e}")
    return False

def unmute_system_microphone():
    """Unmute the system microphone at Windows level."""
    if not WINDOWS_AUDIO_AVAILABLE:
        print("⚠️ Windows audio control not available")
        return False
    
    try:
        mic = get_microphone_device()
        if mic:
            mic.SetMute(0, None)
            print("🎤 System microphone UNMUTED at Windows level")
            return True
    except Exception as e:
        print(f"❌ Error unmuting microphone: {e}")
    return False

def is_microphone_muted():
    """Check if the system microphone is currently muted."""
    if not WINDOWS_AUDIO_AVAILABLE:
        return None
    
    try:
        mic = get_microphone_device()
        if mic:
            return bool(mic.GetMute())
    except Exception as e:
        print(f"❌ Error checking microphone status: {e}")
    return None

# ===== End of Microphone Control Functions =====


class RightPanel(QWidget):
    """Right-side panel for camera, time, and network status."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(350)
        self.setStyleSheet("background-color: transparent;")
        self.camera_available = False
        self.camera = None
        self.assistant = None
        self._video_source = None
        self._frame_counter = 0
        self._last_frame_sent = 0
        self._min_frame_interval = 1 / 20  # 20 FPS

        self.init_ui()
        self.init_camera()

        self.time_timer = QTimer(self)
        self.time_timer.timeout.connect(self.update_time)
        self.time_timer.start(1000)

        self.network_timer = QTimer(self)
        self.network_timer.timeout.connect(self.update_network_info)
        self.network_timer.start(3000)

        self.camera_timer = QTimer(self)
        self.camera_timer.timeout.connect(self.update_camera_feed)
        self.camera_timer.start(50)  # ~20 FPS

    def init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 25, 15, 25)
        layout.setSpacing(20)

        time_label = QLabel("TEMPORAL SYNCHRONIZATION")
        time_label.setStyleSheet(
            """
            color: #ffd700;
            font-size: 14px;
            font-weight: bold;
            padding-bottom: 8px;
            border-bottom: 1px solid rgba(139, 69, 255, 0.3);
            letter-spacing: 1px;
        """
        )
        layout.addWidget(time_label)
        self.time_widget = self.create_time_card()
        layout.addWidget(self.time_widget)

        network_label = QLabel("WIFI CONNECTION")
        network_label.setStyleSheet(
            """
            color: #ffd700;
            font-size: 14px;
            font-weight: bold;
            padding-bottom: 8px;
            border-bottom: 1px solid rgba(139, 69, 255, 0.3);   
            letter-spacing: 1px;
        """
        )
        layout.addWidget(network_label)
        self.network_status_widget = self.create_network_card(
            "CONNECTION", "WiFi (MARK_5G) - 92%"
        )
        layout.addWidget(self.network_status_widget)

        layout.addItem(QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding))

        camera_label = QLabel("VISUAL INPUT")
        camera_label.setStyleSheet(
            """
            color: #ffd700;
            font-size: 14px;
            font-weight: bold;
            padding-bottom: 8px;
            border-bottom: 1px solid rgba(139, 69, 255, 0.3);
            letter-spacing: 1px;
        """
        )
        layout.addWidget(camera_label)
        self.camera_widget = self.create_camera_widget()
        layout.addWidget(self.camera_widget)

        self.setLayout(layout)

    def init_camera(self):
        """Initialize camera with multiple attempts."""
        if self.camera_available:
            return
        for i in range(3):
            try:
                self.camera = cv2.VideoCapture(i, cv2.CAP_DSHOW)
                if self.camera.isOpened():
                    ret, frame = self.camera.read()
                    if ret and frame is not None:
                        self.camera_available = True
                        print(f"✅ Camera initialized successfully on index {i}")
                        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                        self.camera.set(cv2.CAP_PROP_FPS, 20)
                        self.show_no_camera_message(show=False)
                        return
                    self.camera.release()
            except Exception as e:
                print(f"❌ Camera index {i} failed: {e}")
        
        print("❌ No working camera found on indices 0-2")
        self.camera_available = False
        self.show_no_camera_message(show=True)


    def set_video_track(self, video_source):
        """Set the video track to send frames to."""
        self._video_source = video_source
        print("✅ Video track set in RightPanel")

    async def send_frame_to_assistant(self, frame):
        """Send video frame to assistant for processing."""
        if not hasattr(self, "assistant") or not self.assistant:
            return
        try:
            rgba_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2RGBA)
            height, width, _ = rgba_frame.shape
            video_frame = rtc.VideoFrame(
                width, height, VideoBufferType.RGBA, rgba_frame.tobytes()
            )
            if asyncio.iscoroutinefunction(self.assistant.process_visual_frame):
                await self.assistant.process_visual_frame(video_frame)
            else:
                self.assistant.process_visual_frame(video_frame)
        except Exception as e:
            print(f"Frame sending error: {e}")

    def create_time_card(self):
        """Create the time display card."""
        card = QWidget()
        card.setStyleSheet(
            """
            background-color: rgba(0, 20, 40, 120);
            border-radius: 4px;
            border: 1px solid rgba(0, 80, 120, 80);
        """
        )
        card.setFixedHeight(100)
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(5)
        self.time_label = QLabel()
        self.time_label.setStyleSheet(
            """
            color: #ffd700;
            font-size: 28px;
            font-weight: bold;
            qproperty-alignment: AlignCenter;
        """
        )
        self.date_label = QLabel()
        self.date_label.setStyleSheet(
            """
            color: #c8a2ff;
            font-size: 14px;
            qproperty-alignment: AlignCenter;
        """
        )
        layout.addWidget(self.time_label)
        layout.addWidget(self.date_label)
        card.setLayout(layout)
        self.update_time()
        return card

    def create_network_card(self, title, value):
        """Create a network info card."""
        card = QWidget()
        card.setStyleSheet(
            """
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 rgba(30, 15, 50, 180), stop:1 rgba(50, 25, 80, 180));
            border-radius: 8px;
            border: 1px solid rgba(139, 69, 255, 0.4);
        """
        )
        card.setFixedHeight(70)
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)
        title_label = QLabel(title)
        title_label.setStyleSheet(
            """
            color: #c8a2ff;
            font-size: 11px;
            font-weight: bold;
            letter-spacing: 0.5px;
        """
        )
        value_label = QLabel(value)
        value_label.setStyleSheet(
            """
            color: #ffd700;
            font-size: 14px;
        """
        )
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        card.setLayout(layout)
        return card

    def create_camera_widget(self):
        """Create the camera display widget."""
        widget = QWidget()
        widget.setStyleSheet(
            """
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 rgba(30, 15, 50, 180), stop:1 rgba(50, 25, 80, 180));
            border-radius: 8px;
            border: 1px solid rgba(139, 69, 255, 0.4);
        """
        )
        widget.setFixedHeight(220)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.camera_label = QLabel()
        self.camera_label.setStyleSheet(
            """
            background-color: black;
            qproperty-alignment: AlignCenter;
        """
        )
        layout.addWidget(self.camera_label)
        widget.setLayout(layout)
        return widget

    def update_time(self):
        """Update the time display."""
        now = datetime.now()
        self.time_label.setText(now.strftime("%I:%M:%S %p"))
        self.date_label.setText(now.strftime("%A, %d %B %Y"))

    def update_network_info(self):
        """Update WiFi connection information."""
        wifi_details = self.get_wifi_details() or {}
        ssid = wifi_details.get("ssid") or "Wi-Fi"
        signal_display = wifi_details.get("signal")

        status_text = ssid
        if signal_display:
            status_text = f"{ssid} - {signal_display}"

        self.network_status_widget.layout().itemAt(1).widget().setText(status_text)



    def get_wifi_details(self):
        """Retrieve Wi-Fi SSID and signal strength on supported platforms."""
        if platform.system() != "Windows":
            return None

        try:
            result = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True,
                text=True,
                check=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            return None

        ssid = None
        signal = None
        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if not line or ":" not in line:
                continue

            key, value = [part.strip() for part in line.split(":", 1)]
            key_lower = key.lower()

            if key_lower == "ssid":
                # Skip BSSID entries which also include "SSID" substring
                if "bssid" in line.lower():
                    continue
                ssid = value
            elif key_lower == "signal":
                signal = value

        if not ssid and not signal:
            return None

        return {"ssid": ssid, "signal": signal}

    def update_camera_feed(self):
        """Update the camera feed display with robust error handling."""
        if not self.camera_available:
            self.init_camera()
            if not self.camera_available:
                self.show_no_camera_message(show=True)
                return

        try:
            ret, frame = self.camera.read()
            if not ret or frame is None:
                print("⚠️ Failed to read frame from camera")
                self.camera_available = False
                if self.camera:
                    self.camera.release()
                self.show_no_camera_message(show=True)
                return

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_resized = cv2.resize(frame_rgb, (320, 240)) # Adjusted for aspect ratio
            self.display_camera_frame(frame_resized)
            self.send_frame_to_livekit(frame)

        except Exception as e:
            print(f"❌ Camera feed update error: {e}")
            self.camera_available = False
            if self.camera:
                self.camera.release()
            self.show_no_camera_message(show=True)

    def send_frame_to_livekit(self, frame):
        """Send frame to LiveKit video source."""
        current_time = time.time()
        if (current_time - self._last_frame_sent) < self._min_frame_interval:
            return
        self._last_frame_sent = current_time

        if self._video_source:
            try:
                rgba_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
                height, width, _ = rgba_frame.shape
                video_frame = rtc.VideoFrame(
                    width, height, VideoBufferType.RGBA, rgba_frame.tobytes()
                )
                self._video_source.capture_frame(video_frame)
                self._frame_counter += 1
                if self._frame_counter % 60 == 0: # Log every 60 frames
                    print(f"✅ Frame {self._frame_counter} sent to LiveKit: {width}x{height}")
            except Exception as e:
                print(f"❌ Video frame sending error: {e}")

    def display_camera_frame(self, frame):
        """Display frame in the GUI with border."""
        try:
            h, w, ch = frame.shape
            bytes_per_line = ch * w
            q_img = QImage(frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(q_img)
            
            # Create a new pixmap to draw on with rounded corners
            border_pixmap = QPixmap(pixmap.size())
            border_pixmap.fill(Qt.transparent)
            
            painter = QPainter(border_pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            
            path = QPainterPath()
            path.addRoundedRect(QRectF(border_pixmap.rect()), 8, 8)
            painter.setClipPath(path)
            
            painter.drawPixmap(0, 0, pixmap)
            
            border_pen = QPen(QColor(0, 180, 255, 150), 2)
            painter.setPen(border_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path) # Draw the rounded border
            
            painter.end()
            
            self.camera_label.setPixmap(border_pixmap)
        except Exception as e:
            print(f"❌ Display frame error: {e}")

    def show_no_camera_message(self, show=True):
        """Show or hide the 'no camera' message."""
        if not hasattr(self, "_no_camera_label"):
            self._no_camera_label = QLabel(
                "NO CAMERA DETECTED\n\n"
                "• Check connection\n"
                "• Check permissions\n"
                "• Check other apps"
            )
            self._no_camera_label.setStyleSheet(
                """
                color: #ff5555;
                font-size: 12px;
                font-weight: bold;
                background-color: black;
            """
            )
            self._no_camera_label.setAlignment(Qt.AlignCenter)
            
            if self.camera_label.layout() is None:
                layout = QVBoxLayout()
                layout.setContentsMargins(0,0,0,0)
                self.camera_label.setLayout(layout)
            
            self.camera_label.layout().addWidget(self._no_camera_label)

        self._no_camera_label.setVisible(show)


    def paintEvent(self, event):
        """Custom painting for the glassy background effect."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0, QColor(20, 10, 35, 220))
        gradient.setColorAt(0.5, QColor(35, 20, 55, 220))
        gradient.setColorAt(1, QColor(50, 30, 70, 220))
        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(QColor(139, 69, 255, 100), 1))
        painter.drawRect(self.rect())

        glow_pen = QPen(QColor(255, 215, 0, 60), 2)
        painter.setPen(glow_pen)
        painter.drawLine(0, 0, 0, self.height())

    def closeEvent(self, event):
        """Clean up camera resources."""
        if self.camera_available and self.camera:
            self.camera.release()
        super().closeEvent(event)

class SystemStatsPanel(QWidget):
    """Refined left-side panel with professional futuristic design."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(350)
        self.setStyleSheet("background-color: transparent;")
        self.power_source = "AC"
        self.battery_level = 100
        self.init_ui()
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_system_data)
        self.update_timer.start(2000)
        self.update_system_data()

    def init_ui(self):
        """Initialize the refined user interface."""
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 25, 15, 25)
        layout.setSpacing(20)
        sys_info_label = QLabel("SYSTEM STATUS")
        sys_info_label.setStyleSheet(
            """
            color: #ffd700;
            font-size: 14px;
            font-weight: bold;
            padding-bottom: 8px;
            border-bottom: 1px solid rgba(139, 69, 255, 0.3);
            letter-spacing: 1px;
        """
        )
        layout.addWidget(sys_info_label)

        # Get initial battery status
        self._update_battery_status()
        
        power_text = (
            f"Battery ({self.battery_level}%)"
            if self.power_source == "Battery"
            else "AC"
        )
        self.power_widget = self.create_stat_card(
            "POWER STATUS",
            power_text,
            self.battery_level if self.power_source == "Battery" else 100,
            "linear",
        )
        layout.addWidget(self.power_widget)

        layout.addItem(QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding))
        
        self.setLayout(layout)

    def _update_battery_status(self):
        """Update battery status from system."""
        if hasattr(psutil, "sensors_battery"):
            battery = psutil.sensors_battery()
            if battery:
                self.battery_level = int(battery.percent)
                self.power_source = "Battery" if not battery.power_plugged else "AC"
            else:
                # No battery (desktop)
                self.battery_level = 100
                self.power_source = "AC"
        else:
            # Platform doesn't support battery info
            self.battery_level = 100
            self.power_source = "AC"

    def create_stat_card(self, title, value, percentage, style):
        """Create a refined stat card with the specified style."""
        card = QWidget()
        card.setStyleSheet(
            """
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 rgba(30, 15, 50, 180), stop:1 rgba(50, 25, 80, 180));
            border-radius: 8px;
            border: 1px solid rgba(139, 69, 255, 0.4);
        """
        )
        card.setFixedHeight(90)
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        title_label = QLabel(title)
        title_label.setStyleSheet(
            """
            color: #c8a2ff;
            font-size: 11px;
            font-weight: bold;
            letter-spacing: 0.5px;
        """
        )
        value_label = QLabel(value)
        value_label.setStyleSheet(
            """
            color: #ffd700;
            font-size: 16px;
            font-weight: bold;
        """
        )
        layout.addWidget(title_label)
        layout.addWidget(value_label)

        if style == "circular":
            progress = CircularProgressBar(percentage)
        elif style == "temp":
            progress = TemperatureBar(percentage)
        else:
            progress = LinearProgressBar(percentage)
        layout.addWidget(progress)
        card.setLayout(layout)
        return card



    def update_system_data(self):
        """Update with real system data."""
        self.cpu_usage = psutil.cpu_percent()
        mem = psutil.virtual_memory()
        self.ram_usage = mem.used / (1024**3)
        
        # Power status
        self._update_battery_status()

        self.update_widgets()

    def update_widgets(self):
        """Update all widgets with current data."""
        power_text = (
            f"Battery ({self.battery_level}%)"
            if self.power_source == "Battery"
            else "AC"
        )
        self.power_widget.layout().itemAt(1).widget().setText(power_text)
        self.power_widget.layout().itemAt(2).widget().setValue(
            self.battery_level if self.power_source == "Battery" else 100
        )

    def paintEvent(self, event):
        """Custom painting for the glassy background effect."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0, QColor(20, 10, 35, 220))
        gradient.setColorAt(0.5, QColor(35, 20, 55, 220))
        gradient.setColorAt(1, QColor(50, 30, 70, 220))
        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(QColor(139, 69, 255, 100), 1))
        painter.drawRect(self.rect())

        glow_pen = QPen(QColor(255, 215, 0, 60), 2)
        painter.setPen(glow_pen)
        painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())


class CircularProgressBar(QWidget):
    """Refined circular progress bar with smooth animation."""

    def __init__(self, value=0, parent=None):
        super().__init__(parent)
        self._value = value
        self._animation_value = value
        self.setFixedSize(100, 30)
        self.setStyleSheet("background-color: transparent;")
        self.animation = QPropertyAnimation(self, b"animationValue")
        self.animation.setDuration(800)
        self.animation.setEasingCurve(QEasingCurve.OutQuad)

    def setValue(self, value):
        if value != self._value:
            self._value = value
            self.animation.stop()
            self.animation.setStartValue(self._animation_value)
            self.animation.setEndValue(value)
            self.animation.start()

    @pyqtProperty(float)
    def animationValue(self):
        return self._animation_value

    @animationValue.setter
    def animationValue(self, value):
        self._animation_value = value
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        rect = QRectF(10, 5, 80, 20)
        
        # Background arc
        pen = QPen(QColor(80, 40, 120, 150), 2)
        painter.setPen(pen)
        painter.drawArc(rect, 0, 16 * 360)

        # Foreground arc
        progress = self._animation_value / 100.0
        pen = QPen(QColor(255, 215, 0), 2)
        painter.setPen(pen)
        painter.drawArc(rect, 90 * 16, -int(progress * 360 * 16))

        # Indicator dot
        angle_rad = math.radians(90 - progress * 360)
        center_x = rect.center().x()
        center_y = rect.center().y()
        radius_x = rect.width() / 2
        radius_y = rect.height() / 2
        
        end_x = center_x + radius_x * math.cos(angle_rad)
        end_y = center_y - radius_y * math.sin(angle_rad)
        
        painter.setBrush(QBrush(QColor(255, 215, 0)))
        painter.setPen(QPen(QColor(139, 69, 255), 1))
        painter.drawEllipse(QPointF(end_x, end_y), 3, 3)


class LinearProgressBar(QWidget):
    """Refined linear progress bar with smooth animation."""

    def __init__(self, value=0, parent=None):
        super().__init__(parent)
        self._value = value
        self._animation_value = value
        self.setFixedHeight(12)
        self.setStyleSheet("background-color: transparent;")
        self.animation = QPropertyAnimation(self, b"animationValue")
        self.animation.setDuration(800)
        self.animation.setEasingCurve(QEasingCurve.OutQuad)

    def setValue(self, value):
        if value != self._value:
            self._value = value
            self.animation.stop()
            self.animation.setStartValue(self._animation_value)
            self.animation.setEndValue(value)
            self.animation.start()

    @pyqtProperty(float)
    def animationValue(self):
        return self._animation_value

    @animationValue.setter
    def animationValue(self, value):
        self._animation_value = value
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        bg_rect = QRectF(0, 4, self.width(), 4)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(80, 40, 120, 150)))
        painter.drawRoundedRect(bg_rect, 2, 2)

        progress_width = self.width() * (self._animation_value / 100.0)
        progress_rect = QRectF(0, 4, progress_width, 4)
        
        gradient = QLinearGradient(0, 0, progress_width, 0)
        gradient.setColorAt(0, QColor(139, 69, 255))
        gradient.setColorAt(1, QColor(255, 215, 0))
        painter.setBrush(QBrush(gradient))
        painter.drawRoundedRect(progress_rect, 2, 2)

        glow_rect = QRectF(0, 3, progress_width, 6)
        painter.setPen(QPen(QColor(255, 215, 0, 80), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(glow_rect, 3, 3)


class TemperatureBar(LinearProgressBar):
    """Special progress bar for temperature with color coding."""

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        bg_rect = QRectF(0, 4, self.width(), 4)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(80, 40, 120, 150)))
        painter.drawRoundedRect(bg_rect, 2, 2)

        progress_width = self.width() * min(100, self._animation_value) / 100.0
        progress_rect = QRectF(0, 4, progress_width, 4)
        
        gradient = QLinearGradient(0, 0, self.width(), 0) # Gradient over full width
        gradient.setColorAt(0.0, QColor(100, 180, 255))  # Cool
        gradient.setColorAt(0.4, QColor(139, 255, 180))  # Mild
        gradient.setColorAt(0.7, QColor(255, 215, 0))    # Warm
        gradient.setColorAt(1.0, QColor(255, 100, 50))   # Hot
        
        painter.setBrush(QBrush(gradient))
        painter.drawRoundedRect(progress_rect, 2, 2)

        glow_rect = QRectF(0, 3, progress_width, 6)
        # Determine glow color based on temperature
        temp_ratio = self._animation_value / 100.0
        glow_color = QColor(139, 69, 255, 80) # Default
        if temp_ratio > 0.7:
            glow_color = QColor(255, 100, 0, 80)
        elif temp_ratio > 0.4:
            glow_color = QColor(255, 215, 0, 90)

        painter.setPen(QPen(glow_color, 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(glow_rect, 3, 3)



class MARKInterfaceWidget(QWidget):
    """Futuristic MARK token display - four circular letter tokens with pulsing animations."""

    class Token:
        """Data class for each MARK letter token."""
        def __init__(self, letter, index):
            self.letter = letter
            self.index = index
            self.base_radius = 80
            self.current_scale = 1.0
            self.ping_scale = 0.0
            self.hover = False
            self.center = QPointF(0, 0)
            
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(800, 800)
        self.setStyleSheet("background-color: transparent;")
        self.setMouseTracking(True)

        # Create four tokens for M, A, R, K
        self.tokens = [
            self.Token('M', 0),
            self.Token('A', 1),
            self.Token('R', 2),
            self.Token('K', 3),
        ]

        # Animation state
        self.t = 0.0
        self.dt = 1 / 60.0
        
        # Mouse tracking
        self.mouse_pos = QPointF(-1000, -1000)
        
        # Font setup
        self.font = QFont("Orbitron", 48, QFont.Bold)
        # Fallback if Orbitron not available
        if QFontMetrics(self.font).horizontalAdvance("M") == 0:
            self.font = QFont("Arial", 48, QFont.Bold)

        # Animation timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(int(self.dt * 1000))

    def _tick(self):
        """Update animation state."""
        self.t += self.dt
        
        # Update each token's pulsing animation with phase offset
        for token in self.tokens:
            phase_offset = token.index * 0.5  # Offset each token
            base_pulse = math.sin(self.t * 2.0 + phase_offset) * 0.1
            
            if token.hover:
                # Stronger pulse on hover
                token.current_scale = 1.0 + base_pulse * 1.5
            else:
                # Normal gentle pulse
                token.current_scale = 1.0 + base_pulse
            
            # Decay ping animation
            if token.ping_scale > 0:
                token.ping_scale *= 0.9
                if token.ping_scale < 0.01:
                    token.ping_scale = 0.0
        
        self.update()

    def _update_token_positions(self):
        """Calculate token positions based on current widget size."""
        center_x = self.width() / 2
        center_y = self.height() / 2
        
        # Total width for all tokens with spacing
        token_spacing = 200
        total_width = (len(self.tokens) - 1) * token_spacing
        start_x = center_x - total_width / 2
        
        for i, token in enumerate(self.tokens):
            token.center = QPointF(start_x + i * token_spacing, center_y)

    def _is_point_in_token(self, point, token):
        """Check if a point is inside a token's area."""
        dist = math.hypot(
            point.x() - token.center.x(),
            point.y() - token.center.y()
        )
        return dist <= token.base_radius * 1.2

    def mouseMoveEvent(self, event):
        """Handle mouse movement for hover effects."""
        self.mouse_pos = event.pos()
        
        # Update hover state for each token
        for token in self.tokens:
            token.hover = self._is_point_in_token(self.mouse_pos, token)
        
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        """Handle mouse clicks on tokens."""
        if event.button() == Qt.LeftButton:
            for token in self.tokens:
                if self._is_point_in_token(event.pos(), token):
                    print(f"✨ Token '{token.letter}' clicked!")
                    token.ping_scale = 1.5
                    break
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        """Handle keyboard shortcuts."""
        if event.key() == Qt.Key_Space:
            # Trigger all tokens
            for token in self.tokens:
                token.ping_scale = 1.5
        super().keyPressEvent(event)

    def trigger_special_effect(self):
        """Trigger visual effect (called from external sources like TTS)."""
        for token in self.tokens:
            token.ping_scale = 2.0

    def _draw_background(self, p):
        """Draw dark gradient background."""
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0.0, QColor(5, 2, 10))      # #05020a
        gradient.setColorAt(0.5, QColor(18, 8, 33))     # #120821
        gradient.setColorAt(1.0, QColor(10, 5, 20))
        
        p.fillRect(self.rect(), gradient)

    def _draw_token(self, p, token):
        """Draw a single MARK token with outer ring, pulsing inner ring, and letter."""
        center = token.center
        base_r = token.base_radius
        
        # Calculate animated inner radius
        inner_scale = token.current_scale + token.ping_scale
        inner_r = base_r * 0.85 * inner_scale
        
        # Colors
        outer_color = QColor(139, 69, 255, 120)  # Purple
        inner_color = QColor(255, 215, 0, 180)   # Gold
        text_color = QColor(255, 255, 255, 255)  # White
        
        if token.hover:
            # Brighten on hover
            inner_color = QColor(255, 235, 50, 220)
            text_color = QColor(255, 255, 200, 255)
        
        # Draw outer circle (static)
        outer_pen = QPen(outer_color, 2)
        p.setPen(outer_pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(center, base_r, base_r)
        
        # Draw inner circle (pulsing)
        inner_pen = QPen(inner_color, 3)
        p.setPen(inner_pen)
        p.drawEllipse(center, inner_r, inner_r)
        
        # Optional: subtle glow for inner ring
        if token.hover or token.ping_scale > 0:
            glow_color = QColor(inner_color)
            glow_color.setAlpha(60)
            glow_pen = QPen(glow_color, 8)
            p.setPen(glow_pen)
            p.drawEllipse(center, inner_r, inner_r)
        
        # Draw letter
        p.setFont(self.font)
        metrics = QFontMetrics(self.font)
        text_width = metrics.horizontalAdvance(token.letter)
        text_height = metrics.height()
        
        text_pos = QPointF(
            center.x() - text_width / 2,
            center.y() + text_height / 4
        )
        
        # Text glow
        if token.hover or token.ping_scale > 0:
            p.setPen(QPen(QColor(255, 215, 0, 100), 4))
            p.drawText(text_pos, token.letter)
        
        # Solid text
        p.setPen(text_color)
        p.drawText(text_pos, token.letter)

    def paintEvent(self, event):
        """Main paint event - draws the entire widget."""
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        
        # Draw background
        self._draw_background(p)
        
        # Update token positions
        self._update_token_positions()
        
        # Draw all tokens
        for token in self.tokens:
            self._draw_token(p, token)
        
        p.end()

class MARKInterfaceWindow(QMainWindow):
    """Main window for MARK AI Interface."""

    def __init__(self):
        super().__init__()
        self.agent_process = None
        self.setWindowIcon(QIcon(resource_path("Mark_logo.png")))
        self.setWindowTitle(f"MARK AI - {VARIANT_NAME.upper()} Edition")
        self.setGeometry(100, 100, 1600, 900)
        self.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0a0510, stop:0.5 #150a20, stop:1 #0a0510);")

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        main_layout = QHBoxLayout(self.central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.left_panel = SystemStatsPanel()
        self.MARK_widget = MARKInterfaceWidget()
        self.right_panel = RightPanel()

        main_layout.addWidget(self.left_panel)
        main_layout.addWidget(self.MARK_widget, 1) # Central widget takes extra space
        main_layout.addWidget(self.right_panel)

        self.assistant = None
        self.agent_thread = None
        self.agent_loop = None
        self.agent_server = None
        self.mic_muted = False
        
        self._start_agent_background()
        self.setup_callbacks()
        self.add_mic_button()

    def set_video_track(self, video_source):
        """Set the video track for sending frames to LiveKit."""
        print(f"🎯 Setting video source in RightPanel: {video_source is not None}")
        self.right_panel.set_video_track(video_source)

    def set_assistant(self, assistant):
        """Set the assistant reference when it's ready."""
        self.assistant = assistant
        self.right_panel.assistant = assistant
        # Store the agent session for mic control
        if hasattr(assistant, '_session'):
            self.agent_session = assistant._session
        print(f"✅ Main window and right panel assistant set: {assistant is not None}")

    def setup_callbacks(self):
        """Connect TTS to trigger effects in the widget."""
        # This is a placeholder. The actual callback is passed to the agent entrypoint.
        pass

    def add_mic_button(self):
        """Add floating mic mute/unmute button."""
        self.mic_button = QPushButton()
        self.mic_button.setParent(self.central_widget)
        self.mic_button.setFixedSize(70, 70)
        self.mic_button.setCursor(Qt.PointingHandCursor)
        self.update_mic_button_style()
        self.mic_button.clicked.connect(self.toggle_mic)
        
        # Position at bottom center
        x = (self.width() - 70) // 2
        y = self.height() - 100
        self.mic_button.move(x, y)
        self.mic_button.raise_()
        self.mic_button.show()

    def update_mic_button_style(self):
        """Update mic button appearance based on mute state."""
        if self.mic_muted:
            # Muted - red theme
            self.mic_button.setStyleSheet("""
                QPushButton {
                    background: qradialgradient(cx:0.5, cy:0.5, radius:0.8,
                        fx:0.3, fy:0.3,
                        stop:0 rgba(255, 80, 80, 200),
                        stop:0.7 rgba(200, 40, 40, 180),
                        stop:1 rgba(150, 20, 20, 160));
                    border: 2px solid rgba(255, 100, 100, 200);
                    border-radius: 35px;
                    font-size: 28px;
                    color: white;
                }
                QPushButton:hover {
                    background: qradialgradient(cx:0.5, cy:0.5, radius:0.8,
                        fx:0.3, fy:0.3,
                        stop:0 rgba(255, 120, 120, 220),
                        stop:0.7 rgba(220, 60, 60, 200),
                        stop:1 rgba(170, 40, 40, 180));
                    border: 3px solid rgba(255, 150, 150, 255);
                }
                QPushButton:pressed {
                    background: qradialgradient(cx:0.5, cy:0.5, radius:0.8,
                        fx:0.3, fy:0.3,
                        stop:0 rgba(200, 50, 50, 200),
                        stop:1 rgba(120, 20, 20, 160));
                }
            """)
            self.mic_button.setText("🔇")
            self.mic_button.setToolTip("Microphone Muted - Click to Unmute")
        else:
            # Unmuted - gold/purple theme
            self.mic_button.setStyleSheet("""
                QPushButton {
                    background: qradialgradient(cx:0.5, cy:0.5, radius:0.8,
                        fx:0.3, fy:0.3,
                        stop:0 rgba(255, 215, 0, 200),
                        stop:0.7 rgba(200, 150, 255, 180),
                        stop:1 rgba(139, 69, 255, 160));
                    border: 2px solid rgba(255, 215, 0, 200);
                    border-radius: 35px;
                    font-size: 28px;
                    color: white;
                }
                QPushButton:hover {
                    background: qradialgradient(cx:0.5, cy:0.5, radius:0.8,
                        fx:0.3, fy:0.3,
                        stop:0 rgba(255, 235, 50, 220),
                        stop:0.7 rgba(220, 170, 255, 200),
                        stop:1 rgba(159, 89, 255, 180));
                    border: 3px solid rgba(255, 235, 100, 255);
                }
                QPushButton:pressed {
                    background: qradialgradient(cx:0.5, cy:0.5, radius:0.8,
                        fx:0.3, fy:0.3,
                        stop:0 rgba(200, 180, 0, 200),
                        stop:1 rgba(100, 50, 200, 160));
                }
            """)
            self.mic_button.setText("🎤")
            self.mic_button.setToolTip("Microphone Active - Click to Mute")

    def toggle_mic(self):
        """Toggle microphone mute state at Windows system level."""
        self.mic_muted = not self.mic_muted
        self.update_mic_button_style()
        
        # Trigger visual feedback
        self.MARK_widget.trigger_special_effect()
        
        # Control Windows system microphone
        if self.mic_muted:
            success = mute_system_microphone()
            if not success:
                print("⚠️ Failed to mute system microphone, reverting GUI state")
                self.mic_muted = False
                self.update_mic_button_style()
        else:
            success = unmute_system_microphone()
            if not success:
                print("⚠️ Failed to unmute system microphone, reverting GUI state")
                self.mic_muted = True
                self.update_mic_button_style()
        
        # Also try to control LiveKit microphone (if available)
        try:
            if hasattr(self, 'agent_loop') and self.agent_loop:
                asyncio.run_coroutine_threadsafe(
                    self._toggle_mic_async(),
                    self.agent_loop
                )
        except Exception as e:
            print(f"⚠️ Could not control LiveKit mic: {e}")

    async def _toggle_mic_async(self):
        """Async helper to actually mute/unmute the LiveKit microphone."""
        try:
            # Method 1: Through assistant session
            if hasattr(self, 'assistant') and self.assistant:
                if hasattr(self.assistant, '_session'):
                    session = self.assistant._session
                    if hasattr(session, '_room_input') and session._room_input:
                        mic_track = session._room_input._microphone
                        if mic_track:
                            if self.mic_muted:
                                await mic_track.mute()
                                print("🔇 Microphone MUTED - Assistant stopped listening")
                            else:
                                await mic_track.unmute()
                                print("🎤 Microphone UNMUTED - Assistant is listening")
                            return
            
            # Method 2: Direct session access
            if hasattr(self, 'agent_session') and self.agent_session:
                if hasattr(self.agent_session, '_room_input') and self.agent_session._room_input:
                    mic_track = self.agent_session._room_input._microphone
                    if mic_track:
                        if self.mic_muted:
                            await mic_track.mute()
                            print("🔇 Microphone MUTED - Assistant stopped listening")
                        else:
                            await mic_track.unmute()
                            print("🎤 Microphone UNMUTED - Assistant is listening")
                        return
            
            print(f"⚠️ Mic state changed to: {'MUTED' if self.mic_muted else 'UNMUTED'} (No audio track found yet)")
            
        except Exception as e:
            print(f"❌ Error in _toggle_mic_async: {e}")
            import traceback
            traceback.print_exc()

    def resizeEvent(self, event):
        """Reposition mic button on window resize."""
        super().resizeEvent(event)
        if hasattr(self, 'mic_button'):
            x = (self.width() - 70) // 2
            y = self.height() - 100
            self.mic_button.move(x, y)

    def get_effect_callback(self):
        """Return the effect function for external TTS use."""
        return self.MARK_widget.trigger_special_effect

    def _start_agent_background(self):
            """Start LiveKit worker (MARK_Voice_Assistant) in a separate process"""

            def run_agent():
                try:
                    print("🟡 Starting MARK LiveKit worker process...")
                    
                    # Store event loop for mic control
                    self.agent_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(self.agent_loop)

                    # Same venv ka Python use hoga
                    cmd = [
                        sys.executable,
                        "E:\\Nova\\MARK\\Mark_Voice_Assisstant\\Mark_Voice_Assistant.py",
                        "console",      # <- yeh arg LiveKit CLI ke liye hai
                    ]
                    self.agent_process = subprocess.Popen(cmd)

                    print("✅ MARK worker process started.")
                except Exception as e:
                    print(f"❌ Agent process error: {e}")
                    traceback.print_exc()

            self.agent_thread = threading.Thread(target=run_agent, daemon=True)
            self.agent_thread.start()
            print("🟡 Agent thread started")



    def closeEvent(self, event):
        print("Shutting down application...")
        self._stop_agent_background()
        super().closeEvent(event)

        if self.agent_thread and self.agent_thread.is_alive():
            self.agent_thread.join(timeout=5)


    def _stop_agent_background(self):
        """Stops the background agent process if it was started."""
        if self.agent_process:
            try:
                print("🛑 Terminating MARK worker process...")
                self.agent_process.terminate()   # send SIGTERM
                self.agent_process.wait(timeout=5)
                print("✅ Worker terminated.")
            except Exception as e:
                print(f"⚠️ Failed to terminate worker gracefully: {e}")
                self.agent_process.kill()
                print("❌ Worker force-killed.")


    def keyPressEvent(self, event):
        """Handle key press events."""
        if event.key() == Qt.Key_Escape:
            self.close()
        elif event.key() == Qt.Key_M:
            # Toggle mic with 'M' key
            self.toggle_mic()
        elif event.key() == Qt.Key_F11:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
        elif event.key() == Qt.Key_F:
            if self.windowFlags() & Qt.FramelessWindowHint:
                self.setWindowFlags(self.windowFlags() & ~Qt.FramelessWindowHint)
            else:
                self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
            self.show()
        else:
            super().keyPressEvent(event)

# --- Utility and Authentication Functions ---
# Note: These functions are kept separate for clarity but could be in their own modules.

def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller."""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)



def wait_for_internet():
    """Shows a dialog while waiting for an internet connection."""
    # This is a simplified version. A real implementation would use a QDialog.
    print("Checking for internet connection...")
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=5)
        print("✅ Internet connection available.")
        return True
    except OSError:
        print("❌ No internet connection.")
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.setText("Network Error")
        msg_box.setInformativeText("MARK requires an internet connection to start.")
        msg_box.setWindowTitle("Connection Error")
        msg_box.exec_()
        return False

def set_env_variable(key, value):
    """Set environment variable in .env file"""
    try:
        env_path = find_dotenv() or '.env'
        set_key(env_path, key, value)
        return True
    except Exception as e:
        print(f"Error setting env variable {key}: {e}")
        return False

def get_bool(value):
    """Convert value to boolean"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ('true', '1', 'yes', 'on')
    return bool(value)

def safe_message_box(title, message, msg_type='info'):
    """Safe message box that works with or without QApplication"""
    try:
        if msg_type == 'critical':
            QMessageBox.critical(None, title, message)
        elif msg_type == 'warning':
            QMessageBox.warning(None, title, message)
        elif msg_type == 'question':
            return QMessageBox.question(None, title, message, QMessageBox.Yes | QMessageBox.No)
        else:
            QMessageBox.information(None, title, message)
    except:
        # Fallback to console output
        print(f"[{title}] {message}")
        if msg_type == 'question':
            response = input("Continue? (y/n): ").lower()
            return response.startswith('y')
        return None

def prompt_access_key():
    """Prompt user for access key"""
    try:
        from PyQt5.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(None, 'Access Key Required', 'Enter your MARK access key:')
        return text.strip() if ok and text.strip() else None
    except:
        # Fallback to console input if no QApplication
        import getpass
        return input("Enter your MARK access key: ").strip()

def prompt_user_name():
    """Prompt user for their name"""
    try:
        from PyQt5.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(None, 'User Name Setup', 'What should MARK call you?\n(This will be used for personalized interactions):')
        return text.strip() if ok and text.strip() else None
    except:
        # Fallback to console input if no QApplication
        return input("What should MARK call you? ").strip()

def check_and_setup_user_name():
    """Check if user name is set, if not prompt for it"""
    current_name = os.getenv('USER_NAME', '').strip()
    
    # Remove quotes if they exist (from .env file formatting)
    if current_name.startswith('"') and current_name.endswith('"'):
        current_name = current_name[1:-1]
    elif current_name.startswith("'") and current_name.endswith("'"):
        current_name = current_name[1:-1]
    
    if not current_name:
        print("🔧 Setting up user profile...")
        user_name = prompt_user_name()
        
        if user_name:
            # Save to .env file
            set_env_variable('USER_NAME', user_name)
            # Set in runtime environment (without quotes)
            os.environ['USER_NAME'] = user_name
            print(f"✅ User name set to: {user_name}")
            return user_name
        else:
            print("⚠️ No user name provided, using default greetings")
            return None
    else:
        print(f"👤 User name already set: {current_name}")
        return current_name

def main():
    """Main entry point for the application."""
    load_dotenv()
    os.environ['IS_ACTIVATED'] = 'true'
    if not os.getenv('MARK_VARIANT'):
        os.environ['MARK_VARIANT'] = 'ultra'

    if len(sys.argv) > 1 and sys.argv[1].lower() == "console":
        agents_cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
        return

    app = QApplication(sys.argv)
    
    # Set a more modern font if available
    font = QFont("Orbitron")
    if QFontMetrics(font).horizontalAdvance("X") > 0:
        app.setFont(font)

    if not wait_for_internet():
        sys.exit(1)

    # Setup user profile if needed
    check_and_setup_user_name()

    print("🚀 Starting MARK Voice Assistant...")
    window = MARKInterfaceWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()