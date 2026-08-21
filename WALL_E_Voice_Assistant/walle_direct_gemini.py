"""
WALL-E — Raspberry Pi Voice Assistant (MJ-architecture based)
- Speaker thread + bounded TTL queue (receive loop never blocks)
- Mic callback + async bounded TTL queue (stale audio drops)
- Speaker-state echo gating (queue + tail based is_active)
- Gemini Live websocket with reconnect loop
- ESP32 UART eyes + motor tools (Windows + Pi compatible)
- Vision: OLLAMA ONLY (/api/generate with persistent session)
"""

# Force IPv4 to reduce DNS/handshake latency issues.
import socket

_orig_getaddrinfo = socket.getaddrinfo


def _custom_getaddrinfo(*args, **kwargs):
    responses = _orig_getaddrinfo(*args, **kwargs)
    ipv4_responses = [r for r in responses if r[0] == socket.AF_INET]
    return ipv4_responses if ipv4_responses else responses


socket.getaddrinfo = _custom_getaddrinfo

import asyncio
import base64
import json
import logging
import os
import pathlib
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

try:
    import orjson

    dumps = lambda x: orjson.dumps(x).decode()
    loads = orjson.loads
except ImportError:
    dumps = json.dumps
    loads = json.loads

import numpy as np
import sounddevice as sd
import websockets

try:
    import aiohttp
except ImportError:
    aiohttp = None

try:
    import serial
except ImportError:
    serial = None

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# .env loader
# ---------------------------------------------------------------------------
def _load_dotenv():
    candidates = []

    try:
        base = pathlib.Path(__file__).resolve().parent
        candidates.append(pathlib.Path.cwd() / ".env")
        candidates.append(base / ".env")
        candidates.append(base.parent / ".env")
    except Exception:
        pass

    for env_path in candidates:
        try:
            if not env_path.exists():
                continue

            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue

                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")

                if key and val and os.getenv(key) is None:
                    os.environ[key] = val
        except Exception:
            pass


_load_dotenv()


def _env_bool(name, default="0"):
    return str(os.getenv(name, default)).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
API_KEY = os.getenv("GOOGLE_API_KEY", "").strip()

MODEL = os.getenv(
    "GEMINI_LIVE_MODEL",
    "models/gemini-2.5-flash-native-audio-preview-12-2025",
)

if not MODEL.startswith("models/"):
    MODEL = f"models/{MODEL}"

WS_URL = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta."
    "GenerativeService.BidiGenerateContent"
    f"?key={API_KEY}"
)

AGENT_NAME = os.getenv("ROBOT_NAME", "WALL-E").strip()
USER_NAME = os.getenv("USER_NAME", "Aashutosh").strip()

MIC_RATE = 16_000
SPK_RATE = 24_000

try:
    MIC_CHUNK_MS = float(os.getenv("MIC_CHUNK_MS", "20"))
except Exception:
    MIC_CHUNK_MS = 20.0

try:
    SPK_CHUNK_MS = float(os.getenv("SPK_CHUNK_MS", "50"))
except Exception:
    SPK_CHUNK_MS = 50.0

MIC_CHUNK = max(160, int(MIC_RATE * MIC_CHUNK_MS / 1000.0))
SPK_CHUNK = int(SPK_RATE * SPK_CHUNK_MS / 1000.0)

try:
    ECHO_TAIL_MS = int(os.getenv("ECHO_TAIL_MS", "280"))
except Exception:
    ECHO_TAIL_MS = 280

ALLOW_BARGE_IN = _env_bool("ALLOW_BARGE_IN", "0")
ENABLE_VISION = _env_bool("ENABLE_VISION", "1")
ENABLE_MEMORY = _env_bool("ENABLE_MEMORY", "0")
ENABLE_ESP32_IMAGE = _env_bool("ENABLE_ESP32_IMAGE", "0")

SERIAL_PORT = os.getenv("SERIAL_PORT", "/dev/serial0").strip()
BAUD_RATE = int(os.getenv("BAUD_RATE", "115200"))

REALTIME_INPUT_FIELD = os.getenv(
    "REALTIME_INPUT_FIELD", "mediaChunks"
).strip().lower()

VOICE_NAME = os.getenv("VOICE_NAME", "Puck").strip()
GREETING_TRIGGER = os.getenv("GREETING_TRIGGER", "").strip()

# Ollama vision (ONLY vision backend)
OLLAMA_CLOUD_URL = os.getenv(
    "OLLAMA_CLOUD_URL",
    "https://ollama.com",
).rstrip("/")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "").strip()
OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "").strip()

MEMORY_FILE = pathlib.Path(os.getenv("WALL_MEMORY_FILE", "wall_memory.json"))
MEMORY_LIMIT = int(os.getenv("MEMORY_LIMIT", "100"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)

log = logging.getLogger("WALL-E")


# ---------------------------------------------------------------------------
# Executors
# ---------------------------------------------------------------------------
uart_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="uart")
camera_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="camera")
tool_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tool")


