"""
WALL-E — Gemini Live realtime voice assistant.

Architecture:
- Speaker thread + bounded TTL queue  -> receive loop never blocks on audio.
- Mic callback + async bounded TTL queue -> stale audio drops, no backlog.
- Speaker-state echo gating (queue + tail based is_active).
- Gemini Live websocket with auto-reconnect loop.
- ESP32 UART eyes + motor via tools.py  (canonical fixed UART layer).
- Vision: Ollama /api/generate (persistent aiohttp session).
- Memory: conversation_memory.py (SQLite/WAL).
- Prompt: prompts.AGENT_INSTRUCTION.
"""

# Force IPv4 to avoid IPv6 handshake timeouts on some networks.
import socket

_orig_getaddrinfo = socket.getaddrinfo


def _custom_getaddrinfo(*args, **kwargs):
    responses = _orig_getaddrinfo(*args, **kwargs)
    ipv4 = [r for r in responses if r[0] == socket.AF_INET]
    return ipv4 if ipv4 else responses


socket.getaddrinfo = _custom_getaddrinfo

import os
import re
import sys
import json
import time
import queue
import base64
import shutil
import logging
import asyncio
import inspect
import threading
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import numpy as np
import sounddevice as sd
import websockets
import aiohttp

try:
    import orjson

    dumps = lambda x: orjson.dumps(x).decode()
    loads = orjson.loads
except ImportError:
    dumps = json.dumps
    loads = json.loads

# Load .env BEFORE importing project modules (tools.py reads env at import).
from dotenv import load_dotenv

load_dotenv(override=True)

# Project modules.
from prompts import AGENT_INSTRUCTION
from tools import send_uart_command, TOOL_MAP, close_uart
from conversation_memory import (
    init_db,
    save_message,
    format_recent_context,
)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def _env_bool(name, default="0"):
    return str(os.getenv(name, default)).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger("WALL-E")

BASE = os.path.dirname(os.path.abspath(__file__))

# Persistent conversation DB.
init_db()


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
ENABLE_ESP32_IMAGE = _env_bool("ENABLE_ESP32_IMAGE", "0")
ENABLE_GREETING = _env_bool("ENABLE_GREETING", "1")

VOICE_NAME = os.getenv("VOICE_NAME", "Puck").strip()

MEMORY_TURNS = int(os.getenv("MEMORY_TURNS", "30"))
SESSION_ID = os.getenv("WALLE_SESSION_ID", "") or time.strftime("%Y%m%d-%H%M%S")

# Ollama vision (ONLY vision backend).
OLLAMA_CLOUD_URL = os.getenv("OLLAMA_CLOUD_URL", "https://ollama.com").rstrip("/")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "").strip()
OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "").strip()


# ---------------------------------------------------------------------------
# Executors
# ---------------------------------------------------------------------------
uart_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="uart")
camera_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="camera")
tool_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tool")


# ---------------------------------------------------------------------------
# Runtime state
# ---------------------------------------------------------------------------
is_ai_speaking = False
_current_eye = None

_user_transcript_parts = []
_ai_transcript_parts = []

_image_analysis_active = False
_image_analysis_completed = False


def _stamp():
    return time.strftime("%H:%M:%S.") + f"{int((time.time() % 1) * 1000):03d}"


def log_user(text):
    text = (text or "").strip()
    if text:
        logger.info("👤 USER [%s] | %s", _stamp(), text)


def log_ai(text):
    text = (text or "").strip()
    if text:
        logger.info("🤖 AI [%s] | %s", _stamp(), text)


def log_tool(name, args):
    logger.info("🛠️ TOOL CALL [%s] | %s | args=%s", _stamp(), name, args)


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
# OLED eyes (via tools.py UART layer)
# ---------------------------------------------------------------------------
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
        "HAPPY",
        "SAD",
        "ANGRY",
    }

    if state not in valid or state == _current_eye:
        return

    _current_eye = state
    logger.info("👁️ EYE | %s", state)

    try:
        uart_executor.submit(send_uart_command, state)
    except Exception as e:
        logger.warning("Eye UART submit failed: %s", e)


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------
try:
    from picamera2 import Picamera2

    HAS_PICAM2 = True
except ImportError:
    Picamera2 = None
    HAS_PICAM2 = False

HAS_RPICAM = shutil.which("rpicam-still") is not None
HAS_LIBCAMERA = shutil.which("libcamera-still") is not None


