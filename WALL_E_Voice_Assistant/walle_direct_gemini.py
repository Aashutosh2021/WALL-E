"""
WALL-E AI Companion Robot - Direct Gemini Multimodal Live Client
Ultra-Low Latency Raw WebSocket to Google Gemini (BidiGenerateContent)
"""

import os
import sys
import asyncio
import inspect
import logging
import json
import base64
import subprocess
import shutil
import numpy as np
import sounddevice as sd
import websockets
import aiohttp
import time as _time
from datetime import datetime

# Fast JSON for the hot WebSocket path (falls back to stdlib json if orjson missing)
try:
    import orjson
    def _dumps(obj) -> str:
        return orjson.dumps(obj).decode()
    _loads = orjson.loads
except ImportError:
    def _dumps(obj) -> str:
        return json.dumps(obj)
    _loads = json.loads

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv(override=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

from prompts import AGENT_INSTRUCTION
from tools import send_uart_command, TOOL_MAP

# Flag to control mic feedback while AI is speaking
is_ai_speaking = False

# Latency tracking
_last_user_audio_ts = 0.0   # timestamp of last mic chunk sent
_first_ai_audio_ts = 0.0    # timestamp of first AI audio byte received in current turn
_ai_turn_started = False     # whether we've logged the first-byte latency for this turn

# ---------------------------------------------------------------------------
# Multi-Strategy Camera — picamera2 (persistent, warm) → rpicam-still →
# libcamera-still → OpenCV (USB/Windows)
# ---------------------------------------------------------------------------
try:
    from picamera2 import Picamera2
    _HAS_PICAM2 = True
except ImportError:
    Picamera2 = None
    _HAS_PICAM2 = False

_HAS_RPICAM = shutil.which("rpicam-still") is not None
_HAS_LIBCAMERA = shutil.which("libcamera-still") is not None

class _CameraManager:
    """Captures frames. Prefers a persistent picamera2 sensor (opened once, kept
    warm) — avoids the ~500ms-1s cold-start of spawning rpicam-still per call.
    Falls back to rpicam-still / libcamera-still subprocess, then OpenCV."""
    def __init__(self):
        self._cv_cap = None
        self._picam2 = None

        if _HAS_PICAM2:
            try:
                self._picam2 = Picamera2()
                config = self._picam2.create_still_configuration(
                    main={"size": (320, 240), "format": "RGB888"}  # RGB888 = [B,G,R] per-pixel — already OpenCV-ready, no cvtColor needed
                )
                self._picam2.configure(config)
                self._picam2.start()
                logger.info("📷 Camera backend: picamera2 (persistent, sensor kept warm)")
            except Exception as e:
                logger.error(f"picamera2 init failed, falling back to subprocess camera: {e}")
                self._picam2 = None

        if self._picam2 is None:
            if _HAS_RPICAM:
                logger.info("📷 Camera backend: rpicam-still (Pi CSI, cold-start per call)")
            elif _HAS_LIBCAMERA:
                logger.info("📷 Camera backend: libcamera-still (Pi CSI legacy, cold-start per call)")
            else:
                logger.info("📷 Camera backend: OpenCV (USB/Windows)")

    def grab_jpeg(self) -> bytes | None:
        """Grab a single JPEG frame using the best available method."""
        # Strategy 0: picamera2 — persistent, warm sensor (fastest, no process spawn)
        if self._picam2 is not None:
            return self._grab_picam2()
        # Strategy 1: rpicam-still (modern Raspberry Pi OS 64-bit)
        if _HAS_RPICAM:
            return self._grab_rpicam()
        # Strategy 2: libcamera-still (older Pi OS)
        if _HAS_LIBCAMERA:
            return self._grab_libcamera()
        # Strategy 3: OpenCV (USB cameras, Windows)
        return self._grab_opencv()

    def _grab_picam2(self) -> bytes | None:
        try:
            import cv2
            # Flush stale buffered frames — capture_array can return old data
            # from the internal ring buffer. Drop 2 frames to guarantee freshness.
            for _ in range(2):
                self._picam2.capture_array("main")
            frame = self._picam2.capture_array("main")
            ok, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
            if not ok:
                return None
            jpeg_bytes = buf.tobytes()
            logger.info(f"📸 picamera2 captured {len(jpeg_bytes)}B (fresh frame, 2 stale dropped)")
            return jpeg_bytes
        except Exception as e:
            logger.error(f"picamera2 capture error: {e}")
            return None

    def _grab_rpicam(self) -> bytes | None:
        try:
            result = subprocess.run(
                ["rpicam-still", "--output", "-", "--width", "320", "--height", "240",
                 "--quality", "50", "--nopreview", "--immediate", "1",
                 "--encoding", "jpg", "--timeout", "1"],
                capture_output=True, timeout=5
            )
            if result.returncode == 0 and len(result.stdout) > 100:
                logger.info(f"📸 rpicam-still captured {len(result.stdout)}B")
                return result.stdout
            logger.warning(f"rpicam-still failed: rc={result.returncode} stderr={result.stderr[:200]}")
            return None
        except Exception as e:
            logger.error(f"rpicam-still error: {e}")
            return None

    def _grab_libcamera(self) -> bytes | None:
        try:
            result = subprocess.run(
                ["libcamera-still", "--output", "-", "--width", "320", "--height", "240",
                 "--quality", "50", "--nopreview", "--immediate",
                 "--encoding", "jpg", "--timeout", "1"],
                capture_output=True, timeout=5
            )
            if result.returncode == 0 and len(result.stdout) > 100:
                logger.info(f"📸 libcamera-still captured {len(result.stdout)}B")
                return result.stdout
            return None
        except Exception as e:
            logger.error(f"libcamera-still error: {e}")
            return None

    def _grab_opencv(self) -> bytes | None:
        try:
            import cv2
            if self._cv_cap is None or not self._cv_cap.isOpened():
                self._cv_cap = cv2.VideoCapture(0)
                if not self._cv_cap.isOpened():
                    self._cv_cap = None
                    return None
                self._cv_cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
                self._cv_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
                self._cv_cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self._cv_cap.grab()  # flush stale frame 1
            self._cv_cap.grab()  # flush stale frame 2
            self._cv_cap.grab()  # flush stale frame 3
            ret, frame = self._cv_cap.read()
            if not ret or frame is None:
                return None
            ok, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
            return buf.tobytes() if ok else None
        except Exception as e:
            logger.error(f"OpenCV grab error: {e}")
            try: self._cv_cap.release()
            except: pass
            self._cv_cap = None
            return None

    def close(self):
        if self._picam2 is not None:
            try: self._picam2.stop()
            except: pass
            try: self._picam2.close()
            except: pass
            self._picam2 = None
        if self._cv_cap is not None:
            try: self._cv_cap.release()
            except: pass
            self._cv_cap = None

_camera = _CameraManager()
# ---------------------------------------------------------------------------
# State tracking for eye animation
# ---------------------------------------------------------------------------

# State track karne ke liye global variable
_current_eye_state = None

def set_eye_state(state: str):
    """Sends eye animation command over USB only if state actually changes."""
    global _current_eye_state
    
    valid_states = ["BOOT", "IDLE", "LISTEN", "SPEAK", "EYES_TALKING", "EYES_NORMAL", "THINK", "STOP", "HAPPY", "SAD", "ANGRY"]
    if state not in valid_states:
        return
        
    # Ignore duplicate commands (Pehle se EYES_TALKING hai toh wapas mat bhejo)
    if state == _current_eye_state:
        return
        
    _current_eye_state = state
    logger.info(f"👁️ Eye state changed to: {state}")
    
    # Run serial write in a background thread so audio playback never stutters
    asyncio.get_event_loop().run_in_executor(None, send_uart_command, state)

# ---------------------------------------------------------------------------
# OPTIMIZED Audio Helpers — zero-copy where possible
# ---------------------------------------------------------------------------
def _resample_24k_to_48k(raw_pcm_bytes: bytes) -> bytes:
    """Ultra-fast 2x upsample via np.repeat (zero interpolation overhead)."""
    pcm = np.frombuffer(raw_pcm_bytes, dtype=np.int16)
    if len(pcm) == 0:
        return b""
    return np.repeat(pcm, 2).tobytes()

def _open_speaker_stream():
    """Open speaker at model-native 24kHz first (zero resample). Fallback 48k (cheap 2x resample).
    44100 dropped on purpose — old code never resampled for it, causing pitched/fast audio."""
    for rate in [24000, 48000]:
        try:
            stream = sd.RawOutputStream(samplerate=rate, channels=1, dtype='int16')
            stream.start()
            logger.info(f"🔊 Speaker opened at {rate}Hz.")
            return stream, rate
        except Exception:
            continue
    logger.warning("❌ Could not open any speaker output stream.")
    return None, 48000

# ---------------------------------------------------------------------------
# WebSocket Audio Input & Output Loops
# ---------------------------------------------------------------------------
MIC_CHUNK = 1024  # 64ms at 16kHz — half the old 128ms for faster voice detection

async def send_audio_loop(ws, mic_stream):
    """Streams recorded microphone PCM audio chunks over WebSocket."""
    global _last_user_audio_ts
    logger.info("🎤 Mic streaming active (64ms chunks)...")
    loop = asyncio.get_running_loop()

    while True:
        try:
            data, _ = await loop.run_in_executor(None, mic_stream.read, MIC_CHUNK)
            if data and not is_ai_speaking:
                _last_user_audio_ts = _time.monotonic()
                b64 = base64.b64encode(bytes(data)).decode("utf-8")
                await ws.send(_dumps({
                    "realtimeInput": {
                        "mediaChunks": [{"mimeType": "audio/pcm;rate=16000", "data": b64}]
                    }
                }))
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"Mic error: {e}")
            break

