"""WALL-E fast Gemini Live client.

- Gemini Live handles realtime voice + tool calling.
- Gemini 3.5 Flash handles one-shot camera analysis over REST.
- ESP32 uses persistent USB serial (/dev/ttyUSB0 by default).
- Camera stays warm with picamera2.
- Live API input/output transcription is enabled for detailed terminal logs.
"""

import os
import asyncio
import logging
import json
import base64
import subprocess
import shutil
import time
import socket
import inspect
import queue
import threading

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

from dotenv import load_dotenv

load_dotenv(override=True)

from prompts import AGENT_INSTRUCTION
from tools import send_uart_command, TOOL_MAP, close_uart
from conversation_memory import (
    init_db,
    save_message,
    format_recent_context,
)


# ---------------------------------------------------------------------------
# Timestamped logging
# ---------------------------------------------------------------------------

class MillisecondFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        now = time.localtime(record.created)
        ms = int(record.msecs)
        return time.strftime("%H:%M:%S", now) + f".{ms:03d}"


_handler = logging.StreamHandler()
_handler.setFormatter(
    MillisecondFormatter(
        "%(asctime)s - %(levelname)s - %(message)s"
    )
)

root = logging.getLogger()
root.setLevel(logging.INFO)

# Avoid duplicate handlers if module is reloaded.
if not any(getattr(h, "_walle_handler", False) for h in root.handlers):
    _handler._walle_handler = True
    root.addHandler(_handler)

logger = logging.getLogger("WALLE")
BASE = os.path.dirname(os.path.abspath(__file__))

# Persistent conversation DB (SQLite/WAL; no extra package required).
init_db()

MIC_CHUNK = int(os.getenv("MIC_CHUNK", "512"))
VISION_ENABLED = os.getenv("ENABLE_VISION", "1").lower() in {
    "1", "true", "yes", "on"
}
ESP_IMAGE = os.getenv("ENABLE_ESP32_IMAGE", "0").lower() in {
    "1", "true", "yes", "on"
}

# Ollama vision configuration.
# The Live voice/tool model remains Gemini; only image analysis uses Ollama.
OLLAMA_CLOUD_URL = os.getenv(
    "OLLAMA_CLOUD_URL",
    "https://ollama.com",
).rstrip("/")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "").strip()
OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "").strip()

LIVE_MODEL = os.getenv(
    "GEMINI_LIVE_MODEL",
    "models/gemini-2.5-flash-native-audio-preview-12-2025",
)

SERIAL_PORT_DISPLAY = os.getenv("SERIAL_PORT", "/dev/ttyUSB0")
MEMORY_TURNS = int(os.getenv("MEMORY_TURNS", "20"))
SESSION_ID = os.getenv("WALLE_SESSION_ID", "") or time.strftime(
    "%Y%m%d-%H%M%S"
)


# ---------------------------------------------------------------------------
# Runtime state
# ---------------------------------------------------------------------------

is_ai_speaking = False
_current_eye = None

# Current turn transcripts. Gemini may send transcription in multiple chunks.
_user_transcript_parts = []
_ai_transcript_parts = []
_image_analysis_active = False
_image_analysis_completed = False
_turn_started_at = None
_first_ai_text_at = None
_ai_audio_started_at = None

# Low-latency audio playback:
# Gemini receive loop only enqueues PCM. A dedicated worker owns ALSA writes.
_AUDIO_QUEUE_MAX = int(os.getenv("AUDIO_QUEUE_MAX", "48"))
_audio_queue = queue.Queue(maxsize=_AUDIO_QUEUE_MAX)
_audio_stop = threading.Event()
_audio_worker = None
_audio_stream = None
_audio_playback_started = threading.Event()

# 24 kHz mono int16: 960 samples = 40 ms. This is the target write size to
# ALSA — large enough to avoid per-write overhead, small enough to match the
# typical Gemini audio packet cadence and keep latency low.
_WRITE_SAMPLES = 960
_WRITE_BYTES = _WRITE_SAMPLES * 2  # int16 = 2 bytes/sample

# Prebuffer ~80 ms (1920 samples) before the very first ALSA write so the
# device ring buffer has enough data to start without an immediate underrun.
_PREBUF_BYTES = _WRITE_SAMPLES * 2 * 2  # 2 blocks = 80 ms

