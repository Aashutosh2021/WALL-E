"""WALL-E fast hardware/tools layer.

ESP32 is connected to Raspberry Pi by USB.
Default serial device: /dev/serial0.

The UART connection is persistent for low latency. A background reader
prints ESP32 ACK/log lines without blocking movement commands.
"""

import os
import sys
import json
import time
import logging
import asyncio
import threading
from datetime import datetime
from urllib.parse import quote

import aiohttp

logger = logging.getLogger("WALLE")


BASE = os.path.dirname(os.path.abspath(__file__))
_ESP32_PORT = os.getenv("ESP32_PORT", os.getenv("SERIAL_PORT", "/dev/serial0"))
_ESP32_BAUD = int(os.getenv("ESP32_BAUD", os.getenv("BAUD_RATE", "9600")))

_serial_lock = threading.Lock()
_esp32_serial = None


def _get_serial():
    global _esp32_serial
    if _esp32_serial is not None and _esp32_serial.is_open:
        return _esp32_serial
    try:
        import serial
        _esp32_serial = serial.Serial(
            port=_ESP32_PORT,
            baudrate=_ESP32_BAUD,
            timeout=0.15,       # Fast 150ms read timeout (never hangs Python)
            write_timeout=0.2,
        )
        return _esp32_serial
    except Exception as e:
        logger.warning("ESP32 Serial open failed on %s: %s", _ESP32_PORT, e)
        return None


def send_esp32_command(command: str, wait_ack: bool = False) -> str:
    """Thread-safe serial sender. Eye commands use wait_ack=False for zero latency."""
    with _serial_lock:
        ser = _get_serial()
        if not ser:
            return "SERIAL_DISCONNECTED"
        try:
            ser.reset_input_buffer()  # Clear stale ACKs
            payload = f"{command.strip()}\n".encode("utf-8")
            ser.write(payload)
            ser.flush()

            if wait_ack:
                ack = ser.readline().decode("utf-8", errors="ignore").strip()
                return ack or "NO_ACK"
            return "SENT"
        except Exception as e:
            logger.warning("Serial write error (%s): %s", command, e)
            try:
                ser.close()
            except Exception:
                pass
            global _esp32_serial
            _esp32_serial = None
            return f"ERROR: {e}"


def send_uart_command(command: str) -> bool:
    """Send one newline-delimited command to ESP32 (non-blocking)."""
    res = send_esp32_command(command, wait_ack=False)
    return not res.startswith("ERROR") and res != "SERIAL_DISCONNECTED"


def close_uart():
    global _esp32_serial
    with _serial_lock:
        if _esp32_serial is not None:
            try:
                _esp32_serial.close()
            except Exception:
                pass
            _esp32_serial = None



def set_eye_emotion(emotion: str = "HAPPY") -> str:
    """Sets WALL-E eye expression on face display screen."""
    e = (emotion or "HAPPY").upper().strip()
    return send_esp32_command(e, wait_ack=False)


def move_wall_e_autonomous(
    direction: str,
    duration_ms: int = 1000,
    speed: int = 190,
    emotion: str = "HAPPY"
) -> dict:
    """
    Moves WALL-E with AI-decided duration and speed, updates eye emotion,
    and waits for movement to complete so AI can re-evaluate surroundings.
    
    direction: 'FORWARD', 'BACKWARD', 'LEFT', 'RIGHT', or 'STOP'
    duration_ms: 150 to 3500 ms (based on visual distance estimation)
    speed: 130 to 255 PWM speed
    emotion: 'HAPPY', 'SAD', 'ANGRY', 'THINK', 'IDLE'
    """
    direction = (direction or "STOP").upper().strip()
    duration_ms = max(150, min(int(duration_ms), 3500))
    speed = max(130, min(int(speed), 255))

    # 1. Set emotional eye state first (non-blocking)
    if emotion:
        send_esp32_command(emotion.upper().strip(), wait_ack=False)

    # 2. Send formatted packet DIRECTION:DURATION:SPEED to ESP32
    if direction == "STOP":
        ack = send_esp32_command("STOP", wait_ack=True)
        return {"status": "stopped", "esp32_ack": ack}

    packet = f"{direction}:{duration_ms}:{speed}"
    ack = send_esp32_command(packet, wait_ack=True)

    # 3. Wait for physical movement to finish so camera view stabilizes
    time.sleep((duration_ms / 1000.0) + 0.15)

    return {
        "status": "moved",
        "executed_packet": packet,
        "esp32_ack": ack,
        "note": "Movement completed. Check live camera feed to see new position."
    }