class Camera:
    def __init__(self):
        self.picam = None
        self.cap = None

        if HAS_PICAM2:
            try:
                self.picam = Picamera2()
                cfg = self.picam.create_still_configuration(
                    main={"size": (320, 240), "format": "RGB888"}
                )
                self.picam.configure(cfg)
                self.picam.start()
                time.sleep(0.15)
                logger.info("📷 Camera READY | persistent picamera2 | 320x240")
            except Exception as e:
                logger.warning("picamera2 unavailable: %s", e)
                self.picam = None

        if self.picam is None:
            logger.info(
                "📷 Camera fallback | %s",
                "rpicam-still"
                if HAS_RPICAM
                else "libcamera-still"
                if HAS_LIBCAMERA
                else "OpenCV",
            )

    def grab(self):
        """Capture a fresh frame, dropping buffered frames first."""
        t0 = time.monotonic()

        try:
            import cv2

            if self.picam is not None:
                self.picam.capture_array("main")
                self.picam.capture_array("main")
                frame = self.picam.capture_array("main")

                ok, buf = cv2.imencode(
                    ".jpg",
                    frame,
                    [int(cv2.IMWRITE_JPEG_QUALITY), 50],
                )
                if not ok:
                    return None

                jpeg = buf.tobytes()
                logger.info(
                    "📷 CAMERA CAPTURED | %d bytes | %.0f ms",
                    len(jpeg),
                    (time.monotonic() - t0) * 1000.0,
                )
                return jpeg

            if HAS_RPICAM:
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
                    logger.info(
                        "📷 CAMERA CAPTURED | %d bytes | %.0f ms",
                        len(r.stdout),
                        (time.monotonic() - t0) * 1000.0,
                    )
                    return r.stdout
                return None

            if HAS_LIBCAMERA:
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
                    logger.info(
                        "📷 CAMERA CAPTURED | %d bytes | %.0f ms",
                        len(r.stdout),
                        (time.monotonic() - t0) * 1000.0,
                    )
                    return r.stdout
                return None

            if self.cap is None or not self.cap.isOpened():
                self.cap = cv2.VideoCapture(0)
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            self.cap.grab()
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
            logger.info(
                "📷 CAMERA CAPTURED | %d bytes | %.0f ms",
                len(jpeg),
                (time.monotonic() - t0) * 1000.0,
            )
            return jpeg

        except Exception as e:
            logger.exception("❌ CAMERA CAPTURE FAILED | %s", e)
            return None

    def close(self):
        if self.picam:
            try:
                self.picam.stop()
                self.picam.close()
            except Exception:
                pass

        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass


camera = Camera()