# Audio pipeline diagnostics (updated by the worker, read at turn-complete).
_audio_stats_lock = threading.Lock()
_audio_stats = {
    "writes": 0,
    "write_bytes": 0,
    "write_time_ms": 0.0,
    "max_write_ms": 0.0,
    "underruns": 0,
    "queue_peak": 0,
    "queue_waits": 0,
    "rx_chunks": 0,
    "rx_bytes": 0,
    "dropped": 0,
    "last_report": 0.0,
}


def _reset_audio_stats():
    with _audio_stats_lock:
        for k in _audio_stats:
            if k == "last_report":
                _audio_stats[k] = time.monotonic()
            else:
                _audio_stats[k] = 0 if isinstance(_audio_stats[k], int) else 0.0


def _report_audio_stats(force=False):
    """Log aggregate audio stats every ~2 seconds during playback."""
    with _audio_stats_lock:
        now = time.monotonic()
        if not force and (now - _audio_stats["last_report"]) < 2.0:
            return
        if _audio_stats["writes"] == 0 and not force:
            return
        s = dict(_audio_stats)
        _audio_stats["last_report"] = now

    avg_write = (s["write_time_ms"] / s["writes"]) if s["writes"] else 0
    logger.info(
        "📊 AUDIO STATS | writes=%d | bytes=%d | avg_write=%.1fms | "
        "max_write=%.1fms | underruns=%d | q_peak=%d | q_waits=%d | "
        "rx_chunks=%d | rx_bytes=%d | dropped=%d",
        s["writes"], s["write_bytes"], avg_write, s["max_write_ms"],
        s["underruns"], s["queue_peak"], s["queue_waits"],
        s["rx_chunks"], s["rx_bytes"], s["dropped"],
    )


def _audio_worker_loop():
    """Dedicated ALSA consumer — writes consistent ~40ms PCM blocks.

    Key design decisions that prevent ALSA underruns on Pi 3B+:
    1. Prebuffer 80ms before the first write so ALSA's ring buffer has data.
    2. Write in fixed ~960-sample (40ms) blocks — never micro-writes.
    3. Poll the queue every 5ms (not 50ms) so ALSA never starves.
    4. When the queue goes empty during playback, flush whatever remains
       in 'pending' so there is no trailing silence gap.
    """
    global _audio_stream

    pending = bytearray()
    started = False

    def _write_block(data_bytes):
        """Write one block to the ALSA device and track stats."""
        nonlocal started
        stream = _audio_stream
        if stream is None:
            return False
        t0 = time.monotonic()
        try:
            stream.write(data_bytes)
            elapsed = (time.monotonic() - t0) * 1000
            started = True
            with _audio_stats_lock:
                _audio_stats["writes"] += 1
                _audio_stats["write_bytes"] += len(data_bytes)
                _audio_stats["write_time_ms"] += elapsed
                if elapsed > _audio_stats["max_write_ms"]:
                    _audio_stats["max_write_ms"] = elapsed
            return True
        except Exception as e:
            err_str = str(e)
            if "underrun" in err_str.lower() or "Underrun" in err_str:
                with _audio_stats_lock:
                    _audio_stats["underruns"] += 1
                # Underrun recovery: ALSA auto-recovers, just keep writing.
                return True
            logger.warning("🔊 AUDIO WRITE ERROR | %s", e)
            return False

    def _drain_pending():
        """Write as many full blocks from 'pending' as possible."""
        while len(pending) >= _WRITE_BYTES:
            block = bytes(pending[:_WRITE_BYTES])
            del pending[:_WRITE_BYTES]
            if not _write_block(block):
                pending.clear()
                return False
        return True

    while not _audio_stop.is_set():
        try:
            item = _audio_queue.get(timeout=0.005)  # 5ms — keeps ALSA fed
        except queue.Empty:
            with _audio_stats_lock:
                _audio_stats["queue_waits"] += 1

            # Queue is empty but we have leftover PCM from a previous packet.
            # Flush it NOW instead of letting ALSA starve waiting for more.
            if started and len(pending) > 0:
                # Pad to even sample boundary (int16 = 2 bytes)
                if len(pending) % 2:
                    pending.append(0)
                if len(pending) > 0:
                    block = bytes(pending)
                    pending.clear()
                    _write_block(block)

            _report_audio_stats()
            continue

        if item is None:
            break

        try:
            pending.extend(item)

            # Track queue depth
            qsize = _audio_queue.qsize()
            with _audio_stats_lock:
                if qsize > _audio_stats["queue_peak"]:
                    _audio_stats["queue_peak"] = qsize

            if not started:
                # Prebuffer: wait until we have ≥80ms before the first write.
                if len(pending) < _PREBUF_BYTES:
                    continue

            # Write full blocks.
            if not _drain_pending():
                started = False

        finally:
            _audio_queue.task_done()

    # Shutdown: flush anything remaining.
    if len(pending) > 0 and _audio_stream is not None:
        if len(pending) % 2:
            pending.append(0)
        _write_block(bytes(pending))
    pending.clear()