def _move_robot(direction: str, duration_ms: int = 1000, speed: int = 190, emotion: str = "HAPPY") -> str:
    res = move_wall_e_autonomous(direction, duration_ms, speed, emotion)
    return str(res)


    result = "WALL-E stopped." if d == "STOP" else f"WALL-E moving {d}."
    logger.info("🛠️ TOOL RESULT | move_robot | %s", result)
    return result


_http = None


async def _session():
    global _http
    if _http is None or _http.closed:
        _http = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=5)
        )
    return _http


async def _get_weather(city: str = "") -> str:
    try:
        s = await _session()
        lat = lon = None
        name, country = city or "your location", ""

        try:
            async with s.get(
                "http://ip-api.com/json/?fields=lat,lon,city,country,status"
            ) as r:
                g = await r.json(content_type=None)
                if g.get("status") == "success":
                    lat, lon = g.get("lat"), g.get("lon")
                    name = g.get("city") or name
                    country = g.get("country") or ""
        except Exception:
            pass

        if lat is None:
            q = city or "Delhi"
            async with s.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={
                    "name": q,
                    "count": 1,
                    "language": "en",
                    "format": "json",
                },
            ) as r:
                g = await r.json()

            if not g.get("results"):
                return f"Could not find city '{q}'."

            x = g["results"][0]
            lat, lon = x["latitude"], x["longitude"]
            name, country = x.get("name", q), x.get("country", "")

        async with s.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current_weather": "true",
            },
        ) as r:
            w = await r.json()

        c = w.get("current_weather", {})
        return (
            f"Weather in {name}, {country}: "
            f"{c.get('temperature', 'N/A')}°C, "
            f"Wind: {c.get('windspeed', 'N/A')} km/h."
        )

    except Exception as e:
        return f"Weather error: {e}"


async def _get_time_info() -> str:
    n = datetime.now()
    return f"Time: {n:%I:%M %p}, Date: {n:%d %B %Y} ({n:%A})."


async def _search_web(query: str) -> str:
    q = (query or "").strip()
    if not q:
        return "Search query is empty."

    try:
        s = await _session()

        async with s.get(
            "https://api.duckduckgo.com/",
            params={
                "q": q,
                "format": "json",
                "no_html": 1,
                "skip_disambig": 1,
            },
        ) as r:
            if r.status == 200:
                d = await r.json(content_type=None)
                if d.get("AbstractText"):
                    return "Search result: " + d["AbstractText"][:400]

        async with s.get(
            "https://en.wikipedia.org/api/rest_v1/page/summary/"
            + quote(q.replace(" ", "_"))
        ) as r:
            if r.status == 200:
                d = await r.json(content_type=None)
                if d.get("extract"):
                    return "Wikipedia: " + d["extract"][:400]

        return f"No summary found for '{q}'."

    except Exception as e:
        return f"Search error: {e}"


async def _remember_fact(fact: str) -> str:
    try:
        from conversation_memory import load_memory, save_memory
        mem = load_memory()
        if "facts" not in mem or not isinstance(mem["facts"], list):
            mem["facts"] = []
        mem["facts"].append({
            "fact": fact,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        save_memory(mem)
        return f"Memorized: {fact}"
    except Exception as e:
        return f"Failed to memorize: {e}"

TOOL_MAP = {
    "move_robot": move_wall_e_autonomous,
    "move_wall_e_autonomous": move_wall_e_autonomous,
    "set_eye_emotion": set_eye_emotion,
    "get_weather": _get_weather,
    "get_time_info": _get_time_info,
    "search_web": _search_web,
    "remember_fact": _remember_fact,
}