# ---------------------------------------------------------------------------
# Bounded TTL queues
# ---------------------------------------------------------------------------
class BoundedTimeQueue:
    """Thread-safe bounded queue with TTL aging (drop-oldest on overload)."""

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
            logger.warning(
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
    """Async bounded queue with TTL aging (drop-oldest on overload)."""

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
            logger.warning(
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
# Speaker (dedicated playback thread; never blocks receive loop)
# ---------------------------------------------------------------------------
class Speaker:
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

        logger.info("🔊 Speaker ON | queue TTL enabled")

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
                logger.info(
                    "🔊 Speaker stream READY | %d Hz | blocksize=%d",
                    rate,
                    blocksize,
                )
                return stream
            except Exception as e:
                logger.debug("Speaker rate %d failed: %s", rate, e)

        logger.warning("🔊 Speaker stream unavailable")
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
                logger.warning("Stream write error: %s", e)
                try:
                    self.stream.stop()
                    self.stream.close()
                except Exception:
                    pass
                self.stream = None


# ---------------------------------------------------------------------------
# Microphone (callback capture; echo gated by speaker state)
# ---------------------------------------------------------------------------
class MicCapture:
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
                    logger.info(
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

        logger.error("❌ Microphone unavailable | %s", last_error)

    def stop(self):
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None


# ---------------------------------------------------------------------------
# Ollama vision
# ---------------------------------------------------------------------------
vision_session = None


async def get_vision_session():
    global vision_session

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
    global _image_analysis_completed

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
    t0 = time.monotonic()

    logger.info(
        "🌐 OLLAMA VISION START | model=%s | image=%d bytes",
        OLLAMA_VISION_MODEL,
        len(jpeg),
    )

    async with s.post(url, json=payload, headers=headers) as r:
        text = await r.text()
        elapsed = (time.monotonic() - t0) * 1000.0

        logger.info(
            "🌐 OLLAMA VISION HTTP | status=%s | %.0f ms",
            r.status,
            elapsed,
        )

        if r.status != 200:
            logger.error(
                "❌ OLLAMA VISION HTTP ERROR | %s | %s",
                r.status,
                text[:1000],
            )
            return f"Ollama vision error {r.status}: {text[:300]}"

    try:
        d = json.loads(text)
    except Exception:
        logger.error("❌ OLLAMA VISION INVALID JSON | %s", text[:500])
        return "Ollama returned an invalid vision response."

    out = (d.get("response") or "").strip()

    if not out:
        logger.error(
            "❌ OLLAMA VISION EMPTY RESPONSE | %s",
            json.dumps(d)[:1000],
        )
        return "Ollama returned no image analysis."

    logger.info("🌐 OLLAMA VISION RESULT | %s", out)

    _image_analysis_completed = True
    return out


async def analyze_image(jpeg, prompt):
    if not ENABLE_VISION:
        return "Vision is disabled."

    if not jpeg:
        return "No image captured."

    if not OLLAMA_VISION_MODEL:
        logger.error("❌ OLLAMA_VISION_MODEL is missing in .env")
        return "OLLAMA_VISION_MODEL is missing."

    for attempt in (1, 2):
        try:
            return await _ollama_vision_request(jpeg, prompt)

        except asyncio.TimeoutError:
            logger.warning(
                "⏱️ OLLAMA VISION TIMEOUT | attempt=%d/2 | model=%s",
                attempt,
                OLLAMA_VISION_MODEL,
            )
            if attempt == 2:
                return "Image analysis timed out. Please try again."
            await asyncio.sleep(0.15)

        except aiohttp.ClientError as e:
            logger.warning(
                "🌐 OLLAMA VISION NETWORK ERROR | attempt=%d/2 | %s",
                attempt,
                e,
            )
            if attempt == 2:
                return "Image analysis failed (Ollama network error)."
            await asyncio.sleep(0.15)

        except Exception as e:
            logger.exception("❌ OLLAMA VISION UNEXPECTED ERROR | %s", e)
            return f"Image analysis failed: {e}"


# ---------------------------------------------------------------------------
# Tool response helper
# ---------------------------------------------------------------------------
async def send_tool_response(ws, call_id, output):
    await ws.send(
        dumps(
            {
                "toolResponse": {
                    "functionResponses": [
                        {
                            "response": {"output": str(output)},
                            "id": call_id,
                        }
                    ]
                }
            }
        )
    )


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------
async def handle_see_object(args):
    global _image_analysis_active

    _image_analysis_active = True
    loop = asyncio.get_running_loop()

    logger.info("📷 SEE_OBJECT | capturing fresh frame...")

    jpeg = await loop.run_in_executor(camera_executor, camera.grab)

    if not jpeg:
        result = "Failed to capture a photo from WALL-E's camera."
        logger.error("🛠️ TOOL RESULT | see_object | %s", result)
        return result

    if ENABLE_ESP32_IMAGE:
        try:
            await loop.run_in_executor(
                uart_executor,
                send_uart_command,
                "IMG:" + base64.b64encode(jpeg).decode(),
            )
        except Exception as e:
            logger.warning("ESP32 image thumbnail failed: %s", e)

    result = await analyze_image(
        jpeg,
        args.get("prompt", "Describe what you see."),
    )

    logger.info("🛠️ TOOL RESULT | see_object | %s", result)

    try:
        await asyncio.to_thread(
            save_message,
            "tool",
            str(result),
            SESSION_ID,
            "see_object",
            json.dumps(args, ensure_ascii=False),
            str(result),
        )
    except Exception as e:
        logger.warning("💾 MEMORY SAVE VISION FAILED | %s", e)

    return result


async def run_tool(name, args):
    log_tool(name, args)

    if name == "see_object":
        return await handle_see_object(args)

    func = TOOL_MAP.get(name)

    if not func:
        result = f"Unknown tool '{name}'"
        logger.error("🛠️ TOOL RESULT | %s | %s", name, result)
        return result

    try:
        if inspect.iscoroutinefunction(func):
            result = await func(**args)
        else:
            result = await asyncio.to_thread(func, **args)

        logger.info("🛠️ TOOL RESULT | %s | %s", name, result)

        try:
            await asyncio.to_thread(
                save_message,
                "tool",
                str(result),
                SESSION_ID,
                name,
                json.dumps(args, ensure_ascii=False),
                str(result),
            )
        except Exception as e:
            logger.warning("💾 MEMORY SAVE TOOL FAILED | %s", e)

        return result

    except Exception as e:
        logger.exception("❌ TOOL ERROR | %s | %s", name, e)
        return f"Error executing tool: {e}"


async def handle_move(loop, args):
    """Fast path for movement: straight to UART via tools.py."""
    d = str(args.get("direction", "STOP")).upper().strip()

    if d not in {"FORWARD", "BACKWARD", "LEFT", "RIGHT", "STOP"}:
        return f"Invalid direction '{d}'."

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

    logger.info(
        "🚚 MOVE COMPLETE | %s | %.1f ms | result=%s",
        d,
        elapsed,
        result,
    )

    try:
        await asyncio.to_thread(
            save_message,
            "tool",
            str(result),
            SESSION_ID,
            "move_robot",
            json.dumps(args, ensure_ascii=False),
            str(result),
        )
    except Exception as e:
        logger.warning("💾 MEMORY SAVE MOVE FAILED | %s", e)

    return result


# ---------------------------------------------------------------------------
# Function declarations for Gemini
# ---------------------------------------------------------------------------
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
                    "WALL-E sees. Use when user asks what you can see."
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
                "name": "get_weather",
                "description": "Gets current weather.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {"city": {"type": "STRING"}},
                },
            },
            {
                "name": "get_time_info",
                "description": "Gets current local time and date.",
                "parameters": {"type": "OBJECT", "properties": {}},
            },
            {
                "name": "search_web",
                "description": "Searches the web for a factual query.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {"query": {"type": "STRING"}},
                    "required": ["query"],
                },
            },
            {
                "name": "remember_fact",
                "description": "Stores an important fact in long-term memory.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {"fact": {"type": "STRING"}},
                    "required": ["fact"],
                },
            },
        ]
    }
]


