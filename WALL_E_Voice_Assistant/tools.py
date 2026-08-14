"""
WALL-E Tools — optimized hardware interface and agent tools.

Key optimizations:
- Persistent UART connection.
- Thread-safe serial writes.
- No repeated serial.Serial() open/close per command.
- Image payloads disabled by default.
- Async tools remain compatible with Gemini tool calling.
"""

import os
import json
import time
import logging
import asyncio
import threading
import aiohttp

from datetime import datetime
from urllib.parse import quote, quote_plus

logger = logging.getLogger(__name__)

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Serial config
_SERIAL_PORT = os.getenv("SERIAL_PORT") or os.getenv("ESP32_PORT", "/dev/serial0")
_SERIAL_BAUD = int(os.getenv("BAUD_RATE", os.getenv("ESP32_BAUD", "115200")))

# UART image thumbnails are a latency hazard.
_ENABLE_ESP32_IMAGE = os.getenv("ENABLE_ESP32_IMAGE", "0").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

_serial = None
_serial_lock = threading.RLock()
_serial_unavailable_until = 0.0


def _close_serial_locked() -> None:
    global _serial
    if _serial is not None:
        try:
            _serial.close()
        except Exception:
            pass
        _serial = None


def _ensure_serial():
    """
    Returns an open serial object or None.
    Must be called while holding _serial_lock.
    """
    global _serial, _serial_unavailable_until

    if _serial is not None:
        try:
            if _serial.is_open:
                return _serial
        except Exception:
            _serial = None

    now = time.monotonic()
    if now < _serial_unavailable_until:
        return None

    try:
        import serial

        _serial = serial.Serial(
            port=_SERIAL_PORT,
            baudrate=_SERIAL_BAUD,
            timeout=0.02,
            write_timeout=0.05,
        )

        # Discard stale input.
        try:
            _serial.reset_input_buffer()
        except Exception:
            pass

        logger.info(f"UART opened: {_SERIAL_PORT} @ {_SERIAL_BAUD}")
        return _serial

    except Exception as e:
        logger.warning(f"UART unavailable: {_SERIAL_PORT} ({e})")
        _serial = None
        _serial_unavailable_until = now + 5.0
        return None


def send_uart_command(command: str) -> bool:
    """
    Fast, thread-safe UART command sender.
    Returns True if command was written to UART.
    """
    cmd = (command or "").strip()
    if not cmd:
        return False

    if not _ENABLE_ESP32_IMAGE and cmd.startswith("IMG:"):
        return False

    payload = f"{cmd}\n".encode("utf-8")

    with _serial_lock:
        ser = _ensure_serial()
        if ser is None:
            return False

        try:
            ser.write(payload)
            logger.debug(f"UART TX: {cmd}")
            return True
        except Exception as e:
            logger.error(f"UART write failed: {e}")
            _close_serial_locked()
            return False


# ---------------------------------------------------------------------------
# Agent tools
# ---------------------------------------------------------------------------

VALID_DIRECTIONS = {"FORWARD", "BACKWARD", "LEFT", "RIGHT", "STOP"}


async def _move_robot(direction: str) -> str:
    """Controls WALL-E movement via UART."""
    dir_upper = (direction or "").upper().strip()

    if dir_upper not in VALID_DIRECTIONS:
        return (
            f"Invalid direction '{direction}'. "
            "Use: FORWARD, BACKWARD, LEFT, RIGHT, STOP."
        )

    ok = await asyncio.to_thread(send_uart_command, dir_upper)

    if not ok:
        return f"UART unavailable. Could not send {dir_upper}."

    if dir_upper == "STOP":
        return "WALL-E stopped."

    return f"WALL-E moving {dir_upper}."


_http_session: aiohttp.ClientSession | None = None


async def _get_session() -> aiohttp.ClientSession:
    global _http_session

    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=5)
        )

    return _http_session


