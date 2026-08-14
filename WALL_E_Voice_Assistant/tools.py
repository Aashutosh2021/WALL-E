"""
WALL-E Tools — Hardware interface for ESP32 communication and Agent Tools.
"""

import os
import logging
import json
import threading
import aiohttp
from datetime import datetime

logger = logging.getLogger(__name__)

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# ESP32 Serial Communication — PERSISTENT connection
#
# WHY THIS CHANGED: the old code did `with serial.Serial(port, baud) as s:`
# INSIDE send_uart_command(), i.e. opened a brand-new serial connection on
# every single call. On the overwhelming majority of ESP32 dev boards
# (CP2102/CH340/CH9102 USB-UART bridge with auto-program circuitry), opening
# a serial port toggles DTR/RTS — which is wired straight to EN/GPIO0 on
# those boards specifically so esptool/Arduino IDE can auto-reset+flash
# without a manual boot-button press. Every eye-state change, every
# IMG_CLEAR, every IMG: thumbnail send was almost certainly rebooting the
# ESP32 (WiFi AP + web server re-init ~1-3s each). Several of those stack
# per conversational turn — that's very likely your 5-7s (plain) / 5-10s
# (vision, more UART calls in that path) lag, not network/model latency.
#
# Fix: open the port ONCE, keep it alive for the process lifetime, reuse it.
# ---------------------------------------------------------------------------
_ESP32_PORT = os.getenv("SERIAL_PORT", os.getenv("ESP32_PORT", "/dev/ttyUSB0")).strip("\"'")
_ESP32_BAUD = int(os.getenv("BAUD_RATE", "115200"))

_serial_conn = None          # persistent serial.Serial instance
_serial_lock = threading.Lock()  # send_uart_command runs off run_in_executor from multiple call sites — serialize writes


def _open_serial():
    """Opens the persistent connection once. Returns True on success."""
    global _serial_conn
    try:
        import serial
        conn = serial.Serial(_ESP32_PORT, _ESP32_BAUD, timeout=0.2, write_timeout=0.5)
        # NOTE: deliberately NOT touching conn.dtr / conn.rts here.
        # An earlier version set both False as a "defensive" measure — on
        # some boards (non-capacitor-coupled auto-reset circuits) that can
        # hold EN permanently LOW, i.e. the chip never boots at all while
        # the port stays open. Leave DTR/RTS at whatever the OS default is;
        # the fix for the original reset problem is simply not re-opening
        # the port on every call, not manipulating these lines.
        _serial_conn = conn
        logger.info(f"✅ Persistent serial connection opened on {_ESP32_PORT} @ {_ESP32_BAUD}. Motor/Eye control enabled.")
        return True
    except Exception as e:
        logger.info(f"Serial port ({_ESP32_PORT}) not available — Motor/Eye control disabled. ({e})")
        _serial_conn = None
        return False


_USB_AVAILABLE: bool = _open_serial()


def _serial_reader_loop():
    """Continuously drains ESP32's outbound Serial traffic (appendLog() prints
    + ACK_ responses — the firmware sends these on EVERY command/state change).

    WHY THIS EXISTS: nothing was ever reading this. Unread bytes back up in
    the UART TX buffer -> USB-bridge chip buffer -> Pi kernel tty buffer.
    Once that chain fills (fast — appendLog fires constantly), the ESP32's
    next Serial.println() call BLOCKS. Arduino/ESP32 loop() is single-
    threaded and cooperative, so one blocked print freezes the entire board
    — server.handleClient() stops, eye state stops updating, nothing logs.
    That's almost certainly why the web dashboard went silent.

    Side benefit: ESP32-side logs now show up in this Python process's
    logger too (prefixed "ESP32:") — free visibility into what the board
    is actually doing.
    """
    while True:
        conn = _serial_conn
        if conn is None:
            import time
            time.sleep(0.5)
            continue
        try:
            line = conn.readline()  # bounded by the 0.2s timeout set in _open_serial()
            if line:
                logger.debug(f"ESP32: {line.decode('utf-8', errors='replace').strip()}")
        except Exception:
            import time
            time.sleep(0.2)


threading.Thread(target=_serial_reader_loop, daemon=True, name="esp32-serial-reader").start()
logger.info("🧵 Serial reader thread started — draining ESP32 outbound traffic.")


def send_uart_command(command: str) -> bool:
    """Sends command string to ESP32 over the persistent serial connection.
    Thread-safe (called via run_in_executor from several places — eye state,
    IMG thumbnails, IMG_CLEAR — which can overlap)."""
    global _serial_conn, _USB_AVAILABLE

    with _serial_lock:
        if _serial_conn is None:
            # Lost connection (ESP32 power-cycled, cable unplugged, etc.) — try once to recover.
            if not _open_serial():
                return False

        try:
            _serial_conn.write(f"{command}\n".encode("utf-8"))
            _serial_conn.flush()
            logger.info(f"✅ UART Command Sent: {command}")
            return True
        except Exception as e:
            logger.error(f"❌ UART write failed, will reconnect next call: {e}")
            try:
                _serial_conn.close()
            except Exception:
                pass
            _serial_conn = None
            return False