def start_audio_worker(stream):
    global _audio_worker, _audio_stream
    _audio_stream = stream
    _audio_stop.clear()

    if _audio_worker is None or not _audio_worker.is_alive():
        _audio_worker = threading.Thread(
            target=_audio_worker_loop,
            name="WALLE-Audio-ALSA",
            daemon=True,
        )
        _audio_worker.start()


def clear_audio_queue():
    """Drop stale AI audio so an old response can never delay a new command."""
    dropped = 0
    while True:
        try:
            _audio_queue.get_nowait()
            _audio_queue.task_done()
            dropped += 1
        except queue.Empty:
            break

    if dropped:
        logger.info("🔊 AUDIO QUEUE CLEAR | dropped=%d chunks", dropped)


def stop_audio_worker():
    global _audio_worker, _audio_stream
    _audio_stop.set()

    try:
        _audio_queue.put_nowait(None)
    except queue.Full:
        clear_audio_queue()
        try:
            _audio_queue.put_nowait(None)
        except queue.Full:
            pass

    if _audio_worker is not None and _audio_worker.is_alive():
        _audio_worker.join(timeout=1.0)

    _audio_worker = None
    _audio_stream = None


def _stamp():
    return time.strftime("%H:%M:%S.") + f"{int((time.time() % 1) * 1000):03d}"


def _latency_ms(start, end=None):
    if start is None:
        return None
    return ((end if end is not None else time.monotonic()) - start) * 1000


def _log_latency(label, ms):
    if ms is not None:
        logger.info("⚡ LATENCY | %s | %.0f ms (%.2f s)", label, ms, ms / 1000.0)


def log_user(text):
    text = (text or "").strip()
    if text:
        logger.info("👤 USER [%s] | %s", _stamp(), text)


def log_ai(text):
    text = (text or "").strip()
    if text:
        logger.info("🤖 AI [%s] | %s", _stamp(), text)


