"""WALL-E fast Gemini Live client.
- Gemini Live handles realtime voice/tool calling.
- Gemini 3.5 Flash handles one-shot camera analysis over REST.
- ESP32 is controlled over persistent USB serial (/dev/ttyUSB0 by default).
- Camera stays warm with picamera2 when available.
"""
import os, sys, asyncio, logging, json, base64, subprocess, shutil, time
import inspect
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("WALLE")
BASE = os.path.dirname(os.path.abspath(__file__))

MIC_CHUNK = int(os.getenv("MIC_CHUNK", "512"))
VISION_ENABLED = os.getenv("ENABLE_VISION", "1").lower() in {"1","true","yes","on"}
ESP_IMAGE = os.getenv("ENABLE_ESP32_IMAGE", "0").lower() in {"1","true","yes","on"}
VISION_MODEL = os.getenv("GEMINI_VISION_MODEL", "gemini-3.5-flash")
LIVE_MODEL = os.getenv("GEMINI_LIVE_MODEL", "models/gemini-2.5-flash-native-audio-preview-12-2025")

is_ai_speaking = False
_last_audio = 0.0
_turn_started = False
_current_eye = None

# ---------------- Camera ----------------
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
                cfg = self.picam.create_still_configuration(main={"size":(320,240),"format":"RGB888"})
                self.picam.configure(cfg)
                self.picam.start()
                time.sleep(0.15)
                logger.info("Camera: persistent picamera2 320x240")
            except Exception as e:
                logger.warning("picamera2 unavailable: %s", e)
                self.picam = None
        if self.picam is None:
            logger.info("Camera fallback: %s", "rpicam-still" if HAS_RPICAM else "libcamera-still" if HAS_LIBCAMERA else "OpenCV")

    def grab(self):
        try:
            import cv2
            if self.picam is not None:
                # Drop buffered frames so "look" uses the latest scene.
                self.picam.capture_array("main")
                self.picam.capture_array("main")
                frame = self.picam.capture_array("main")
                ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
                return buf.tobytes() if ok else None
            if HAS_RPICAM:
                r = subprocess.run(["rpicam-still","--output","-","--width","320","--height","240","--quality","50","--nopreview","--immediate","1","--encoding","jpg","--timeout","1"], capture_output=True, timeout=4)
                return r.stdout if r.returncode == 0 and len(r.stdout) > 100 else None
            if HAS_LIBCAMERA:
                r = subprocess.run(["libcamera-still","--output","-","--width","320","--height","240","--quality","50","--nopreview","--immediate","--encoding","jpg","--timeout","1"], capture_output=True, timeout=4)
                return r.stdout if r.returncode == 0 and len(r.stdout) > 100 else None
            if self.cap is None or not self.cap.isOpened():
                self.cap = cv2.VideoCapture(0)
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self.cap.grab(); self.cap.grab()
            ok, frame = self.cap.read()
            if not ok: return None
            ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY),50])
            return buf.tobytes() if ok else None
        except Exception as e:
            logger.warning("Camera capture failed: %s", e)
            return None

    def close(self):
        if self.picam:
            try: self.picam.stop(); self.picam.close()
            except Exception: pass
        if self.cap:
            try: self.cap.release()
            except Exception: pass

camera = Camera()

# ---------------- Eyes ----------------
def eye(state):
    global _current_eye
    valid = {"BOOT","IDLE","LISTEN","SPEAK","EYES_TALKING","EYES_NORMAL","THINK","STOP","HAPPY","SAD","ANGRY"}
    if state not in valid or state == _current_eye: return
    _current_eye = state
    try:
        asyncio.get_running_loop().run_in_executor(None, send_uart_command, state)
    except RuntimeError:
        send_uart_command(state)

# ---------------- Audio ----------------
def open_speaker():
    for rate in (24000, 48000):
        try:
            s = sd.RawOutputStream(samplerate=rate, channels=1, dtype="int16")
            s.start(); return s, rate
        except Exception: pass
    return None, 24000

def resample24to48(b):
    return np.repeat(np.frombuffer(b, dtype=np.int16), 2).tobytes()

async def mic_loop(ws, mic):
    global _last_audio
    loop = asyncio.get_running_loop()
    while True:
        try:
            data, _ = await loop.run_in_executor(None, mic.read, MIC_CHUNK)
            if data and not is_ai_speaking:
                _last_audio = time.monotonic()
                await ws.send(dumps({"realtimeInput":{"mediaChunks":[{"mimeType":"audio/pcm;rate=16000","data":base64.b64encode(bytes(data)).decode()}]}}))
        except asyncio.CancelledError: return
        except Exception as e:
            logger.warning("Mic loop stopped: %s", e); return

