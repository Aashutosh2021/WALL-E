"""
WALL-E AI Companion Robot — Direct Gemini Fast Client

Optimized for lower latency:
- move_robot UART command is sent before non-critical eye commands.
- No EYES_THINKING before movement commands.
- UART image thumbnails disabled by default.
- Vision disabled by default for strict low-latency mode.
- Persistent HTTP session for vision.
- Smaller mic chunks.
"""

import os
import sys
import json
import base64
import asyncio
import inspect
import logging
import shutil
import subprocess
import time as _time

import numpy as np
import sounddevice as sd
import websockets
import aiohttp

try:
    import orjson

    def _dumps(obj) -> str:
        return orjson.dumps(obj).decode()

    _loads = orjson.loads

except ImportError:

    def _dumps(obj) -> str:
        return json.dumps(obj)

    _loads = json.loads

from dotenv import load_dotenv

load_dotenv(override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)

from prompts import AGENT_INSTRUCTION
from tools import send_uart_command, TOOL_MAP

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MIC_CHUNK = int(os.getenv("MIC_CHUNK", "512"))

ENABLE_ESP32_IMAGE = os.getenv("ENABLE_ESP32_IMAGE", "0").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

ENABLE_VISION = os.getenv("ENABLE_VISION", "0").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

VALID_MOVE = {"FORWARD", "BACKWARD", "LEFT", "RIGHT", "STOP"}

# ---------------------------------------------------------------------------
# Runtime state
# ---------------------------------------------------------------------------

is_ai_speaking = False

_last_user_audio_ts = 0.0
_first_ai_audio_ts = 0.0
_ai_turn_started = False

_current_eye_state = None


def set_eye_state(state: str) -> None:
    """Send eye state only when it changes."""
    global _current_eye_state

    valid_states = {
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

    if state not in valid_states:
        return

    if state == _current_eye_state:
        return

    _current_eye_state = state

    try:
        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, send_uart_command, state)
    except RuntimeError:
        send_uart_command(state)


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

def _resample_24k_to_48k(raw_pcm_bytes: bytes) -> bytes:
    pcm = np.frombuffer(raw_pcm_bytes, dtype=np.int16)
    if len(pcm) == 0:
        return b""
    return np.repeat(pcm, 2).tobytes()


def _open_speaker_stream():
    for rate in (24000, 48000):
        try:
            stream = sd.RawOutputStream(
                samplerate=rate,
                channels=1,
                dtype="int16",
            )
            stream.start()
            logger.info(f"Speaker opened at {rate}Hz")
            return stream, rate
        except Exception:
            continue

    logger.warning("Could not open speaker stream.")
    return None, 48000


# ---------------------------------------------------------------------------
# Mic loop
# ---------------------------------------------------------------------------

async def send_audio_loop(ws, mic_stream):
    global _last_user_audio_ts

    logger.info(f"Mic streaming active, chunk={MIC_CHUNK}")
    loop = asyncio.get_running_loop()

    while True:
        try:
            data, _ = await loop.run_in_executor(
                None,
                mic_stream.read,
                MIC_CHUNK,
            )

            if data and not is_ai_speaking:
                _last_user_audio_ts = _time.monotonic()

                b64 = base64.b64encode(bytes(data)).decode("utf-8")

                await ws.send(
                    _dumps(
                        {
                            "realtimeInput": {
                                "mediaChunks": [
                                    {
                                        "mimeType": "audio/pcm;rate=16000",
                                        "data": b64,
                                    }
                                ]
                            }
                        }
                    )
                )

        except asyncio.CancelledError:
            break

        except Exception as e:
            logger.warning(f"Mic error: {e}")
            break


# ---------------------------------------------------------------------------
# Vision helpers
# ---------------------------------------------------------------------------

_vision_http_session: aiohttp.ClientSession | None = None


async def _get_vision_session() -> aiohttp.ClientSession:
    global _vision_http_session

    if _vision_http_session is None or _vision_http_session.closed:
        _vision_http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10)
        )

    return _vision_http_session