def log_tool(name, args):
    logger.info(
        "🛠️ TOOL CALL [%s] | %s | args=%s",
        _stamp(),
        name,
        args,
    )


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
                    main={
                        "size": (320, 240),
                        "format": "RGB888",
                    }
                )

                self.picam.configure(cfg)
                self.picam.start()

                # Short warm-up only.
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
                # Discard old frames so "look" describes the current scene.
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
                    (time.monotonic() - t0) * 1000,
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
                        "--immediate",
                        "1",
                        "--encoding", "jpg",
                        "--timeout", "1",
                    ],
                    capture_output=True,
                    timeout=4,
                )

                if r.returncode == 0 and len(r.stdout) > 100:
                    logger.info(
                        "📷 CAMERA CAPTURED | %d bytes | %.0f ms",
                        len(r.stdout),
                        (time.monotonic() - t0) * 1000,
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
                    timeout=4,
                )

                if r.returncode == 0 and len(r.stdout) > 100:
                    logger.info(
                        "📷 CAMERA CAPTURED | %d bytes | %.0f ms",
                        len(r.stdout),
                        (time.monotonic() - t0) * 1000,
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
                (time.monotonic() - t0) * 1000,
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
# OLED eyes
# ---------------------------------------------------------------------------

def eye(state):
    global _current_eye

    valid = {
        "BOOT",
        "IDLE",
        "LISTEN",
        "SPEAK",
        "EYES_TALKING",
        "EYES_NORMAL",
        "THINK",
        "STOP",
        "HAPPY",
        "SAD",
        "ANGRY",
    }

    if state not in valid or state == _current_eye:
        return

    _current_eye = state

    logger.info("👁️ ESP32 EYE | %s", state)

    try:
        asyncio.get_running_loop().run_in_executor(
            None,
            send_uart_command,
            state,
        )
    except RuntimeError:
        send_uart_command(state)


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------

def open_speaker():
    # Gemini Live PCM is 24 kHz mono int16.
    #
    # KEY DESIGN DECISIONS to prevent ALSA underruns on Pi 3B+:
    #
    # 1. Do NOT set blocksize. With blocksize set, PortAudio's blocking-write
    #    API only accepts writes aligned to that blocksize, causing the audio
    #    worker's variable-size writes to trigger partial fills → underruns.
    #    Without blocksize, ALSA accepts whatever we give it immediately.
    #
    # 2. Use latency=0.1 (100ms ring buffer), NOT "high" (~500ms+). A 100ms
    #    buffer is large enough to absorb network jitter and Python GIL
    #    scheduling, but small enough to keep perceived playback latency low.
    #
    # 3. 48000 Hz is only a fallback with explicit 2x sample replication.
    for rate in (24000, 48000):
        try:
            s = sd.RawOutputStream(
                samplerate=rate,
                channels=1,
                dtype="int16",
                latency=0.1,  # 100ms ALSA ring buffer
            )
            s.start()

            # Log actual device parameters for diagnostics.
            try:
                dev_info = sd.query_devices(s.device, "output")
                logger.info(
                    "🔊 Speaker READY | %d Hz | latency=100ms | "
                    "device='%s' | host_api=%s | "
                    "default_low_latency=%.1fms | default_high_latency=%.1fms",
                    rate,
                    dev_info.get("name", "unknown"),
                    dev_info.get("hostapi", "?"),
                    dev_info.get("default_low_output_latency", 0) * 1000,
                    dev_info.get("default_high_output_latency", 0) * 1000,
                )
            except Exception:
                logger.info("🔊 Speaker READY | %d Hz | latency=100ms", rate)
            return s, rate
        except Exception as e:
            logger.warning("🔊 Speaker open failed | rate=%d | %s", rate, e)

    logger.warning("🔊 Speaker stream unavailable")
    return None, 24000


def resample24to48(b):
    return np.repeat(
        np.frombuffer(b, dtype=np.int16),
        2,
    ).tobytes()


# ---------------------------------------------------------------------------
# Microphone
# ---------------------------------------------------------------------------

async def mic_loop(ws, mic):
    """Continuously forward microphone PCM to Gemini with minimal scheduling delay."""
    loop = asyncio.get_running_loop()
    tx_count = 0

    while True:
        try:
            t_capture = time.monotonic()

            data, _ = await loop.run_in_executor(
                None,
                mic.read,
                MIC_CHUNK,
            )

            if not data:
                continue

            # IMPORTANT: Do not gate microphone input on is_ai_speaking.
            # Gating it caused user speech to be silently discarded while
            # WALL-E was speaking and could create huge apparent delays.
            payload = {
                "realtimeInput": {
                    "mediaChunks": [
                        {
                            "mimeType": "audio/pcm;rate=16000",
                            "data": base64.b64encode(bytes(data)).decode(),
                        }
                    ]
                }
            }

            t_send = time.monotonic()
            await ws.send(dumps(payload))
            tx_count += 1

            # Log only periodically to avoid flooding the Pi terminal.
            if tx_count % 100 == 0:
                logger.info(
                    "🎙️ MIC PIPELINE | chunks=%d | capture→send=%.1f ms",
                    tx_count,
                    (time.monotonic() - t_capture) * 1000,
                )

        except asyncio.CancelledError:
            return

        except Exception as e:
            logger.warning("🎤 MIC LOOP ERROR | %s", e)
            await asyncio.sleep(0.05)


# ---------------------------------------------------------------------------
# Ollama vision
# ---------------------------------------------------------------------------

vision_session = None


async def get_vision_session():
    global vision_session

    if vision_session is None or vision_session.closed:
        # Reuse the HTTP connection so every see_object call does not pay
        # a fresh TLS/connect handshake.
        connector = aiohttp.TCPConnector(
            family=socket.AF_INET,
            limit=2,
            ttl_dns_cache=300,
        )

        vision_session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(
                total=20,
                connect=5,
                sock_connect=5,
                sock_read=15,
            ),
        )

    return vision_session