def close_uart():
    """Call on clean shutdown to release the port."""
    global _serial_conn
    if _serial_conn is not None:
        try:
            _serial_conn.close()
        except Exception:
            pass
        _serial_conn = None


# ---------------------------------------------------------------------------
# Hardware & Software Tools
# ---------------------------------------------------------------------------
async def _move_robot(direction: str) -> str:
    """Controls WALL-E movement via UART."""
    dir_upper = direction.upper().strip()
    valid = ["FORWARD", "BACKWARD", "LEFT", "RIGHT", "STOP"]
    if dir_upper not in valid:
        return f"Invalid direction '{direction}'. Use: FORWARD, BACKWARD, LEFT, RIGHT, STOP."
    send_uart_command(dir_upper)
    return f"WALL-E moving {dir_upper}." if dir_upper != "STOP" else "WALL-E stopped."

_http_session: aiohttp.ClientSession | None = None

async def _get_session() -> aiohttp.ClientSession:
    """Reuses one aiohttp session across calls — skips repeated TLS/connect handshake."""
    global _http_session
    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession()
    return _http_session

_cached_ip_loc = None  # (lat, lon, city_name, country)

async def _get_weather(city: str = "") -> str:
    """Fetches real-time weather with cached IP auto-detection and sub-100ms Open-Meteo queries."""
    global _cached_ip_loc
    try:
        sess = await _get_session()
        lat, lon, name, country = None, None, city, ""

        # Auto-detect location if city not provided
        if not city:
            if _cached_ip_loc:
                lat, lon, name, country = _cached_ip_loc
            else:
                try:
                    async with sess.get("http://ip-api.com/json/?fields=lat,lon,city,country,status", timeout=aiohttp.ClientTimeout(total=3)) as r:
                        geo = await r.json()
                    if geo.get("status") == "success":
                        lat = geo["lat"]
                        lon = geo["lon"]
                        name = geo.get("city", "your location")
                        country = geo.get("country", "")
                        _cached_ip_loc = (lat, lon, name, country)
                except Exception:
                    pass

        # Fallback to city geocoding if location not found
        if lat is None:
            target_city = city or "Delhi"
            async with sess.get(f"https://geocoding-api.open-meteo.com/v1/search?name={target_city}&count=1&language=en&format=json", timeout=aiohttp.ClientTimeout(total=4)) as r:
                geo = await r.json()
            if not geo.get("results"):
                return f"City '{target_city}' not found."
            loc = geo["results"][0]
            lat, lon = loc["latitude"], loc["longitude"]
            name = loc.get("name", target_city)
            country = loc.get("country", "")

        # Fetch live forecast
        async with sess.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true", timeout=aiohttp.ClientTimeout(total=4)) as r:
            w = await r.json()
        curr = w.get("current_weather", {})
        temp = curr.get("temperature", "N/A")
        wind = curr.get("windspeed", "N/A")
        return f"Weather in {name}, {country}: {temp}°C, Wind: {wind} km/h."
    except Exception as e:
        return f"Weather error: {e}"

async def _get_time_info() -> str:
    """Returns current time and date."""
    now = datetime.now()
    return f"Time: {now.strftime('%I:%M %p')}, Date: {now.strftime('%d %B %Y')} ({now.strftime('%A')})."

async def _search_web(query: str) -> str:
    """Parallelized ultra-fast web search via DuckDuckGo and Wikipedia."""
    try:
        sess = await _get_session()

        async def _query_ddg():
            try:
                async with sess.get(f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1&skip_disambig=1", timeout=aiohttp.ClientTimeout(total=3)) as r:
                    if r.status == 200:
                        data = await r.json(content_type=None)
                        abstract = data.get("AbstractText", "").strip()
                        if abstract:
                            return f"Search result: {abstract[:250]}"
            except Exception:
                pass
            return None

        async def _query_wiki():
            try:
                async with sess.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{query.replace(' ','_')}", timeout=aiohttp.ClientTimeout(total=3)) as r:
                    if r.status == 200:
                        data = await r.json()
                        extract = data.get("extract", "").strip()
                        if extract:
                            return f"Wikipedia: {extract[:250]}"
            except Exception:
                pass
            return None

        # Run both searches in parallel for minimum latency
        results = await asyncio.gather(_query_ddg(), _query_wiki(), return_exceptions=True)
        for res in results:
            if isinstance(res, str) and res:
                return res

        return f"No quick summary found for '{query}'."
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
    
    new_memory = {
        "fact": fact,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    memories.append(new_memory)
    
    # Cap at 50 memories to prevent file bloat
    if len(memories) > 50:
        memories = memories[-50:]
    
    try:
        with open(memory_file, "w", encoding="utf-8") as f:
            json.dump(memories, f, indent=2)
        logger.info(f"🧠 Memory saved: {fact}")
        return f"✅ Memorized: {fact}"
    except Exception as e:
        logger.error(f"Failed to write to memory.json: {e}")
        return f"❌ Failed to memorize: {e}"

TOOL_MAP = {
    "move_robot": _move_robot,
    "get_weather": _get_weather,
    "get_time_info": _get_time_info,
    "search_web": _search_web,
    "remember_fact": _remember_fact,
}