def _grab_jpeg_sync() -> bytes | None:
    """
    Simple JPEG grabber for vision.
    Vision is disabled by default in low-latency mode.
    """
    try:
        if shutil.which("rpicam-still"):
            result = subprocess.run(
                [
                    "rpicam-still",
                    "--output",
                    "-",
                    "--width",
                    "320",
                    "--height",
                    "240",
                    "--quality",
                    "40",
                    "--nopreview",
                    "--immediate",
                    "1",
                    "--encoding",
                    "jpg",
                    "--timeout",
                    "1",
                ],
                capture_output=True,
                timeout=4,
            )

            if result.returncode == 0 and len(result.stdout) > 100:
                return result.stdout

        if shutil.which("libcamera-still"):
            result = subprocess.run(
                [
                    "libcamera-still",
                    "--output",
                    "-",
                    "--width",
                    "320",
                    "--height",
                    "240",
                    "--quality",
                    "40",
                    "--nopreview",
                    "--immediate",
                    "--encoding",
                    "jpg",
                    "--timeout",
                    "1",
                ],
                capture_output=True,
                timeout=4,
            )

            if result.returncode == 0 and len(result.stdout) > 100:
                return result.stdout

        import cv2

        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            return None

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        # Flush stale frames.
        for _ in range(2):
            cap.grab()

        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            return None

        ok, buf = cv2.imencode(
            ".jpg",
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), 40],
        )

        if not ok:
            return None

        return buf.tobytes()

    except Exception as e:
        logger.warning(f"Camera capture failed: {e}")
        return None


async def _analyze_image_gemini(
    jpeg_bytes: bytes,
    prompt: str,
    api_key: str,
) -> str:
    if not ENABLE_VISION:
        return "Vision is disabled for low-latency mode."

    if not jpeg_bytes:
        return "No image captured."

    model = os.getenv("GEMINI_VISION_MODEL", "gemini-2.0-flash")

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )

    img_b64 = base64.b64encode(jpeg_bytes).decode("utf-8")

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            "Briefly describe what you see in 1-2 short sentences. "
                            f"Focus on: {prompt}"
                        )
                    },
                    {
                        "inlineData": {
                            "mimeType": "image/jpeg",
                            "data": img_b64,
                        }
                    },
                ]
            }
        ],
        "generationConfig": {
            "maxOutputTokens": 80,
            "temperature": 0.2,
        },
    }

    try:
        sess = await _get_vision_session()

        t0 = _time.monotonic()

        async with sess.post(url, json=payload) as resp:
            if resp.status != 200:
                err = await resp.text()
                logger.warning(f"Vision API error {resp.status}: {err[:200]}")
                return "Could not analyze the image right now."

            data = await resp.json()

        logger.info(
            f"Vision call took {(_time.monotonic() - t0) * 1000:.0f}ms"
        )

        candidates = data.get("candidates") or []
        if not candidates:
            return "I looked, but couldn't recognize anything."

        parts = candidates[0].get("content", {}).get("parts", [])
        texts = [p.get("text", "") for p in parts if p.get("text")]

        if texts:
            return " ".join(texts).strip()

        return "I looked, but couldn't recognize anything."

    except Exception as e:
        logger.warning(f"Vision request failed: {e}")
        return "Image analysis failed due to a network error."


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