# ---------------------------------------------------------------------------
# Instruction (prompt + memory context)
# ---------------------------------------------------------------------------
def build_instruction():
    memory_text = ""

    # remember_fact writes to memory.json via tools._remember_fact.
    memory_json = os.path.join(BASE, "memory.json")
    try:
        if os.path.exists(memory_json):
            with open(memory_json, encoding="utf-8") as f:
                m = json.load(f)
            if isinstance(m, list):
                facts = [
                    f"- {x.get('fact') or x.get('content')}"
                    for x in m[-20:]
                    if isinstance(x, dict)
                    and (x.get("fact") or x.get("content"))
                ]
                if facts:
                    memory_text += "\n\nPAST MEMORIES:\n" + "\n".join(facts)
    except Exception:
        pass

    recent = format_recent_context(limit=MEMORY_TURNS, session_id=None)
    if recent:
        memory_text += "\n\n" + recent

    return AGENT_INSTRUCTION + memory_text


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------
async def run_session():
    global is_ai_speaking
    global _image_analysis_active, _image_analysis_completed

    if not API_KEY:
        logger.error("❌ GOOGLE_API_KEY missing in .env")
        return

    loop = asyncio.get_running_loop()

    speaker = Speaker()
    mic = MicCapture(loop, speaker)

    instruction = build_instruction()

    setup = {
        "setup": {
            "model": MODEL,
            "inputAudioTranscription": {},
            "outputAudioTranscription": {},
            "generation_config": {
                "response_modalities": ["AUDIO"],
                "thinking_config": {"thinking_budget": 0},
                "speech_config": {
                    "voice_config": {
                        "prebuilt_voice_config": {"voice_name": VOICE_NAME}
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
            "system_instruction": {"parts": [{"text": instruction}]},
            "tools": TOOLS,
        }
    }

    # Open UART early so first command is fast.
    try:
        await loop.run_in_executor(uart_executor, send_uart_command, "BOOT")
    except Exception:
        pass

    eye("EYES_NORMAL")

    is_reconnect = False

    while True:
        audio_task = None
        send_lock = asyncio.Lock()

        st = dict(
            user_buf="",
            asst_buf="",
            greeted=not ENABLE_GREETING,
        )

        async def safe_send(msg):
            try:
                async with send_lock:
                    await ws.send(msg)
            except Exception as e:
                logger.warning("WS send failed: %s", e)

        async def inject(text):
            await safe_send(
                dumps(
                    {
                        "clientContent": {
                            "turns": [
                                {"role": "user", "parts": [{"text": text}]}
                            ],
                            "turnComplete": True,
                        }
                    }
                )
            )
            logger.info("💉 %s", text[:90])

        async def audio_sender():
            was_active = False

            while True:
                try:
                    active = speaker.is_active() or mic.response_in_progress

                    if active and not ALLOW_BARGE_IN:
                        if not was_active:
                            logger.info("🔊 %s speaking: holding mic", AGENT_NAME)
                            was_active = True
                        mic.clear_queue()
                        await asyncio.sleep(0.05)
                        continue

                    if not active and was_active:
                        logger.info("🎤 Listening for voice input...")
                        mic.clear_queue()
                        was_active = False

                    b64 = await mic.queue.get()

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
                    logger.error("audio_sender error: %s", e)
                    break

        try:
            logger.info("🔌 Connecting to Gemini Live...")

            async with websockets.connect(
                WS_URL,
                max_size=10_000_000,
                ping_interval=25,
                ping_timeout=20,
                open_timeout=15,
                compression=None,
            ) as ws:
                await ws.send(dumps(setup))
                logger.info("📤 Setup sent")

                async for raw in ws:
                    try:
                        data = loads(raw)
                    except Exception:
                        continue

                    if "error" in data:
                        logger.error(
                            "API error: %s",
                            data.get("error", {}).get("message", "?"),
                        )
                        continue

                    if "setupComplete" in data:
                        logger.info("✅ Ready!")

                        speaker.clear()
                        mic.response_in_progress = False
                        mic.start()

                        audio_task = asyncio.create_task(audio_sender())

                        if not st["greeted"]:
                            st["greeted"] = True
                            await inject(
                                "Greet the user briefly and ask for orders."
                            )
                        else:
                            logger.info("🎤 Bolo boss!")

                        eye("EYES_NORMAL")
                        continue

                    sc = data.get("serverContent") or {}

                    # Interruption
                    if sc.get("interrupted"):
                        logger.info("⚡ [Interruption] User interrupted %s", AGENT_NAME)

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
                            log_user(user_text)
                        if ai_text:
                            clean_asst = re.sub(
                                r"\[TOOL:[^\]]*\]", "", ai_text
                            ).strip()
                            log_ai(clean_asst)

                        # Persist completed turn.
                        if user_text:
                            try:
                                await asyncio.to_thread(
                                    save_message, "user", user_text, SESSION_ID
                                )
                            except Exception as e:
                                logger.warning("💾 SAVE USER FAILED | %s", e)

                        if ai_text:
                            try:
                                await asyncio.to_thread(
                                    save_message, "assistant", ai_text, SESSION_ID
                                )
                            except Exception as e:
                                logger.warning("💾 SAVE AI FAILED | %s", e)

                        # Clear ESP32 image only after successful vision turn.
                        if _image_analysis_active and _image_analysis_completed:
                            logger.info("🧹 IMAGE ANALYSIS COMPLETE | IMG_CLEAR")
                            await loop.run_in_executor(
                                uart_executor, send_uart_command, "IMG_CLEAR"
                            )

                        _image_analysis_active = False
                        _image_analysis_completed = False

                        st["user_buf"] = ""
                        st["asst_buf"] = ""

                        if not speaker.is_active():
                            eye("EYES_NORMAL")

                    # Native tool calls
                    tc = data.get("toolCall")
                    if tc:
                        print()

                        calls = tc.get("functionCalls", [])

                        moves = [
                            c for c in calls if c.get("name") == "move_robot"
                        ]
                        others = [
                            c for c in calls if c.get("name") != "move_robot"
                        ]

                        # Movement: absolute shortest path to UART.
                        for c in moves:
                            args = c.get("args") or {}
                            result = await handle_move(loop, args)
                            await send_tool_response(
                                ws, c.get("id", ""), result
                            )

                        # Other tools.
                        if others:
                            eye("THINK")
                            for c in others:
                                result = await run_tool(
                                    c.get("name", ""), c.get("args") or {}
                                )
                                await send_tool_response(
                                    ws, c.get("id", ""), result
                                )
                            eye("EYES_NORMAL")

        except websockets.exceptions.ConnectionClosed as e:
            logger.warning("🔌 WS connection closed: %s", e)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("🔌 Session error: %s", e, exc_info=True)
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

            logger.info("🔌 Cleanup complete.")

        is_reconnect = True
        logger.info("🔄 Reconnecting in 3 seconds...")
        await asyncio.sleep(3)


# Alias so both `run` and `run_session` work.
run = run_session


# ---------------------------------------------------------------------------
# Entry (direct run)
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
║   UART         : tools.py canonical layer
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
            # Stop motors, then close UART.
            send_uart_command("STOP")
        except Exception:
            pass
        try:
            close_uart()
        except Exception:
            pass
        try:
            camera.close()
        except Exception:
            pass