# ---------------- Gemini vision ----------------
vision_session = None
async def get_vision_session():
    global vision_session
    if vision_session is None or vision_session.closed:
        vision_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12))
    return vision_session

async def analyze_image(jpeg, prompt, key):
    if not VISION_ENABLED: return "Vision is disabled."
    if not key: return "GOOGLE_API_KEY is missing."
    if not jpeg: return "No image captured."
    model = os.getenv("GEMINI_VISION_MODEL", VISION_MODEL)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {"contents":[{"parts":[{"text":f"Describe what you see in 1-2 concise sentences. Focus on: {prompt or 'everything important in the scene.'}"},{"inlineData":{"mimeType":"image/jpeg","data":base64.b64encode(jpeg).decode()}}]}],"generationConfig":{"maxOutputTokens":100}}
    try:
        s = await get_vision_session()
        t=time.monotonic()
        async with s.post(url, params={"key":key}, json=payload) as r:
            text=await r.text()
            if r.status != 200:
                logger.error("Gemini vision HTTP %s: %s", r.status, text[:500])
                return f"Gemini vision error {r.status}: {text[:220]}"
        d=json.loads(text)
        parts=(d.get("candidates") or [{}])[0].get("content",{}).get("parts",[])
        out=" ".join(p.get("text","") for p in parts if p.get("text")).strip()
        logger.info("Vision %.0f ms (%s)", (time.monotonic()-t)*1000, model)
        return out or "I could not recognize anything clearly."
    except Exception as e:
        logger.exception("Vision request failed")
        return f"Image analysis failed: {e}"

async def send_tool_response(ws, call_id, output):
    await ws.send(dumps({"toolResponse":{"functionResponses":[{"response":{"output":str(output)},"id":call_id}]}}))

async def handle_other_tool(call):
    name=call.get("name"); args=call.get("args") or {}
    if name == "see_object":
        loop=asyncio.get_running_loop()
        jpeg=await loop.run_in_executor(None,camera.grab)
        if not jpeg: return "Failed to capture a photo from WALL-E's camera."
        if ESP_IMAGE:
            # Only use this if the ESP32 web UI really needs the image; it can add UART load.
            try:
                await loop.run_in_executor(None,send_uart_command,"IMG:"+base64.b64encode(jpeg).decode())
            except Exception: pass
        return await analyze_image(jpeg,args.get("prompt","Describe what you see."),os.getenv("GOOGLE_API_KEY",""))
    func=TOOL_MAP.get(name)
    if not func: return f"Unknown tool '{name}'"
    try:
        if inspect.iscoroutinefunction(func): return await func(**args)
        return await asyncio.to_thread(func,**args)
    except Exception as e:
        return f"Error executing tool: {e}"

# ---------------- Receive / tool handling ----------------
async def receive_loop(ws, speaker_info):
    global is_ai_speaking, _turn_started
    speaker, rate=speaker_info
    loop=asyncio.get_running_loop(); need_resample=rate==48000
    async for raw in ws:
        try: data=loads(raw)
        except Exception: continue
        if "setupComplete" in data:
            logger.info("Gemini Live ready")
            eye("EYES_NORMAL")
        sc=data.get("serverContent")
        if sc:
            if sc.get("interrupted"):
                is_ai_speaking=False; _turn_started=False; eye("EYES_NORMAL")
            mt=sc.get("modelTurn")
            if mt:
                for p in mt.get("parts",[]):
                    x=p.get("inlineData")
                    if x and x.get("data"):
                        is_ai_speaking=True
                        eye("EYES_TALKING")
                        audio=base64.b64decode(x["data"])
                        if len(audio)%2: audio=audio[:-1]
                        if need_resample: audio=resample24to48(audio)
                        if speaker: await loop.run_in_executor(None,speaker.write,audio)
            if sc.get("turnComplete"):
                is_ai_speaking=False; _turn_started=False; eye("EYES_NORMAL")
                if ESP_IMAGE: await loop.run_in_executor(None,send_uart_command,"IMG_CLEAR")
        tc=data.get("toolCall")
        if not tc: continue
        calls=tc.get("functionCalls",[])
        # Movement gets the shortest possible path to UART.
        moves=[c for c in calls if c.get("name")=="move_robot"]
        others=[c for c in calls if c.get("name")!="move_robot"]
        for c in moves:
            cid=c.get("id",""); d=str((c.get("args") or {}).get("direction","STOP")).upper().strip()
            if d in {"FORWARD","BACKWARD","LEFT","RIGHT","STOP"}:
                ok=await loop.run_in_executor(None,send_uart_command,d)
                result=("WALL-E stopped." if d=="STOP" else f"WALL-E moving {d}.") if ok else "ESP32 USB UART unavailable."
            else: result=f"Invalid direction '{d}'."
            await send_tool_response(ws,cid,result)
        if others:
            eye("THINK")
            # Do not serialize unrelated tools unnecessarily; one at a time keeps tool ordering deterministic.
            for c in others:
                result=await handle_other_tool(c)
                await send_tool_response(ws,c.get("id",""),result)
            eye("EYES_NORMAL")