async def _send_tool_response(ws, call_id: str, output: str) -> None:
    await ws.send(
        _dumps(
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


async def _handle_non_move_tool(call: dict) -> str:
    fn_name = call.get("name")
    args = call.get("args", {}) or {}

    if fn_name == "see_object":
        if not ENABLE_VISION:
            return "Vision is disabled for low-latency mode."

        loop = asyncio.get_running_loop()

        jpeg_bytes = await loop.run_in_executor(None, _grab_jpeg_sync)

        if not jpeg_bytes:
            return "Failed to capture photo from camera."

        if ENABLE_ESP32_IMAGE:
            # Optional and intentionally off by default.
            # Sending base64 over UART can delay motor commands.
            try:
                thumb_b64 = base64.b64encode(jpeg_bytes).decode("utf-8")
                await loop.run_in_executor(
                    None,
                    send_uart_command,
                    f"IMG:{thumb_b64}",
                )
            except Exception as e:
                logger.warning(f"Failed sending image to ESP32: {e}")

        api_key = os.getenv("GOOGLE_API_KEY", "").strip()
        prompt_text = args.get("prompt", "Describe what you see.")

        return await _analyze_image_gemini(
            jpeg_bytes,
            prompt_text,
            api_key,
        )

    func = TOOL_MAP.get(fn_name)

    if func is None:
        return f"Unknown tool '{fn_name}'"

    try:
        if inspect.iscoroutinefunction(func):
            return str(await func(**args))

        return str(await asyncio.to_thread(func, **args))

    except Exception as e:
        return f"Error executing tool: {e}"


# ---------------------------------------------------------------------------
# Receive loop
# ---------------------------------------------------------------------------

async def receive_messages_loop(ws, speaker_stream_tuple):
    global is_ai_speaking
    global _first_ai_audio_ts
    global _ai_turn_started

    speaker_stream, active_rate = speaker_stream_tuple

    logger.info("Speaker listener active")

    loop = asyncio.get_running_loop()
    need_resample = active_rate == 48000

    try:
        async for message in ws:
            data = _loads(message)

            if "setupComplete" in data:
                logger.info("Gemini Live handshake complete")
                set_eye_state("EYES_NORMAL")

            server_content = data.get("serverContent")

            if server_content:
                if server_content.get("interrupted"):
                    is_ai_speaking = False
                    _ai_turn_started = False
                    set_eye_state("EYES_NORMAL")
                    logger.info("AI interrupted by user")

                model_turn = server_content.get("modelTurn")

                if model_turn:
                    parts = model_turn.get("parts", [])

                    for part in parts:
                        inline_data = part.get("inlineData")

                        if inline_data and inline_data.get("data"):
                            if not _ai_turn_started:
                                _ai_turn_started = True
                                _first_ai_audio_ts = _time.monotonic()

                                if _last_user_audio_ts > 0:
                                    latency_ms = (
                                        _first_ai_audio_ts - _last_user_audio_ts
                                    ) * 1000

                                    logger.info(
                                        f"LATENCY: {latency_ms:.0f}ms "
                                        "last mic chunk -> first AI audio"
                                    )

                            is_ai_speaking = True
                            set_eye_state("EYES_TALKING")

                            audio_bytes = base64.b64decode(
                                inline_data["data"]
                            )

                            if len(audio_bytes) % 2 != 0:
                                audio_bytes = audio_bytes[:-1]

                            if need_resample:
                                audio_bytes = _resample_24k_to_48k(audio_bytes)

                            if speaker_stream:
                                await loop.run_in_executor(
                                    None,
                                    speaker_stream.write,
                                    audio_bytes,
                                )

                if server_content.get("turnComplete"):
                    if _ai_turn_started and _first_ai_audio_ts > 0:
                        turn_duration_ms = (
                            _time.monotonic() - _first_ai_audio_ts
                        ) * 1000

                        logger.info(
                            f"AI turn complete ({turn_duration_ms:.0f}ms)"
                        )

                    is_ai_speaking = False
                    _ai_turn_started = False
                    set_eye_state("EYES_NORMAL")

                    if ENABLE_ESP32_IMAGE:
                        await loop.run_in_executor(
                            None,
                            send_uart_command,
                            "IMG_CLEAR",
                        )

            tool_call = data.get("toolCall")

            if tool_call:
                function_calls = tool_call.get("functionCalls", [])

                move_calls = [
                    c
                    for c in function_calls
                    if c.get("name") == "move_robot"
                ]

                other_calls = [
                    c
                    for c in function_calls
                    if c.get("name") != "move_robot"
                ]

                # Execute movement immediately and do not send EYES_THINKING
                # before movement. This avoids extra UART chatter.
                for call in move_calls:
                    call_id = call.get("id", "")
                    args = call.get("args", {}) or {}

                    direction = str(args.get("direction", "STOP")).upper().strip()

                    if direction in VALID_MOVE:
                        await loop.run_in_executor(
                            None,
                            send_uart_command,
                            direction,
                        )

                        if direction == "STOP":
                            result = "WALL-E stopped."
                        else:
                            result = f"WALL-E moving {direction}."
                    else:
                        result = (
                            f"Invalid direction '{direction}'. "
                            "Use FORWARD, BACKWARD, LEFT, RIGHT, STOP."
                        )

                    await _send_tool_response(ws, call_id, result)
                    logger.info(f"Move tool done: {result}")

                if other_calls:
                    set_eye_state("EYES_THINKING")

                    for call in other_calls:
                        call_id = call.get("id", "")
                        fn_name = call.get("name")

                        logger.info(f"Tool: {fn_name}")

                        result = await _handle_non_move_tool(call)

                        await _send_tool_response(ws, call_id, result)

                        logger.info(f"Tool done: {str(result)[:80]}")

                    set_eye_state("EYES_NORMAL")

    except asyncio.CancelledError:
        pass

    except Exception as e:
        logger.warning(f"Receive loop error: {e}")


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

async def run_direct_gemini_robot():
    api_key = os.getenv("GOOGLE_API_KEY", "").strip()

    if not api_key:
        logger.error("GOOGLE_API_KEY is missing in .env")
        return

    logger.info("Booting WALL-E fast mode")

    set_eye_state("EYES_NORMAL")

    memory_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "memory.json",
    )

    past_memory_text = ""

    if os.path.exists(memory_file):
        try:
            with open(memory_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    memories = json.loads(content)

                    if isinstance(memories, list) and memories:
                        recent = memories[-20:]
                        past_memory_text = "\n\nPAST MEMORIES:\n"

                        for m in recent:
                            if isinstance(m, dict):
                                fact = m.get("fact") or m.get("content")
                                if fact:
                                    past_memory_text += f"- {fact}\n"

        except Exception as e:
            logger.error(f"Failed to load memory: {e}")

    final_instruction = AGENT_INSTRUCTION

    if past_memory_text:
        final_instruction += past_memory_text
        logger.info("Loaded past memories")

    model = os.getenv(
        "GEMINI_LIVE_MODEL",
        "models/gemini-2.5-flash-native-audio-preview-12-2025",
    )

    url = (
        "wss://generativelanguage.googleapis.com/ws/"
        "google.ai.generativelanguage.v1beta.GenerativeService."
        f"BidiGenerateContent?key={api_key}"
    )

    setup_payload = {
        "setup": {
            "model": model,
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {
                            "voiceName": "Puck"
                        }
                    }
                },
            },
            "systemInstruction": {
                "parts": [{"text": final_instruction}]
            },
            "tools": [
                {
                    "functionDeclarations": [
                        {
                            "name": "move_robot",
                            "description": "Controls WALL-E robot movement.",
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
                                "Captures a photo from WALL-E's camera and "
                                "returns a description."
                            ),
                            "parameters": {
                                "type": "OBJECT",
                                "properties": {
                                    "prompt": {
                                        "type": "STRING",
                                        "description": (
                                            "What to analyze in the image"
                                        ),
                                    }
                                },
                            },
                        },
                        {
                            "name": "get_weather",
                            "description": "Fetches real-time weather.",
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
                            "description": "Returns current time and date.",
                            "parameters": {
                                "type": "OBJECT",
                                "properties": {},
                            },
                        },
                        {
                            "name": "search_web",
                            "description": "Performs web search.",
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
                            "description": (
                                "Saves an important fact to WALL-E's memory."
                            ),
                            "parameters": {
                                "type": "OBJECT",
                                "properties": {
                                    "fact": {
                                        "type": "STRING",
                                        "description": (
                                            "The information to remember."
                                        ),
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

    mic_stream = sd.RawInputStream(
        samplerate=16000,
        channels=1,
        dtype="int16",
        blocksize=MIC_CHUNK,
    )

    mic_stream.start()

    speaker_stream_info = _open_speaker_stream()

    try:
        logger.info("Connecting to Gemini Live WebSocket")

        async with websockets.connect(
            url,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=1,
            max_size=4 * 1024 * 1024,
        ) as ws:

            logger.info("Connected to Gemini Live")

            await ws.send(json.dumps(setup_payload))

            send_task = asyncio.create_task(
                send_audio_loop(ws, mic_stream)
            )

            recv_task = asyncio.create_task(
                receive_messages_loop(ws, speaker_stream_info)
            )

            await asyncio.gather(send_task, recv_task)

    except Exception as e:
        logger.error(f"WebSocket error: {e}")

    finally:
        mic_stream.stop()
        mic_stream.close()

        if speaker_stream_info[0] is not None:
            speaker_stream_info[0].stop()
            speaker_stream_info[0].close()

        set_eye_state("STOP")


if __name__ == "__main__":
    try:
        asyncio.run(run_direct_gemini_robot())
    except KeyboardInterrupt:
        logger.info("WALL-E stopped.")