async def _vision_request(jpeg, prompt):
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
        "images": [
            base64.b64encode(jpeg).decode("utf-8")
        ],
        "stream": False,
    }

    headers = {
        "Content-Type": "application/json",
    }

    if OLLAMA_API_KEY:
        headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"

    s = await get_vision_session()
    t0 = time.monotonic()

    logger.info(
        "🌐 OLLAMA VISION START | model=%s | image=%d bytes",
        OLLAMA_VISION_MODEL,
        len(jpeg),
    )

    async with s.post(
        url,
        json=payload,
        headers=headers,
    ) as r:
        text = await r.text()
        elapsed = (time.monotonic() - t0) * 1000

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
            return (
                f"Ollama vision error {r.status}: "
                f"{text[:300]}"
            )

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

    logger.info(
        "🌐 OLLAMA VISION RESULT | %s",
        out,
    )

    global _image_analysis_completed
    _image_analysis_completed = True
    return out


async def analyze_image(jpeg, prompt, key=None):
    if not VISION_ENABLED:
        logger.warning("⚠️ Vision disabled by ENABLE_VISION")
        return "Vision is disabled."

    if not jpeg:
        return "No image captured."

    if not OLLAMA_VISION_MODEL:
        logger.error("❌ OLLAMA_VISION_MODEL is missing in .env")
        return "OLLAMA_VISION_MODEL is missing."

    for attempt in (1, 2):
        try:
            return await _vision_request(
                jpeg,
                prompt,
            )

        except asyncio.TimeoutError:
            logger.warning(
                "⏱️ OLLAMA VISION TIMEOUT | attempt=%d/2 | model=%s",
                attempt,
                OLLAMA_VISION_MODEL,
            )

            if attempt == 2:
                return (
                    "Image analysis timed out. "
                    "Please try again."
                )

            await asyncio.sleep(0.15)

        except aiohttp.ClientError as e:
            logger.warning(
                "🌐 OLLAMA VISION NETWORK ERROR | attempt=%d/2 | %s",
                attempt,
                e,
            )

            if attempt == 2:
                return (
                    "Image analysis failed because the "
                    "Ollama vision network request failed."
                )

            await asyncio.sleep(0.15)

        except Exception as e:
            logger.exception(
                "❌ OLLAMA VISION UNEXPECTED ERROR | %s",
                e,
            )
            return f"Image analysis failed: {e}"


# ---------------------------------------------------------------------------
# Tool response
# ---------------------------------------------------------------------------

async def send_tool_response(ws, call_id, output):
    await ws.send(
        dumps(
            {
                "toolResponse": {
                    "functionResponses": [
                        {
                            "response": {
                                "output": str(output)
                            },
                            "id": call_id,
                        }
                    ]
                }
            }
        )
    )


async def handle_other_tool(call):
    name = call.get("name")
    args = call.get("args") or {}

    log_tool(name, args)

    if name == "see_object":
        global _image_analysis_active

        _image_analysis_active = True
        loop = asyncio.get_running_loop()
        vision_tool_started = time.monotonic()

        logger.info("📷 SEE_OBJECT | image analysis started | args=%s", args)
        logger.info("📷 SEE_OBJECT | capturing fresh frame...")
        jpeg = await loop.run_in_executor(
            None,
            camera.grab,
        )

        if not jpeg:
            result = "Failed to capture a photo from WALL-E's camera."
            logger.error("🛠️ TOOL RESULT | see_object | %s", result)
            return result

        if ESP_IMAGE:
            try:
                await loop.run_in_executor(
                    None,
                    send_uart_command,
                    "IMG:" + base64.b64encode(jpeg).decode(),
                )
            except Exception as e:
                logger.warning(
                    "ESP32 image thumbnail failed: %s",
                    e,
                )

        result = await analyze_image(
            jpeg,
            args.get("prompt", "Describe what you see."),
            os.getenv("GOOGLE_API_KEY", ""),
        )

        _log_latency(
            "see_object tool total",
            _latency_ms(vision_tool_started),
        )

        logger.info(
            "🛠️ TOOL RESULT | see_object | %s",
            result,
        )

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

    func = TOOL_MAP.get(name)

    if not func:
        result = f"Unknown tool '{name}'"
        logger.error("🛠️ TOOL RESULT | %s | %s", name, result)
        return result

    try:
        if inspect.iscoroutinefunction(func):
            result = await func(**args)
        else:
            result = await asyncio.to_thread(
                func,
                **args,
            )

        logger.info(
            "🛠️ TOOL RESULT | %s | %s",
            name,
            result,
        )

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
        logger.exception(
            "❌ TOOL ERROR | %s | %s",
            name,
            e,
        )
        return f"Error executing tool: {e}"