# ---------------------------------------------------------------------------
# Queues with TTL
# ---------------------------------------------------------------------------
class BoundedTimeQueue:
    """Thread-safe bounded queue with TTL aging."""

    def __init__(self, maxsize, ttl_seconds):
        self.maxsize = maxsize
        self.ttl = ttl_seconds
        self.queue = queue.Queue(maxsize=maxsize)
        self.lock = threading.Lock()

    def put(self, item):
        with self.lock:
            if self.queue.full():
                try:
                    self.queue.get_nowait()
                except queue.Empty:
                    pass

            self.queue.put((item, time.time()))

    def get(self, timeout=0.05):
        while True:
            item_data, timestamp = self.queue.get(timeout=timeout)

            if time.time() - timestamp < self.ttl:
                return item_data

            log.warning(
                "⏱️ Speaker queue discarded stale chunk | age=%.2fs",
                time.time() - timestamp,
            )

    def empty(self):
        return self.queue.empty()

    def qsize(self):
        return self.queue.qsize()

    def flush(self):
        with self.lock:
            while not self.queue.empty():
                try:
                    self.queue.get_nowait()
                except queue.Empty:
                    break


class AsyncBoundedTimeQueue:
    """Async bounded queue with TTL aging."""

    def __init__(self, maxsize, ttl_seconds):
        self.maxsize = maxsize
        self.ttl = ttl_seconds
        self.queue = asyncio.Queue(maxsize=maxsize)

    def put_nowait(self, item):
        if self.queue.full():
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                pass

        self.queue.put_nowait((item, time.time()))

    async def get(self):
        while True:
            item_data, timestamp = await self.queue.get()

            if time.time() - timestamp < self.ttl:
                return item_data

            log.warning(
                "⏱️ Mic queue discarded stale chunk | age=%.2fs",
                time.time() - timestamp,
            )

    def get_nowait(self):
        while True:
            item_data, timestamp = self.queue.get_nowait()

            if time.time() - timestamp < self.ttl:
                return item_data

    def empty(self):
        return self.queue.empty()

    def qsize(self):
        return self.queue.qsize()

    def full(self):
        return self.queue.full()

    def clear(self):
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------
def safe_read_memory():
    if not MEMORY_FILE.exists() or MEMORY_FILE.stat().st_size == 0:
        return []

    for _ in range(3):
        try:
            content = MEMORY_FILE.read_text(encoding="utf-8").strip()
            if not content:
                return []

            data = json.loads(content)
            if isinstance(data, list):
                return data

            return []
        except Exception:
            time.sleep(0.05)

    return []


