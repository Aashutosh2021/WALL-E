"""
WALL-E AI Companion Robot - Direct Gemini Multimodal Live Client
Direct WebSocket to Google Gemini API (BidiGenerateContent)
Native WebSocket Image Injection for Vision (No 404 REST API Errors!)
"""

import os
import sys
import asyncio
import inspect
import logging
import json
import base64
import sqlite3
import numpy as np
import sounddevice as sd
import websockets
import aiohttp, cv2, gc, time as _time
from datetime import datetime

# Absolute path to script directory (works regardless of CWD)
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
from tools import send_uart_command

# Flag to control mic feedback while AI is speaking
is_ai_speaking = False

# ---------------------------------------------------------------------------
# Camera Frame Capture Helper (Runs in background thread)
# ---------------------------------------------------------------------------
def _capture_camera_jpeg_bytes() -> bytes | None:
    """Captures a frame from webcam and returns raw JPEG bytes."""
    try:
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            logger.error("Camera error: Could not access video capture device.")
            return None
        
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        # Sensor warmup frames
        for _ in range(5): 
            cap.grab()
            
        ret, frame = cap.read()
        cap.release()
        
        if not ret or frame is None:
            logger.error("Camera error: Failed to capture frame.")
            return None
            
        success, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        del frame
        gc.collect()
        
        if success:
            return buffer.tobytes()
        return None
    except Exception as e:
        logger.error(f"Camera capture exception: {e}")
        return None

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

async def _get_weather(city: str = "Delhi") -> str:
    """Fetches real-time weather from Open-Meteo."""
    try:
        async with aiohttp.ClientSession() as sess:
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
        async with aiohttp.ClientSession() as sess:
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
    
    try:
        with open(memory_file, "w", encoding="utf-8") as f:
            json.dump(memories, f, indent=2)
        logger.info(f"🧠 Memory saved to {memory_file}: {fact}")
        return f"✅ Memorized: {fact}"
    except Exception as e:
        logger.error(f"Failed to write to memory.json: {e}")
        return f"❌ Failed to memorize: {e}"


# ---------------------------------------------------------------------------
# SQLite Chat History — auto-saves every conversation turn
# ---------------------------------------------------------------------------
_CHAT_DB_PATH = os.path.join(_SCRIPT_DIR, "walle_memory", "chat_history.db")

