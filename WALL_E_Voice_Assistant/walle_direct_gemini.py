"""
WALL-E AI Companion Robot - Direct Gemini Multimodal Live Client
Direct WebSocket to Google Gemini API (BidiGenerateContent)
Ultra Low Latency (~300ms) & Ultra Low RAM Overhead (~30MB)
Uses sounddevice for cross-platform zero-dependency audio I/O.
"""

import os
import sys
import asyncio
import logging
import traceback
import sounddevice as sd

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv(override=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

from google import genai
from google.genai import types

from prompts import AGENT_INSTRUCTION
from tools import (
    send_uart_command,
    move_robot,
    see_object,
    get_weather,
    get_time_info,
    search_web
)

# Map available tools for direct execution
TOOL_MAP = {
    "move_robot": move_robot,
    "see_object": see_object,
    "get_weather": get_weather,
    "get_time_info": get_time_info,
    "search_web": search_web,
}

def set_eye_state(state: str):
    """Sends OLED eye animation command to ESP32 over UART serial."""
    send_uart_command(state)

async def audio_input_loop(session, mic_stream):
    """Captures mic audio & streams PCM chunks to Gemini Live WebSocket."""
    logger.info("🎤 Microphone audio streaming loop active...")
    CHUNK_SIZE = 1024
    loop = asyncio.get_running_loop()
    
    while True:
        try:
            data, overflowed = await loop.run_in_executor(None, mic_stream.read, CHUNK_SIZE)
            if data:
                await session.send(
                    realtime_input=types.LiveClientRealtimeInput(
                        media_chunks=[types.Blob(data=bytes(data), mime_type="audio/pcm")]
                    )
                )
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Mic input error: {e}")
            await asyncio.sleep(0.01)

async def audio_output_loop(session, speaker_stream):
    """Receives responses from Gemini Live WebSocket & plays audio / handles tool calls."""
    logger.info("🔊 Speaker playback loop active...")
    loop = asyncio.get_running_loop()
    
    async for response in session.receive():
        server_content = response.server_content
        if server_content is not None:
            model_turn = server_content.model_turn
            if model_turn is not None:
                for part in model_turn.parts:
                    if part.inline_data and part.inline_data.data:
                        set_eye_state("EYES_TALKING")
                        await loop.run_in_executor(None, speaker_stream.write, part.inline_data.data)
                        
            if server_content.turn_complete:
                set_eye_state("EYES_NORMAL")

        # Handle Function Calling (Tool Calls)
        tool_call = response.tool_call
        if tool_call is not None:
            set_eye_state("EYES_THINKING")
            for function_call in tool_call.function_calls:
                name = function_call.name
                call_id = function_call.id
                args = function_call.args or {}
                
                logger.info(f"🔧 Direct Tool Call Triggered: {name}({args})")
                
                result = "Error executing tool"
                if name in TOOL_MAP:
                    try:
                        func = TOOL_MAP[name]
                        if asyncio.iscoroutinefunction(func):
                            result = await func(**args)
                        else:
                            result = func(**args)
                    except Exception as e:
                        result = f"Error: {e}"
                
                # Send Tool Response back over WebSocket
                await session.send(
                    realtime_input=types.LiveClientRealtimeInput(
                        tool_response=types.LiveClientToolResponse(
                            function_responses=[
                                types.FunctionResponse(
                                    name=name,
                                    id=call_id,
                                    response={"result": str(result)}
                                )
                            ]
                        )
                    )
                )
                logger.info(f"✅ Tool Response Sent: {result}")
            set_eye_state("EYES_NORMAL")

async def run_direct_gemini_robot():
    api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not api_key:
        logger.error("❌ GOOGLE_API_KEY is missing in .env! Please set a valid Gemini API key.")
        return

    logger.info("⚡ Booting Direct Gemini Live WebSocket Client (~300ms Latency)...")
    set_eye_state("EYES_NORMAL")

    client = genai.Client(api_key=api_key)

    # Configure Direct Multimodal Live Session
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Puck")
            )
        ),
        system_instruction=types.Content(
            parts=[types.Part.from_text(text=AGENT_INSTRUCTION)]
        ),
        tools=[move_robot, see_object, get_weather, get_time_info, search_web]
    )

    # Initialize SoundDevice streams
    # Input: 16kHz 16-bit Mono PCM
    mic_stream = sd.RawInputStream(
        samplerate=16000,
        channels=1,
        dtype='int16',
        blocksize=1024
    )

    # Output: 24kHz 16-bit Mono PCM
    speaker_stream = sd.RawOutputStream(
        samplerate=24000,
        channels=1,
        dtype='int16'
    )

    mic_stream.start()
    speaker_stream.start()

    try:
        async with client.aio.live.connect(
            model="models/gemini-2.5-flash-native-audio-preview-12-2025",
            config=config
        ) as session:
            logger.info("🚀 CONNECTED DIRECTLY TO GOOGLE GEMINI MULTIMODAL LIVE WEBSOCKET!")
            
            # Run input and output loops concurrently
            input_task = asyncio.create_task(audio_input_loop(session, mic_stream))
            output_task = asyncio.create_task(audio_output_loop(session, speaker_stream))
            
            await asyncio.gather(input_task, output_task)
    except Exception as e:
        logger.error(f"Direct Gemini Live error: {e}")
        traceback.print_exc()
    finally:
        mic_stream.stop()
        mic_stream.close()
        speaker_stream.stop()
        speaker_stream.close()
        set_eye_state("STOP")

if __name__ == "__main__":
    try:
        asyncio.run(run_direct_gemini_robot())
    except KeyboardInterrupt:
        logger.info("🛑 WALL-E Direct Gemini Live Stopped by User.")
