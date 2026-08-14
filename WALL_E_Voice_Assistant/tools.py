"""WALL-E fast hardware/tools layer.
USB ESP32 serial is the default because the ESP32 is connected to Raspberry Pi by USB.
"""
import os, json, time, logging, asyncio, threading
from datetime import datetime
from urllib.parse import quote
import aiohttp

logger = logging.getLogger(__name__)
BASE = os.path.dirname(os.path.abspath(__file__))
SERIAL_PORT = os.getenv("SERIAL_PORT", os.getenv("ESP32_PORT", "/dev/ttyUSB0"))
BAUD = int(os.getenv("BAUD_RATE", os.getenv("ESP32_BAUD", "115200")))
ENABLE_ESP32_IMAGE = os.getenv("ENABLE_ESP32_IMAGE", "0").lower() in {"1","true","yes","on"}

_ser = None
_lock = threading.RLock()


def _open_serial_locked():
    global _ser
    if _ser is not None:
        try:
            if _ser.is_open:
                return _ser
        except Exception:
            _ser = None
    try:
        import serial
        _ser = serial.Serial(
            SERIAL_PORT, BAUD,
            timeout=0.02,
            write_timeout=0.05,
            exclusive=False,
        )
        try:
            _ser.reset_input_buffer()
        except Exception:
            pass
        logger.info("ESP32 USB UART connected: %s @ %d", SERIAL_PORT, BAUD)
        # USB serial opening can reset many ESP32 boards. Give firmware a moment.
        time.sleep(0.25)
        return _ser
    except Exception as e:
        logger.error("ESP32 USB UART unavailable (%s): %s", SERIAL_PORT, e)
        _ser = None
        return None


def send_uart_command(command: str) -> bool:
    cmd = (command or "").strip()
    if not cmd:
        return False
    if cmd.startswith("IMG:") and not ENABLE_ESP32_IMAGE:
        return False
    payload = (cmd + "\n").encode("utf-8")
    with _lock:
        ser = _open_serial_locked()
        if ser is None:
            return False
        try:
            ser.write(payload)
            ser.flush()
            logger.debug("UART TX: %s", cmd if not cmd.startswith("IMG:") else "IMG:<data>")
            return True
        except Exception as e:
            logger.warning("UART write failed: %s", e)
            try: ser.close()
            except Exception: pass
            globals()["_ser"] = None
            return False


def close_uart():
    global _ser
    with _lock:
        if _ser is not None:
            try: _ser.close()
            except Exception: pass
            _ser = None


VALID_DIRECTIONS = {"FORWARD", "BACKWARD", "LEFT", "RIGHT", "STOP"}

async def _move_robot(direction: str) -> str:
    d = (direction or "").upper().strip()
    if d not in VALID_DIRECTIONS:
        return f"Invalid direction '{direction}'. Use FORWARD, BACKWARD, LEFT, RIGHT, STOP."
    ok = await asyncio.to_thread(send_uart_command, d)
    if not ok:
        return f"ESP32 USB UART unavailable. Could not send {d}."
    return "WALL-E stopped." if d == "STOP" else f"WALL-E moving {d}."

_http = None
async def _session():
    global _http
    if _http is None or _http.closed:
        _http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5))
    return _http

async def _get_weather(city: str = "") -> str:
    try:
        s = await _session()
        lat = lon = None
        name, country = city or "your location", ""
        try:
            async with s.get("http://ip-api.com/json/?fields=lat,lon,city,country,status") as r:
                g = await r.json(content_type=None)
                if g.get("status") == "success":
                    lat, lon = g.get("lat"), g.get("lon")
                    name, country = g.get("city") or name, g.get("country") or ""
        except Exception:
            pass
        if lat is None:
            q = city or "Delhi"
            async with s.get("https://geocoding-api.open-meteo.com/v1/search", params={"name":q,"count":1,"language":"en","format":"json"}) as r:
                g = await r.json()
            if not g.get("results"):
                return f"Could not find city '{q}'."
            x = g["results"][0]
            lat, lon = x["latitude"], x["longitude"]
            name, country = x.get("name", q), x.get("country", "")
        async with s.get("https://api.open-meteo.com/v1/forecast", params={"latitude":lat,"longitude":lon,"current_weather":"true"}) as r:
            w = await r.json()
        c = w.get("current_weather", {})
        return f"Weather in {name}, {country}: {c.get('temperature','N/A')}°C, Wind: {c.get('windspeed','N/A')} km/h."
    except Exception as e:
        return f"Weather error: {e}"

async def _get_time_info() -> str:
    n = datetime.now()
    return f"Time: {n:%I:%M %p}, Date: {n:%d %B %Y} ({n:%A})."

async def _search_web(query: str) -> str:
    q = (query or "").strip()
    if not q: return "Search query is empty."
    try:
        s = await _session()
        async with s.get("https://api.duckduckgo.com/", params={"q":q,"format":"json","no_html":1,"skip_disambig":1}) as r:
            if r.status == 200:
                d = await r.json(content_type=None)
                if d.get("AbstractText"):
                    return "Search result: " + d["AbstractText"][:400]
        async with s.get("https://en.wikipedia.org/api/rest_v1/page/summary/" + quote(q.replace(" ","_"))) as r:
            if r.status == 200:
                d = await r.json(content_type=None)
                if d.get("extract"):
                    return "Wikipedia: " + d["extract"][:400]
        return f"No summary found for '{q}'."
    except Exception as e:
        return f"Search error: {e}"

async def _remember_fact(fact: str) -> str:
    path = os.path.join(BASE, "memory.json")
    memories = []
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f: memories = json.load(f)
        if not isinstance(memories, list): memories = []
    except Exception: memories = []
    memories.append({"fact": fact, "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    try:
        with open(path, "w", encoding="utf-8") as f: json.dump(memories[-50:], f, indent=2, ensure_ascii=False)
        return f"Memorized: {fact}"
    except Exception as e:
        return f"Failed to memorize: {e}"

TOOL_MAP = {
    "move_robot": _move_robot,
    "get_weather": _get_weather,
    "get_time_info": _get_time_info,
    "search_web": _search_web,
    "remember_fact": _remember_fact,
}