# ---------------------------------------------------------------------------
# Gemini receive / tool handling
# ---------------------------------------------------------------------------

async def receive_loop(ws, speaker_info):
    global is_ai_speaking
    global _turn_started_at, _first_ai_text_at, _ai_audio_started_at
    global _image_analysis_active, _image_analysis_completed

    speaker, rate = speaker_info
    loop = asyncio.get_running_loop()
    need_resample = rate == 48000

    async for raw in ws:
        try:
            data = loads(raw)
        except Exception:
            continue

        if "setupComplete" in data:
            logger.info("🟢 Gemini Live READY")
            eye("EYES_NORMAL")
            continue

        sc = data.get("serverContent")

        if sc:
            # ---------------------------------------------------------------
            # USER TRANSCRIPTION
            # ---------------------------------------------------------------
            inp = sc.get("inputTranscription")
            if inp:
                text = inp.get("text", "")
                if text:
                    now = time.monotonic()

                    if not _user_transcript_parts:
                        _turn_started_at = now
                        _first_ai_text_at = None
                        _ai_audio_started_at = None
                        _image_analysis_active = False
                        _image_analysis_completed = False
                        logger.info("🎤 USER TURN START [%s]", _stamp())
                        _reset_audio_stats()

                    _user_transcript_parts.append(text)
                    logger.info(
                        "👤 USER TRANSCRIPT [%s] | %s",
                        _stamp(),
                        text,
                    )

            # ---------------------------------------------------------------
            # AI OUTPUT TRANSCRIPTION
            # ---------------------------------------------------------------
            out = sc.get("outputTranscription")
            if out:

                text = out.get("text", "")

                if text:

                    now = time.monotonic()

                    if _first_ai_text_at is None:

                        _first_ai_text_at = now

                        _log_latency(

                            "user first transcript → AI first transcript",

                            _latency_ms(_turn_started_at, now),

                        )

                    _ai_transcript_parts.append(text)

                    logger.info(

                        "🤖 AI TRANSCRIPT [%s] | %s",

                        _stamp(),

                        text,

                    )

            if sc.get("interrupted"):
                logger.info("⛔ AI TURN INTERRUPTED")
                clear_audio_queue()
                is_ai_speaking = False
                eye("EYES_NORMAL")

            mt = sc.get("modelTurn")

            if mt:
                for p in mt.get("parts", []):
                    x = p.get("inlineData")

                    if x and x.get("data"):
                        if not is_ai_speaking:
                            _ai_audio_started_at = time.monotonic()
                            logger.info(
                                "🔊 AI AUDIO START [%s]",
                                _stamp(),
                            )
                            _log_latency(
                                "user first transcript → AI audio start",
                                _latency_ms(_turn_started_at, _ai_audio_started_at),
                            )

                        is_ai_speaking = True
                        eye("EYES_TALKING")

                        audio = base64.b64decode(x["data"])

                        if len(audio) % 2:
                            audio = audio[:-1]

                        if need_resample:
                            audio = resample24to48(audio)

                        if speaker:
                            # Never write to ALSA from the Gemini WebSocket
                            # receive coroutine. Queue it for the dedicated
                            # playback worker.
                            with _audio_stats_lock:
                                _audio_stats["rx_chunks"] += 1
                                _audio_stats["rx_bytes"] += len(audio)
                            try:
                                _audio_queue.put_nowait(audio)
                            except queue.Full:
                                # Stale audio is worse than dropping one chunk:
                                # keep the robot responsive to the current turn.
                                with _audio_stats_lock:
                                    _audio_stats["dropped"] += 1
                                try:
                                    _audio_queue.get_nowait()
                                    _audio_queue.task_done()
                                except queue.Empty:
                                    pass
                                try:
                                    _audio_queue.put_nowait(audio)
                                except queue.Full:
                                    pass

            if sc.get("turnComplete"):
                # Final turn summaries.
                user_text = "".join(_user_transcript_parts).strip()
                ai_text = "".join(_ai_transcript_parts).strip()

                if user_text:
                    logger.info(
                        "👤 USER FINAL [%s] | %s",
                        _stamp(),
                        user_text,
                    )

                if ai_text:
                    log_ai(ai_text)

                # Persist the completed conversational turn.
                # SQLite WAL keeps this fast and crash-safe enough for Pi use.
                if user_text:
                    try:
                        await asyncio.to_thread(
                            save_message,
                            "user",
                            user_text,
                            SESSION_ID,
                        )
                    except Exception as e:
                        logger.warning(
                            "💾 MEMORY SAVE USER FAILED | %s",
                            e,
                        )

                if ai_text:
                    try:
                        await asyncio.to_thread(
                            save_message,
                            "assistant",
                            ai_text,
                            SESSION_ID,
                        )
                    except Exception as e:
                        logger.warning(
                            "💾 MEMORY SAVE AI FAILED | %s",
                            e,
                        )

                _user_transcript_parts.clear()
                _ai_transcript_parts.clear()

                is_ai_speaking = False
                eye("EYES_NORMAL")

                # Clear the ESP32 image ONLY after a successful image-analysis turn.
                if _image_analysis_active and _image_analysis_completed:
                    logger.info("🧹 IMAGE ANALYSIS COMPLETE | sending IMG_CLEAR")
                    clear_ok = await loop.run_in_executor(
                        None,
                        send_uart_command,
                        "IMG_CLEAR",
                    )
                    logger.info("🧹 IMG_CLEAR RESULT | sent=%s", clear_ok)
                elif _image_analysis_active:
                    logger.warning(
                        "⚠️ IMAGE TURN ENDED WITHOUT SUCCESSFUL ANALYSIS | "
                        "IMG_CLEAR NOT SENT"
                    )

                if _turn_started_at is not None:
                    _log_latency(
                        "user first transcript → turn complete",
                        _latency_ms(_turn_started_at),
                    )

                logger.info(
                    "📊 TURN STATS | user=%d chars | ai=%d chars | "
                    "audio_queue=%d | mic_continuous=True",
                    len(user_text),
                    len(ai_text),
                    _audio_queue.qsize(),
                )
                _report_audio_stats(force=True)

                _image_analysis_active = False
                _image_analysis_completed = False
                _turn_started_at = None
                _first_ai_text_at = None
                _ai_audio_started_at = None

        # ---------------------------------------------------------------
        # TOOL CALLS
        # ---------------------------------------------------------------
        tc = data.get("toolCall")

        if not tc:
            continue

        calls = tc.get("functionCalls", [])

        moves = [
            c for c in calls
            if c.get("name") == "move_robot"
        ]

        others = [
            c for c in calls
            if c.get("name") != "move_robot"
        ]

        # Movement gets absolute shortest path to UART.
        for c in moves:
            cid = c.get("id", "")
            args = c.get("args") or {}
            d = str(
                args.get("direction", "STOP")
            ).upper().strip()

            log_tool("move_robot", args)

            if d in {
                "FORWARD",
                "BACKWARD",
                "LEFT",
                "RIGHT",
                "STOP",
            }:
                t0 = time.monotonic()

                ok = await loop.run_in_executor(
                    None,
                    send_uart_command,
                    d,
                )

                elapsed = (time.monotonic() - t0) * 1000

                if ok:
                    result = (
                        "WALL-E stopped."
                        if d == "STOP"
                        else f"WALL-E moving {d}."
                    )
                else:
                    result = "ESP32 USB UART unavailable."

                logger.info(
                    "🛠️ MOVE COMPLETE | %s | %.1f ms | result=%s",
                    d,
                    elapsed,
                    result,
                )

            else:
                result = f"Invalid direction '{d}'."

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

            await send_tool_response(
                ws,
                cid,
                result,
            )

        # Other tools are handled after movement.
        if others:
            eye("THINK")

            for c in others:
                result = await handle_other_tool(c)

                await send_tool_response(
                    ws,
                    c.get("id", ""),
                    result,
                )

            eye("EYES_NORMAL")


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