async def _get_weather(city: str = "") -> str:
    """Fetches real-time weather. Auto-detects location from public IP."""
    try:
        sess = await _get_session()

        lat = None
        lon = None
        name = city or "your location"
        country = ""

        # Try IP geolocation first.
        try:
            async with sess.get(
                "http://ip-api.com/json/?fields=lat,lon,city,country,status"
            ) as r:
                geo = await r.json()

            if geo.get("status") == "success":
                lat = geo.get("lat")
                lon = geo.get("lon")
                name = geo.get("city") or name
                country = geo.get("country") or ""
        except Exception:
            pass

        # Fallback city geocoding.
        if lat is None or lon is None:
            fallback_city = city or "Delhi"

            async with sess.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={
                    "name": fallback_city,
                    "count": 1,
                    "language": "en",
                    "format": "json",
                },
            ) as r:
                geo = await r.json()

            results = geo.get("results") or []
            if not results:
                return f"Could not detect location. City '{fallback_city}' not found."

            loc = results[0]
            lat = loc.get("latitude")
            lon = loc.get("longitude")
            name = loc.get("name") or fallback_city
            country = loc.get("country") or ""

        async with sess.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current_weather": "true",
            },
        ) as r:
            w = await r.json()

        curr = w.get("current_weather", {})

        return (
            f"Weather in {name}, {country}: "
            f"{curr.get('temperature', 'N/A')}°C, "
            f"Wind: {curr.get('windspeed', 'N/A')} km/h."
        )

    except Exception as e:
        return f"Weather error: {e}"


async def _get_time_info() -> str:
    """Returns current time and date."""
    now = datetime.now()
    return (
        f"Time: {now.strftime('%I:%M %p')}, "
        f"Date: {now.strftime('%d %B %Y')} ({now.strftime('%A')})."
    )


async def _search_web(query: str) -> str:
    """Lightweight web search via DuckDuckGo and Wikipedia."""
    try:
        sess = await _get_session()
        q = (query or "").strip()

        if not q:
            return "Search query is empty."

        async with sess.get(
            "https://api.duckduckgo.com/",
            params={
                "q": q,
                "format": "json",
                "no_html": 1,
                "skip_disambig": 1,
            },
        ) as r:
            if r.status == 200:
                data = await r.json(content_type=None)
                abstract = (data.get("AbstractText") or "").strip()
                if abstract:
                    return f"Search result: {abstract[:300]}"

        wiki_query = quote(q.replace(" ", "_"))

        async with sess.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{wiki_query}"
        ) as r:
            if r.status == 200:
                data = await r.json()
                extract = (data.get("extract") or "").strip()
                if extract:
                    return f"Wikipedia: {extract[:300]}"

        return f"No summary found for '{q}'."

    except Exception as e:
        return f"Search error: {e}"


async def _remember_fact(fact: str) -> str:
    """Saves an important fact or reminder to WALL-E's long-term memory."""
    memory_file = os.path.join(_SCRIPT_DIR, "memory.json")
    memories = []

    if os.path.exists(memory_file):
        try:
            with open(memory_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    memories = json.loads(content)
        except Exception as e:
            logger.error(f"Failed to read memory.json: {e}")

    if not isinstance(memories, list):
        memories = []

    memories.append(
        {
            "fact": fact,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )

    # Keep only latest 50 memories.
    memories = memories[-50:]

    try:
        with open(memory_file, "w", encoding="utf-8") as f:
            json.dump(memories, f, indent=2)

        logger.info(f"Memory saved: {fact}")
        return f"Memorized: {fact}"

    except Exception as e:
        logger.error(f"Failed to write memory.json: {e}")
        return f"Failed to memorize: {e}"


TOOL_MAP = {
    "move_robot": _move_robot,
    "get_weather": _get_weather,
    "get_time_info": _get_time_info,
    "search_web": _search_web,
    "remember_fact": _remember_fact,
}