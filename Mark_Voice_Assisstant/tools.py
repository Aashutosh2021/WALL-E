import os
import gc
import cv2
import time
import json
import logging
import asyncio
import aiohttp
import webbrowser
from datetime import datetime
from typing import Optional, Literal
from livekit.agents import function_tool
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

SERIAL_PORT = os.getenv("SERIAL_PORT", "/dev/serial0")
BAUD_RATE = int(os.getenv("BAUD_RATE", "115200"))
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

def send_uart_command(command: str) -> bool:
    """Send command over UART hardware serial to ESP32."""
    formatted_cmd = f"{command.strip().upper()}\n"
    try:
        import serial
        with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1) as ser:
            ser.write(formatted_cmd.encode('utf-8'))
            logger.info(f"UART Sent: {formatted_cmd.strip()}")
            return True
    except Exception as e:
        logger.warning(f"UART Serial Port ({SERIAL_PORT}) not available or failed: {e}. Simulating command: {formatted_cmd.strip()}")
        return False


@function_tool()
async def move_robot(direction: Literal["FORWARD", "BACKWARD", "LEFT", "RIGHT", "STOP"]) -> str:
    """
    Controls the WALL-E robot's movement by sending serial commands to the ESP32 motor driver.
    
    Args:
        direction: Movement direction ("FORWARD", "BACKWARD", "LEFT", "RIGHT", "STOP")
    """
    dir_upper = direction.upper().strip()
    valid_directions = ["FORWARD", "BACKWARD", "LEFT", "RIGHT", "STOP"]
    
    if dir_upper not in valid_directions:
        return f"❌ Invalid direction '{direction}'. Valid options: FORWARD, BACKWARD, LEFT, RIGHT, STOP."
    
    send_uart_command(dir_upper)
    if dir_upper == "STOP":
        return "🤖 WALL-E robot stopped."
    return f"🤖 WALL-E robot moving {dir_upper}."


@function_tool()
async def see_object(prompt: str = "Describe what you see in front of the camera in 1-2 short sentences.") -> str:
    """
    Captures a frame using the camera and uses Gemini Vision to describe what is seen in front of WALL-E.
    
    Args:
        prompt: Optional specific question about what to look for.
    """
    temp_filename = f"walle_vision_{int(time.time())}.jpg"
    try:
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            return "❌ Camera error: Could not access video capture device."
        
        # Set lightweight 640x480 resolution for Pi RAM optimization
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        for _ in range(5):
            cap.grab()
            
        ret, frame = cap.read()
        cap.release()
        
        if not ret or frame is None:
            return "❌ Camera error: Failed to capture frame."
            
        cv2.imwrite(temp_filename, frame)
        del frame
        
        # Gemini 2.5 Flash Vision Analysis
        analysis_text = ""
        try:
            from google import genai
            client = genai.Client(api_key=GOOGLE_API_KEY)
            
            with open(temp_filename, "rb") as img_file:
                image_bytes = img_file.read()
                
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    genai.types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                    prompt
                ]
            )
            analysis_text = response.text if response.text else "Could not analyze image."
        except Exception as api_err:
            try:
                import google.generativeai as genai_legacy
                genai_legacy.configure(api_key=GOOGLE_API_KEY)
                model = genai_legacy.GenerativeModel("gemini-2.5-flash")
                import PIL.Image
                img = PIL.Image.open(temp_filename)
                response = model.generate_content([prompt, img])
                analysis_text = response.text if response.text else "Could not analyze image."
            except Exception as legacy_err:
                logger.error(f"Gemini Vision API error: {api_err} | {legacy_err}")
                analysis_text = f"❌ Vision API Error: {str(api_err)}"

        return f"👀 WALL-E sees: {analysis_text}"
        
    except Exception as e:
        logger.error(f"see_object error: {e}")
        return f"❌ Failed to process vision request: {str(e)}"
    finally:
        if os.path.exists(temp_filename):
            try:
                os.remove(temp_filename)
            except Exception:
                pass
        gc.collect()


@function_tool()
async def get_weather(city: str = "Delhi") -> str:
    """
    Fetches real-time weather information for a specified city using Open-Meteo API.
    
    Args:
        city: Name of the city (e.g. "Delhi", "Mumbai", "London")
    """
    try:
        async with aiohttp.ClientSession() as session:
            geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=en&format=json"
            async with session.get(geo_url, timeout=5) as resp:
                if resp.status != 200:
                    return f"❌ Could not find city coordinates for '{city}'."
                geo_data = await resp.json()
                
            if not geo_data.get("results"):
                return f"❌ City '{city}' not found."
                
            location = geo_data["results"][0]
            lat, lon = location["latitude"], location["longitude"]
            city_name = location.get("name", city)
            country = location.get("country", "")
            
            weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
            async with session.get(weather_url, timeout=5) as resp:
                if resp.status != 200:
                    return f"❌ Failed to fetch weather data for '{city}'."
                w_data = await resp.json()
                
            curr = w_data.get("current_weather", {})
            temp = curr.get("temperature", "N/A")
            wind = curr.get("windspeed", "N/A")
            
            return f"🌤️ Weather in {city_name}, {country}: {temp}°C, Wind Speed: {wind} km/h."
    except Exception as e:
        logger.error(f"get_weather error: {e}")
        return f"❌ Failed to fetch weather: {str(e)}"


@function_tool()
async def get_time_info() -> str:
    """
    Returns current time, date, and day of the week.
    """
    now = datetime.now()
    time_str = now.strftime("%I:%M %p")
    date_str = now.strftime("%d %B %Y")
    day_str = now.strftime("%A")
    return f"🕒 Current time is {time_str}, Date: {date_str} ({day_str})."


@function_tool()
async def search_web(query: str) -> str:
    """
    Performs a lightweight web search using Wikipedia / DuckDuckGo API.
    
    Args:
        query: Search query string
    """
    try:
        async with aiohttp.ClientSession() as session:
            ddg_url = f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1&skip_disambig=1"
            async with session.get(ddg_url, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    abstract = data.get("AbstractText", "").strip()
                    if abstract:
                        return f"🔍 Search result: {abstract[:300]}"
            
            wiki_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{query.replace(' ', '_')}"
            async with session.get(wiki_url, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    extract = data.get("extract", "").strip()
                    if extract:
                        return f"🔍 Wikipedia: {extract[:300]}"
                        
        return f"🔍 No direct web summary found for '{query}'."
    except Exception as e:
        logger.error(f"search_web error: {e}")
        return f"❌ Web search failed: {str(e)}"


@function_tool()
async def play_media(media_name: str) -> str:
    """
    Plays requested song or audio/video media on YouTube or browser.
    
    Args:
        media_name: Name of song or video to play
    """
    try:
        search_url = f"https://www.youtube.com/results?search_query={media_name.replace(' ', '+')}"
        webbrowser.open(search_url)
        return f"🎵 Playing '{media_name}' on YouTube."
    except Exception as e:
        logger.error(f"play_media error: {e}")
        return f"❌ Failed to play media: {str(e)}"