async def run():
    key = os.getenv("GOOGLE_API_KEY", "").strip()

    if not key:
        logger.error("❌ GOOGLE_API_KEY missing in .env")
        return

    memory = os.path.join(BASE, "memory.json")
    memory_text = ""

    try:
        if os.path.exists(memory):
            with open(memory, encoding="utf-8") as f:
                m = json.load(f)

            if isinstance(m, list):
                memory_text = (
                    "\n\nPAST MEMORIES:\n"
                    + "\n".join(
                        f"- {x.get('fact') or x.get('content')}"
                        for x in m[-20:]
                        if isinstance(x, dict)
                        and (
                            x.get("fact")
                            or x.get("content")
                        )
                    )
                )

    except Exception:
        pass

    recent_conversation = format_recent_context(
        limit=MEMORY_TURNS,
        session_id=None,
    )

    if recent_conversation:
        memory_text += "\n\n" + recent_conversation

    instruction = (
        AGENT_INSTRUCTION
        + "\n\nLATENCY RULES: For movement/tool commands, act immediately. "
          "Do not add explanations before calling the tool. Keep spoken "
          "confirmation to one short sentence after the tool succeeds."
        + memory_text
    )

    setup = {
        "setup": {
            "model": LIVE_MODEL,
            # Live API transcription settings are setup-level fields.
            "inputAudioTranscription": {},
            "outputAudioTranscription": {},

            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "temperature": 0.25,
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {
                            "voiceName": "Puck"
                        }
                    }
                },
            },

            "systemInstruction": {
                "parts": [
                    {
                        "text": instruction
                    }
                ]
            },

            "tools": [
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
                                "Captures a fresh camera frame and "
                                "describes what WALL-E sees. "
                                "Use whenever the user asks what "
                                "you can see or look at."
                            ),
                            "parameters": {
                                "type": "OBJECT",
                                "properties": {
                                    "prompt": {
                                        "type": "STRING",
                                        "description": (
                                            "What to inspect in the image"
                                        ),
                                    }
                                },
                            },
                        },
                        {
                            "name": "get_weather",
                            "description": "Gets current weather.",
                            "parameters": {
                                "type": "OBJECT",
                                "properties": {
                                    "city": {
                                        "type": "STRING"
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
                        {
                            "name": "search_web",
                            "description": "Searches the web for a factual query.",
                            "parameters": {
                                "type": "OBJECT",
                                "properties": {
                                    "query": {
                                        "type": "STRING"
                                    }
                                },
                                "required": ["query"],
                            },
                        },
                        {
                            "name": "remember_fact",
                            "description": "Stores an important fact in long-term memory.",
                            "parameters": {
                                "type": "OBJECT",
                                "properties": {
                                    "fact": {
                                        "type": "STRING"
                                    }
                                },
                                "required": ["fact"],
                            },
                        },
                    ]
                }
            ],
        }
    }

    mic = sd.RawInputStream(
        samplerate=16000,
        channels=1,
        dtype="int16",
        blocksize=MIC_CHUNK,
    )
    mic.start()

    speaker_info = open_speaker()
    start_audio_worker(speaker_info[0])

    url = (
        "wss://generativelanguage.googleapis.com/ws/"
        "google.ai.generativelanguage.v1beta."
        "GenerativeService.BidiGenerateContent?key="
        + key
    )

    try:
        logger.info(
            "🚀 WALL-E BOOT | Live=%s | Vision=%s (Ollama:%s) | UART=%s | Memory=SQLite(%d turns)",
            LIVE_MODEL,
            VISION_ENABLED,
            OLLAMA_VISION_MODEL or "NOT_SET",
            SERIAL_PORT_DISPLAY,
            MEMORY_TURNS,
        )

        # Open UART once during startup so the first command is fast.
        await asyncio.to_thread(send_uart_command, "BOOT")

        eye("EYES_NORMAL")

        async with websockets.connect(
            url,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=1,
            max_size=4 * 1024 * 1024,
        ) as ws:

            await ws.send(dumps(setup))

            mic_task = asyncio.create_task(
                mic_loop(ws, mic),
                name="WALLE-Mic",
            )

            receive_task = asyncio.create_task(
                receive_loop(ws, speaker_info),
                name="WALLE-Gemini",
            )

            done, pending = await asyncio.wait(
                {mic_task, receive_task},
                return_when=asyncio.FIRST_EXCEPTION,
            )

            for task in pending:
                task.cancel()

            for task in done:
                try:
                    task.result()
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.exception(
                        "❌ WALL-E task failed: %s",
                        e,
                    )

    except Exception as e:
        logger.exception(
            "❌ Gemini Live connection failed: %s",
            e,
        )

    finally:
        try:
            mic.stop()
            mic.close()
        except Exception:
            pass

        stop_audio_worker()

        if speaker_info[0]:
            try:
                speaker_info[0].stop()
                speaker_info[0].close()
            except Exception:
                pass

        eye("STOP")
        close_uart()

        if vision_session and not vision_session.closed:
            await vision_session.close()

        camera.close()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