async def receive_messages_loop(ws, speaker_stream_tuple):
    """Receives Gemini Live WebSocket messages (Audio, Camera requests & Tool Calls)."""
    global is_ai_speaking, _first_ai_audio_ts, _ai_turn_started
    speaker_stream, active_rate = speaker_stream_tuple
    logger.info("🔊 Speaker listener active...")
    loop = asyncio.get_running_loop()
    need_resample = (active_rate == 48000)

    try:
        async for message in ws:
            data = _loads(message)

            if "setupComplete" in data:
                logger.info("🚀 Gemini Live Handshake Complete! Ready for speech.")
                set_eye_state("EYES_NORMAL")

            server_content = data.get("serverContent")
            if server_content:
                if server_content.get("interrupted"):
                    is_ai_speaking = False
                    _ai_turn_started = False
                    set_eye_state("EYES_NORMAL")
                    logger.info("⏹️ AI interrupted by user.")

                model_turn = server_content.get("modelTurn")
                if model_turn:
                    parts = model_turn.get("parts", [])
                    for part in parts:
                        inline_data = part.get("inlineData")
                        if inline_data and inline_data.get("data"):
                            # Log first-byte latency (user audio → AI audio)
                            if not _ai_turn_started:
                                _ai_turn_started = True
                                _first_ai_audio_ts = _time.monotonic()
                                if _last_user_audio_ts > 0:
                                    latency_ms = (_first_ai_audio_ts - _last_user_audio_ts) * 1000
                                    logger.info(f"⚡ LATENCY: {latency_ms:.0f}ms (last mic chunk → first AI audio)")

                            is_ai_speaking = True
                            set_eye_state("EYES_TALKING")

                            audio_bytes = base64.b64decode(inline_data["data"])
                            if len(audio_bytes) % 2 != 0:
                                audio_bytes = audio_bytes[:-1]

                            if need_resample:
                                audio_bytes = _resample_24k_to_48k(audio_bytes)

                            if speaker_stream:
                                await loop.run_in_executor(
                                    None, speaker_stream.write, audio_bytes
                                )

                if server_content.get("turnComplete"):
                    # Log total AI turn duration
                    if _ai_turn_started and _first_ai_audio_ts > 0:
                        turn_duration_ms = (_time.monotonic() - _first_ai_audio_ts) * 1000
                        logger.info(f"🏁 AI turn complete ({turn_duration_ms:.0f}ms total speech)")
                    is_ai_speaking = False
                    _ai_turn_started = False
                    set_eye_state("EYES_NORMAL")
                    await loop.run_in_executor(None, send_uart_command, "IMG_CLEAR")

            # Handle Tool Calls
            tool_call = data.get("toolCall")
            if tool_call:
                set_eye_state("EYES_THINKING")
                function_calls = tool_call.get("functionCalls", [])
                for call in function_calls:
                    fn_name = call.get("name")
                    call_id = call.get("id")
                    args = call.get("args", {})

                    logger.info(f"🔧 Tool: {fn_name}({args})")

                    # 📸 Camera Vision — image FIRST, then toolResponse
                    # Sending image before toolResponse ensures Gemini has the
                    # new frame in context BEFORE it starts composing a reply.
                    if fn_name == "see_object":
                        logger.info("📸 Capturing photo...")
                        jpeg_bytes = await loop.run_in_executor(None, _camera.grab_jpeg)

                        if jpeg_bytes:
                            prompt_text = args.get("prompt", "Describe what you see.")

                            # --- SEND THUMBNAIL TO ESP32 FOR WEB UI ---
                            try:
                                import cv2, numpy as np
                                arr = np.frombuffer(jpeg_bytes, np.uint8)
                                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                                if img is not None:
                                    thumb = cv2.resize(img, (160, 120))
                                    ok, buf = cv2.imencode('.jpg', thumb, [int(cv2.IMWRITE_JPEG_QUALITY), 30])
                                    if ok:
                                        b64_thumb = base64.b64encode(buf.tobytes()).decode('utf-8')
                                        # Send over UART in background so it doesn't block Gemini pipeline
                                        loop.run_in_executor(None, send_uart_command, f"IMG:{b64_thumb}")
                            except Exception as e:
                                logger.warning(f"Failed to send thumbnail to ESP32: {e}")

                            # STEP 1: Inject the NEW image FIRST
                            base64_img = base64.b64encode(jpeg_bytes).decode("utf-8")
                            await ws.send(_dumps({
                                "realtimeInput": {
                                    "mediaChunks": [
                                        {"mimeType": "image/jpeg", "data": base64_img}
                                    ]
                                }
                            }))
                            logger.info(f"✅ Photo injected ({len(jpeg_bytes)}B)")

                            # STEP 2: Now complete the tool call — Gemini already
                            # has the fresh image, so its response will describe it
                            await ws.send(_dumps({
                                "toolResponse": {
                                    "functionResponses": [{
                                        "response": {"output": f"Photo captured. Describe ONLY this latest image. {prompt_text}"},
                                        "id": call_id
                                    }]
                                }
                            }))
                            continue  # skip the generic toolResponse below — already sent
                        else:
                            tool_result = "Failed to capture photo from camera."

                    # Standard Tools Execution
                    elif fn_name in TOOL_MAP:
                        try:
                            func = TOOL_MAP[fn_name]
                            if inspect.iscoroutinefunction(func):
                                tool_result = await func(**args)
                            else:
                                tool_result = func(**args)
                        except Exception as e:
                            tool_result = f"Error executing tool: {e}"
                    else:
                        tool_result = f"Unknown tool '{fn_name}'"

                    # Send Tool Response Back
                    await ws.send(json.dumps({
                        "toolResponse": {
                            "functionResponses": [{
                                "response": {"output": str(tool_result)},
                                "id": call_id
                            }]
                        }
                    }))
                    logger.info(f"✅ Tool done: {tool_result[:80]}")

                set_eye_state("EYES_NORMAL")

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.warning(f"Receive loop error: {e}")