async def run():
    key=os.getenv("GOOGLE_API_KEY","").strip()
    if not key:
        logger.error("GOOGLE_API_KEY missing in .env"); return
    memory=os.path.join(BASE,"memory.json")
    memory_text=""
    try:
        if os.path.exists(memory):
            with open(memory,encoding="utf-8") as f: m=json.load(f)
            if isinstance(m,list): memory_text="\n\nPAST MEMORIES:\n"+"\n".join(f"- {x.get('fact') or x.get('content')}" for x in m[-20:] if isinstance(x,dict) and (x.get('fact') or x.get('content')))
    except Exception: pass
    instruction=AGENT_INSTRUCTION+memory_text
    setup={"setup":{"model":LIVE_MODEL,"generationConfig":{"responseModalities":["AUDIO"],"speechConfig":{"voiceConfig":{"prebuiltVoiceConfig":{"voiceName":"Puck"}}}},"systemInstruction":{"parts":[{"text":instruction}]},"tools":[{"functionDeclarations":[
        {"name":"move_robot","description":"Immediately controls WALL-E movement. Use for forward, backward, left, right, stop.","parameters":{"type":"OBJECT","properties":{"direction":{"type":"STRING","enum":["FORWARD","BACKWARD","LEFT","RIGHT","STOP"]}},"required":["direction"]}},
        {"name":"see_object","description":"Captures a fresh camera frame and describes what WALL-E sees. Use whenever the user asks what you can see/look at.","parameters":{"type":"OBJECT","properties":{"prompt":{"type":"STRING","description":"What to inspect in the image"}}}},
        {"name":"get_weather","description":"Gets current weather.","parameters":{"type":"OBJECT","properties":{"city":{"type":"STRING"}}}},
        {"name":"get_time_info","description":"Gets current local time and date.","parameters":{"type":"OBJECT","properties":{}}},
        {"name":"search_web","description":"Searches the web for a factual query.","parameters":{"type":"OBJECT","properties":{"query":{"type":"STRING"}},"required":["query"]}},
        {"name":"remember_fact","description":"Stores an important fact in long-term memory.","parameters":{"type":"OBJECT","properties":{"fact":{"type":"STRING"}},"required":["fact"]}}
    ]}]}}
    mic=sd.RawInputStream(samplerate=16000,channels=1,dtype="int16",blocksize=MIC_CHUNK); mic.start()
    speaker_info=open_speaker()
    url="wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key="+key
    try:
        logger.info("WALL-E fast boot | Live=%s | Vision=%s (%s) | UART=%s",LIVE_MODEL,VISION_ENABLED,VISION_MODEL,os.getenv("SERIAL_PORT","/dev/ttyUSB0"))
        eye("EYES_NORMAL")
        async with websockets.connect(url,ping_interval=20,ping_timeout=20,close_timeout=1,max_size=4*1024*1024) as ws:
            await ws.send(dumps(setup))
            a=asyncio.create_task(mic_loop(ws,mic)); b=asyncio.create_task(receive_loop(ws,speaker_info))
            done,_=await asyncio.wait({a,b},return_when=asyncio.FIRST_EXCEPTION)
            for t in (a,b):
                if not t.done(): t.cancel()
    except Exception as e:
        logger.exception("Gemini Live connection failed: %s",e)
    finally:
        try: mic.stop(); mic.close()
        except Exception: pass
        if speaker_info[0]:
            try: speaker_info[0].stop(); speaker_info[0].close()
            except Exception: pass
        eye("STOP"); close_uart()
        if vision_session and not vision_session.closed: await vision_session.close()
        camera.close()

if __name__=="__main__":
    try: asyncio.run(run())
    except KeyboardInterrupt: pass