def _init_chat_db():
    """Create the chat_history table if it doesn't exist."""
    os.makedirs(os.path.dirname(_CHAT_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_CHAT_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    logger.info(f"🗄️ Chat history DB ready at {_CHAT_DB_PATH}")

def save_chat_message(role: str, content: str):
    """Save a single chat message (user or model) to the DB."""
    try:
        conn = sqlite3.connect(_CHAT_DB_PATH)
        conn.execute(
            "INSERT INTO chat_history (role, content, timestamp) VALUES (?, ?, ?)",
            (role, content, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to save chat message: {e}")

def get_recent_chat_history(limit: int = 50) -> str:
    """Read the last N messages from DB and return as readable text."""
    try:
        conn = sqlite3.connect(_CHAT_DB_PATH)
        rows = conn.execute(
            "SELECT role, content, timestamp FROM chat_history ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()
        if not rows:
            return "No previous history."
        rows.reverse()  # oldest first
        lines = []
        for role, content, ts in rows:
            lines.append(f"[{ts}] {role}: {content}")
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"Failed to read chat history: {e}")
        return "No previous history."

TOOL_MAP = {
    "move_robot": _move_robot,
    "get_weather": _get_weather,
    "get_time_info": _get_time_info,
    "search_web": _search_web,
    "remember_fact": _remember_fact,
}

def set_eye_state(state: str):
    send_uart_command(state)

def resample_24k_to_48k_clean(raw_pcm_bytes):
    pcm_24k = np.frombuffer(raw_pcm_bytes, dtype=np.int16)
    if len(pcm_24k) == 0:
        return b""
    old_indices = np.arange(len(pcm_24k))
    new_indices = np.linspace(0, len(pcm_24k) - 1, len(pcm_24k) * 2)
    pcm_48k = np.interp(new_indices, old_indices, pcm_24k).astype(np.int16)
    return pcm_48k.tobytes()

def _open_speaker_stream():
    for rate in [48000, 44100, 24000]:
        try:
            stream = sd.RawOutputStream(samplerate=rate, channels=1, dtype='int16')
            stream.start()
            logger.info(f"🔊 Speaker output stream opened successfully at {rate}Hz.")
            return stream, rate
        except Exception as e:
            logger.debug(f"Failed opening speaker at {rate}Hz: {e}")
            continue

    logger.warning("❌ Could not open any speaker output stream.")
    return None, 48000

# ---------------------------------------------------------------------------
# WebSocket Audio Input & Output Loops
# ---------------------------------------------------------------------------
async def send_audio_loop(ws, mic_stream):
    """Streams recorded microphone PCM audio chunks over WebSocket."""
    logger.info("🎤 Microphone streaming loop active...")
    loop = asyncio.get_running_loop()
    CHUNK_SIZE = 2048 

    while True:
        try:
            data, overflowed = await loop.run_in_executor(None, mic_stream.read, CHUNK_SIZE)
            if data:
                if is_ai_speaking:
                    data_bytes = b'\x00' * len(data)
                else:
                    data_bytes = bytes(data)

                base64_audio = base64.b64encode(data_bytes).decode("utf-8")
                msg = {
                    "realtimeInput": {
                        "mediaChunks": [
                            {
                                "mimeType": "audio/pcm;rate=16000",
                                "data": base64_audio
                            }
                        ]
                    }
                }
                await ws.send(json.dumps(msg))
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"Mic input error: {e}")
            break

async def receive_messages_loop(ws, speaker_stream_tuple):
    """Receives Gemini Live WebSocket messages (Audio, Camera requests & Tool Calls)."""
    global is_ai_speaking
    speaker_stream, active_rate = speaker_stream_tuple
    logger.info("🔊 Speaker playback listener active...")
    loop = asyncio.get_running_loop()
    _current_turn_text = []  # accumulate text parts from model turn

    try:
        async for message in ws:
            data = json.loads(message)

            if "setupComplete" in data:
                logger.info("🚀 Gemini Live Handshake Complete! Ready for speech.")
                set_eye_state("EYES_NORMAL")

            server_content = data.get("serverContent")
            if server_content:
                if server_content.get("interrupted"):
                    is_ai_speaking = False
                    set_eye_state("EYES_NORMAL")
                    _current_turn_text.clear()

                model_turn = server_content.get("modelTurn")
                if model_turn:
                    parts = model_turn.get("parts", [])
                    for part in parts:
                        # Capture any text parts from the model
                        if "text" in part and part["text"].strip():
                            _current_turn_text.append(part["text"])

                        inline_data = part.get("inlineData")
                        if inline_data and inline_data.get("data"):
                            is_ai_speaking = True
                            set_eye_state("EYES_TALKING")

                            audio_bytes = base64.b64decode(inline_data["data"])
                            if len(audio_bytes) % 2 != 0:
                                audio_bytes = audio_bytes[:-1]

                            if active_rate == 48000:
                                audio_to_play = resample_24k_to_48k_clean(audio_bytes)
                            else:
                                audio_to_play = audio_bytes

                            if speaker_stream:
                                await loop.run_in_executor(
                                    None, speaker_stream.write, audio_to_play
                                )

                if server_content.get("turnComplete"):
                    is_ai_speaking = False
                    set_eye_state("EYES_NORMAL")
                    # Auto-save any text the model produced this turn
                    if _current_turn_text:
                        full_text = " ".join(_current_turn_text).strip()
                        if full_text:
                            save_chat_message("model", full_text)
                            logger.info(f"💾 Auto-saved model response to chat history")
                        _current_turn_text.clear()

            # Handle Tool Calls
            tool_call = data.get("toolCall")
            if tool_call:
                set_eye_state("EYES_THINKING")
                function_calls = tool_call.get("functionCalls", [])
                for call in function_calls:
                    fn_name = call.get("name")
                    call_id = call.get("id")
                    args = call.get("args", {})

                    logger.info(f"🔧 Tool Call Triggered: {fn_name}({args})")
                    # Save user's tool request to chat history
                    save_chat_message("user_tool", f"[Tool: {fn_name}] {json.dumps(args, ensure_ascii=False)}")

                    # 📸 Special Direct Handling for Camera Vision
                    if fn_name == "see_object":
                        logger.info("📸 Capturing photo for Gemini Live Vision...")
                        jpeg_bytes = await loop.run_in_executor(None, _capture_camera_jpeg_bytes)
                        
                        if jpeg_bytes:
                            # 1. Inject JPEG photo directly into Gemini Live WebSocket
                            base64_img = base64.b64encode(jpeg_bytes).decode("utf-8")
                            img_msg = {
                                "realtimeInput": {
                                    "mediaChunks": [
                                        {
                                            "mimeType": "image/jpeg",
                                            "data": base64_img
                                        }
                                    ]
                                }
                            }
                            await ws.send(json.dumps(img_msg))
                            tool_result = "Photo captured and injected into your vision stream. Describe what you see in the photo."
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

                    # 2. Send Tool Response Back over WebSocket
                    tool_resp_msg = {
                        "toolResponse": {
                            "functionResponses": [
                                {
                                    "response": {"output": str(tool_result)},
                                    "id": call_id
                                }
                            ]
                        }
                    }
                    await ws.send(json.dumps(tool_resp_msg))
                    logger.info(f"✅ Tool Response Sent: {tool_result}")
                    # Save tool result to chat history
                    save_chat_message("tool_result", f"[{fn_name}] {str(tool_result)[:500]}")

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

    logger.info("⚡ Booting Direct Gemini Live Raw WebSocket Client...")
    set_eye_state("EYES_NORMAL")
    
    # Initialize chat history database
    _init_chat_db()

    # Load past memory from memory.json
    memory_file = os.path.join(_SCRIPT_DIR, "memory.json")
    past_memory_text = ""
    if os.path.exists(memory_file):
        try:
            with open(memory_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    memories = json.loads(content)
                    if isinstance(memories, list) and len(memories) > 0:
                        past_memory_text = "\n\n--- PAST MEMORIES & FACTS ---\n"
                        for m in memories:
                            if "fact" in m:
                                past_memory_text += f"- [{m.get('date')}] {m['fact']}\n"
                            elif "content" in m:
                                past_memory_text += f"- [{m.get('date')}] {m.get('role', 'unknown')}: {m['content']}\n"
        except Exception as e:
            logger.error(f"Failed to load memory for initialization: {e}")

    # Load past chat history from SQLite
    past_chat_text = get_recent_chat_history(50)
    if past_chat_text and past_chat_text != "No previous history.":
        past_memory_text += "\n\n--- PAST CONVERSATIONS ---\n" + past_chat_text + "\n"
        logger.info("🧠 Loaded past chat history from SQLite DB")

    final_instruction = AGENT_INSTRUCTION
    if past_memory_text:
        final_instruction += past_memory_text
        logger.info(f"🧠 Loaded past memories from {memory_file}")

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
                            "description": "Saves an important fact, reminder, or user detail to WALL-E's long-term memory so he remembers it forever.",
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
        blocksize=2048
    )
    mic_stream.start()
    speaker_stream_info = _open_speaker_stream()

    try:
        logger.info("📡 Connecting to Google Gemini Live WebSocket...")
        async with websockets.connect(url) as ws:
            logger.info("🚀 CONNECTED TO GEMINI LIVE WEBSOCKET!")

            await ws.send(json.dumps(setup_payload))

            send_task = asyncio.create_task(send_audio_loop(ws, mic_stream))
            recv_task = asyncio.create_task(receive_messages_loop(ws, speaker_stream_info))

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
        logger.info("🛑 WALL-E Direct Gemini Live Stopped by User.")