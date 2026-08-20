"""WALL-E fast hardware/tools layer.

ESP32 is connected to Raspberry Pi by USB.
Default serial device: /dev/serial0.

The UART connection is persistent for low latency. A background reader
prints ESP32 ACK/log lines without blocking movement commands.
"""

import os
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
SERIAL_PORT = os.getenv("SERIAL_PORT", os.getenv("ESP32_PORT", "/dev/serial0"))
BAUD = int(os.getenv("BAUD_RATE", os.getenv("ESP32_BAUD", "115200")))
ENABLE_ESP32_IMAGE = os.getenv("ENABLE_ESP32_IMAGE", "0").lower() in {
    "1", "true", "yes", "on"
}

_ser = None
_lock = threading.RLock()
_reader_thread = None
_reader_stop = None


def _open_serial_locked():
    """Open the USB serial port once and keep it open."""
    global _ser, _reader_thread, _reader_stop

    if _ser is not None:
        try:
            if _ser.is_open:
                return _ser
        except Exception:
            _ser = None

    try:
        import serial

        _ser = serial.Serial(
            port=SERIAL_PORT,
            baudrate=BAUD,
            timeout=0.05,
            write_timeout=0.05,
            exclusive=False,
        )

        # Opening USB serial can reset ESP32. Give firmware time to boot.
        time.sleep(0.35)

        try:
            _ser.reset_input_buffer()
        except Exception:
            pass

        logger.info("🔌 ESP32 UART CONNECTED | port=%s | baud=%d", SERIAL_PORT, BAUD)

        # Start ACK/log reader once.
        if _reader_thread is None or not _reader_thread.is_alive():
            _reader_stop = threading.Event()
            _reader_thread = threading.Thread(
                target=_serial_reader,
                args=(_reader_stop,),
                daemon=True,
                name="ESP32-UART-Reader",
            )
            _reader_thread.start()

        return _ser

    except Exception as e:
        logger.error("❌ ESP32 UART OPEN FAILED | port=%s | error=%s", SERIAL_PORT, e)
        _ser = None
        return None


def _serial_reader(stop_event):
    """Read ESP32 ACK/debug lines asynchronously so motor commands stay fast."""
    global _ser

    while not stop_event.is_set():
        try:
            ser = _ser
            if ser is None or not ser.is_open:
                time.sleep(0.1)
                continue

            raw = ser.readline()
            if not raw:
                continue

            text = raw.decode("utf-8", errors="replace").strip()
            if text:
                # ESP32 firmware sends ACK_<command> and may also send debug text.
                if text.startswith("ACK_"):
                    logger.info("📥 ESP32 ACK | %s", text)
                else:
                    logger.info("📥 ESP32 LOG | %s", text)

        except Exception as e:
            if not stop_event.is_set():
                logger.debug("UART reader: %s", e)
            time.sleep(0.1)


def send_uart_command(command: str) -> bool:
    """Send one newline-delimited command to ESP32."""
    cmd = (command or "").strip()
    if not cmd:
        return False

    if cmd.startswith("IMG:") and not ENABLE_ESP32_IMAGE:
        logger.debug("UART image skipped because ENABLE_ESP32_IMAGE=0")
        return False

    payload = (cmd + "\n").encode("utf-8")

    with _lock:
        ser = _open_serial_locked()
        if ser is None:
            return False

        try:
            t0 = time.monotonic()
            ser.write(payload)
            ser.flush()
            elapsed = (time.monotonic() - t0) * 1000

            display_cmd = "IMG:<base64>" if cmd.startswith("IMG:") else cmd
            logger.info("📤 ESP32 TX | %s | %.1f ms", display_cmd, elapsed)
            return True

        except Exception as e:
            logger.error("❌ UART WRITE FAILED | command=%s | error=%s", cmd, e)
            try:
                ser.close()
            except Exception:
                pass
            _ser = None
            return False


def close_uart():
    global _ser, _reader_thread, _reader_stop

    with _lock:
        if _reader_stop is not None:
            _reader_stop.set()

        if _ser is not None:
            try:
                _ser.close()
            except Exception:
                pass

        _ser = None
        _reader_thread = None
        _reader_stop = None


VALID_DIRECTIONS = {"FORWARD", "BACKWARD", "LEFT", "RIGHT", "STOP"}


async def _move_robot(direction: str) -> str:
    d = (direction or "").upper().strip()

    if d not in VALID_DIRECTIONS:
        return (
            f"Invalid direction '{direction}'. "
            "Use FORWARD, BACKWARD, LEFT, RIGHT, STOP."
        )

    ok = await asyncio.to_thread(send_uart_command, d)

    if not ok:
        result = f"ESP32 USB UART unavailable. Could not send {d}."
        logger.error("🛠️ TOOL RESULT | move_robot | %s", result)
        return result

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


def _remember_fact_sync(fact: str) -> str:
    path = os.path.join(BASE, "memory.json")
    memories = []

    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                memories = json.load(f)

        if not isinstance(memories, list):
            memories = []

    except Exception:
        memories = []

    memories.append({
        "fact": fact,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                memories[-50:],
                f,
                indent=2,
                ensure_ascii=False,
            )

        return f"Memorized: {fact}"

    except Exception as e:
        return f"Failed to memorize: {e}"


async def _remember_fact(fact: str) -> str:
    # This function is a coroutine, and the tool dispatcher awaits
    # coroutines directly (assuming they don't block). The file I/O below
    # is synchronous disk access — on Pi's SD card this can stall for real
    # time under contention, blocking the ENTIRE asyncio event loop
    # (mic reads, audio playback, everything) for that duration. Push it
    # to a worker thread instead.
    return await asyncio.to_thread(_remember_fact_sync, fact)


TOOL_MAP = {
    "move_robot": _move_robot,
    "get_weather": _get_weather,
    "get_time_info": _get_time_info,
    "search_web": _search_web,
    "remember_fact": _remember_fact,
}