# ---------------------------------------------------------------------------
# Main Execution Runner
# ---------------------------------------------------------------------------
async def run_direct_gemini_robot():
    api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not api_key:
        logger.error("❌ GOOGLE_API_KEY is missing in .env!")
        return

    logger.info("⚡ Booting WALL-E (Ultra-Low Latency Mode)...")
    set_eye_state("EYES_NORMAL")
    
    # Load past memory from memory.json (compact — max 20 most recent facts)
    memory_file = os.path.join(_SCRIPT_DIR, "memory.json")
    past_memory_text = ""
    if os.path.exists(memory_file):
        try:
            with open(memory_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    memories = json.loads(content)
                    if isinstance(memories, list) and len(memories) > 0:
                        # Only inject last 20 facts to keep system prompt small
                        recent = memories[-20:]
                        past_memory_text = "\n\nPAST MEMORIES:\n"
                        for m in recent:
                            if "fact" in m:
                                past_memory_text += f"- {m['fact']}\n"
                            elif "content" in m:
                                past_memory_text += f"- {m['content']}\n"
        except Exception as e:
            logger.error(f"Failed to load memory: {e}")

    final_instruction = AGENT_INSTRUCTION
    if past_memory_text:
        final_instruction += past_memory_text
        logger.info("🧠 Loaded past memories.")

    url = f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key={api_key}"

    setup_payload = {
        "setup": {
            "model": "models/gemini-2.5-flash-native-audio-preview-12-2025",
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {"voiceName": "Puck"}
                    }
                }
            },
            "systemInstruction": {
                "parts": [{"text": final_instruction}]
            },
            "tools": [
                {
                    "functionDeclarations": [
                        {
                            "name": "remember_fact",
                            "description": "Saves an important fact, reminder, or user detail to WALL-E's long-term memory.",
                            "parameters": {
                                "type": "OBJECT",
                                "properties": {
                                    "fact": {"type": "STRING", "description": "The information to remember."}
                                },
                                "required": ["fact"]
                            }
                        },
                        {
                            "name": "see_object",
                            "description": "Captures a frame from camera and sees what is in front of WALL-E.",
                            "parameters": {
                                "type": "OBJECT",
                                "properties": {
                                    "prompt": {"type": "STRING"}
                                }
                            }
                        },
                        {
                            "name": "move_robot",
                            "description": "Controls WALL-E robot movement.",
                            "parameters": {
                                "type": "OBJECT",
                                "properties": {
                                    "direction": {
                                        "type": "STRING",
                                        "enum": ["FORWARD", "BACKWARD", "LEFT", "RIGHT", "STOP"]
                                    }
                                },
                                "required": ["direction"]
                            }
                        },
                        {
                            "name": "get_weather",
                            "description": "Fetches real-time weather for a city.",
                            "parameters": {
                                "type": "OBJECT",
                                "properties": {
                                    "city": {"type": "STRING"}
                                }
                            }
                        },
                        {
                            "name": "get_time_info",
                            "description": "Returns current time and date.",
                            "parameters": {"type": "OBJECT", "properties": {}}
                        },
                        {
                            "name": "search_web",
                            "description": "Performs web search.",
                            "parameters": {
                                "type": "OBJECT",
                                "properties": {
                                    "query": {"type": "STRING"}
                                },
                                "required": ["query"]
                            }
                        }
                    ]
                }
            ]
        }
    }

    mic_stream = sd.RawInputStream(
        samplerate=16000,
        channels=1,
        dtype='int16',
        blocksize=MIC_CHUNK
    )
    mic_stream.start()
    speaker_stream_info = _open_speaker_stream()

    try:
        logger.info("📡 Connecting to Gemini Live WebSocket...")
        async with websockets.connect(url) as ws:
            logger.info("🚀 CONNECTED TO GEMINI LIVE!")

            await ws.send(json.dumps(setup_payload))

            send_task = asyncio.create_task(send_audio_loop(ws, mic_stream))
            recv_task = asyncio.create_task(receive_messages_loop(ws, speaker_stream_info))

            await asyncio.gather(send_task, recv_task)

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        mic_stream.stop()
        mic_stream.close()
        _camera.close()  # release persistent camera
        if speaker_stream_info[0] is not None:
            speaker_stream_info[0].stop()
            speaker_stream_info[0].close()
        set_eye_state("STOP")

if __name__ == "__main__":
    try:
        asyncio.run(run_direct_gemini_robot())
    except KeyboardInterrupt:
        logger.info("🛑 WALL-E Stopped.")