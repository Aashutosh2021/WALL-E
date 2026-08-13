"""
WALL-E Tools — Hardware interface for ESP32 communication and Agent Tools.
"""

import os
import logging
import json
import aiohttp
from datetime import datetime

logger = logging.getLogger(__name__)

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# ESP32 USB Serial Communication
# ---------------------------------------------------------------------------
_ESP32_PORT = os.getenv("ESP32_PORT", "/dev/ttyUSB0")
_ESP32_BAUD = 115200

_serial_conn = None

def _probe_usb_serial() -> bool:
    """Check once at startup and KEEP THE PORT OPEN."""
    global _serial_conn
    try:
        import serial
        # Open port once globally
        _serial_conn = serial.Serial(_ESP32_PORT, _ESP32_BAUD, timeout=0)
        # Prevent ESP32 from resetting on connection
        _serial_conn.setDTR(False)
        _serial_conn.setRTS(False)
        logger.info(f"✅ USB Serial Port ({_ESP32_PORT}) opened permanently.")
        return True
    except Exception as e:
        logger.info(f"❌ USB Serial Port not available: {e}")
        return False

_USB_AVAILABLE: bool = _probe_usb_serial()

def send_uart_command(command: str) -> bool:
    """Sends command string to ESP32 over ALREADY OPEN USB serial."""
    global _serial_conn
    if not _USB_AVAILABLE or not _serial_conn:
        return False
    try:
        _serial_conn.write(f"{command}\n".encode('utf-8'))
        _serial_conn.flush() # Ensure data is pushed immediately
        logger.info(f"⚡ USB Command Sent: {command}")
        return True
    except Exception as e:
        logger.error(f"❌ USB Comm Error: {e}")
        return False


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

async def _get_weather(city: str = "Delhi") -> str:
    """Fetches real-time weather from Open-Meteo."""
    try:
        sess = await _get_session()
        async with sess.get(f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=en&format=json", timeout=aiohttp.ClientTimeout(total=5)) as r:
            geo = await r.json()
        if not geo.get("results"):
            return f"City '{city}' not found."
        loc = geo["results"][0]
        lat, lon = loc["latitude"], loc["longitude"]
        name = loc.get("name", city)
        country = loc.get("country", "")
        async with sess.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true", timeout=aiohttp.ClientTimeout(total=5)) as r:
            w = await r.json()
        curr = w.get("current_weather", {})
        return f"Weather in {name}, {country}: {curr.get('temperature','N/A')}°C, Wind: {curr.get('windspeed','N/A')} km/h."
    except Exception as e:
        return f"Weather error: {e}"

async def _get_time_info() -> str:
    """Returns current time and date."""
    now = datetime.now()
    return f"Time: {now.strftime('%I:%M %p')}, Date: {now.strftime('%d %B %Y')} ({now.strftime('%A')})."

async def _search_web(query: str) -> str:
    """Lightweight web search via DuckDuckGo / Wikipedia."""
    try:
        sess = await _get_session()
        async with sess.get(f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1&skip_disambig=1", timeout=aiohttp.ClientTimeout(total=5)) as r:
            if r.status == 200:
                data = await r.json(content_type=None)
                abstract = data.get("AbstractText", "").strip()
                if abstract:
                    return f"Search result: {abstract[:300]}"
        async with sess.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{query.replace(' ','_')}", timeout=aiohttp.ClientTimeout(total=5)) as r:
            if r.status == 200:
                data = await r.json()
                extract = data.get("extract", "").strip()
                if extract:
                    return f"Wikipedia: {extract[:300]}"
        return f"No summary found for '{query}'."
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