def safe_save_memory_list(history):
    try:
        MEMORY_FILE.write_text(
            json.dumps(history, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True
    except Exception:
        return False


def save_memory(user_text, assistant_text):
    if not ENABLE_MEMORY:
        return

    try:
        history = safe_read_memory()
        ts = datetime.now().isoformat()

        history.append(
            {"role": "user", "content": user_text.strip(), "timestamp": ts}
        )
        history.append(
            {"role": "assistant", "content": assistant_text.strip(), "timestamp": ts}
        )

        if len(history) > MEMORY_LIMIT:
            history = history[-MEMORY_LIMIT:]

        if safe_save_memory_list(history):
            log.debug("💾 Memory saved | %d entries", len(history))
        else:
            log.warning("⚠️ Memory save failed")
    except Exception as e:
        log.warning("⚠️ Memory save failed: %s", e)


def merge_transcripts(old_text, new_text):
    old_clean = (old_text or "").strip()
    new_clean = (new_text or "").strip()

    if not old_clean:
        return new_clean

    if not new_clean:
        return old_clean

    if new_clean.startswith(old_clean):
        return new_clean

    max_overlap = min(len(old_clean), len(new_clean))

    for i in range(max_overlap, 0, -1):
        if old_clean.endswith(new_clean[:i]):
            return old_clean + new_clean[i:]

    return old_clean + " " + new_clean


# ---------------------------------------------------------------------------
# UART / ESP32 (Windows + Pi compatible)
# ---------------------------------------------------------------------------
_ser = None
_ser_lock = threading.RLock()
_reader_thread = None
_reader_stop = None


def _open_serial_locked():
    global _ser, _reader_thread, _reader_stop

    if _ser is not None:
        try:
            if _ser.is_open:
                return _ser
        except Exception:
            _ser = None

    if serial is None:
        log.error("❌ pyserial not installed")
        return None

    try:
        # NOTE: no `exclusive` argument — win32 requires exclusive access,
        # Linux default is fine.
        _ser = serial.Serial(
            port=SERIAL_PORT,
            baudrate=BAUD_RATE,
            timeout=0.05,
            write_timeout=0.05,
        )

        # Opening serial can reset ESP32. Give it boot time.
        time.sleep(0.35)

        try:
            _ser.reset_input_buffer()
        except Exception:
            pass

        log.info(
            "🔌 ESP32 UART CONNECTED | port=%s | baud=%d",
            SERIAL_PORT,
            BAUD_RATE,
        )

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
        log.error(
            "❌ ESP32 UART OPEN FAILED | port=%s | error=%s",
            SERIAL_PORT,
            e,
        )
        _ser = None
        return None


def _serial_reader(stop_event):
    global _ser

    while not stop_event.is_set():
        try:
            ser = _ser

            if ser is None or not ser.is_open:
                stop_event.wait(0.1)
                continue

            raw = ser.readline()
            if not raw:
                continue

            text = raw.decode("utf-8", errors="replace").strip()
            if not text:
                continue

            if text.startswith("ACK_"):
                log.info("📥 ESP32 ACK | %s", text)
            else:
                log.info("📥 ESP32 LOG | %s", text)

        except Exception as e:
            if not stop_event.is_set():
                log.debug("UART reader: %s", e)

            time.sleep(0.1)


def send_uart_command(command):
    cmd = (command or "").strip()

    if not cmd:
        return False

    if cmd.startswith("IMG:") and not ENABLE_ESP32_IMAGE:
        log.debug("UART image skipped because ENABLE_ESP32_IMAGE=0")
        return False

    payload = (cmd + "\n").encode("utf-8")

    with _ser_lock:
        ser = _open_serial_locked()

        if ser is None:
            return False

        try:
            t0 = time.monotonic()
            ser.write(payload)
            ser.flush()

            elapsed = (time.monotonic() - t0) * 1000.0
            display_cmd = "IMG:<base64>" if cmd.startswith("IMG:") else cmd

            log.info("📤 ESP32 TX | %s | %.1f ms", display_cmd, elapsed)

            return True

        except Exception as e:
            log.error(
                "❌ UART WRITE FAILED | command=%s | error=%s",
                cmd,
                e,
            )

            try:
                ser.close()
            except Exception:
                pass

            _ser = None
            return False


def close_uart():
    global _ser, _reader_thread, _reader_stop

    with _ser_lock:
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


_current_eye = None


def eye(state):
    global _current_eye

    valid = {
        "BOOT",
        "IDLE",
        "LISTEN",
        "THINK",
        "SPEAK",
        "EYES_TALKING",
        "EYES_NORMAL",
        "STOP",
        "HAPPY",
        "SAD",
        "ANGRY",
    }

    if state not in valid or state == _current_eye:
        return

    _current_eye = state
    log.info("👁️ EYE | %s", state)

    try:
        uart_executor.submit(send_uart_command, state)
    except Exception as e:
        log.warning("Eye UART submit failed: %s", e)


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------
HAS_RPICAM = shutil.which("rpicam-still") is not None
HAS_LIBCAMERA = shutil.which("libcamera-still") is not None


class Camera:
    def __init__(self):
        self.cap = None

    def grab(self):
        if not ENABLE_VISION:
            return None

        t0 = time.monotonic()

        if HAS_RPICAM:
            try:
                r = subprocess.run(
                    [
                        "rpicam-still",
                        "--output", "-",
                        "--width", "320",
                        "--height", "240",
                        "--quality", "50",
                        "--nopreview",
                        "--immediate", "1",
                        "--encoding", "jpg",
                        "--timeout", "1",
                    ],
                    capture_output=True,
                    timeout=5,
                )

                if r.returncode == 0 and len(r.stdout) > 100:
                    log.info(
                        "📷 CAMERA CAPTURED | %d bytes | %.0f ms",
                        len(r.stdout),
                        (time.monotonic() - t0) * 1000.0,
                    )
                    return r.stdout

            except Exception as e:
                log.warning("rpicam-still failed: %s", e)

        if HAS_LIBCAMERA:
            try:
                r = subprocess.run(
                    [
                        "libcamera-still",
                        "--output", "-",
                        "--width", "320",
                        "--height", "240",
                        "--quality", "50",
                        "--nopreview",
                        "--immediate",
                        "--encoding", "jpg",
                        "--timeout", "1",
                    ],
                    capture_output=True,
                    timeout=5,
                )

                if r.returncode == 0 and len(r.stdout) > 100:
                    log.info(
                        "📷 CAMERA CAPTURED | %d bytes | %.0f ms",
                        len(r.stdout),
                        (time.monotonic() - t0) * 1000.0,
                    )
                    return r.stdout

            except Exception as e:
                log.warning("libcamera-still failed: %s", e)

        try:
            import cv2

            if self.cap is None or not self.cap.isOpened():
                self.cap = cv2.VideoCapture(0)
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            # Drop one buffered frame so scene is fresh.
            self.cap.grab()

            ok, frame = self.cap.read()

            if not ok:
                return None

            ok, buf = cv2.imencode(
                ".jpg",
                frame,
                [int(cv2.IMWRITE_JPEG_QUALITY), 50],
            )

            if not ok:
                return None

            jpeg = buf.tobytes()

            log.info(
                "📷 CAMERA CAPTURED | %d bytes | %.0f ms",
                len(jpeg),
                (time.monotonic() - t0) * 1000.0,
            )

            return jpeg

        except Exception as e:
            log.warning("OpenCV camera failed: %s", e)
            return None

    def close(self):
        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass


camera = Camera()


# ---------------------------------------------------------------------------
# Vision — OLLAMA ONLY
# ---------------------------------------------------------------------------
vision_session = None


async def get_vision_session():
    """Persistent aiohttp session so every see_object call does not pay a
    fresh TLS/connect handshake."""
    global vision_session

    if aiohttp is None:
        return None

    if vision_session is None or vision_session.closed:
        connector = aiohttp.TCPConnector(
            family=socket.AF_INET,
            limit=2,
            ttl_dns_cache=300,
        )

        vision_session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(
                total=25,
                connect=5,
                sock_connect=5,
                sock_read=20,
            ),
        )

    return vision_session


async def _ollama_vision_request(jpeg, prompt):
    """Analyze one fresh camera JPEG through Ollama /api/generate."""
    if not OLLAMA_VISION_MODEL:
        return "OLLAMA_VISION_MODEL is missing."

    url = OLLAMA_CLOUD_URL + "/api/generate"

    payload = {
        "model": OLLAMA_VISION_MODEL,
        "prompt": (
            "Describe what you see in 1-2 concise sentences. "
            "Focus on: "
            + (prompt or "everything important in the scene.")
        ),
        "images": [base64.b64encode(jpeg).decode("utf-8")],
        "stream": False,
    }

    headers = {"Content-Type": "application/json"}

    if OLLAMA_API_KEY:
        headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"

    s = await get_vision_session()

    if s is None:
        return "aiohttp is not installed. pip install aiohttp"

    t0 = time.monotonic()

    log.info(
        "🌐 OLLAMA VISION START | model=%s | image=%d bytes | url=%s",
        OLLAMA_VISION_MODEL,
        len(jpeg),
        url,
    )

    async with s.post(url, json=payload, headers=headers) as r:
        text = await r.text()
        elapsed = (time.monotonic() - t0) * 1000.0

        log.info(
            "🌐 OLLAMA VISION HTTP | status=%s | %.0f ms",
            r.status,
            elapsed,
        )

        if r.status != 200:
            log.error(
                "❌ OLLAMA VISION HTTP ERROR | %s | %s",
                r.status,
                text[:1000],
            )
            return f"Ollama vision error {r.status}: {text[:300]}"

    try:
        d = json.loads(text)
    except Exception:
        log.error("❌ OLLAMA VISION INVALID JSON | %s", text[:500])
        return "Ollama returned an invalid vision response."

    out = (d.get("response") or "").strip()

    if not out:
        log.error(
            "❌ OLLAMA VISION EMPTY RESPONSE | %s",
            json.dumps(d)[:1000],
        )
        return "Ollama returned no image analysis."

    log.info("🌐 OLLAMA VISION RESULT | %s", out)

    return out


async def analyze_image_async(jpeg, prompt):
    if not ENABLE_VISION:
        return "Vision is disabled."

    if not jpeg:
        return "No image captured."

    if not OLLAMA_VISION_MODEL:
        log.error("❌ OLLAMA_VISION_MODEL is missing in .env")
        return "OLLAMA_VISION_MODEL is missing."

    for attempt in (1, 2):
        try:
            return await _ollama_vision_request(jpeg, prompt)

        except asyncio.TimeoutError:
            log.warning(
                "⏱️ OLLAMA VISION TIMEOUT | attempt=%d/2 | model=%s",
                attempt,
                OLLAMA_VISION_MODEL,
            )
            if attempt == 2:
                return "Image analysis timed out. Please try again."
            await asyncio.sleep(0.15)

        except Exception as e:
            if aiohttp is not None and isinstance(e, aiohttp.ClientError):
                log.warning(
                    "🌐 OLLAMA VISION NETWORK ERROR | attempt=%d/2 | %s",
                    attempt,
                    e,
                )
            else:
                log.exception("❌ OLLAMA VISION UNEXPECTED ERROR | %s", e)

            if attempt == 2:
                return f"Image analysis failed: {e}"

            await asyncio.sleep(0.15)


# ---------------------------------------------------------------------------
# Speaker
# ---------------------------------------------------------------------------
class Speaker:
    """Plays audio chunks in a dedicated thread.
    is_active() = queue not empty OR within ECHO_TAIL_MS after last write."""

    def __init__(self):
        self._q = BoundedTimeQueue(
            maxsize=int(os.getenv("SPK_QUEUE_MAX", "160")),
            ttl_seconds=float(os.getenv("SPK_QUEUE_TTL", "5.0")),
        )

        self._stop = threading.Event()
        self._playing = threading.Event()
        self._last_wrote = 0.0
        self._lock = threading.Lock()

        self.stream = None
        self.rate = SPK_RATE
        self._need_resample = False

        threading.Thread(
            target=self._run,
            daemon=True,
            name="Speaker-Player",
        ).start()

        log.info("🔊 Speaker ON | queue TTL enabled")

    def play(self, b64):
        try:
            raw = base64.b64decode(b64)
        except Exception:
            return

        if len(raw) % 2:
            raw = raw[:-1]

        if raw:
            self._q.put(raw)

    def is_active(self):
        if self._playing.is_set() or not self._q.empty():
            return True

        with self._lock:
            tail_elapsed = time.time() - self._last_wrote

        return tail_elapsed < (ECHO_TAIL_MS / 1000.0)

    def clear(self):
        self._q.flush()
        self._playing.clear()

        with self._lock:
            self._last_wrote = 0.0

    def stop(self):
        self._stop.set()
        self.clear()

        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass

            self.stream = None

    def _open_stream(self):
        for rate in (24000, 48000):
            try:
                blocksize = int(rate * 0.05)

                stream = sd.RawOutputStream(
                    samplerate=rate,
                    channels=1,
                    dtype="int16",
                    blocksize=blocksize,
                )

                stream.start()

                self.rate = rate
                self._need_resample = rate == 48000

                log.info(
                    "🔊 Speaker stream READY | %d Hz | blocksize=%d",
                    rate,
                    blocksize,
                )

                return stream

            except Exception as e:
                log.debug("Speaker rate %d failed: %s", rate, e)

        log.warning("🔊 Speaker stream unavailable")
        return None

    def _run(self):
        self.stream = self._open_stream()

        while not self._stop.is_set():
            try:
                chunk = self._q.get(timeout=0.05)
            except queue.Empty:
                if self._playing.is_set() and (
                    time.time() - self._last_wrote > 0.40
                ):
                    self._playing.clear()

                continue
            except Exception:
                continue

            if self.stream is None:
                self.stream = self._open_stream()

                if self.stream is None:
                    time.sleep(0.2)
                    continue

            if self._need_resample:
                try:
                    chunk = np.repeat(
                        np.frombuffer(chunk, dtype=np.int16),
                        2,
                    ).tobytes()
                except Exception:
                    continue

            self._playing.set()

            with self._lock:
                self._last_wrote = time.time()

            try:
                self.stream.write(chunk)
            except Exception as e:
                log.warning("Stream write error: %s", e)

                try:
                    self.stream.stop()
                    self.stream.close()
                except Exception:
                    pass

                self.stream = None


# ---------------------------------------------------------------------------
# Microphone
# ---------------------------------------------------------------------------
class MicCapture:
    """Captures mic via sounddevice callback.
    Frames queued only when WALL-E is not speaking (echo gate)."""

    def __init__(self, loop, speaker):
        self._loop = loop
        self._speaker = speaker

        self._q = AsyncBoundedTimeQueue(
            maxsize=int(os.getenv("MIC_QUEUE_MAX", "80")),
            ttl_seconds=float(os.getenv("MIC_QUEUE_TTL", "1.5")),
        )

        self._stream = None
        self._active_rate = MIC_RATE
        self.response_in_progress = False

    @property
    def queue(self):
        return self._q

    def clear_queue(self):
        self._q.clear()

    def _safe_put(self, b64):
        try:
            self._q.put_nowait(b64)
        except Exception:
            pass

    def start(self):
        self.clear_queue()

        def _cb(indata, frames, time_info, status):
            try:
                # Echo gate: do not capture while WALL-E is speaking.
                if self._speaker.is_active() and not ALLOW_BARGE_IN:
                    return

                if indata.ndim > 1 and indata.shape[1] > 1:
                    mono = np.mean(
                        indata.astype(np.float32),
                        axis=1,
                    ).astype(np.int16)
                else:
                    mono = indata.flatten().astype(np.int16)

                if len(mono) == 0:
                    return

                if self._active_rate != MIC_RATE:
                    target_samples = int(
                        len(mono) * MIC_RATE / self._active_rate
                    )

                    if target_samples <= 0:
                        return

                    xp = np.linspace(0, len(mono) - 1, len(mono))
                    x = np.linspace(0, len(mono) - 1, target_samples)

                    mono = np.interp(x, xp, mono).astype(np.int16)

                b64 = base64.b64encode(mono.tobytes()).decode()

                self._loop.call_soon_threadsafe(self._safe_put, b64)

            except Exception:
                pass

        devices_to_try = []

        try:
            default_input = sd.default.device[0]

            if default_input is not None and default_input >= 0:
                devices_to_try.append(default_input)

            for idx, dev in enumerate(sd.query_devices()):
                if dev.get("max_input_channels", 0) > 0:
                    if idx not in devices_to_try:
                        devices_to_try.append(idx)

        except Exception:
            devices_to_try = [None]

        if not devices_to_try:
            devices_to_try = [None]

        last_error = None

        for dev_id in devices_to_try:
            native_rate = MIC_RATE
            native_channels = 1
            dev_name = "Default Device"

            try:
                if dev_id is not None:
                    info = sd.query_devices(dev_id)
                    native_rate = int(info.get("default_samplerate", MIC_RATE))
                    native_channels = int(info.get("max_input_channels", 1))
                    dev_name = info.get("name", f"Device {dev_id}")
            except Exception:
                pass

            if native_channels <= 0:
                native_channels = 1

            attempts = [
                (MIC_RATE, 1),
                (native_rate, native_channels),
            ]

            for rate, channels in attempts:
                if rate <= 0 or channels <= 0:
                    continue

                try:
                    self._active_rate = rate

                    self._stream = sd.InputStream(
                        device=dev_id,
                        samplerate=rate,
                        channels=channels,
                        dtype="int16",
                        blocksize=int(rate * MIC_CHUNK_MS / 1000.0),
                        callback=_cb,
                    )

                    self._stream.start()

                    log.info(
                        "🎙️ Mic ON | %s | %d Hz | %d ch | chunk=%.0fms",
                        dev_name,
                        rate,
                        channels,
                        MIC_CHUNK_MS,
                    )

                    return

                except Exception as ex:
                    last_error = ex
                    self._stream = None
                    continue

        log.error("❌ Microphone unavailable | %s", last_error)

    def stop(self):
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass

            self._stream = None


# ---------------------------------------------------------------------------
# WALL-E tools
# ---------------------------------------------------------------------------
VALID_DIRECTIONS = {"FORWARD", "BACKWARD", "LEFT", "RIGHT", "STOP"}


async def tool_move_robot(args):
    loop = asyncio.get_running_loop()

    d = str(args.get("direction", "STOP")).upper().strip()

    if d not in VALID_DIRECTIONS:
        return (
            f"Invalid direction '{d}'. "
            "Use FORWARD, BACKWARD, LEFT, RIGHT, STOP."
        )

    t0 = time.monotonic()

    ok = await loop.run_in_executor(
        uart_executor,
        send_uart_command,
        d,
    )

    elapsed = (time.monotonic() - t0) * 1000.0

    if ok:
        result = "WALL-E stopped." if d == "STOP" else f"WALL-E moving {d}."
    else:
        result = "ESP32 UART unavailable."

    log.info(
        "🚚 MOVE COMPLETE | %s | %.1f ms | result=%s",
        d,
        elapsed,
        result,
    )

    return result


async def tool_see_object(args):
    if not ENABLE_VISION:
        return "Vision is disabled."

    loop = asyncio.get_running_loop()

    prompt = args.get("prompt", "Describe what you see.")

    log.info("📷 SEE_OBJECT | capturing fresh frame...")

    jpeg = await loop.run_in_executor(
        camera_executor,
        camera.grab,
    )

    if not jpeg:
        return "Failed to capture a photo from WALL-E's camera."

    if ENABLE_ESP32_IMAGE:
        try:
            uart_executor.submit(
                send_uart_command,
                "IMG:" + base64.b64encode(jpeg).decode(),
            )
        except Exception as e:
            log.warning("ESP32 image thumbnail failed: %s", e)

    result = await analyze_image_async(jpeg, prompt)

    log.info("📷 SEE_OBJECT RESULT | %s", result)

    return result


def tool_get_time_info():
    n = datetime.now()
    return f"Time: {n:%I:%M %p}, Date: {n:%d %B %Y} ({n:%A})."


TOOLS = [
    {
        "functionDeclarations": [
            {
                "name": "move_robot",
                "description": (
                    "Immediately controls WALL-E movement. "
                    "Use for forward, backward, left, right, stop."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "direction": {
                            "type": "STRING",
                            "enum": [
                                "FORWARD",
                                "BACKWARD",
                                "LEFT",
                                "RIGHT",
                                "STOP",
                            ],
                        }
                    },
                    "required": ["direction"],
                },
            },
            {
                "name": "see_object",
                "description": (
                    "Captures a fresh camera frame and describes what "
                    "WALL-E sees. Use when user asks what you can see "
                    "or to look at something."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "prompt": {
                            "type": "STRING",
                            "description": "What to inspect in the image",
                        }
                    },
                },
            },
            {
                "name": "get_time_info",
                "description": "Gets current local time and date.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {},
                },
            },
        ]
    }
]


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = f"""
You are {AGENT_NAME}, a cute mini AI companion robot.
You were built by Aashutosh Sir.
The user's name is {USER_NAME}.

Rules:
- Speak naturally in Hindi/Hinglish unless the user speaks another language.
- Keep replies very short: 1-3 sentences.
- Be friendly, energetic, and helpful.
- Use move_robot tool immediately for movement commands.
- Use see_object tool when asked what you can see.
- Do not mention tools, JSON, function names, or technical internals.
- Do not output markdown.
""".strip()


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------
async def run_session():
    loop = asyncio.get_running_loop()

    speaker = Speaker()
    mic = MicCapture(loop, speaker)

    # Open UART early.
    try:
        await loop.run_in_executor(
            uart_executor,
            send_uart_command,
            "BOOT",
        )
    except Exception:
        pass

    eye("EYES_NORMAL")

    is_reconnect = False

    while True:
        audio_task = None
        send_lock = asyncio.Lock()

        st = dict(
            greeting=bool(GREETING_TRIGGER),
            user_buf="",
            asst_buf="",
        )

        async def safe_send(msg):
            try:
                async with send_lock:
                    await ws.send(msg)
            except Exception as e:
                log.warning("WS send failed: %s", e)

        async def inject(text):
            await safe_send(
                dumps(
                    {
                        "clientContent": {
                            "turns": [
                                {
                                    "role": "user",
                                    "parts": [{"text": text}],
                                }
                            ],
                            "turnComplete": True,
                        }
                    }
                )
            )

            log.info("💉 %s", text[:90])

        async def audio_sender():
            was_active = False

            while True:
                try:
                    if st["greeting"]:
                        mic.clear_queue()
                        await asyncio.sleep(0.10)
                        continue

                    active = speaker.is_active() or mic.response_in_progress

                    if active and not ALLOW_BARGE_IN:
                        if not was_active:
                            log.info("🔊 %s speaking: holding mic", AGENT_NAME)
                            was_active = True

                        mic.clear_queue()
                        await asyncio.sleep(0.05)
                        continue

                    if not active and was_active:
                        log.info("🎤 Listening for voice input...")
                        mic.clear_queue()
                        was_active = False

                    b64 = await mic.queue.get()

                    if REALTIME_INPUT_FIELD == "audio":
                        payload = {
                            "realtimeInput": {
                                "audio": {
                                    "mimeType": "audio/pcm;rate=16000",
                                    "data": b64,
                                }
                            }
                        }
                    else:
                        payload = {
                            "realtimeInput": {
                                "mediaChunks": [
                                    {
                                        "mimeType": "audio/pcm;rate=16000",
                                        "data": b64,
                                    }
                                ]
                            }
                        }

                    await safe_send(dumps(payload))

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    log.error("audio_sender error: %s", e)
                    break

        async def handle_tool_calls(tc):
            calls = tc.get("functionCalls", [])

            if not calls:
                return

            has_move = any(c.get("name") == "move_robot" for c in calls)

            if not has_move:
                eye("THINK")

            for call in calls:
                name = call.get("name", "")
                args = call.get("args") or {}
                call_id = call.get("id", "")

                log.info("🔧 Tool: %s | args=%s", name, args)

                if name == "move_robot":
                    result = await tool_move_robot(args)

                elif name == "see_object":
                    result = await tool_see_object(args)

                elif name == "get_time_info":
                    result = await loop.run_in_executor(
                        tool_executor,
                        tool_get_time_info,
                    )

                else:
                    result = f"Unknown tool '{name}'."

                log.info("✅ [%s] %s", name, result)

                await safe_send(
                    dumps(
                        {
                            "toolResponse": {
                                "functionResponses": [
                                    {
                                        "response": {"output": str(result)},
                                        "id": call_id,
                                    }
                                ]
                            }
                        }
                    )
                )

            if not speaker.is_active():
                eye("EYES_NORMAL")

        try:
            log.info("🔌 Connecting to Gemini Live...")

            async with websockets.connect(
                WS_URL,
                max_size=10_000_000,
                ping_interval=25,
                ping_timeout=20,
                open_timeout=15,
                compression=None,
            ) as ws:
                setup = {
                    "setup": {
                        "model": MODEL,
                        "generation_config": {
                            "response_modalities": ["AUDIO"],
                            "thinking_config": {"thinking_budget": 0},
                            "speech_config": {
                                "voice_config": {
                                    "prebuilt_voice_config": {
                                        "voice_name": VOICE_NAME
                                    }
                                }
                            },
                        },
                        "realtimeInputConfig": {
                            "automaticActivityDetection": {
                                "startOfSpeechSensitivity": "START_SENSITIVITY_HIGH",
                                "endOfSpeechSensitivity": "END_SENSITIVITY_HIGH",
                                "prefixPaddingMs": 80,
                                "silenceDurationMs": 280,
                            }
                        },
                        "inputAudioTranscription": {},
                        "outputAudioTranscription": {},
                        "system_instruction": {
                            "parts": [{"text": SYSTEM_PROMPT}]
                        },
                        "tools": TOOLS,
                    }
                }

                await ws.send(dumps(setup))
                log.info("📤 Setup sent")

                async for raw in ws:
                    try:
                        data = loads(raw)
                    except Exception:
                        continue

                    if "error" in data:
                        log.error(
                            "API error: %s",
                            data.get("error", {}).get("message", "?"),
                        )
                        continue

                    if "setupComplete" in data:
                        log.info("✅ Ready!")

                        speaker.clear()
                        mic.response_in_progress = False
                        mic.start()

                        audio_task = asyncio.create_task(audio_sender())

                        if GREETING_TRIGGER:
                            st["greeting"] = True
                            await inject(GREETING_TRIGGER)
                        else:
                            st["greeting"] = False
                            log.info("🎤 Bolo boss!")

                        eye("EYES_NORMAL")
                        continue

                    sc = data.get("serverContent") or {}

                    # Interruption
                    if sc.get("interrupted"):
                        log.info(
                            "⚡ [Interruption] User interrupted %s", AGENT_NAME
                        )

                        st["user_buf"] = ""
                        st["asst_buf"] = ""

                        mic.response_in_progress = False
                        speaker.clear()

                        eye("EYES_NORMAL")
                        continue

                    # User transcript
                    u = (sc.get("inputTranscription") or {}).get("text", "")

                    if u:
                        if not st["user_buf"]:
                            eye("LISTEN")

                        st["user_buf"] = merge_transcripts(st["user_buf"], u)

                        try:
                            print(
                                f"\r👤 USER: {st['user_buf'][:80]:<80}",
                                end="",
                                flush=True,
                            )
                        except Exception:
                            pass

                    # Assistant transcript
                    a = (sc.get("outputTranscription") or {}).get("text", "")

                    if a:
                        st["asst_buf"] = merge_transcripts(st["asst_buf"], a)

                    # Audio playback
                    for part in (sc.get("modelTurn") or {}).get("parts", []):
                        b64 = (part.get("inlineData") or {}).get("data", "")

                        if not b64:
                            continue

                        try:
                            audio_bytes = base64.b64decode(b64)
                        except Exception:
                            continue

                        if len(audio_bytes) >= 100:
                            mic.response_in_progress = True

                            if not speaker.is_active():
                                eye("EYES_TALKING")

                            speaker.play(b64)

                    # Turn complete
                    if sc.get("turnComplete"):
                        print()

                        mic.response_in_progress = False

                        user_text = st["user_buf"].strip()
                        ai_text = st["asst_buf"].strip()

                        if user_text:
                            log.info("🎙️ User: %s", user_text)

                        if ai_text:
                            clean_asst = re.sub(
                                r"\[TOOL:[^\]]*\]",
                                "",
                                ai_text,
                            ).strip()

                            log.info("🤖 %s: %s", AGENT_NAME, clean_asst)

                        if ENABLE_MEMORY and user_text and ai_text:
                            threading.Thread(
                                target=save_memory,
                                args=(user_text, ai_text),
                                daemon=True,
                            ).start()

                        if st["greeting"]:
                            st["greeting"] = False
                            log.info("🎤 Bolo boss!")

                        st["user_buf"] = ""
                        st["asst_buf"] = ""

                        if not speaker.is_active():
                            eye("EYES_NORMAL")

                    # Native tool calls
                    tc = data.get("toolCall")

                    if tc:
                        print()
                        await handle_tool_calls(tc)

        except websockets.exceptions.ConnectionClosed as e:
            log.warning("🔌 WS connection closed: %s", e)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.error("🔌 Session error: %s", e, exc_info=True)
        finally:
            if audio_task:
                try:
                    audio_task.cancel()
                except Exception:
                    pass

            try:
                mic.stop()
            except Exception:
                pass

            log.info("🔌 Cleanup complete.")

        log.info("🔄 Reconnecting in 3 seconds...")
        await asyncio.sleep(3)


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if not API_KEY:
        print("⚠️ GOOGLE_API_KEY set karo .env me")
        raise SystemExit(1)

    print(
        f"""
╔══════════════════════════════════════════════════════╗
║   {AGENT_NAME} — Raspberry Pi Voice Assistant          ║
║   Echo tail    : {ECHO_TAIL_MS} ms
║   Mic chunk    : {MIC_CHUNK_MS:.0f} ms
║   Speaker queue: TTL bounded
║   Vision       : Ollama ({OLLAMA_VISION_MODEL or 'NOT_SET'})
║   Memory       : {'ON' if ENABLE_MEMORY else 'OFF'}
║   Ctrl+C       : stop
╚══════════════════════════════════════════════════════╝
"""
    )

    try:
        asyncio.run(run_session())
    except KeyboardInterrupt:
        print("\n[Stop] Bye!")
    finally:
        try:
            close_uart()
        except Exception:
            pass

        try:
            camera.close()
        except Exception:
            pass