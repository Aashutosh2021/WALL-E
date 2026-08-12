"""
WALL-E Tools — Hardware interface for ESP32 communication.
Only send_uart_command is used by walle_direct_gemini.py.
All tool functions (move, weather, search, etc.) live in walle_direct_gemini.py.
"""

import os
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ESP32 USB Serial Communication
# ---------------------------------------------------------------------------
_ESP32_PORT = os.getenv("ESP32_PORT", "/dev/ttyUSB0")
_ESP32_BAUD = 115200

def _probe_usb_serial() -> bool:
    """Check once at startup if ESP32 USB serial port is accessible."""
    try:
        import serial
        with serial.Serial(_ESP32_PORT, _ESP32_BAUD, timeout=0.5):
            pass
        logger.info(f"USB Serial Port ({_ESP32_PORT}) detected. Motor/Eye control enabled.")
        return True
    except Exception:
        logger.info(f"USB Serial Port ({_ESP32_PORT}) not available. Motor/Eye control disabled.")
        return False

_USB_AVAILABLE: bool = _probe_usb_serial()


def send_uart_command(command: str) -> bool:
    """Sends command string to ESP32 over USB serial."""
    if not _USB_AVAILABLE:
        return False
    try:
        import serial
        with serial.Serial(_ESP32_PORT, _ESP32_BAUD, timeout=0.1) as s:
            s.write(f"{command}\n".encode('utf-8'))
            logger.info(f"✅ USB Command Sent to ESP32: {command}")
        return True
    except Exception as e:
        logger.error(f"❌ USB Communication Error: {e}")
        return False
