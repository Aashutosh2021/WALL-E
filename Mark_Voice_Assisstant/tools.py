import logging
from livekit.agents import function_tool
import requests
from langchain_community.tools import DuckDuckGoSearchRun
import subprocess
import ctypes
import pygetwindow as gw
import platform
import time
import os
import webbrowser
from typing import Optional, Literal
from datetime import datetime
import psutil
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import pyautogui
import re
from dotenv import load_dotenv
import json
import wikipedia
from typing import List, Dict
import asyncio
import aiohttp
assistant_instance = None 

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
GMAIL_USER = os.getenv("GMAIL_USER", "")
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD", "")

# Safety settings
pyautogui.PAUSE = 0.1
pyautogui.FAILSAFE = True

def validate_email(email: str) -> bool:
    """ईमेल एड्रेस को वैलिडेट करें"""
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return re.match(pattern, email) is not None

@function_tool()
async def get_weather(city: str) -> str:
    """

    Fetches current weather conditions for a specified city in Hindi/English.
    
    Args:
        city (str): The city name to get weather for (e.g., "Delhi")
        
    Returns:
        str: Formatted weather string with temperature and wind speed
        
    Behavior:
        1. First tries Open-Meteo geocoding API
        2. Falls back to OpenStreetMap if needed
        3. Returns temperature (°C) and wind speed (km/h)
        
    Example:
        "Delhi का वर्तमान तापमान है 32°C और पवन की गति है 12 km/h।"
    
    """
    try:
        print(f"🌤️ Getting weather for: {city}")
        
        async with aiohttp.ClientSession() as session:
            # Get location coordinates
            async with session.get(
                f"https://geocoding-api.open-meteo.com/v1/search?name={city}",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                geo_data = await response.json()

            if not geo_data.get("results"):
                async with session.get(
                    f"https://nominatim.openstreetmap.org/search?q={city}&format=json",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    geo_data = await response.json()
                    if not geo_data:
                        return f"क्षमा करें, मैं स्थान नहीं ढूंढ पाया: {city}."

            location = geo_data[0] if isinstance(geo_data, list) else geo_data["results"][0]
            
            weather_url = (
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={location.get('lat', location.get('latitude'))}&"
                f"longitude={location.get('lon', location.get('longitude'))}&"
                f"current_weather=true"
            )
            
            async with session.get(weather_url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                weather_data = await response.json()

            if "current_weather" in weather_data:
                current = weather_data["current_weather"]
                location_name = location.get('display_name', location.get('name', city))
                result = (
                    f"{location_name} का वर्तमान तापमान है {current['temperature']}°C "
                    f"और पवन की गति है {current['windspeed']} km/h।"
                )
                print(f"✅ Weather result: {result}")
                return result
            
            return f"मौसम की जानकारी प्राप्त करने में असमर्थ: {city}"
    except Exception as e:
        logger.error(f"मौसम त्रुटि: {e}")
        return "मौसम सेवा अस्थायी रूप से अनुपलब्ध है। कृपया बाद में प्रयास करें।"

@function_tool()
async def system_power_action(action: Literal["shutdown", "restart", "lock"]) -> str:
    """
    Controls system power state across Windows/Linux/MacOS.
    
    Args:
        action: Power action to perform:
            - "shutdown": Powers off system
            - "restart": Reboots system
            - "lock": Locks workstation
            
    Returns:
        str: Action confirmation in Hindi/English
        
    Security:
        - Requires admin privileges for shutdown/restart
    """
    try:
        print(f"🔧 Power action: {action}")
        
        system = platform.system()
        
        if action == "shutdown":
            if system == "Windows":
                await asyncio.create_task(asyncio.to_thread(os.system, "shutdown /s /t 1"))
            elif system == "Linux":
                await asyncio.create_task(asyncio.to_thread(os.system, "shutdown now"))
            elif system == "Darwin":
                await asyncio.create_task(asyncio.to_thread(os.system, "sudo shutdown -h now"))
            return "सिस्टम शटडाउन किया जा रहा है।"
        
        elif action == "restart":
            if system == "Windows":
                await asyncio.create_task(asyncio.to_thread(os.system, "shutdown /r /t 1"))
            elif system == "Linux":
                await asyncio.create_task(asyncio.to_thread(os.system, "reboot"))
            elif system == "Darwin":
                await asyncio.create_task(asyncio.to_thread(os.system, "sudo shutdown -r now"))
            return "सिस्टम रीस्टार्ट किया जा रहा है।"
        
        elif action == "lock":
            if system == "Windows":
                await asyncio.create_task(asyncio.to_thread(ctypes.windll.user32.LockWorkStation))
            elif system == "Linux":
                await asyncio.create_task(asyncio.to_thread(
                    subprocess.run, ["loginctl", "lock-session"], check=True
                ))
            elif system == "Darwin":
                await asyncio.create_task(asyncio.to_thread(
                    subprocess.run, 
                    ["/System/Library/CoreServices/Menu Extras/User.menu/Contents/Resources/CGSession", "-suspend"]
                ))
            return "🔒 स्क्रीन लॉक की गई है।"
            
    except Exception as e:
        logger.error(f"पावर एक्शन विफल: {e}")
        return f"{action} करने में समस्या आई: {str(e)}"

@function_tool()
async def manage_window(action: Literal["close", "minimize", "maximize"]) -> str:
    """
    Manages the currently active application window.
    
    Args:
        action: Window operation:
            - "close": Terminates window
            - "minimize": Minimizes to taskbar
            - "maximize": Expands window
            
    Returns:
        str: Window title with action confirmation
        
    Notes:
        - Uses pygetwindow for cross-platform support

    """
    try:
        print(f"🪟 Window action: {action}")
        
        # Run pygetwindow operations in thread pool
        active_win = await asyncio.create_task(asyncio.to_thread(gw.getActiveWindow))
        if not active_win:
            return "❌ कोई सक्रिय विंडो नहीं मिली।"

        title = active_win.title.strip() or "अज्ञात विंडो"
        
        if action == "close":
            await asyncio.create_task(asyncio.to_thread(active_win.close))
            return f"✅ '{title}' विंडो बंद कर दी गई।"
            
        elif action == "minimize":
            await asyncio.create_task(asyncio.to_thread(active_win.minimize))
            return f"✅ '{title}' विंडो छोटी की गई।"
            
        elif action == "maximize":
            await asyncio.create_task(asyncio.to_thread(active_win.maximize))
            return f"✅ '{title}' विंडो बड़ी की गई।"
            
    except Exception as e:
        logger.error(f"विंडो प्रबंधन विफल: {e}")
        return f"❌ विंडो {action} करने में समस्या आई: {str(e)}"

@function_tool()
async def get_time_info() -> str:
    """
    Provides current datetime information in Hindi.
    
    Returns:
        str: Formatted string containing:
            - Date (DD-MM-YYYY)
            - Time (12-hour format)
            - Day of week
            
    Example:
        "आज की तारीख है 19-07-2023। अभी का समय है 03:45 PM। सप्ताह का दिन है Wednesday।"
    """
  
    now = datetime.now()
    result = (
        f"आज की तारीख है {now.strftime('%d-%m-%Y')}। "
        f"अभी का समय है {now.strftime('%I:%M %p')}। "
        f"सप्ताह का दिन है {now.strftime('%A')}।"
    )
    
    return result

@function_tool()
async def search_web(query: str) -> str:
    """
    Performs multi-source web search with fallback logic.
    
    Args:
        query: Search terms
        
    Workflow:
        1. Attempts Wikipedia summary
        2. Tries DuckDuckGo API
        3. Falls back to DuckDuckGo search
        
    Returns:
        str: First 2 sentences from Wikipedia or top search result
        
    Notes:
        - Results limited to 500 characters
    """
    try:
        print(f"🔍 Searching web for: {query}")
        
        # Try Wikipedia first
        try:
            summary = await asyncio.create_task(asyncio.to_thread(wikipedia.summary, query, sentences=2))
            print(f"✅ Wikipedia result found")
            return f"📚 विकिपीडिया:\n{summary}"
        except Exception as e:
            print(f"⚠️ Wikipedia failed: {e}")

        # Try DuckDuckGo API
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://api.duckduckgo.com/"
                params = {"q": query, "format": "json", "no_redirect": "1", "no_html": "1"}
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    data = await response.json()

                if data.get("AbstractText"):
                    print(f"✅ DuckDuckGo API result found")
                    return f"🦆 DuckDuckGo:\n{data['AbstractText']}"
                elif data.get("RelatedTopics"):
                    print(f"✅ DuckDuckGo related topics found")
                    return f"🔍 संबंधित:\n{data['RelatedTopics'][0]['Text']}"
        except Exception as e:
            print(f"⚠️ DuckDuckGo API failed: {e}")

        # Try DuckDuckGo Search tool
        try:
            search_tool = DuckDuckGoSearchRun()
            results = await asyncio.create_task(asyncio.to_thread(search_tool.run, query))
            if results:
                print(f"✅ DuckDuckGo search tool result found")
                return f"🔎 परिणाम:\n{results}"
        except Exception as e:
            print(f"⚠️ DuckDuckGo search tool failed: {e}")

        return "❌ क्षमा करें, अभी कोई उपयोगी जानकारी नहीं मिली।"
    except Exception as e:
        logger.error(f"खोज त्रुटि: {e}")
        return f"❌ वेब खोज में त्रुटि: {e}"

@function_tool()
async def play_media(media_name: str, media_type: Literal["song", "video"] = "song") -> str:
    """
    Plays media content from YouTube.
    
    Args:
        media_name: Name of song/video
        media_type: Content type (default: "song")
        
    Behavior:
        - Uses YouTube Data API if key available
        - Falls back to browser search
        
    Returns:
        str: Currently playing confirmation or search link

    """
    try:
        print(f"🎵 Playing media: {media_name} (type: {media_type})")
        
        if not YOUTUBE_API_KEY:
            await asyncio.create_task(asyncio.to_thread(webbrowser.open, f"https://www.youtube.com/results?search_query={media_name}"))
            return f"YouTube पर '{media_name}' खोल रहा हूँ..."
            
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={media_name}&type=video&key={YOUTUBE_API_KEY}",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                data = await response.json()
        
        if data.get('items'):
            video = data['items'][0]
            await asyncio.create_task(asyncio.to_thread(webbrowser.open, f"https://www.youtube.com/watch?v={video['id']['videoId']}"))
            return f"🎵 अब बज रहा है: {video['snippet']['title']}"
        
        await asyncio.create_task(asyncio.to_thread(webbrowser.open, f"https://www.youtube.com/results?search_query={media_name}"))
        return f"YouTube पर '{media_name}' खोल रहा हूँ..."
    except Exception as e:
        logger.error(f"मीडिया त्रुटि: {e}")
        return f"❌ मीडिया चलाने में समस्या आई: {str(e)}"

@function_tool()
async def desktop_control(action: Literal["show", "scroll"], direction: Optional[Literal["up", "down"]] = None, amount: Optional[int] = 3) -> str:
    """
    Controls desktop UI elements.
    
    Args:
        action: "show" desktop or "scroll"
        direction: Scroll direction (required if action=scroll)
        amount: Scroll units (default: 3)
        
    Returns:
        str: Action confirmation
        
    Notes:
        - Restores mouse position after operation
    """
    try:
        print(f"🖥️ Desktop control: {action}")
        
        original_pos = await asyncio.create_task(asyncio.to_thread(pyautogui.position))
        
        if action == "show":
            try:
                await asyncio.create_task(asyncio.to_thread(pyautogui.hotkey, 'win', 'd'))
                return "🖥️ डेस्कटॉप दिखाया जा रहा है।"
            except Exception:
                try:
                    await asyncio.create_task(asyncio.to_thread(pyautogui.click, button='right'))
                    await asyncio.sleep(0.5)
                    await asyncio.create_task(asyncio.to_thread(pyautogui.press, 'm'))
                    return "🖥️ डेस्कटॉप दिखाया जा रहा है।"
                except Exception as e:
                    return f"❌ डेस्कटॉप दिखाने में विफल: {str(e)}"
                    
        elif action == "scroll":
            if not direction:
                direction = "up"
            if not amount:
                amount = 3
                
            try:
                screen_width, screen_height = await asyncio.create_task(asyncio.to_thread(pyautogui.size))
                await asyncio.create_task(asyncio.to_thread(pyautogui.moveTo, screen_width//2, screen_height//2, duration=0.1))
                
                scroll_amount = amount if direction == "up" else -amount
                await asyncio.create_task(asyncio.to_thread(pyautogui.scroll, scroll_amount))
                return f"✅ सफलतापूर्वक {direction} की ओर {amount} यूनिट स्क्रॉल किया।"
            except Exception as e:
                return f"❌ स्क्रॉल करने में विफल: {str(e)}"
                
    except Exception as e:
        return f"❌ डेस्कटॉप कंट्रोल में त्रुटि: {str(e)}"
    finally:
        try:
            await asyncio.create_task(asyncio.to_thread(pyautogui.moveTo, original_pos.x, original_pos.y, duration=0.1))
        except:
            pass

@function_tool()
async def send_email(to_email: str, subject: str, message: str, cc_email: Optional[str] = None) -> str:
    """
    Sends emails via authenticated Gmail SMTP.
    
    Args:
        to_email: Primary recipient
        subject: Email subject
        message: Body content
        cc_email: CC recipient (optional)
        
    Validation:
        - Strict email format validation
        - Requires GMAIL_USER/GMAIL_PASSWORD in .env
        
    Returns:
        str: Delivery confirmation or error
    """
    try:
        print(f"📧 Sending email to: {to_email}")
        
        if not validate_email(to_email):
            return f"❌ अमान्य प्राप्तकर्ता ईमेल: {to_email}"
            
        if cc_email and not validate_email(cc_email):
            return f"❌ अमान्य CC ईमेल: {cc_email}"
            
        if not GMAIL_USER or not GMAIL_PASSWORD:
            return "❌ ईमेल credentials नहीं मिले। कृपया .env फाइल चेक करें।"
            
        def send_email_sync():
            msg = MIMEMultipart()
            msg['From'] = GMAIL_USER
            msg['To'] = to_email
            msg['Subject'] = subject
            
            if cc_email:
                msg['Cc'] = cc_email
                
            msg.attach(MIMEText(message, 'plain'))
            
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(GMAIL_USER, GMAIL_PASSWORD)
                recipients = [to_email] + ([cc_email] if cc_email else [])
                server.sendmail(GMAIL_USER, recipients, msg.as_string())
                return recipients
        
        recipients = await asyncio.create_task(asyncio.to_thread(send_email_sync))
        return f"✅ ईमेल सफलतापूर्वक भेजा गया: {', '.join(recipients)}"
    except Exception as e:
        logger.error(f"ईमेल त्रुटि: {e}")
        return f"❌ ईमेल भेजने में त्रुटि: {str(e)}"

@function_tool()
async def list_active_windows() -> str:
    """
    Lists all visible application windows.
    
    Returns:
        str: Formatted list with:
            - Window titles
            - Current state (minimized/maximized/active)
            
    Example:
        "• Chrome (Maximized)\n• Notepad (Active)"
    """
    try:
        print("🪟 Listing active windows")
        
        windows = await asyncio.create_task(asyncio.to_thread(gw.getAllWindows))
        result = []
        
        for window in windows:
            if window and window.title:
                try:
                    is_minimized = await asyncio.create_task(asyncio.to_thread(lambda: window.isMinimized))
                    is_maximized = await asyncio.create_task(asyncio.to_thread(lambda: window.isMaximized))
                    status = "Minimized" if is_minimized else "Maximized" if is_maximized else "Active"
                    result.append(f"• {window.title.strip()} ({status})")
                except Exception:
                    continue
        
        if result:
            return f"📋 खुली हुई विंडोज:\n" + "\n".join(result)
        else:
            return "❌ कोई विंडो नहीं मिली"
            
    except Exception as e:
        logger.error(f"विंडो सूची त्रुटि: {e}")
        return f"❌ विंडो डिटेक्शन विफल: {str(e)}"

@function_tool()
async def manage_window_state(action: Literal["maximize", "minimize", "restore", "close"], window_title: Optional[str] = None) -> str:
    """विशिष्ट या सक्रिय विंडो की स्थिति प्रबंधित करें (बड़ा करें, छोटा करें, पुनर्स्थापित करें, बंद करें)"""
    try:
        print(f"🪟 Managing window state: {action} for {window_title or 'active window'}")
        
        def find_window_by_title(title):
            """Find window by title with better matching"""
            try:
                all_windows = gw.getAllWindows()
                for win in all_windows:
                    if win and win.title:
                        win_title = win.title.strip()
                        if title.lower() in win_title.lower():
                            return win
                return None
            except Exception as e:
                print(f"Error finding window: {e}")
                return None
        
        def activate_and_manage_window(win, operation):
            """Activate window first, then perform operation"""
            try:
                # Try to activate/focus the window first
                try:
                    win.activate()
                    time.sleep(0.1)  # Small delay for activation
                except:
                    pass  # Some windows can't be activated, but we can still try operations
                
                # Perform the requested operation
                if operation == "maximize":
                    win.maximize()
                elif operation == "minimize":
                    win.minimize()
                elif operation == "restore":
                    win.restore()
                elif operation == "close":
                    win.close()
                    
                return True
            except Exception as e:
                print(f"Window operation failed: {e}")
                return False

        target_window = None
        
        if window_title:
            # Find specific window
            target_window = await asyncio.create_task(asyncio.to_thread(find_window_by_title, window_title))
            if not target_window:
                return f"❌ '{window_title}' नाम की कोई विंडो नहीं मिली"
        else:
            # Use active window
            target_window = await asyncio.create_task(asyncio.to_thread(gw.getActiveWindow))
            if not target_window:
                return "❌ कोई सक्रिय विंडो नहीं मिली"

        # Get window title for response
        win_title = target_window.title.strip() if target_window.title else "अज्ञात विंडो"
        
        # Perform the window operation
        success = await asyncio.create_task(asyncio.to_thread(activate_and_manage_window, target_window, action))
        
        if success:
            return f"✅ विंडो '{win_title}' को {action} किया गया"
        else:
            return f"❌ विंडो '{win_title}' को {action} करने में विफल"
            
    except Exception as e:
        logger.error(f"Window management error: {e}")
        return f"❌ त्रुटि: {str(e)}"

@function_tool()
async def say_reminder(msg: str) -> str:
    """
    Creates audible/visual reminders.
    
    Args:
        msg: Reminder content
        
    Returns:
        str: Formatted reminder with bell icon
        
    Example:
        "🔔 याद दिलाना: Meeting at 3 PM"
    """
    print(f"🔔 Reminder: {msg}")
    return f"🔔 याद दिलाना: {msg}"

# Database and reminder functions
from datetime import datetime, date
import sqlite3

DB_PATH = "nova_memory/chat_history.db"
TABLE_NAME = "chat_messages"

async def get_today_reminder_message_from_db() -> str | None:
    """Get today's reminders from the database"""
    today = datetime.now().date()
    try:
        print(f"🔍 Checking reminders for {today}")
        
        def db_operation():
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            cursor.execute(f"SELECT role, content FROM {TABLE_NAME} ORDER BY created_at ASC")
            rows = cursor.fetchall()
            conn.close()
            return rows
        
        rows = await asyncio.create_task(asyncio.to_thread(db_operation))
        reminders = []

        for role, content_json in rows:
            if role != "user":
                continue

            try:
                content_items = json.loads(content_json)
                for item in content_items:
                    item_lower = item.lower()

                    if "remind" in item_lower or "remember" in item_lower or "याद दिला" in item_lower:
                        date = extract_date_from_text(item_lower)
                        if date and date == today:
                            reminders.append(item)
            except Exception as e:
                print(f"⚠️ Error parsing content: {e}")
                continue

        if reminders:
            combined = "\n".join(f"🔔 {r}" for r in reminders)
            return f"🧠 सर, आज आपको याद है न — {combined}"

        return None

    except Exception as e:
        print(f"❌ Error while checking reminders: {e}")
        return None

def extract_date_from_text(text: str) -> Optional[date]:
    """Extract date from text"""
    today = datetime.now().date()

    date_match = re.search(r"\d{4}-\d{2}-\d{2}", text)
    if date_match:
        try:
            return datetime.strptime(date_match.group(), "%Y-%m-%d").date()
        except:
            return None

    if "आज" in text:
        return today
    elif "कल" in text:
        from datetime import timedelta
        return today + timedelta(days=1)

    return None

import asyncio
import os
import subprocess
import pyautogui
import time
from typing import Tuple



@function_tool()
async def send_whatsapp_message(contact: str, message: str) -> str:
    
    """
    Sends WhatsApp messages via desktop automation.
    
    Args:
        contact: Name/number from contacts
        message: Content to send
        
    Workflow:
        1. Opens WhatsApp
        2. Searches contact
        3. Sends message
        
    Returns:
        str: Delivery confirmation and follow-up prompt
    """
    import pyautogui
    import asyncio
    import os

    try:
        print(f"📨 WhatsApp भेजने की प्रक्रिया शुरू: {contact} -> {message}")
        original_pos = await asyncio.to_thread(pyautogui.position)

        # Step 1: Press Win key
        await asyncio.to_thread(pyautogui.press, 'win')
        await asyncio.sleep(1)

        # Step 2: Type "whatsapp" and press Enter
        await asyncio.to_thread(pyautogui.typewrite, 'whatsapp', interval=0.1)
        await asyncio.sleep(1)
        await asyncio.to_thread(pyautogui.press, 'enter')
        await asyncio.sleep(3)

        # Step 3: Ctrl + F to search
        await asyncio.to_thread(pyautogui.hotkey, 'ctrl', 'f')
        await asyncio.sleep(2)

        # Step 4: Type contact name and open chat
        await asyncio.to_thread(pyautogui.typewrite, contact, interval=0.1)
        await asyncio.sleep(1.5)
        await asyncio.to_thread(pyautogui.press, 'down')
        await asyncio.sleep(0.5)
        await asyncio.to_thread(pyautogui.press, 'enter')
        await asyncio.sleep(1.5)

        # Step 5: Send initial message
        await asyncio.to_thread(pyautogui.typewrite, message, interval=0.06)
        await asyncio.to_thread(pyautogui.press, 'enter')
        await asyncio.sleep(1)

        # Step 6: Ask for more (Agent-level trigger only)
        return (
            f"✅ '{contact}' को संदेश भेजा गया: \"{message}\"\n"
            f"🧠 क्या कुछ और भेजना है sir? जवाब दें — Nova उस संदेश को भेज देगा।"
        )

    except Exception as e:
        return f"❌ संदेश भेजने में त्रुटि: {str(e)}"

    finally:
        try:
            await asyncio.to_thread(pyautogui.moveTo, original_pos.x, original_pos.y, duration=0.1)
        except:
            pass


# PyAutoGUI सेटिंग्स - import करते समय automatically set हो जाएंगी
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1


@function_tool()
async def write_in_notepad(title: str, content: str, document_type: str = "letter") -> str:
    """
    Creates formatted documents in Notepad.

    Args:
        title: Document heading
        content: Main text (typing should always be in English)
        document_type: Format template:
            - "letter": Formal layout
            - "application": Structured
            - "note": Simple text

    Returns:
        str: Saved file path confirmation
    """

    import pyautogui
    import asyncio
    import datetime

    try:
        print(f"📝 Starting Notepad writing process: {document_type} - {title}")
        original_pos = await asyncio.to_thread(pyautogui.position)

        # Step 1: Open Notepad using Win key
        print("🔧 Opening Notepad...")
        await asyncio.to_thread(pyautogui.press, 'win')
        await asyncio.sleep(1)

        # Step 2: Type "notepad" and press Enter
        await asyncio.to_thread(pyautogui.typewrite, 'notepad', interval=0.1)
        await asyncio.sleep(1)
        await asyncio.to_thread(pyautogui.press, 'enter')
        await asyncio.sleep(3)  # Wait for Notepad to open

        # Step 3: Create new file (Ctrl+N) to ensure clean slate
        print("📄 Creating new file...")
        await asyncio.to_thread(pyautogui.hotkey, 'ctrl', 'n')
        await asyncio.sleep(1)

        # Step 4: Clear any existing content (Ctrl+A, Delete)
        await asyncio.to_thread(pyautogui.hotkey, 'ctrl', 'a')
        await asyncio.sleep(0.5)
        await asyncio.to_thread(pyautogui.press, 'delete')
        await asyncio.sleep(0.5)

        # Step 5: Start writing the document with proper formatting
        print("✍️ Writing document content...")
        
        # Add date at the top
        current_date = datetime.datetime.now().strftime("%d/%m/%Y")
        await asyncio.to_thread(pyautogui.typewrite, f"Date: {current_date}", interval=0.05)
        await asyncio.to_thread(pyautogui.press, 'enter')
        await asyncio.to_thread(pyautogui.press, 'enter')

        # Add document title
        await asyncio.to_thread(pyautogui.typewrite, f"Subject: {title}", interval=0.05)
        await asyncio.to_thread(pyautogui.press, 'enter')
        await asyncio.to_thread(pyautogui.press, 'enter')

        # Add greeting for letters/applications
        if document_type.lower() in ["letter", "application"]:
            await asyncio.to_thread(pyautogui.typewrite, "Dear Sir/Madam,", interval=0.05)
            await asyncio.to_thread(pyautogui.press, 'enter')
            await asyncio.to_thread(pyautogui.press, 'enter')

        # Write main content with proper paragraph formatting
        paragraphs = content.split('\n\n')
        for i, paragraph in enumerate(paragraphs):
            if paragraph.strip():  # Skip empty paragraphs
                # Clean the paragraph text
                clean_paragraph = paragraph.strip()
                await asyncio.to_thread(pyautogui.typewrite, clean_paragraph, interval=0.03)
                await asyncio.to_thread(pyautogui.press, 'enter')
                await asyncio.to_thread(pyautogui.press, 'enter')

        # Add professional closing for letters/applications
        if document_type.lower() in ["letter", "application"]:
            await asyncio.to_thread(pyautogui.typewrite, "Thank you for your time and consideration.", interval=0.05)
            await asyncio.to_thread(pyautogui.press, 'enter')
            await asyncio.to_thread(pyautogui.press, 'enter')
            await asyncio.to_thread(pyautogui.typewrite, "Yours sincerely,", interval=0.05)
            await asyncio.to_thread(pyautogui.press, 'enter')
            await asyncio.to_thread(pyautogui.press, 'enter')
            await asyncio.to_thread(pyautogui.typewrite, "[Your Name]", interval=0.05)

        # Step 6: Save the document
        print("💾 Saving document...")
        await asyncio.sleep(1)
        await asyncio.to_thread(pyautogui.hotkey, 'ctrl', 's')
        await asyncio.sleep(2)
        
        # Create clean filename
        safe_title = title.replace(' ', '_').replace('/', '_').replace('\\', '_')
        filename = f"{document_type}_{safe_title}_{current_date.replace('/', '_')}.txt"
        
        await asyncio.to_thread(pyautogui.typewrite, filename, interval=0.05)
        await asyncio.to_thread(pyautogui.press, 'enter')
        await asyncio.sleep(1)

        print("✅ Document created successfully!")
        return (
            f"✅ '{title}' {document_type} successfully created in Notepad\n"
            f"📄 File saved as: {filename}\n"
            f"🎯 Document type: {document_type.title()}\n"
            f"📝 Content written with proper formatting\n"
            f"🔄 New file created for clean writing experience"
        )

    except Exception as e:
        error_msg = f"❌ Error writing to Notepad: {str(e)}"
        print(error_msg)
        return error_msg

    finally:
        try:
            # Return mouse to original position
            await asyncio.to_thread(pyautogui.moveTo, original_pos.x, original_pos.y, duration=0.1)
        except:
            pass


# PyAutoGUI Configuration
import pyautogui
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1



@function_tool()
async def open_app(app_name: str) -> str:
    """
    Launches applications via Start Menu search.
    
    Args:
        app_name: Application name (e.g., "chrome")
        
    Returns:
        str: Launch confirmation or error
        
    Notes:
        - Windows-specific implementation
    """
    import pyautogui
    import asyncio

    try:
        print(f"🚀 ऐप खोलने का प्रयास: {app_name}")
        original_pos = await asyncio.to_thread(pyautogui.position)

        # Step 1: Press Win key to open start menu
        await asyncio.to_thread(pyautogui.press, 'win')
        await asyncio.sleep(1)

        # Step 2: Type app name
        await asyncio.to_thread(pyautogui.typewrite, app_name, interval=0.1)
        await asyncio.sleep(1)

        # Step 3: Press Enter to open the app
        await asyncio.to_thread(pyautogui.press, 'enter')

        return f"✅ '{app_name}' खोल दिया गया है।"

    except Exception as e:
        return f"❌ ऐप खोलने में त्रुटि: {str(e)}"

    finally:
        try:
            await asyncio.to_thread(pyautogui.moveTo, original_pos.x, original_pos.y, duration=0.1)
        except:
            pass


@function_tool()
async def press_key(key: str) -> str:
    """
    Simulates keyboard key presses.
    
    Args:
        key: Single key ("enter") or combo ("ctrl+alt+del")
        
    Returns:
        str: Press confirmation
        
    Notes:
        - Supports most standard keyboard keys
    """
    import pyautogui
    import asyncio

    try:
        # Normalize input
        key = key.strip().lower()

        # Split combination if needed
        if '+' in key:
            keys = [k.strip() for k in key.split('+')]
            await asyncio.to_thread(pyautogui.hotkey, *keys)
        else:
            await asyncio.to_thread(pyautogui.press, key)

        return f"✅ '{key}' दबा दिया गया है।"

    except Exception as e:
        return f"❌ कुंजी दबाने में त्रुटि: {str(e)}"
    


@function_tool()
async def get_system_info() -> str:
    """
    Provides comprehensive system diagnostics.
    
    Returns:
        str: Formatted report containing:
            - Battery status
            - Storage space
            - Network info
            - CPU/RAM usage
            
    Metrics:
        - Updates in real-time
    """
    import psutil
    import socket
    import platform
    import shutil

    try:
        # Battery Info
        battery = psutil.sensors_battery()
        if battery:
            battery_percent = battery.percent
            charging = "⚡ Charging" if battery.power_plugged else "🔋 On Battery"
        else:
            battery_percent = "N/A"
            charging = "N/A"

        # Storage Info
        total, used, free = shutil.disk_usage("/")
        total_gb = total // (2**30)
        free_gb = free // (2**30)

        # Network Info
        try:
            hostname = socket.gethostname()
            ip_address = socket.gethostbyname(hostname)
            network_status = f"Connected (IP: {ip_address})"
        except:
            network_status = "❌ Not Connected"

        # CPU & RAM
        cpu_percent = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory()
        ram_percent = ram.percent
        ram_total_gb = round(ram.total / (1024 ** 3), 1)
        ram_used_gb = round(ram.used / (1024 ** 3), 1)

        # System Name
        system_name = platform.node()

        return (
            f"🧠 System Info for: {system_name}\n"
            f"🔋 Battery: {battery_percent}% ({charging})\n"
            f"💾 Storage: {free_gb} GB free of {total_gb} GB\n"
            f"📶 Network: {network_status}\n"
            f"🧠 CPU Usage: {cpu_percent}%\n"
            f"📈 RAM Usage: {ram_percent}% ({ram_used_gb} GB of {ram_total_gb} GB)"
        )

    except Exception as e:
        return f"❌ सिस्टम जानकारी प्राप्त करने में त्रुटि: {str(e)}"



@function_tool()
async def type_user_message_auto(message: str) -> str:
    """
    Types content into active window.
    
    Args:
        message: Text to type
        
    Returns:
        str: Typing confirmation
        
    Behavior:
        - Natural typing speed (0.1s intervals)
        - Preserves original cursor position

    """
    import pyautogui
    import asyncio

    if not message.strip():
        return "⚠️ Sir, message खाली है।"

    await asyncio.to_thread(pyautogui.typewrite, message, interval=0.1)
    return f"✅ टाइप कर दिया गया: \"{message}\""


import numpy as np
import cv2
from mss import mss
import pytesseract
import win32gui
import time
from PIL import Image
import os
from datetime import datetime
import re
from functools import wraps
import json

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

# Global setup
sct = mss()
monitor = sct.monitors[1]



@function_tool()
async def click_on_text(target_text: str) -> str:
    """
    Clicks on screen text using OCR.
    
    Args:
        target_text: Visible text to click
        
    Returns:
        str: Click confirmation or error
        
    Technology:
        - Uses Tesseract OCR
        - Fuzzy text matching
    """
    import pyautogui
    import pytesseract
    import cv2
    import numpy as np
    import asyncio
    from difflib import SequenceMatcher

    def similarity(text1: str, text2: str) -> float:
        return SequenceMatcher(None, text1.lower().strip(), text2.lower().strip()).ratio()

    try:
        # Screenshot
        screenshot = await asyncio.to_thread(pyautogui.screenshot)
        screenshot_np = np.array(screenshot)
        image = cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2BGR)
        
        # Preprocess
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        
        # OCR
        data = await asyncio.to_thread(
            pytesseract.image_to_data,
            gray,
            output_type=pytesseract.Output.DICT
        )
        
        # Find best match
        best_match = None
        best_score = 0
        
        for i in range(len(data['text'])):
            text = data['text'][i].strip()
            if not text:
                continue
            
            score = similarity(target_text, text)
            if score > best_score and score > 0.7:
                best_score = score
                best_match = {
                    'text': text,
                    'x': int(data['left'][i] / 2),
                    'y': int(data['top'][i] / 2),
                    'w': int(data['width'][i] / 2),
                    'h': int(data['height'][i] / 2)
                }
        
        if not best_match:
            return f"❌ '{target_text}' नहीं मिला"
        
        # Click
        center_x = best_match['x'] + best_match['w'] // 2
        center_y = best_match['y'] + best_match['h'] // 2
        
        await asyncio.to_thread(pyautogui.moveTo, center_x, center_y, duration=0.2)
        await asyncio.to_thread(pyautogui.click)
        
        return f"✅ '{target_text}' पर क्लिक किया गया!"

    except Exception as e:
        return f"🚫 Error: {str(e)}"
    

@function_tool()
async def scan_system_for_viruses() -> str:
    """
    Performs quick virus scan using Windows Defender.
    
    Returns:
        str: Scan summary with:
            - Threats found
            - Scan duration
            - Last update
            
    Notes:
        - Requires admin privileges
    """
    import asyncio
    import subprocess

    try:
        cmd = [
            r"C:\Program Files\Windows Defender\MpCmdRun.exe",  # Older path
            "-Scan", "-ScanType", "1"  # 1 = quick scan
        ]

        # fallback path for Windows 10+
        alt_cmd = [
            r"C:\ProgramData\Microsoft\Windows Defender\Platform\4.18.23070.2003-0\MpCmdRun.exe",
            "-Scan", "-ScanType", "1"
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        except FileNotFoundError:
            proc = await asyncio.create_subprocess_exec(
                *alt_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

        stdout, stderr = await proc.communicate()

        output = stdout.decode().strip()
        if "Scan starting" in output or "Scan completed" in output:
            return f"🛡️ सिस्टम स्कैन पूरा हुआ:\n\n{output[-500:]}"
        else:
            return f"⚠️ स्कैन पूरा हुआ, लेकिन कोई जानकारी नहीं मिली:\n\n{output[-500:]}"
        
    except Exception as e:
        return f"❌ स्कैन में त्रुटि: {str(e)}"
    


    


from typing import Literal
import aiohttp
import asyncio
from datetime import datetime
import json

@function_tool()
async def control_ac_bulb(
    action: Literal["on", "off", "status"],
    ip_address: str = "10.216.226.11",
    timeout: float = 5.0
) -> str:
    """
    Advanced control for ESP32-connected AC bulb with safety checks
    
    Args:
        action: "on", "off", or "status"
        ip_address: ESP32 IP (default: 10.231.149.11)
        timeout: Request timeout in seconds (default: 5.0)
        
    Returns:
        str: Detailed status with safety warnings
        
    Safety Features:
        - Pre-flight high voltage warnings
        - State verification
        - Timeout protection
        - Manual JSON parsing
    """
    
    endpoint_map = {
        "on": "/on",
        "off": "/off",
        "status": "/status"
    }
    
    # Safety warnings
    high_voltage_warning = "⚡ HIGH VOLTAGE WARNING: 220V AC will be LIVE - Ensure proper insulation!\n" if action == "on" else ""
    
    try:
        url = f"http://{ip_address}{endpoint_map[action]}"
        start_time = datetime.now()
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.get(url) as response:
                response_time = (datetime.now() - start_time).total_seconds()
                
                content = await response.text()
                # Manual JSON parsing (since ESP32 sends simple JSON string)
                try:
                    data = json.loads(content)
                except:
                    return f"❌ Invalid response from ESP32: {content}"
                
                if response.status == 200:
                    if action == "status":
                        return (
                            f"🔍 Current Status: {data.get('state', 'unknown')}\n"
                            f"Response Time: {response_time:.2f}s"
                        )
                    else:
                        return (
                            "Light turned on successfully sir"
                        )
                else:
                    return (
                        f"❌ Control failed (HTTP {response.status})!\n"
                        f"Error: {data.get('message', 'Unknown error')}\n"
                        "Check: 1. ESP32 power 2. WiFi connection"
                    )
    
    except asyncio.TimeoutError:
        return (
            "⌛ Timeout - ESP32 unresponsive!\n"
            f"• Verify ESP32 is powered and connected to WiFi\n"
            f"• Check IP address: {ip_address}\n"
            "• Physical inspection required if unresponsive for >1 minute"
        )
    
    except Exception as e:
        return (
            "⚡ CRITICAL FAILURE!\n"
            f"Technical Error: {str(e)}\n\n"
            "EMERGENCY PROTOCOL:\n"
            "1. Cut power to ESP32 immediately\n"
            "2. Check relay wiring\n"
            "3. Do not touch exposed contacts\n"
            "4. Restart system after inspection"
        )



import pyautogui
import time
import screen_brightness_control as sbc
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume


# ================= Brightness Control ==================
@function_tool()
async def control_screen_brightness(prompt: str, brightness_level: int) -> str:
    """
    Sets the screen brightness to a specific percentage.

    Args:
        prompt: The user's request, e.g., "set brightness to 75%".
        brightness_level: An integer (0-100) representing the desired brightness.

    Returns:
        A confirmation message after adjusting the brightness.
    """
    try:
        if 0 <= brightness_level <= 100:
            sbc.set_brightness(brightness_level)  # Direct hardware brightness control
            return f"✅ Screen brightness has been set to {brightness_level}%."
        else:
            return "⚠️ Error: Brightness level must be between 0 and 100."
    except Exception as e:
        return f"❌ Failed to adjust brightness: {str(e)}"

# ================= Media Control ==================
import keyboard  # pip install keyboard

@function_tool()
async def control_media(prompt: str, action: str) -> str:
    """
    Controls media playback by simulating AutoHotkey hotkeys (F9-F12).

    Args:
        prompt: The user's request, e.g., "pause music".
        action: One of ["play_pause", "next", "previous"]

    Returns:
        Confirmation message after simulating the hotkey.
    """
    try:
        if action == "previous":
            pyautogui.press("f9")   # AHK mapped to Media_Prev
            return "⏮️ Previous track triggered."
        elif action == "play_pause":
            pyautogui.press("f10")  # AHK mapped to Media_Play_Pause
            return "⏯️ Play/Pause toggled."
        elif action == "next":
            pyautogui.press("f11")  # AHK mapped to Media_Next
            return "⏭️ Next track triggered."
        else:
            return "⚠️ Invalid action. Use play_pause, next, previous, or stop."
    except Exception as e:
        return f"❌ Failed to control media via hotkey: {str(e)}"


# ================= Volume Control ==================
@function_tool()
async def control_system_volume(prompt: str, volume_level: int) -> str:
    """
    Adjusts the system volume to a specific level.

    Args:
        prompt: The user's request, e.g., "set volume to 50".
        volume_level: An integer (0-100) representing the desired volume.

    Returns:
        A confirmation message after adjusting the volume.
    """
    try:
        if 0 <= volume_level <= 100:
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))

            # 0.0 = min, 1.0 = max
            normalized_volume = volume_level / 100
            volume.SetMasterVolumeLevelScalar(normalized_volume, None)

            return f"✅ System volume has been set to {volume_level}%."
        else:
            return "⚠️ Error: Volume level must be between 0 and 100."
    except Exception as e:
        return f"❌ Failed to adjust volume: {str(e)}"


# ================= Smart Clipboard ==================
@function_tool()
async def use_smart_clipboard(prompt: str, action: str, item_index: int = None) -> str:
    """
    Manages the Windows clipboard history.

    Args:
        prompt: The user's request, e.g., "open smart clipboard" or "paste the 4th item".
        action: The specific command, like "open_history" or "paste_item".
        item_index: The position of the clipboard item to paste (starting from 1).
                    This is optional and used only with "paste_item" action.

    Returns:
        A message confirming the action.
    """
    try:
        if action == "open_history":
            # Open Clipboard History (Win + V)
            pyautogui.hotkey("win", "v")
            return "📋 Clipboard history opened."

        elif action == "paste_item" and item_index is not None:
            if item_index < 1:
                return "⚠️ Error: Item index must be 1 or greater."

            # Open Clipboard History
            pyautogui.hotkey("win", "v")
            time.sleep(0.5)

            # Navigate with down arrow
            for _ in range(item_index - 1):
                pyautogui.press("down")

            # Select item
            pyautogui.press("enter")

            return f"📋 Pasted item at index {item_index} from clipboard history."

        else:
            return "⚠️ Invalid action or missing/invalid item index."
    except Exception as e:
        return f"❌ Smart clipboard operation failed: {str(e)}"



# ================= Multi-Task Executor ==================
# ================= Multi-Task Executor ==================
@function_tool()
async def execute_multi_task(tasks: list[dict]) -> str:
    """
    Executes multiple tools sequentially as per user request.

    Args:
        tasks: A list of dictionaries, each containing:
            - 'tool_name': Name of the tool (string)
            - 'params': Dictionary of parameters for that tool

        Example:
        tasks = [
            {"tool_name": "get_weather", "params": {"location": "Surat"}},
            {"tool_name": "play_media", "params": {"media_path": "song.mp3"}},
            {"tool_name": "control_system_volume", "params": {"volume_level": 50}}
        ]

    Returns:
        A message indicating completion of all tasks.
    """
    results = []

    # Loop through each task sequentially
    for idx, task in enumerate(tasks, start=1):
        tool_name = task.get("tool_name")
        params = task.get("params", {})

        if not tool_name:
            results.append(f"⚠️ Task {idx}: 'tool_name' missing.")
            continue

        # Dynamically get the function
        tool_func = globals().get(tool_name)
        if not tool_func:
            results.append(f"⚠️ Task {idx}: Tool '{tool_name}' not found.")
            continue

        try:
            # Execute the tool and wait for completion before next
            result = await tool_func(**params)
            results.append(f"✅ Task {idx} ({tool_name}) executed: {result}")
        except Exception as e:
            results.append(f"❌ Task {idx} ({tool_name}) failed: {str(e)}")

    return "🔹 Multi-Task Execution Complete:\n" + "\n".join(results)

# import asyncio
# import pandas as pd
# import numpy as np
# from pathlib import Path
# import tkinter as tk
# from tkinter import filedialog
# import json
# import tempfile
# import webbrowser
# from typing import Dict, List, Any, Optional, Union
# import traceback
# import warnings
# import http.server
# import socketserver
# import threading
# import os
# import base64
# from io import BytesIO
# from plotly.subplots import make_subplots
# import plotly.graph_objects as go
# import plotly.io as pio

# warnings.filterwarnings('ignore')

# # Data analysis libraries
# from sklearn.impute import SimpleImputer
# from sklearn.preprocessing import StandardScaler
# from sklearn.cluster import KMeans
# from sklearn.decomposition import PCA
# from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
# from sklearn.metrics import accuracy_score, f1_score, mean_squared_error, r2_score
# from sklearn.model_selection import train_test_split

# # Visualization libraries
# import plotly.express as px
# import matplotlib.pyplot as plt
# import seaborn as sns
# from matplotlib.colors import LinearSegmentedColormap

# # Set dark theme for matplotlib
# plt.style.use('dark_background')
# sns.set_palette("dark")
# sns.set_style("darkgrid")

# # Create a dark color palette for Plotly
# plotly_dark_template = go.layout.Template(
#     layout=go.Layout(
#         paper_bgcolor='rgba(0,0,0,0)',
#         plot_bgcolor='rgba(0,0,0,0)',
#         font=dict(color='#e6e6e6'),
#         colorway=['#ff6b6b', '#4ecdc4', '#45b7d1', '#f9c80e', '#f86624', 
#                  '#ea3546', '#662e9b', '#c5d86d', '#0cce6b', '#5f0f40']
#     )
# )

# @function_tool()
# async def analyze_dataset(
#     ml_target: Optional[str] = None,
#     port: int = 8080,
#     sample_size: Optional[int] = 10000,
#     max_categories: int = 50
# ) -> Dict[str, Any]:
#     """
#     Advanced data analysis and report generator with dark theme and image-based visualizations.
    
#     This function automatically opens a file selection dialog for CSV/Excel files,
#     performs comprehensive data analysis, and generates an interactive web report.
#     Visualizations are saved as images for better performance and compatibility.
    
#     VOICE COMMAND: "Nova, I want to analyze a dataset"
#     """
    
#     # Step 1: File selection dialog
#     root = tk.Tk()
#     root.withdraw()
#     root.attributes('-topmost', True)
    
#     file_path = filedialog.askopenfilename(
#         title="Select dataset file",
#         filetypes=[
#             ("CSV files", "*.csv"),
#             ("Excel files", "*.xls *.xlsx"),
#             ("All files", "*.*")
#         ]
#     )
    
#     if not file_path:
#         return {"error": "No file selected"}
    
#     # Step 2: Read file robustly
#     try:
#         if file_path.endswith('.csv'):
#             encodings = ['utf-8', 'latin-1', 'windows-1252', 'iso-8859-1']
#             delimiters = [',', ';', '\t', '|']
            
#             for encoding in encodings:
#                 try:
#                     with open(file_path, 'r', encoding=encoding) as f:
#                         first_line = f.readline()
#                     break
#                 except UnicodeDecodeError:
#                     continue
#             else:
#                 encoding = 'utf-8'
            
#             for delim in delimiters:
#                 if delim in first_line:
#                     delimiter = delim
#                     break
#             else:
#                 delimiter = ','
            
#             df = pd.read_csv(file_path, encoding=encoding, delimiter=delimiter, low_memory=False)
            
#         elif file_path.endswith(('.xls', '.xlsx')):
#             df = pd.read_excel(file_path, engine='openpyxl')
            
#     except Exception as e:
#         return {"error": f"Failed to read file: {str(e)}"}
    
#     # Handle large datasets with sampling
#     original_size = len(df)
#     if sample_size and len(df) > sample_size:
#         df = df.sample(sample_size, random_state=42)
    
#     # Step 3: Data type detection and cleaning
#     df_clean = df.copy()
    
#     # Convert potential date columns
#     date_columns = []
#     for col in df_clean.columns:
#         if df_clean[col].dtype == 'object':
#             try:
#                 df_clean[col] = pd.to_datetime(df_clean[col], errors='coerce')
#                 if not df_clean[col].isna().all():
#                     date_columns.append(col)
#             except:
#                 pass
    
#     # Detect numeric columns (excluding dates)
#     numeric_columns = df_clean.select_dtypes(include=[np.number]).columns.tolist()
    
#     # Detect categorical columns
#     categorical_columns = []
#     for col in df_clean.select_dtypes(include=['object']).columns:
#         if col not in date_columns and df_clean[col].nunique() <= max_categories:
#             categorical_columns.append(col)
    
#     # Text columns (high cardinality)
#     text_columns = [col for col in df_clean.select_dtypes(include=['object']).columns 
#                    if col not in categorical_columns and col not in date_columns]
    
#     # Convert numpy types to Python native types for JSON serialization
#     def convert_to_python_types(obj):
#         if isinstance(obj, (np.integer, np.int64)):
#             return int(obj)
#         elif isinstance(obj, (np.floating, np.float64)):
#             return float(obj)
#         elif isinstance(obj, np.bool_):
#             return bool(obj)
#         elif isinstance(obj, np.ndarray):
#             return obj.tolist()
#         elif isinstance(obj, dict):
#             return {k: convert_to_python_types(v) for k, v in obj.items()}
#         elif isinstance(obj, list):
#             return [convert_to_python_types(item) for item in obj]
#         elif pd.isna(obj):
#             return None
#         return obj
    
#     # Step 4: Data quality analysis
#     data_quality = {
#         "total_rows": len(df_clean),
#         "total_columns": len(df_clean.columns),
#         "missing_values": convert_to_python_types(df_clean.isnull().sum().to_dict()),
#         "missing_percentage": convert_to_python_types((df_clean.isnull().sum() / len(df_clean) * 100).to_dict()),
#         "duplicate_rows": int(df_clean.duplicated().sum()),
#         "column_types": {
#             "numeric": numeric_columns,
#             "categorical": categorical_columns,
#             "datetime": date_columns,
#             "text": text_columns
#         }
#     }
    
#     # Step 5: Summary statistics
#     summary_stats = {}
#     for col in numeric_columns:
#         summary_stats[col] = convert_to_python_types({
#             "mean": df_clean[col].mean(),
#             "median": df_clean[col].median(),
#             "std": df_clean[col].std(),
#             "min": df_clean[col].min(),
#             "max": df_clean[col].max(),
#             "q1": df_clean[col].quantile(0.25),
#             "q3": df_clean[col].quantile(0.75),
#             "skewness": df_clean[col].skew(),
#             "kurtosis": df_clean[col].kurtosis()
#         })
    
#     for col in categorical_columns:
#         value_counts = df_clean[col].value_counts()
#         summary_stats[col] = convert_to_python_types({
#             "unique_count": df_clean[col].nunique(),
#             "most_common": value_counts.index[0] if len(value_counts) > 0 else None,
#             "most_common_count": value_counts.iloc[0] if len(value_counts) > 0 else 0,
#             "value_counts": value_counts.head(10).to_dict()
#         })
    
#     # Step 6: Correlation analysis
#     numeric_df = df_clean[numeric_columns].dropna()
#     if len(numeric_columns) > 1:
#         correlation_matrix = numeric_df.corr(method='pearson')
#         spearman_matrix = numeric_df.corr(method='spearman')
#     else:
#         correlation_matrix = pd.DataFrame()
#         spearman_matrix = pd.DataFrame()
    
#     # Step 7: Outlier detection
#     outliers = {}
#     for col in numeric_columns:
#         Q1 = df_clean[col].quantile(0.25)
#         Q3 = df_clean[col].quantile(0.75)
#         IQR = Q3 - Q1
#         lower_bound = Q1 - 1.5 * IQR
#         upper_bound = Q3 + 1.5 * IQR
#         outlier_count = ((df_clean[col] < lower_bound) | (df_clean[col] > upper_bound)).sum()
#         outliers[col] = convert_to_python_types({
#             "count": outlier_count,
#             "percentage": (outlier_count / len(df_clean)) * 100,
#             "lower_bound": lower_bound,
#             "upper_bound": upper_bound
#         })
    
#     # Step 8: Clustering analysis
#     clustering_results = {}
#     if len(numeric_columns) >= 2:
#         try:
#             cluster_data = numeric_df.dropna()
#             if len(cluster_data) > 10:
#                 scaler = StandardScaler()
#                 scaled_data = scaler.fit_transform(cluster_data)
                
#                 kmeans = KMeans(n_clusters=min(5, len(cluster_data)//10), random_state=42)
#                 clusters = kmeans.fit_predict(scaled_data)
                
#                 if len(numeric_columns) > 2:
#                     pca = PCA(n_components=2, random_state=42)
#                     reduced_data = pca.fit_transform(scaled_data)
#                 else:
#                     reduced_data = scaled_data
                
#                 clustering_results = convert_to_python_types({
#                     "n_clusters": len(set(clusters)),
#                     "cluster_sizes": pd.Series(clusters).value_counts().to_dict(),
#                     "reduced_data": reduced_data.tolist(),
#                     "clusters": clusters.tolist(),
#                     "features": numeric_columns
#                 })
#         except Exception as e:
#             clustering_results = {"error": str(e)}
    
#     # Step 9: Predictive modeling (optional)
#     ml_results = {}
#     if ml_target and ml_target in df_clean.columns:
#         try:
#             if df_clean[ml_target].notna().sum() > 0:
#                 X = df_clean.drop(columns=[ml_target]).select_dtypes(include=[np.number])
#                 y = df_clean[ml_target]
                
#                 imputer = SimpleImputer(strategy='mean')
#                 X_imputed = imputer.fit_transform(X)
                
#                 X_train, X_test, y_train, y_test = train_test_split(
#                     X_imputed, y, test_size=0.2, random_state=42
#                 )
                
#                 if y.nunique() <= 10 and y.nunique() > 1:
#                     model = RandomForestClassifier(n_estimators=100, random_state=42)
#                     model.fit(X_train, y_train)
#                     y_pred = model.predict(X_test)
#                     accuracy = accuracy_score(y_test, y_pred)
#                     f1 = f1_score(y_test, y_pred, average='weighted') if y.nunique() > 2 else f1_score(y_test, y_pred)
                    
#                     ml_results = convert_to_python_types({
#                         "type": "classification",
#                         "accuracy": accuracy,
#                         "f1_score": f1,
#                         "feature_importance": dict(zip(X.columns, model.feature_importances_)),
#                         "model_type": "RandomForestClassifier"
#                     })
#                 elif y.nunique() > 10:
#                     model = RandomForestRegressor(n_estimators=100, random_state=42)
#                     model.fit(X_train, y_train)
#                     y_pred = model.predict(X_test)
#                     rmse = np.sqrt(mean_squared_error(y_test, y_pred))
#                     r2 = r2_score(y_test, y_pred)
                    
#                     ml_results = convert_to_python_types({
#                         "type": "regression",
#                         "rmse": rmse,
#                         "r2_score": r2,
#                         "feature_importance": dict(zip(X.columns, model.feature_importances_)),
#                         "model_type": "RandomForestRegressor"
#                     })
#                 else:
#                     ml_results = {"error": "Target column doesn't have enough variation for modeling"}
#             else:
#                 ml_results = {"error": "Target column has no valid data"}
                
#         except Exception as e:
#             ml_results = {"error": str(e)}
    
#     # Step 10: Generate visualizations and save as images
#     visualizations = {}
#     temp_dir = tempfile.mkdtemp()
#     static_dir = Path(temp_dir)
#     images_dir = static_dir / "images"
#     images_dir.mkdir(exist_ok=True)
    
#     # Create a function to save Plotly figures as images
#     def save_plotly_figure(fig, filename, width=800, height=600):
#         try:
#             # Save as PNG
#             img_path = images_dir / f"{filename}.png"
#             pio.write_image(fig, str(img_path), width=width, height=height, scale=2)
            
#             # Convert to base64 for embedding
#             with open(img_path, "rb") as img_file:
#                 img_data = base64.b64encode(img_file.read()).decode('utf-8')
            
#             return f"data:image/png;base64,{img_data}"
#         except Exception as e:
#             print(f"Error saving visualization {filename}: {str(e)}")
#             return None
    
#     # Create a function to save matplotlib figures as images
#     def save_matplotlib_figure(fig, filename, width=800, height=600, dpi=100):
#         try:
#             # Set size
#             fig.set_size_inches(width/dpi, height/dpi)
            
#             # Save as PNG
#             img_path = images_dir / f"{filename}.png"
#             fig.savefig(str(img_path), dpi=dpi, bbox_inches='tight', facecolor='#0f1116')
#             plt.close(fig)
            
#             # Convert to base64 for embedding
#             with open(img_path, "rb") as img_file:
#                 img_data = base64.b64encode(img_file.read()).decode('utf-8')
            
#             return f"data:image/png;base64,{img_data}"
#         except Exception as e:
#             print(f"Error saving matplotlib visualization {filename}: {str(e)}")
#             return None
    
#     # Correlation heatmap
#     if len(numeric_columns) > 1:
#         fig_corr = px.imshow(
#             correlation_matrix, 
#             title="📊 Correlation Heatmap",
#             aspect="auto",
#             color_continuous_scale="RdBu_r",
#             width=800, 
#             height=600,
#             labels=dict(x="Features", y="Features", color="Correlation")
#         )
#         fig_corr.update_layout(
#             font=dict(size=12, color='#e6e6e6'),
#             title_font_size=20,
#             title_x=0.5,
#             paper_bgcolor='rgba(0,0,0,0)',
#             plot_bgcolor='rgba(0,0,0,0)',
#             template=plotly_dark_template
#         )
#         visualizations["correlation_heatmap"] = save_plotly_figure(fig_corr, "correlation_heatmap")
    
#     # Create distribution charts for numeric columns
#     if len(numeric_columns) > 0:
#         for i, col in enumerate(numeric_columns[:6]):  # Limit to first 6 columns
#             # Create a matplotlib figure for better control
#             fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
#             fig.suptitle(f'Distribution of {col}', fontsize=16, color='white')
            
#             # Histogram with KDE
#             sns.histplot(df_clean[col].dropna(), kde=True, ax=ax1, color='#4ecdc4')
#             ax1.set_title('Histogram with KDE')
#             ax1.set_xlabel(col)
#             ax1.set_ylabel('Frequency')
            
#             # Box plot
#             sns.boxplot(y=df_clean[col].dropna(), ax=ax2, color='#ff6b6b')
#             ax2.set_title('Box Plot')
#             ax2.set_ylabel(col)
            
#             plt.tight_layout()
#             visualizations[f"distribution_{col}"] = save_matplotlib_figure(fig, f"distribution_{col}", width=1000, height=500)
    
#     # Categorical charts
#     if len(categorical_columns) > 0:
#         for i, col in enumerate(categorical_columns[:4]):  # Limit to first 4 columns
#             value_counts = df_clean[col].value_counts().head(10)
            
#             # Create a matplotlib figure
#             fig, ax = plt.subplots(figsize=(10, 6))
#             colors = plt.cm.Set3(np.linspace(0, 1, len(value_counts)))
            
#             bars = ax.bar(range(len(value_counts)), value_counts.values, color=colors)
#             ax.set_title(f'Top 10 Categories in {col}', fontsize=16, color='white')
#             ax.set_xlabel('Categories')
#             ax.set_ylabel('Count')
#             ax.set_xticks(range(len(value_counts)))
#             ax.set_xticklabels([str(x) for x in value_counts.index], rotation=45, ha='right')
            
#             # Add value labels on bars
#             for bar in bars:
#                 height = bar.get_height()
#                 ax.text(bar.get_x() + bar.get_width()/2., height + 0.1,
#                         f'{int(height)}', ha='center', va='bottom', color='white')
            
#             plt.tight_layout()
#             visualizations[f"categorical_{col}"] = save_matplotlib_figure(fig, f"categorical_{col}", width=800, height=500)
    
#     # Clustering visualization
#     if clustering_results and "reduced_data" in clustering_results:
#         reduced_df = pd.DataFrame(clustering_results["reduced_data"], columns=['PC1', 'PC2'])
#         reduced_df['Cluster'] = clustering_results["clusters"]
        
#         fig_cluster = px.scatter(
#             reduced_df, 
#             x='PC1', 
#             y='PC2', 
#             color='Cluster',
#             title="🎯 Cluster Analysis (PCA)",
#             width=800, 
#             height=500,
#             labels={'PC1': 'Principal Component 1', 'PC2': 'Principal Component 2'},
#             hover_data={'Cluster': True, 'PC1': ':.3f', 'PC2': ':.3f'}
#         )
        
#         fig_cluster.update_layout(
#             title_font_size=20,
#             title_x=0.5,
#             legend_title_text='Cluster',
#             font=dict(color='#e6e6e6'),
#             paper_bgcolor='rgba(0,0,0,0)',
#             plot_bgcolor='rgba(0,0,0,0)',
#             template=plotly_dark_template
#         )
#         visualizations["clustering"] = save_plotly_figure(fig_cluster, "clustering")
    
#     # Add missing values visualization
#     missing_data = pd.DataFrame({
#         'Column': list(data_quality['missing_percentage'].keys()),
#         'Missing_Percentage': list(data_quality['missing_percentage'].values())
#     }).sort_values('Missing_Percentage', ascending=False)

#     # Create a matplotlib figure for missing values
#     fig, ax = plt.subplots(figsize=(10, max(6, len(missing_data) * 0.3)))
#     colors = ['#ff6b6b' if x > 50 else '#f9c80e' if x > 10 else '#4ecdc4' for x in missing_data['Missing_Percentage']]
    
#     bars = ax.barh(range(len(missing_data)), missing_data['Missing_Percentage'], color=colors)
#     ax.set_title('Missing Values by Column', fontsize=16, color='white')
#     ax.set_xlabel('Missing Percentage (%)')
#     ax.set_yticks(range(len(missing_data)))
#     ax.set_yticklabels(missing_data['Column'])
#     ax.set_xlim(0, 100)
    
#     # Add value labels on bars
#     for i, bar in enumerate(bars):
#         width = bar.get_width()
#         ax.text(width + 1, bar.get_y() + bar.get_height()/2.,
#                 f'{width:.1f}%', ha='left', va='center', color='white')
    
#     plt.tight_layout()
#     visualizations["missing_values"] = save_matplotlib_figure(fig, "missing_values", width=800, height=max(400, len(missing_data) * 20))
    
#     # Create a pairplot for the first 5 numeric columns (if available)
#     if len(numeric_columns) >= 3:
#         try:
#             pairplot_cols = numeric_columns[:5]
#             pairplot_data = df_clean[pairplot_cols].dropna()
            
#             # Create a pairplot with seaborn
#             pairplot_grid = sns.pairplot(pairplot_data, diag_kind='kde', plot_kws={'alpha': 0.6, 's': 30})
#             pairplot_grid.fig.suptitle('Pairplot of Numeric Variables', y=1.02, color='white', fontsize=16)
            
#             # Save the pairplot
#             visualizations["pairplot"] = save_matplotlib_figure(pairplot_grid.fig, "pairplot", width=1200, height=1000)
#         except Exception as e:
#             print(f"Error creating pairplot: {str(e)}")
    
#     # Step 11: Create advanced HTTP server with HTML report
#     # Save artifacts to JSON
#     artifacts = convert_to_python_types({
#         "processed_data": df_clean.to_dict(),
#         "data_quality": data_quality,
#         "summary_stats": summary_stats,
#         "correlations": {
#             "pearson": correlation_matrix.to_dict(),
#             "spearman": spearman_matrix.to_dict()
#         },
#         "outliers": outliers,
#         "clustering": clustering_results,
#         "ml_results": ml_results,
#         "visualizations": visualizations
#     })
    
#     artifacts_file = static_dir / "artifacts.json"
#     with open(artifacts_file, 'w') as f:
#         json.dump(artifacts, f, indent=2, default=str)
    
#     # Save processed data to CSV
#     processed_csv = static_dir / "processed_data.csv"
#     df_clean.to_csv(processed_csv, index=False)
    
#     # Create HTML content with advanced dark theme
#     html_content = f"""
#     <!DOCTYPE html>
#     <html lang="en">
#     <head>
#         <meta charset="UTF-8">
#         <meta name="viewport" content="width=device-width, initial-scale=1.0">
#         <title>Advanced Data Analysis Report</title>
#         <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
#         <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
#         <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
#         <style>
#             :root {{
#                 --primary: #6366f1;
#                 --primary-dark: #4f46e5;
#                 --secondary: #94a3b8;
#                 --success: #10b981;
#                 --warning: #f59e0b;
#                 --danger: #ef4444;
#                 --info: #0ea5e9;
#                 --dark: #0f1116;
#                 --darker: #0a0c10;
#                 --light: #1e293b;
#                 --lighter: #334155;
#                 --text: #e6e6e6;
#                 --text-muted: #94a3b8;
#                 --shadow-sm: 0 1px 3px 0 rgba(0, 0, 0, 0.5);
#                 --shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.5), 0 2px 4px -1px rgba(0, 0, 0, 0.4);
#                 --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.5), 0 4px 6px -2px rgba(0, 0, 0, 0.4);
#                 --radius: 12px;
#                 --radius-sm: 8px;
#                 --transition: all 0.3s ease;
#                 --gradient: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
#             }}

#             * {{
#                 margin: 0;
#                 padding: 0;
#                 box-sizing: border-box;
#             }}

#             body {{
#                 font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
#                 background: var(--darker);
#                 color: var(--text);
#                 line-height: 1.6;
#                 min-height: 100vh;
#                 padding: 20px;
#             }}

#             .container {{
#                 max-width: 1400px;
#                 margin: 0 auto;
#             }}

#             .glass-card {{
#                 background: rgba(30, 41, 59, 0.7);
#                 backdrop-filter: blur(20px);
#                 border-radius: var(--radius);
#                 border: 1px solid rgba(255, 255, 255, 0.1);
#                 box-shadow: var(--shadow-lg);
#                 padding: 30px;
#                 margin-bottom: 24px;
#                 transition: var(--transition);
#             }}

#             .glass-card:hover {{
#                 transform: translateY(-2px);
#                 box-shadow: var(--shadow-lg), 0 25px 50px -12px rgba(0, 0, 0, 0.5);
#             }}

#             .header {{
#                 text-align: center;
#                 margin-bottom: 32px;
#                 background: var(--gradient);
#                 padding: 40px 30px;
#                 position: relative;
#                 overflow: hidden;
#             }}

#             .header::before {{
#                 content: '';
#                 position: absolute;
#                 top: 0;
#                 left: 0;
#                 right: 0;
#                 bottom: 0;
#                 background: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23ffffff' fill-opacity='0.05'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
#                 opacity: 0.3;
#             }}

#             .header h1 {{
#                 font-size: 2.8rem;
#                 font-weight: 800;
#                 margin-bottom: 12px;
#                 position: relative;
#                 background: linear-gradient(135deg, #fff 0%, #cbd5e1 100%);
#                 -webkit-background-clip: text;
#                 -webkit-text-fill-color: transparent;
#             }}

#             .header p {{
#                 font-size: 1.2rem;
#                 color: rgba(255, 255, 255, 0.8);
#                 position: relative;
#                 max-width: 600px;
#                 margin: 0 auto;
#             }}

#             .stats-grid {{
#                 display: grid;
#                 grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
#                 gap: 20px;
#                 margin-bottom: 32px;
#             }}

#             .stat-card {{
#                 background: linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.7) 100%);
#                 padding: 24px;
#                 border-radius: var(--radius);
#                 border-left: 4px solid var(--primary);
#                 box-shadow: var(--shadow);
#                 transition: var(--transition);
#                 display: flex;
#                 flex-direction: column;
#             }}

#             .stat-card:hover {{
#                 transform: translateY(-3px);
#                 box-shadow: var(--shadow-lg);
#             }}

#             .stat-card h3 {{
#                 font-size: 0.9rem;
#                 font-weight: 500;
#                 color: var(--text-muted);
#                 margin-bottom: 12px;
#                 text-transform: uppercase;
#                 letter-spacing: 0.5px;
#             }}

#             .stat-card p {{
#                 font-size: 2.2rem;
#                 font-weight: 700;
#                 color: var(--primary);
#                 margin-top: auto;
#             }}

#             .stat-card .trend {{
#                 display: flex;
#                 align-items: center;
#                 margin-top: 8px;
#                 font-size: 0.9rem;
#             }}

#             .stat-card .trend.up {{
#                 color: var(--success);
#             }}

#             .stat-card .trend.down {{
#                 color: var(--danger);
#             }}

#             .chart-container {{
#                 background: rgba(15, 23, 42, 0.5);
#                 padding: 24px;
#                 border-radius: var(--radius);
#                 box-shadow: var(--shadow);
#                 margin: 24px 0;
#                 border: 1px solid rgba(255, 255, 255, 0.1);
#             }}

#             .chart-grid {{
#                 display: grid;
#                 grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
#                 gap: 24px;
#                 margin: 24px 0;
#             }}

#             .chart-title {{
#                 font-size: 1.4rem;
#                 font-weight: 600;
#                 margin-bottom: 20px;
#                 color: var(--text);
#                 display: flex;
#                 align-items: center;
#                 gap: 10px;
#             }}

#             .chart-img {{
#                 width: 100%;
#                 border-radius: var(--radius-sm);
#                 box-shadow: var(--shadow);
#                 transition: var(--transition);
#             }}

#             .chart-img:hover {{
#                 transform: scale(1.02);
#                 box-shadow: var(--shadow-lg);
#             }}

#             .nav {{
#                 display: flex;
#                 gap: 8px;
#                 margin-bottom: 32px;
#                 flex-wrap: wrap;
#                 background: rgba(15, 23, 42, 0.5);
#                 padding: 12px;
#                 border-radius: var(--radius);
#             }}

#             .nav-btn {{
#                 padding: 12px 24px;
#                 border: none;
#                 background: rgba(30, 41, 59, 0.7);
#                 color: var(--text);
#                 border-radius: var(--radius-sm);
#                 cursor: pointer;
#                 font-weight: 500;
#                 transition: var(--transition);
#                 display: flex;
#                 align-items: center;
#                 gap: 8px;
#                 border: 1px solid rgba(255, 255, 255, 0.1);
#             }}

#             .nav-btn:hover {{
#                 background: var(--primary);
#                 transform: translateY(-2px);
#             }}

#             .nav-btn.active {{
#                 background: var(--gradient);
#                 box-shadow: var(--shadow);
#             }}

#             .section {{
#                 display: none;
#                 animation: fadeIn 0.5s ease;
#             }}

#             .section.active {{
#                 display: block;
#             }}

#             .section h2 {{
#                 font-size: 1.8rem;
#                 font-weight: 700;
#                 color: var(--text);
#                 margin-bottom: 24px;
#                 padding-bottom: 12px;
#                 border-bottom: 2px solid rgba(255, 255, 255, 0.1);
#                 display: flex;
#                 align-items: center;
#                 gap: 12px;
#             }}

#             .data-quality-meters {{
#                 display: grid;
#                 grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
#                 gap: 20px;
#                 margin: 30px 0;
#             }}

#             .meter {{
#                 background: rgba(15, 23, 42, 0.5);
#                 padding: 20px;
#                 border-radius: var(--radius);
#                 box-shadow: var(--shadow);
#             }}

#             .meter-header {{
#                 display: flex;
#                 justify-content: between;
#                 align-items: center;
#                 margin-bottom: 15px;
#             }}

#             .meter-title {{
#                 font-size: 1.1rem;
#                 font-weight: 600;
#                 color: var(--text);
#             }}

#             .meter-value {{
#                 font-size: 1.5rem;
#                 font-weight: 700;
#                 color: var(--primary);
#             }}

#             .meter-bar {{
#                 height: 8px;
#                 background: rgba(255, 255, 255, 0.1);
#                 border-radius: 4px;
#                 overflow: hidden;
#                 margin: 10px 0;
#             }}

#             .meter-fill {{
#                 height: 100%;
#                 border-radius: 4px;
#                 transition: width 1s ease;
#             }}

#             .quality-good {{
#                 background: var(--success);
#             }}

#             .quality-warning {{
#                 background: var(--warning);
#             }}

#             .quality-bad {{
#                 background: var(--danger);
#             }}

#             .export-btns {{
#                 display: flex;
#                 gap: 16px;
#                 margin-top: 32px;
#                 flex-wrap: wrap;
#             }}

#             .export-btn {{
#                 padding: 12px 24px;
#                 border: 2px solid var(--primary);
#                 background: transparent;
#                 color: var(--primary);
#                 border-radius: var(--radius-sm);
#                 cursor: pointer;
#                 font-weight: 500;
#                 transition: var(--transition);
#                 display: flex;
#                 align-items: center;
#                 gap: 8px;
#             }}

#             .export-btn:hover {{
#                 background: var(--primary);
#                 color: white;
#                 transform: translateY(-2px);
#             }}

#             @keyframes fadeIn {{
#                 from {{ opacity: 0; transform: translateY(20px); }}
#                 to {{ opacity: 1; transform: translateY(0); }}
#             }}

#             .badge {{
#                 display: inline-block;
#                 padding: 4px 12px;
#                 border-radius: 20px;
#                 font-size: 0.8rem;
#                 font-weight: 500;
#                 margin-left: 8px;
#             }}

#             .badge-success {{
#                 background: var(--success);
#                 color: white;
#             }}

#             .badge-warning {{
#                 background: var(--warning);
#                 color: white;
#             }}

#             .badge-danger {{
#                 background: var(--danger);
#                 color: white;
#             }}

#             .badge-info {{
#                 background: var(--info);
#                 color: white;
#             }}

#             .loading {{
#                 display: flex;
#                 justify-content: center;
#                 align-items: center;
#                 padding: 40px;
#             }}

#             .spinner {{
#                 width: 40px;
#                 height: 40px;
#                 border: 4px solid rgba(255, 255, 255, 0.1);
#                 border-top: 4px solid var(--primary);
#                 border-radius: 50%;
#                 animation: spin 1s linear infinite;
#             }}

#             @keyframes spin {{
#                 0% {{ transform: rotate(0deg); }}
#                 100% {{ transform: rotate(360deg); }}
#             }}

#             @media (max-width: 768px) {{
#                 .container {{
#                     padding: 12px;
#                 }}
                
#                 .nav {{
#                     flex-direction: column;
#                 }}
                
#                 .chart-grid {{
#                     grid-template-columns: 1fr;
#                 }}
                
#                 .stats-grid {{
#                     grid-template-columns: 1fr;
#                 }}
                
#                 .export-btns {{
#                     flex-direction: column;
#                 }}
                
#                 .header h1 {{
#                     font-size: 2rem;
#                 }}
                
#                 .header p {{
#                     font-size: 1rem;
#                 }}
#             }}
#         </style>
#     </head>
#     <body>
#         <div class="container">
#             <div class="glass-card header">
#                 <h1><i class="fas fa-chart-network"></i> Advanced Data Analysis Report</h1>
#                 <p>Comprehensive analysis of your dataset with interactive metrics and visualizations</p>
#             </div>

#             <div class="glass-card">
#                 <div class="nav">
#                     <button class="nav-btn active" onclick="showSection('overview')">
#                         <i class="fas fa-chart-pie"></i> Overview
#                     </button>
#                     <button class="nav-btn" onclick="showSection('quality')">
#                         <i class="fas fa-tachometer-alt"></i> Data Quality
#                     </button>
#                     <button class="nav-btn" onclick="showSection('columns')">
#                         <i class="fas fa-columns"></i> Columns
#                     </button>
#                     <button class="nav-btn" onclick="showSection('visualizations')">
#                         <i class="fas fa-chart-line"></i> Visualizations
#                     </button>
#                     <button class="nav-btn" onclick="showSection('modeling')">
#                         <i class="fas fa-brain"></i> Modeling
#                     </button>
#                     <button class="nav-btn" onclick="showSection('exports')">
#                         <i class="fas fa-download"></i> Exports
#                     </button>
#                 </div>

#                 <div id="overview" class="section active">
#                     <h2><i class="fas fa-chart-pie"></i> Dataset Overview</h2>
#                     <div class="stats-grid">
#                         <div class="stat-card">
#                             <h3>Total Rows</h3>
#                             <p>{data_quality['total_rows']}</p>
#                             <div class="trend up">
#                                 <i class="fas fa-database"></i>
#                                 <span>Original: {original_size}</span>
#                             </div>
#                         </div>
#                         <div class="stat-card">
#                             <h3>Total Columns</h3>
#                             <p>{data_quality['total_columns']}</p>
#                         </div>
#                         <div class="stat-card">
#                             <h3>Duplicate Rows</h3>
#                             <p>{data_quality['duplicate_rows']}</p>
#                             <div class="trend {{ 'down' if data_quality['duplicate_rows'] > 0 else 'up' }}">
#                                 <i class="fas {{ 'fa-exclamation-triangle' if data_quality['duplicate_rows'] > 0 else 'fa-check-circle' }}"></i>
#                                 <span>{{ 'Has duplicates' if data_quality['duplicate_rows'] > 0 else 'No duplicates' }}</span>
#                             </div>

#                         </div>
#                         <div class="stat-card">
#                             <h3>Missing Values</h3>
#                             <p>{sum(data_quality['missing_values'].values())}</p>
#                             <div class="trend {{ 'down' if sum(data_quality['missing_values'].values()) > 0 else 'up' }}">
#                                 <i class="fas {{ 'fa-exclamation-triangle' if sum(data_quality['missing_values'].values()) > 0 else 'fa-check-circle' }}"></i>
#                                 <span>{{ 'Has missing values' if sum(data_quality['missing_values'].values()) > 0 else 'Complete data' }}</span>
#                             </div>

#                         </div>
#                     </div>

#                     <h3><i class="fas fa-layer-group"></i> Column Types</h3>
#                     <div class="stats-grid">
#                         <div class="stat-card">
#                             <h3>Numeric</h3>
#                             <p>{len(data_quality['column_types']['numeric'])}</p>
#                         </div>
#                         <div class="stat-card">
#                             <h3>Categorical</h3>
#                             <p>{len(data_quality['column_types']['categorical'])}</p>
#                         </div>
#                         <div class="stat-card">
#                             <h3>Date/Time</h3>
#                             <p>{len(data_quality['column_types']['datetime'])}</p>
#                         </div>
#                         <div class="stat-card">
#                             <h3>Text</h3>
#                             <p>{len(data_quality['column_types']['text'])}</p>
#                         </div>
#                     </div>
#                 </div>

#                 <div id="quality" class="section">
#                     <h2><i class="fas fa-tachometer-alt"></i> Data Quality Assessment</h2>
                    
#                     <div class="data-quality-meters">
#                         <div class="meter">
#                             <div class="meter-header">
#                                 <span class="meter-title">Completeness Score</span>
#                                 <span class="meter-value">{100 - (sum(data_quality['missing_values'].values()) / (data_quality['total_rows'] * data_quality['total_columns']) * 100):.1f}%</span>
#                             </div>
#                             <div class="meter-bar">
#                                 <div class="meter-fill quality-good" style="width: {100 - (sum(data_quality['missing_values'].values()) / (data_quality['total_rows'] * data_quality['total_columns']) * 100)}%"></div>
#                             </div>
#                             <p>Percentage of non-missing values across the dataset</p>
#                         </div>
                        
#                         <div class="meter">
#                             <div class="meter-header">
#                                 <span class="meter-title">Uniqueness Score</span>
#                                 <span class="meter-value">{100 - (data_quality['duplicate_rows'] / data_quality['total_rows'] * 100):.1f}%</span>
#                             </div>
#                             <div class="meter-bar">
#                                 <div class="meter-fill {{ 'quality-warning' if (data_quality['duplicate_rows'] / data_quality['total_rows'] * 100) > 5 else 'quality-good' }}" 
#                                     style="width: {{ 100 - (data_quality['duplicate_rows'] / data_quality['total_rows'] * 100) }}%">
#                                 </div>
#                             </div>

#                             <p>Percentage of unique rows in the dataset</p>
#                         </div>
#                     </div>
                    
#                     <div class="chart-container">
#                         <h3 class="chart-title"><i class="fas fa-exclamation-triangle"></i> Missing Values by Column</h3>
#                         <img src="{visualizations.get('missing_values', '')}" class="chart-img" alt="Missing Values Chart">
#                     </div>
#                 </div>

#                 <div id="columns" class="section">
#                     <h2><i class="fas fa-columns"></i> Column Analysis</h2>
#                     <div id="column-stats" class="chart-grid"></div>
#                 </div>

#                 <div id="visualizations" class="section">
#                     <h2><i class="fas fa-chart-line"></i> Advanced Visualizations</h2>
                    
#                     <div class="chart-container">
#                         <h3 class="chart-title"><i class="fas fa-heartbeat"></i> Correlation Heatmap</h3>
#                         <img src="{visualizations.get('correlation_heatmap', '')}" class="chart-img" alt="Correlation Heatmap">
#                     </div>
                    
#                     <div class="chart-grid">
#                         <div class="chart-container">
#                             <h3 class="chart-title"><i class="fas fa-project-diagram"></i> Cluster Analysis</h3>
#                             <img src="{visualizations.get('clustering', '')}" class="chart-img" alt="Cluster Analysis">
#                         </div>
                        
#                         <div class="chart-container">
#                             <h3 class="chart-title"><i class="fas fa-chart-scatter"></i> Variable Relationships</h3>
#                             <img src="{visualizations.get('pairplot', '')}" class="chart-img" alt="Pairplot">
#                         </div>
#                     </div>
                    
#                     <div class="chart-grid" id="distribution-charts">
#                         <!-- Distribution charts will be inserted here -->
#                     </div>
#                 </div>

#                 <div id="modeling" class="section">
#                     <h2><i class="fas fa-brain"></i> Predictive Modeling</h2>
#                     <div id="model-results"></div>
#                 </div>

#                 <div id="exports" class="section">
#                     <h2><i class="fas fa-download"></i> Export Options</h2>
#                     <p>Download your analysis results and processed data</p>
#                     <div class="export-btns">
#                         <button class="export-btn" onclick="exportHTML()">
#                             <i class="fas fa-file-code"></i> Export HTML Report
#                         </button>
#                         <button class="export-btn" onclick="exportPDF()">
#                             <i class="fas fa-file-pdf"></i> Export PDF Report
#                         </button>
#                         <button class="export-btn" onclick="exportCSV()">
#                             <i class="fas fa-file-csv"></i> Download Processed Data
#                         </button>
#                     </div>
#                 </div>
#             </div>
#         </div>

#         <script>
#             let artifacts = {{}};
#             let currentSection = 'overview';
            
#             function showSection(sectionId) {{
#                 // Hide all sections
#                 document.querySelectorAll('.section').forEach(section => {{
#                     section.style.display = 'none';
#                 }});
                
#                 // Remove active class from all buttons
#                 document.querySelectorAll('.nav-btn').forEach(btn => {{
#                     btn.classList.remove('active');
#                 }});
                
#                 // Show selected section and activate button
#                 document.getElementById(sectionId).style.display = 'block';
#                 const selector = `.nav-btn[onclick*="showSection('${{sectionId}}')"]`;
#                 document.querySelector(selector).classList.add('active');
#                 currentSection = sectionId;
#             }}
            
#             async function loadArtifacts() {{
#                 try {{
#                     const response = await fetch('/artifacts.json');
#                     artifacts = await response.json();
#                     renderColumnStats();
#                     renderModelResults();
#                     renderDistributionCharts();
#                 }} catch (error) {{
#                     console.error('Error loading artifacts:', error);
#                 }}
#             }}
            
#             function renderDistributionCharts() {{
#                 const container = document.getElementById('distribution-charts');
#                 if (!container) return;
                
#                 if (artifacts.visualizations) {{
#                     Object.keys(artifacts.visualizations).forEach(key => {{
#                         if (key.startsWith('distribution_') || key.startsWith('categorical_')) {{
#                             const chartDiv = document.createElement('div');
#                             chartDiv.className = 'chart-container';
                            
#                             const title = key.startsWith('distribution_') 
#                                 ? `Distribution of ${{key.replace('distribution_', '')}}` 
#                                 : `Categories in ${{key.replace('categorical_', '')}}`;
                                
#                             const icon = key.startsWith('distribution_') 
#                                 ? 'fas fa-chart-bar' 
#                                 : 'fas fa-chart-pie';
                                
#                             chartDiv.innerHTML = `
#                                 <h3 class="chart-title"><i class="${{icon}}"></i> ${{title}}</h3>
#                                 <img src="${{artifacts.visualizations[key]}}" class="chart-img" alt="${{title}}">
#                             `;
                            
#                             container.appendChild(chartDiv);
#                         }}
#                     }});
#                 }}
#             }}
            
#             function renderColumnStats() {{
#                 const container = document.getElementById('column-stats');
#                 if (!container || !artifacts.summary_stats) return;
                
#                 Object.entries(artifacts.summary_stats).forEach(([col, stats]) => {{
#                     const card = document.createElement('div');
#                     card.className = 'chart-container';
                    
#                     let statsHTML = '';
#                     if (stats.mean !== undefined) {{
#                         // Numeric column
#                         statsHTML = `
#                             <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
#                                 <div><strong>Mean:</strong> ${{stats.mean?.toFixed(4)}}</div>
#                                 <div><strong>Std:</strong> ${{stats.std?.toFixed(4)}}</div>
#                                 <div><strong>Min:</strong> ${{stats.min?.toFixed(4)}}</div>
#                                 <div><strong>Max:</strong> ${{stats.max?.toFixed(4)}}</div>
#                                 <div><strong>Q1:</strong> ${{stats.q1?.toFixed(4)}}</div>
#                                 <div><strong>Q3:</strong> ${{stats.q3?.toFixed(4)}}</div>
#                                 <div><strong>Skewness:</strong> ${{stats.skewness?.toFixed(4)}}</div>
#                                 <div><strong>Kurtosis:</strong> ${{stats.kurtosis?.toFixed(4)}}</div>
#                             </div>
#                         `;
#                     }} else {{
#                         // Categorical column
#                         statsHTML = `
#                             <div><strong>Unique Values:</strong> ${{stats.unique_count}}</div>
#                             <div><strong>Most Common:</strong> ${{stats.most_common}} (${{stats.most_common_count}} occurrences)</div>
#                             <div style="margin-top: 12px;">
#                                 <strong>Value Counts (Top 10):</strong>
#                                 <pre style="background: rgba(0,0,0,0.2); padding: 10px; border-radius: 6px; margin-top: 8px; max-height: 200px; overflow-y: auto;">
# ${{JSON.stringify(stats.value_counts, null, 2)}}
#                                 </pre>
#                             </div>
#                         `;
#                     }}
                    
#                     card.innerHTML = `
#                         <h3 class="chart-title"><i class="fas ${{stats.mean !== undefined ? 'fa-calculator' : 'fa-list'}}"></i> ${{col}}</h3>
#                         ${{statsHTML}}
#                     `;
                    
#                     container.appendChild(card);
#                 }});
#             }}
            
#             function renderModelResults() {{
#                 const container = document.getElementById('model-results');
#                 if (!container) return;
                
#                 if (artifacts.ml_results && !artifacts.ml_results.error) {{
#                     const card = document.createElement('div');
#                     card.className = 'chart-container';
                    
#                     let resultsHTML = '';
#                     if (artifacts.ml_results.type === 'classification') {{
#                         resultsHTML = `
#                             <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
#                                 <div class="stat-card">
#                                     <h3>Accuracy</h3>
#                                     <p>${{(artifacts.ml_results.accuracy * 100).toFixed(2)}}%</p>
#                                 </div>
#                                 <div class="stat-card">
#                                     <h3>F1 Score</h3>
#                                     <p>${{(artifacts.ml_results.f1_score * 100).toFixed(2)}}%</p>
#                                 </div>
#                             </div>
#                             <div style="margin-top: 20px;">
#                                 <h4>Feature Importance</h4>
#                                 <pre style="background: rgba(0,0,0,0.2); padding: 10px; border-radius: 6px; margin-top: 8px; max-height: 300px; overflow-y: auto;">
# ${{JSON.stringify(artifacts.ml_results.feature_importance, null, 2)}}
#                                 </pre>
#                             </div>
#                         `;
#                     }} else if (artifacts.ml_results.type === 'regression') {{
#                         resultsHTML = `
#                             <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
#                                 <div class="stat-card">
#                                     <h3>RMSE</h3>
#                                     <p>${{artifacts.ml_results.rmse?.toFixed(4)}}</p>
#                                 </div>
#                                 <div class="stat-card">
#                                     <h3>R² Score</h3>
#                                     <p>${{(artifacts.ml_results.r2_score * 100).toFixed(2)}}%</p>
#                                 </div>
#                             </div>
#                             <div style="margin-top: 20px;">
#                                 <h4>Feature Importance</h4>
#                                 <pre style="background: rgba(0,0,0,0.2); padding: 10px; border-radius: 6px; margin-top: 8px; max-height: 300px; overflow-y: auto;">
# ${{JSON.stringify(artifacts.ml_results.feature_importance, null, 2)}}
#                                 </pre>
#                             </div>
#                         `;
#                     }}
                    
#                     card.innerHTML = `
#                         <h3 class="chart-title"><i class="fas fa-brain"></i> Model Results (${{artifacts.ml_results.type}})</h3>
#                         ${{resultsHTML}}
#                     `;
                    
#                     container.appendChild(card);
#                 }} else {{
#                     container.innerHTML = `
#                         <div class="chart-container">
#                             <h3 class="chart-title"><i class="fas fa-info-circle"></i> Predictive Modeling</h3>
#                             <p>No target column was specified for predictive modeling. To enable machine learning features, 
#                             specify a target column when starting the analysis.</p>
#                             <p>Example voice command: "Nova, analyze dataset with target sales"</p>
#                         </div>
#                     `;
#                 }}
#             }}
            
#             function exportHTML() {{
#                 const htmlContent = document.documentElement.outerHTML;
#                 const blob = new Blob([htmlContent], {{type: 'text/html'}});
#                 const url = URL.createObjectURL(blob);
#                 const a = document.createElement('a');
#                 a.href = url;
#                 a.download = 'advanced_data_analysis_report.html';
#                 a.click();
#             }}
            
#             function exportPDF() {{
#                 alert('PDF export feature would be implemented with a PDF generation library like jsPDF');
#             }}
            
#             function exportCSV() {{
#                 window.location.href = '/processed_data.csv';
#             }}
            
#             // Initialize when DOM is loaded
#             document.addEventListener('DOMContentLoaded', function() {{
#                 showSection('overview');
#                 loadArtifacts();
                
#                 // Animate meter bars
#                 setTimeout(() => {{
#                     document.querySelectorAll('.meter-fill').forEach(bar => {{
#                         bar.style.width = bar.style.width;
#                     }});
#                 }}, 500);
#             }});
#         </script>
#     </body>
#     </html>
#     """
    
#     # Save HTML file
#     html_file = static_dir / "index.html"
#     with open(html_file, 'w', encoding='utf-8') as f:
#         f.write(html_content)
    
#     # Create simple HTTP server
#     class DataAnalysisHandler(http.server.SimpleHTTPRequestHandler):
#         def __init__(self, *args, **kwargs):
#             super().__init__(*args, directory=str(static_dir), **kwargs)
    
#     def run_server():
#         with socketserver.TCPServer(("", port), DataAnalysisHandler) as httpd:
#             print(f"Serving at port {port}")
#             httpd.serve_forever()
    
#     # Start server in background thread
#     server_thread = threading.Thread(target=run_server, daemon=True)
#     server_thread.start()
    
#     # Wait for server to start
#     await asyncio.sleep(2)
    
#     # Open browser
#     webbrowser.open(f"http://localhost:{port}")
    
#     # Return results
#     return {
#         "report_url": f"http://localhost:{port}",
#         "summary": {
#             "data_quality": data_quality,
#             "dataset_size": f"{len(df_clean)} rows  {len(df_clean.columns)} columns",
#             "analysis_completed": True
#         },
#         "artifacts": {
#             "processed_csv": str(processed_csv),
#             "model": "Baseline model trained" if ml_results and "error" not in ml_results else "No model trained"
#         }
#     }
# PyAutoGUI Configuration
import asyncio
import pandas as pd
import numpy as np
from pathlib import Path
import json
import tempfile
import webbrowser
import warnings
import http.server
import socketserver
import threading
import base64
from datetime import datetime
from plotly.subplots import make_subplots
import plotly.graph_objects as go
import plotly.express as px
import plotly.io as pio

warnings.filterwarnings('ignore')

# Advanced data analysis libraries
from sklearn.ensemble import RandomForestRegressor, IsolationForest
from sklearn.linear_model import LinearRegression
from sklearn.tree import DecisionTreeRegressor
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error, r2_score
from scipy import stats
from scipy import signal
from scipy.optimize import curve_fit
import statsmodels.api as sm
from typing import Dict, Any, List, Tuple

# Set dark theme for Plotly
plotly_dark_template = go.layout.Template(
    layout=go.Layout(
        paper_bgcolor='rgba(15, 23, 42, 1)',
        plot_bgcolor='rgba(15, 23, 42, 0.8)',
        font=dict(color='#e6e6e6', family='Inter'),
        title_font=dict(size=24, color='#ffffff'),
        colorway=['#ff6b6b', '#4ecdc4', '#45b7d1', '#f9c80e', '#f86624', 
                 '#ea3546', '#662e9b', '#c5d86d', '#0cce6b', '#5f0f40']
    )
)

class AdvancedGroundwaterAnalysisEngine:
    """Enhanced groundwater data analysis engine with advanced ML capabilities"""
    
    def __init__(self):
        self.dataset = None
        self.selected_state = None
        self.selected_district = None
        self.selected_block = None
        self.filtered_data = None
        self.analysis_results = {}
        self.ml_models = {}
        
    def detect_state_datasets(self, folder_path: str) -> Dict[str, List[str]]:
        """Detect all state datasets in the current folder"""
        state_datasets = {}
        folder = Path(folder_path)
        
        state_patterns = {
            'gujarat': ['gujarat', 'guj', 'gj'],
            'maharashtra': ['maharashtra', 'maha', 'mh'],
            'rajasthan': ['rajasthan', 'raj', 'rj'],
            'karnataka': ['karnataka', 'karn', 'ka'],
            'tamilnadu': ['tamilnadu', 'tamil', 'tn'],
            'kerala': ['kerala', 'ker', 'kl'],
            'andhra': ['andhra', 'ap'],
            'telangana': ['telangana', 'tel', 'tg'],
            'punjab': ['punjab', 'pun', 'pb'],
            'haryana': ['haryana', 'har', 'hr'],
            'uttarakhand': ['uttarakhand', 'uk'],
            'himachal': ['himachal', 'hp'],
            'assam': ['assam', 'as'],
            'bihar': ['bihar', 'br'],
            'jharkhand': ['jharkhand', 'jh'],
            'odisha': ['odisha', 'odi', 'or'],
            'westbengal': ['westbengal', 'bengal', 'wb'],
            'madhyapradesh': ['madhyapradesh', 'mp'],
            'uttarpradesh': ['uttarpradesh', 'up'],
            'goa': ['goa', 'ga']
        }
        
        for file_path in folder.glob("*.*"):
            if file_path.suffix.lower() in ['.xlsx', '.xls', '.csv']:
                filename = file_path.stem.lower()
                
                for state, patterns in state_patterns.items():
                    if any(pattern in filename for pattern in patterns):
                        if state not in state_datasets:
                            state_datasets[state] = []
                        state_datasets[state].append(str(file_path))
                        break
        
        return state_datasets
    
    def load_groundwater_data(self, file_path: str) -> pd.DataFrame:
        """Load groundwater dataset with intelligent column detection and preprocessing"""
        try:
            if file_path.endswith('.csv'):
                df = pd.read_csv(file_path, encoding='utf-8', low_memory=False)
            else:
                df = pd.read_excel(file_path, engine='openpyxl')
            
            # Standardize column names
            df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
            
            # Intelligent column mapping
            column_mappings = {
                'state': ['state', 'st', 'state_name'],
                'district': ['district', 'dist', 'district_name'],
                'block': ['block', 'block_name', 'block_no', 'block_number', 'taluka'],
                'year': ['year', 'yr', 'year_of_data'],
                'annual_recharge_mcm': ['annual_recharge_mcm', 'recharge', 'annual_recharge'],
                'extractable_resource_mcm': ['extractable_resource_mcm', 'extractable', 'resource'],
                'extraction_mcm': ['extraction_mcm', 'extraction', 'annual_extraction'],
                'stage_of_extraction_percent': ['stage_of_extraction_percent', 'extraction_percent', 'stage'],
                'category': ['category', 'cat', 'status', 'groundwater_category']
            }
            
            # Map columns
            for standard_col, possible_cols in column_mappings.items():
                for col in possible_cols:
                    if col in df.columns and standard_col not in df.columns:
                        df[standard_col] = df[col]
                        break
            
            # Data preprocessing
            df = self.preprocess_data(df)
            
            return df
            
        except Exception as e:
            raise ValueError(f"Error loading dataset: {str(e)}")
    
    def preprocess_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Advanced data preprocessing and feature engineering"""
        # Handle missing values
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        df[numeric_cols] = df[numeric_cols].fillna(df[numeric_cols].median())
        
        # Feature engineering
        if all(col in df.columns for col in ['annual_recharge_mcm', 'extraction_mcm']):
            df['water_deficit_mcm'] = df['extraction_mcm'] - df['annual_recharge_mcm']
            df['sustainability_index'] = df['annual_recharge_mcm'] / df['extraction_mcm']
        
        if 'year' in df.columns:
            df['year_normalized'] = (df['year'] - df['year'].min()) / (df['year'].max() - df['year'].min())
        
        # Create temporal features
        if 'year' in df.columns:
            df['time_trend'] = df['year'] - df['year'].min()
            df['year_squared'] = df['year'] ** 2
        
        return df
    
    def find_matching_block(self, district: str, block_search_term: str) -> str:
        """Find the exact block name matching the search term"""
        if self.dataset is None:
            return None
        
        district_data = self.dataset[self.dataset['district'] == district]
        if district_data.empty:
            return None
        
        blocks = district_data['block'].dropna().unique()
        block_search_term = str(block_search_term).lower().strip()
        
        # Search for matching block
        for block in blocks:
            block_str = str(block).lower()
            # Exact match
            if block_search_term == block_str:
                return block
            # Number match (search for "123" in "Block_123")
            if block_search_term in block_str:
                return block
            # Remove special characters and compare
            clean_block = ''.join(c for c in block_str if c.isalnum())
            clean_search = ''.join(c for c in block_search_term if c.isalnum())
            if clean_search in clean_block:
                return block
        
        return None
    
    def filter_data(self, district: str, block: str) -> pd.DataFrame:
        """Filter data for specific district and block"""
        if self.dataset is None:
            return pd.DataFrame()
        
        # Find exact block name
        exact_block = self.find_matching_block(district, block)
        if exact_block is None:
            return pd.DataFrame()
        
        filtered = self.dataset[
            (self.dataset['district'] == district) & 
            (self.dataset['block'] == exact_block)
        ].sort_values('year')
        return filtered
    
    def advanced_analysis(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Perform comprehensive advanced analysis with ML"""
        if data.empty:
            return {"error": "No data available for analysis"}
        
        analysis = {}
        
        # Basic statistics
        analysis['basic_stats'] = self.calculate_basic_statistics(data)
        
        # Trend analysis
        analysis['trend'] = self.analyze_trends(data)
        
        # Seasonal decomposition
        analysis['seasonal'] = self.seasonal_decomposition(data)
        
        # Risk assessment
        analysis['risk_assessment'] = self.ml_risk_assessment(data)
        
        # Water balance analysis
        analysis['water_balance'] = self.water_balance_analysis(data)
        
        # Predictive modeling
        analysis['predictive'] = self.predictive_modeling(data)
        
        # Cluster analysis
        analysis['clustering'] = self.cluster_analysis(data)
        
        # Anomaly detection
        analysis['anomalies'] = self.anomaly_detection(data)
        
        # Sustainability scoring
        analysis['sustainability'] = self.calculate_sustainability_score(data)
        
        # Comparative analysis
        analysis['comparative'] = self.comparative_analysis(data)
        
        return analysis
    
    def calculate_basic_statistics(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Calculate comprehensive statistics"""
        stats = {
            'total_records': len(data),
            'years_covered': sorted(data['year'].unique()) if 'year' in data.columns else [],
            'current_status': data.iloc[-1]['category'] if 'category' in data.columns else 'Unknown',
            'data_range': f"{data['year'].min()}-{data['year'].max()}" if 'year' in data.columns else 'Unknown'
        }
        
        numeric_cols = data.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            stats[f'{col}_stats'] = {
                'mean': data[col].mean(),
                'median': data[col].median(),
                'std': data[col].std(),
                'min': data[col].min(),
                'max': data[col].max(),
                'trend': self.calculate_trend_strength(data, col)
            }
        
        return stats
    
    def calculate_trend_strength(self, data: pd.DataFrame, column: str) -> float:
        """Calculate trend strength using Mann-Kendall test"""
        if 'year' not in data.columns or len(data) < 3:
            return 0
        
        try:
            from scipy.stats import kendalltau
            tau, p_value = kendalltau(data['year'], data[column])
            return abs(tau)  # Absolute value of Kendall's tau
        except:
            return 0
    
    def analyze_trends(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Advanced trend analysis with robust error handling"""
        if 'year' not in data.columns or 'stage_of_extraction_percent' not in data.columns:
            return {"error": "Insufficient data for trend analysis"}
        
        try:
            trend_data = data.groupby('year')['stage_of_extraction_percent'].mean().sort_index()
            
            if len(trend_data) < 2:
                return {
                    "error": "Insufficient data points for trend analysis",
                    "linear_trend": {"slope": 0, "intercept": 0, "r_squared": 0, "p_value": 1}
                }
            
            # Linear regression
            X = np.array(trend_data.index).reshape(-1, 1)
            y = trend_data.values
            slope, intercept, r_value, p_value, std_err = stats.linregress(X.flatten(), y)
            
            # Polynomial trend (2nd degree) with error handling
            try:
                poly_coeffs = np.polyfit(X.flatten(), y, 2)
                poly_trend = np.poly1d(poly_coeffs)
                poly_equation = f"{poly_coeffs[0]:.3f}x² + {poly_coeffs[1]:.3f}x + {poly_coeffs[2]:.3f}"
            except:
                poly_coeffs = [0, 0, 0]
                poly_equation = "Not available"
            
            # Moving average
            window_size = min(3, len(trend_data))
            moving_avg = trend_data.rolling(window=window_size).mean()
            
            return {
                'years': trend_data.index.tolist(),
                'extraction_percent': trend_data.values.tolist(),
                'linear_trend': {
                    'slope': slope,
                    'intercept': intercept,
                    'r_squared': r_value**2,
                    'p_value': p_value
                },
                'polynomial_trend': {
                    'coefficients': poly_coeffs.tolist(),
                    'equation': poly_equation
                },
                'moving_average': moving_avg.dropna().tolist(),
                'trend_direction': 'increasing' if slope > 0 else 'decreasing',
                'trend_strength': abs(r_value),
                'volatility': trend_data.std(),
                'acceleration': poly_coeffs[0] if len(poly_coeffs) > 0 else 0
            }
            
        except Exception as e:
            return {
                "error": f"Trend analysis failed: {str(e)}",
                "linear_trend": {"slope": 0, "intercept": 0, "r_squared": 0, "p_value": 1},
                "trend_direction": "unknown",
                "trend_strength": 0
            }
    
    def seasonal_decomposition(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Seasonal decomposition of time series data"""
        if 'year' not in data.columns or 'stage_of_extraction_percent' not in data.columns:
            return {"error": "Insufficient data for seasonal analysis"}
        
        try:
            # Create regular time series
            ts_data = data.set_index('year')['stage_of_extraction_percent'].sort_index()
            
            # Simple decomposition
            trend = ts_data.rolling(window=3, center=True).mean()
            seasonal = ts_data - trend
            residual = ts_data - trend - seasonal.mean()
            
            return {
                'trend_component': trend.dropna().tolist(),
                'seasonal_component': seasonal.dropna().tolist(),
                'residual_component': residual.dropna().tolist(),
                'seasonal_strength': seasonal.std() / ts_data.std() if ts_data.std() > 0 else 0
            }
        except Exception as e:
            return {"error": f"Seasonal decomposition failed: {str(e)}"}
    
    def ml_risk_assessment(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Advanced machine learning based risk assessment"""
        if data.empty:
            return {"error": "No data for risk assessment"}
        
        latest_data = data.iloc[-1]
        current_extraction = latest_data.get('stage_of_extraction_percent', 0)
        
        # Multi-factor risk assessment
        risk_factors = self.calculate_risk_factors(data)
        composite_risk_score = self.calculate_composite_risk_score(risk_factors)
        
        risk_level, risk_color = self.classify_risk_level(composite_risk_score)
        
        return {
            'current_extraction': current_extraction,
            'risk_level': risk_level,
            'risk_score': composite_risk_score,
            'risk_color': risk_color,
            'risk_factors': risk_factors,
            'recommendations': self.generate_recommendations(risk_level, risk_factors),
            'composite_score_breakdown': self.explain_composite_score(risk_factors)
        }
    
    def calculate_risk_factors(self, data: pd.DataFrame) -> Dict[str, float]:
        """Calculate multiple risk factors"""
        factors = {}
        
        # Extraction level risk
        current_extraction = data.iloc[-1].get('stage_of_extraction_percent', 0)
        factors['extraction_risk'] = min(current_extraction / 100, 1.0)
        
        # Trend risk
        trend_data = self.analyze_trends(data)
        if 'linear_trend' in trend_data:
            trend_slope = trend_data['linear_trend']['slope']
            factors['trend_risk'] = abs(trend_slope) / 10  # Normalize
        
        # Volatility risk
        if 'stage_of_extraction_percent' in data.columns:
            factors['volatility_risk'] = data['stage_of_extraction_percent'].std() / 50
        
        # Water balance risk
        water_balance = self.water_balance_analysis(data)
        if water_balance.get('sustainability_ratio', 0) > 1:
            factors['balance_risk'] = min(water_balance['sustainability_ratio'] - 1, 1.0)
        else:
            factors['balance_risk'] = 0
        
        # Historical risk (deterioration)
        if len(data) > 1:
            first_extraction = data.iloc[0].get('stage_of_extraction_percent', 0)
            deterioration = max(0, current_extraction - first_extraction) / 100
            factors['historical_risk'] = deterioration
        
        return factors
    
    def calculate_composite_risk_score(self, risk_factors: Dict[str, float]) -> float:
        """Calculate weighted composite risk score"""
        weights = {
            'extraction_risk': 0.4,
            'trend_risk': 0.2,
            'volatility_risk': 0.1,
            'balance_risk': 0.2,
            'historical_risk': 0.1
        }
        
        composite_score = 0
        for factor, weight in weights.items():
            composite_score += risk_factors.get(factor, 0) * weight
        
        return min(composite_score, 1.0)
    
    def classify_risk_level(self, risk_score: float) -> Tuple[str, str]:
        """Classify risk level based on score"""
        if risk_score >= 0.8:
            return "CRITICAL", "#dc2626"
        elif risk_score >= 0.6:
            return "HIGH", "#ea580c"
        elif risk_score >= 0.4:
            return "MEDIUM", "#d97706"
        elif risk_score >= 0.2:
            return "LOW", "#65a30d"
        else:
            return "SAFE", "#16a34a"
    
    def explain_composite_score(self, risk_factors: Dict[str, float]) -> Dict[str, Any]:
        """Explain how composite risk score was calculated"""
        return {
            'factors': risk_factors,
            'weights': {
                'extraction_risk': 'Current extraction level (40%)',
                'trend_risk': 'Trend direction and strength (20%)',
                'balance_risk': 'Water balance sustainability (20%)',
                'volatility_risk': 'Data volatility (10%)',
                'historical_risk': 'Historical deterioration (10%)'
            },
            'calculation': 'Weighted sum of all risk factors'
        }
    
    def generate_recommendations(self, risk_level: str, risk_factors: Dict[str, float]) -> List[Dict[str, Any]]:
        """Generate targeted recommendations based on risk factors"""
        recommendations = []
        
        # Base recommendations by risk level
        if risk_level == "CRITICAL":
            base_recs = [
                {"priority": 1, "action": "🚨 Emergency Response", "details": "Implement immediate water usage restrictions and emergency measures"},
                {"priority": 2, "action": "🆘 Crisis Management", "details": "Activate groundwater crisis management protocol"},
                {"priority": 3, "action": "💧 Alternative Sources", "details": "Deploy emergency water supply systems"}
            ]
        elif risk_level == "HIGH":
            base_recs = [
                {"priority": 1, "action": "📊 Enhanced Monitoring", "details": "Increase monitoring frequency to weekly assessments"},
                {"priority": 2, "action": "⚡ Efficiency Measures", "details": "Implement strict water efficiency standards"},
                {"priority": 3, "action": "🌧️ Rainwater Harvesting", "details": "Accelerate community rainwater harvesting projects"}
            ]
        elif risk_level == "MEDIUM":
            base_recs = [
                {"priority": 1, "action": "📈 Regular Assessment", "details": "Conduct monthly groundwater level reviews"},
                {"priority": 2, "action": "🎓 Conservation Education", "details": "Launch water conservation awareness programs"},
                {"priority": 3, "action": "📝 Sustainable Planning", "details": "Develop comprehensive water management plan"}
            ]
        else:
            base_recs = [
                {"priority": 1, "action": "👀 Preventive Monitoring", "details": "Maintain regular groundwater assessment schedule"},
                {"priority": 2, "action": "🛡️ Risk Prevention", "details": "Implement preventive conservation measures"},
                {"priority": 3, "action": "🌱 Future Resilience", "details": "Plan for long-term climate resilience"}
            ]
        
        recommendations.extend(base_recs)
        
        # Factor-specific recommendations
        if risk_factors.get('trend_risk', 0) > 0.3:
            recommendations.append({
                "priority": 2,
                "action": "📉 Trend Reversal",
                "details": "Implement measures to reverse increasing extraction trend"
            })
        
        if risk_factors.get('balance_risk', 0) > 0.3:
            recommendations.append({
                "priority": 2,
                "action": "⚖️ Balance Restoration",
                "details": "Focus on increasing recharge and reducing extraction"
            })
        
        return sorted(recommendations, key=lambda x: x['priority'])
    
    def water_balance_analysis(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Comprehensive water balance analysis"""
        if not all(col in data.columns for col in ['annual_recharge_mcm', 'extraction_mcm']):
            return {"error": "Insufficient data for water balance analysis"}
        
        latest_data = data.iloc[-1]
        recharge = latest_data.get('annual_recharge_mcm', 0)
        extraction = latest_data.get('extraction_mcm', 0)
        
        balance = recharge - extraction
        sustainability_ratio = extraction / recharge if recharge > 0 else float('inf')
        
        # Historical balance trend
        historical_balance = data['annual_recharge_mcm'] - data['extraction_mcm']
        balance_trend = self.calculate_trend_strength(
            pd.DataFrame({'year': data['year'], 'balance': historical_balance}), 
            'balance'
        )
        
        return {
            'recharge_mcm': recharge,
            'extraction_mcm': extraction,
            'balance_mcm': balance,
            'sustainability_ratio': sustainability_ratio,
            'status': 'Sustainable' if sustainability_ratio <= 1 else 'Unsustainable',
            'deficit_percentage': ((extraction - recharge) / recharge * 100) if recharge > 0 else float('inf'),
            'historical_balance_trend': balance_trend,
            'average_annual_deficit': historical_balance[historical_balance < 0].mean() if any(historical_balance < 0) else 0
        }
    
    def predictive_modeling(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Predictive modeling for future groundwater trends"""
        if 'year' not in data.columns or 'stage_of_extraction_percent' not in data.columns:
            return {"error": "Insufficient data for predictive modeling"}
        
        try:
            # Prepare data
            X = data[['year']].values
            y = data['stage_of_extraction_percent'].values
            
            # Linear regression prediction
            lr_model = LinearRegression()
            lr_model.fit(X, y)
            future_years = np.array(range(data['year'].max() + 1, data['year'].max() + 6)).reshape(-1, 1)
            lr_predictions = lr_model.predict(future_years)
            
            # Polynomial regression
            poly_features = np.column_stack([X.flatten(), X.flatten()**2])
            poly_model = LinearRegression()
            poly_model.fit(poly_features, y)
            poly_predictions = poly_model.predict(
                np.column_stack([future_years.flatten(), future_years.flatten()**2])
            )
            
            return {
                'future_years': future_years.flatten().tolist(),
                'linear_predictions': lr_predictions.tolist(),
                'polynomial_predictions': poly_predictions.tolist(),
                'critical_year_linear': self.find_critical_year(future_years.flatten(), lr_predictions, 100),
                'critical_year_poly': self.find_critical_year(future_years.flatten(), poly_predictions, 100),
                'model_accuracy': {
                    'linear_r2': r2_score(y, lr_model.predict(X)),
                    'poly_r2': r2_score(y, poly_model.predict(poly_features))
                }
            }
        except Exception as e:
            return {"error": f"Predictive modeling failed: {str(e)}"}
    
    def find_critical_year(self, years: np.array, predictions: np.array, threshold: float) -> int:
        """Find year when predictions cross critical threshold"""
        for year, pred in zip(years, predictions):
            if pred >= threshold:
                return int(year)
        return None
    
    def cluster_analysis(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Cluster analysis to identify patterns"""
        try:
            # Select features for clustering
            features = data.select_dtypes(include=[np.number]).columns
            if len(features) < 2 or len(data) < 3:
                return {"error": "Insufficient data for clustering"}
            
            X = data[features].fillna(0).values
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)
            
            # K-means clustering
            kmeans = KMeans(n_clusters=min(3, len(data)), random_state=42)
            clusters = kmeans.fit_predict(X_scaled)
            
            return {
                'clusters': clusters.tolist(),
                'cluster_centers': kmeans.cluster_centers_.tolist(),
                'inertia': kmeans.inertia_,
                'silhouette_score': self.calculate_silhouette_score(X_scaled, clusters)
            }
        except Exception as e:
            return {"error": f"Cluster analysis failed: {str(e)}"}
    
    def calculate_silhouette_score(self, X: np.array, clusters: np.array) -> float:
        """Calculate silhouette score for clustering quality"""
        try:
            from sklearn.metrics import silhouette_score
            return silhouette_score(X, clusters)
        except:
            return -1
    
    def anomaly_detection(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Detect anomalies in groundwater data"""
        try:
            if 'stage_of_extraction_percent' not in data.columns:
                return {"error": "No extraction data for anomaly detection"}
            
            # Isolation Forest for anomaly detection
            X = data[['stage_of_extraction_percent']].values
            iso_forest = IsolationForest(contamination=0.1, random_state=42)
            anomalies = iso_forest.fit_predict(X)
            
            anomaly_indices = np.where(anomalies == -1)[0]
            anomaly_years = data.iloc[anomaly_indices]['year'].tolist() if 'year' in data.columns else []
            
            return {
                'anomaly_indices': anomaly_indices.tolist(),
                'anomaly_years': anomaly_years,
                'anomaly_values': data.iloc[anomaly_indices]['stage_of_extraction_percent'].tolist(),
                'total_anomalies': len(anomaly_indices)
            }
        except Exception as e:
            return {"error": f"Anomaly detection failed: {str(e)}"}
    
    def calculate_sustainability_score(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Calculate comprehensive sustainability score with proper error handling"""
        scores = {}
        
        try:
            # Extraction sustainability (0-100, higher is better)
            current_extraction = data.iloc[-1].get('stage_of_extraction_percent', 0)
            scores['extraction_score'] = max(0, 100 - current_extraction)
            
            # Balance sustainability
            water_balance = self.water_balance_analysis(data)
            if 'error' not in water_balance:
                if water_balance.get('sustainability_ratio', 0) <= 1:
                    scores['balance_score'] = 100
                else:
                    scores['balance_score'] = max(0, 100 / water_balance['sustainability_ratio'])
            else:
                scores['balance_score'] = 50  # Default score if balance analysis fails
            
            # Trend sustainability with error handling
            trend_data = self.analyze_trends(data)
            if 'error' not in trend_data and 'linear_trend' in trend_data:
                slope = trend_data['linear_trend'].get('slope', 0)
                if slope < 0:
                    scores['trend_score'] = 100  # Improving trend
                else:
                    scores['trend_score'] = max(0, 100 - abs(slope * 10))
            else:
                scores['trend_score'] = 50  # Default score if trend analysis fails
            
            # Composite sustainability score
            weights = {'extraction_score': 0.5, 'balance_score': 0.3, 'trend_score': 0.2}
            composite_score = sum(scores[metric] * weight for metric, weight in weights.items())
            
            return {
                'component_scores': scores,
                'composite_sustainability_score': composite_score,
                'sustainability_level': self.classify_sustainability(composite_score),
                'weights': weights
            }
            
        except Exception as e:
            # Fallback sustainability calculation
            current_extraction = data.iloc[-1].get('stage_of_extraction_percent', 0)
            fallback_score = max(0, 100 - current_extraction)
            
            return {
                'component_scores': {'extraction_score': fallback_score, 'balance_score': 50, 'trend_score': 50},
                'composite_sustainability_score': fallback_score,
                'sustainability_level': self.classify_sustainability(fallback_score),
                'weights': {'extraction_score': 1.0, 'balance_score': 0.0, 'trend_score': 0.0},
                'error': f"Simplified calculation used: {str(e)}"
            }
    
    def classify_sustainability(self, score: float) -> str:
        """Classify sustainability level"""
        if score >= 80:
            return "Highly Sustainable"
        elif score >= 60:
            return "Sustainable"
        elif score >= 40:
            return "Moderately Sustainable"
        elif score >= 20:
            return "Unsustainable"
        else:
            return "Critically Unsustainable"
    
    def comparative_analysis(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Comparative analysis with regional averages"""
        if self.dataset is None or self.selected_district is None:
            return {"error": "No regional data for comparative analysis"}
        
        try:
            # District average
            district_avg = self.dataset[
                self.dataset['district'] == self.selected_district
            ].groupby('year')['stage_of_extraction_percent'].mean()
            
            # State average
            state_avg = self.dataset.groupby('year')['stage_of_extraction_percent'].mean()
            
            # Block's performance relative to averages
            block_data = data.set_index('year')['stage_of_extraction_percent']
            
            comparative_metrics = {}
            if not block_data.empty and not district_avg.empty:
                latest_year = block_data.index.max()
                if latest_year in district_avg.index:
                    comparative_metrics['vs_district'] = {
                        'block_value': block_data[latest_year],
                        'district_avg': district_avg[latest_year],
                        'difference': block_data[latest_year] - district_avg[latest_year],
                        'performance': 'Better' if block_data[latest_year] < district_avg[latest_year] else 'Worse'
                    }
            
            if not block_data.empty and not state_avg.empty:
                latest_year = block_data.index.max()
                if latest_year in state_avg.index:
                    comparative_metrics['vs_state'] = {
                        'block_value': block_data[latest_year],
                        'state_avg': state_avg[latest_year],
                        'difference': block_data[latest_year] - state_avg[latest_year],
                        'performance': 'Better' if block_data[latest_year] < state_avg[latest_year] else 'Worse'
                    }
            
            return comparative_metrics
        except Exception as e:
            return {"error": f"Comparative analysis failed: {str(e)}"}

# Rest of the code remains the same with enhanced visualization functions...

@function_tool()
async def analyze_groundwater_dataset(
    state_name: str,
    district_name: str,
    block_name: str,
    port: int = 8079
) -> Dict[str, Any]:
    """
    Advanced groundwater data analysis engine for INGRES datasets.
    
    Args:
        state_name: Name of the state (e.g., "gujarat")
        district_name: Name of the district (e.g., "Ahmedabad")
        block_name: Block name or number (e.g., "123" or "Block_123")
        port: Web server port (default: 8080)
    
    Returns:
        Dictionary with analysis results and report URL
    """
    
    # Initialize analysis engine
    engine = AdvancedGroundwaterAnalysisEngine()
    current_folder = Path.cwd()
    
    # Step 1: Detect available state datasets
    state_datasets = engine.detect_state_datasets(current_folder)
    
    if not state_datasets:
        return {"error": "No state groundwater datasets found in current folder"}
    
    # Step 2: Validate state name
    state_name_lower = state_name.lower()
    matching_state = None
    
    for state in state_datasets.keys():
        if state_name_lower in state.lower() or state.lower() in state_name_lower:
            matching_state = state
            break
    
    if not matching_state:
        available_states = list(state_datasets.keys())
        return {"error": f"State '{state_name}' not found. Available states: {available_states}"}
    
    # Step 3: Load the selected state dataset
    dataset_file = state_datasets[matching_state][0]
    try:
        engine.dataset = engine.load_groundwater_data(dataset_file)
        engine.selected_state = matching_state
    except Exception as e:
        return {"error": f"Error loading {matching_state} dataset: {str(e)}"}
    
    # Step 4: Validate district name
    districts = engine.dataset['district'].dropna().unique()
    matching_district = None
    
    for district in districts:
        if district_name.lower() in str(district).lower() or str(district).lower() in district_name.lower():
            matching_district = district
            break
    
    if not matching_district:
        available_districts = [str(d) for d in districts]
        return {"error": f"District '{district_name}' not found. Available districts: {available_districts}"}
    
    engine.selected_district = matching_district
    
    # Step 5: Find and validate block
    matching_block = engine.find_matching_block(matching_district, block_name)
    if not matching_block:
        blocks = engine.dataset[engine.dataset['district'] == matching_district]['block'].dropna().unique()
        available_blocks = [str(b) for b in blocks]
        return {"error": f"Block '{block_name}' not found in {matching_district}. Available blocks: {available_blocks}"}
    
    engine.selected_block = matching_block
    
    # Step 6: Filter data and perform analysis
    filtered_data = engine.filter_data(matching_district, matching_block)
    
    if filtered_data.empty:
        return {"error": f"No data found for {matching_block} in {matching_district}"}
    
    # Perform advanced analysis
    analysis_results = engine.advanced_analysis(filtered_data)
    engine.analysis_results = analysis_results
    
    if "error" in analysis_results:
        return analysis_results
    
    # Step 7: Generate visualizations
    temp_dir = tempfile.mkdtemp()
    static_dir = Path(temp_dir)
    images_dir = static_dir / "images"
    images_dir.mkdir(exist_ok=True)
    
    def save_plotly_figure(fig, filename, width=1000, height=600):
        try:
            fig.update_layout(template=plotly_dark_template)
            img_path = images_dir / f"{filename}.png"
            pio.write_image(fig, str(img_path), width=width, height=height, scale=2)
            
            with open(img_path, "rb") as img_file:
                img_data = base64.b64encode(img_file.read()).decode('utf-8')
            
            return f"data:image/png;base64,{img_data}"
        except Exception as e:
            print(f"Error saving visualization {filename}: {str(e)}")
            return None
    
    visualizations = {}
    
    # 1. Extraction Trend Chart
    if 'year' in filtered_data.columns and 'stage_of_extraction_percent' in filtered_data.columns:
        fig_trend = go.Figure()
        
        fig_trend.add_trace(go.Scatter(
            x=filtered_data['year'], y=filtered_data['stage_of_extraction_percent'],
            mode='lines+markers', name='Extraction %',
            line=dict(color='#4ecdc4', width=4),
            marker=dict(size=8, color='#4ecdc4')
        ))
        
        # Add critical thresholds
        fig_trend.add_hline(y=70, line=dict(color="green", dash="dash", width=2), 
                           annotation_text="Safe Limit")
        fig_trend.add_hline(y=90, line=dict(color="orange", dash="dash", width=2), 
                           annotation_text="Semi-Critical")
        fig_trend.add_hline(y=100, line=dict(color="red", dash="dash", width=2), 
                           annotation_text="Critical")
        
        fig_trend.update_layout(
            title=dict(text=f'Groundwater Extraction Trend - {matching_block}', x=0.5),
            xaxis_title="Year",
            yaxis_title="Extraction Percentage (%)",
            showlegend=True
        )
        visualizations["extraction_trend"] = save_plotly_figure(fig_trend, "extraction_trend")
    
    # 2. Risk Assessment Gauge
    if 'risk_assessment' in analysis_results:
        risk_data = analysis_results['risk_assessment']
        
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=risk_data['current_extraction'],
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': f"Risk Level: {risk_data['risk_level']}"},
            gauge={
                'axis': {'range': [None, 150]},
                'bar': {'color': "darkblue"},
                'steps': [
                    {'range': [0, 70], 'color': "green"},
                    {'range': [70, 90], 'color': "orange"},
                    {'range': [90, 100], 'color': "red"},
                    {'range': [100, 150], 'color': "darkred"}
                ],
                'threshold': {
                    'line': {'color': "white", 'width': 4},
                    'value': risk_data['current_extraction']
                }
            }
        ))
        
        fig_gauge.update_layout(
            title=dict(text=f'Groundwater Risk Assessment - {matching_block}', x=0.5)
        )
        visualizations["risk_gauge"] = save_plotly_figure(fig_gauge, "risk_gauge")
    
    # 3. Water Balance Chart
    if 'water_balance' in analysis_results:
        balance_data = analysis_results['water_balance']
        
        fig_balance = go.Figure()
        
        fig_balance.add_trace(go.Bar(
            name='Annual Recharge',
            x=['Water Balance'],
            y=[balance_data['recharge_mcm']],
            marker_color='#10b981'
        ))
        
        fig_balance.add_trace(go.Bar(
            name='Extraction',
            x=['Water Balance'],
            y=[balance_data['extraction_mcm']],
            marker_color='#ef4444'
        ))
        
        fig_balance.update_layout(
            title=dict(text=f'Water Balance Analysis - {matching_block}', x=0.5),
            yaxis_title="Million Cubic Meters (MCM)"
        )
        visualizations["water_balance"] = save_plotly_figure(fig_balance, "water_balance")
    
    # Step 8: Create HTML report
    risk_data = analysis_results.get('risk_assessment', {})
    basic_stats = analysis_results.get('basic_stats', {})
    
    html_content = create_html_report(engine, analysis_results, visualizations)
    
    # Save HTML file
    html_file = static_dir / "index.html"
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    # Save analysis results
    artifacts = {
        "analysis": analysis_results,
        "filtered_data": filtered_data.to_dict('records'),
        "metadata": {
            "state": engine.selected_state,
            "district": engine.selected_district,
            "block": engine.selected_block,
            "timestamp": pd.Timestamp.now().isoformat()
        }
    }
    
    artifacts_file = static_dir / "artifacts.json"
    with open(artifacts_file, 'w') as f:
        json.dump(artifacts, f, indent=2, default=str)
    
    # Step 9: Start web server
    class GroundwaterAnalysisHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(static_dir), **kwargs)
        
        def log_message(self, format, *args):
            pass  # Suppress server logs
    
    def run_server():
        try:
            
            with socketserver.TCPServer(("", port + 1), GroundwaterAnalysisHandler) as httpd:
                print(f"🌊 Groundwater analysis server running at http://localhost:{port}")
                httpd.serve_forever()
        except OSError:
            # Port busy, try next port
            with socketserver.TCPServer(("", port + 1), GroundwaterAnalysisHandler) as httpd:
                print(f"🌊 Groundwater analysis server running at http://localhost:{port + 1}")
                httpd.serve_forever()
    
    # Start server in a thread
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # Wait for server to start and open browser
    await asyncio.sleep(2)
    webbrowser.open(f"http://localhost:{port}")
    
    # Return results
    return {
        "report_url": f"http://localhost:{port}",
        "analysis_summary": {
            "location": f"{engine.selected_block}, {engine.selected_district}, {engine.selected_state}",
            "current_status": basic_stats.get('current_status', 'Unknown'),
            "risk_level": risk_data.get('risk_level', 'Unknown'),
            "extraction_percentage": risk_data.get('current_extraction', 0),
            "trend_direction": analysis_results.get('trend', {}).get('trend_direction', 'Unknown'),
        },
        "message": f"✅ Analysis completed for {matching_block}, {matching_district}. Report: http://localhost:{port}"
    }

def create_html_report(engine, analysis_results, visualizations):
    """Create advanced HTML report with attractive CSS"""
    
    risk_data = analysis_results.get('risk_assessment', {})
    basic_stats = analysis_results.get('basic_stats', {})
    trend_data = analysis_results.get('trend', {})
    water_balance = analysis_results.get('water_balance', {})
    predictive = analysis_results.get('predictive', {})
    sustainability = analysis_results.get('sustainability', {})
    comparative = analysis_results.get('comparative', {})
    anomalies = analysis_results.get('anomalies', {})
    
    risk_level = risk_data.get('risk_level', 'UNKNOWN')
    risk_color = risk_data.get('risk_color', '#ef4444')
    
    # Sustainability level and color
    sustainability_level = sustainability.get('sustainability_level', 'Unknown')
    sustainability_color = get_sustainability_color(sustainability_level)
    
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Advanced Groundwater Analysis - {engine.selected_block}</title>
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <style>
            :root {{
                --primary: #3b82f6;
                --secondary: #10b981;
                --danger: #ef4444;
                --warning: #f59e0b;
                --dark: #0f172a;
                --darker: #020617;
                --light: #f8fafc;
                --card-bg: rgba(30, 41, 59, 0.8);
                --gradient-primary: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                --gradient-danger: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                --gradient-success: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
                --gradient-warning: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
            }}
            
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: 'Inter', sans-serif;
                background: var(--darker);
                color: var(--light);
                line-height: 1.6;
                background-image: 
                    radial-gradient(at 80% 20%, rgba(56, 189, 248, 0.1) 0px, transparent 50%),
                    radial-gradient(at 20% 80%, rgba(232, 121, 249, 0.1) 0px, transparent 50%);
                min-height: 100vh;
            }}
            
            .container {{
                max-width: 1400px;
                margin: 0 auto;
                padding: 20px;
            }}
            
            /* Header Styles */
            .header {{
                text-align: center;
                padding: 40px 30px;
                background: var(--gradient-primary);
                border-radius: 20px;
                margin-bottom: 30px;
                position: relative;
                overflow: hidden;
                box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
            }}
            
            .header::before {{
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><pattern id="water" x="0" y="0" width="20" height="20" patternUnits="userSpaceOnUse"><path d="M10,0 L20,10 L10,20 L0,10 Z" fill="rgba(255,255,255,0.1)"/></pattern></defs><rect width="100" height="100" fill="url(#water)"/></svg>');
                opacity: 0.1;
            }}
            
            .header h1 {{
                font-size: 3em;
                font-weight: 700;
                margin-bottom: 10px;
                text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.3);
            }}
            
            .header h2 {{
                font-size: 1.5em;
                font-weight: 400;
                opacity: 0.9;
                margin-bottom: 20px;
            }}
            
            .risk-badge {{
                display: inline-block;
                background: {risk_color};
                padding: 12px 30px;
                border-radius: 50px;
                font-weight: 600;
                font-size: 1.2em;
                box-shadow: 0 10px 20px rgba(0, 0, 0, 0.2);
                backdrop-filter: blur(10px);
                border: 2px solid rgba(255, 255, 255, 0.2);
            }}
            
            /* Stats Grid */
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                gap: 25px;
                margin: 30px 0;
            }}
            
            .stat-card {{
                background: var(--card-bg);
                padding: 25px;
                border-radius: 15px;
                text-align: center;
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255, 255, 255, 0.1);
                transition: transform 0.3s ease, box-shadow 0.3s ease;
                position: relative;
                overflow: hidden;
            }}
            
            .stat-card:hover {{
                transform: translateY(-5px);
                box-shadow: 0 15px 30px rgba(0, 0, 0, 0.4);
            }}
            
            .stat-card::before {{
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 4px;
                background: var(--gradient-primary);
            }}
            
            .stat-card i {{
                font-size: 2.5em;
                margin-bottom: 15px;
                opacity: 0.8;
            }}
            
            .stat-card h3 {{
                font-size: 1.1em;
                font-weight: 500;
                margin-bottom: 10px;
                opacity: 0.8;
            }}
            
            .stat-card .value {{
                font-size: 2.2em;
                font-weight: 700;
                margin: 10px 0;
            }}
            
            .stat-card .trend {{
                font-size: 0.9em;
                padding: 4px 12px;
                border-radius: 20px;
                background: rgba(255, 255, 255, 0.1);
                display: inline-block;
            }}
            
            /* Chart Containers */
            .chart-section {{
                margin: 40px 0;
            }}
            
            .section-header {{
                display: flex;
                align-items: center;
                margin-bottom: 20px;
                padding-bottom: 15px;
                border-bottom: 2px solid rgba(255, 255, 255, 0.1);
            }}
            
            .section-header i {{
                font-size: 1.8em;
                margin-right: 15px;
                opacity: 0.8;
            }}
            
            .section-header h2 {{
                font-size: 1.8em;
                font-weight: 600;
            }}
            
            .chart-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(600px, 1fr));
                gap: 25px;
            }}
            
            .chart-container {{
                background: var(--card-bg);
                padding: 25px;
                border-radius: 15px;
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255, 255, 255, 0.1);
            }}
            
            .chart-container h3 {{
                font-size: 1.3em;
                margin-bottom: 20px;
                font-weight: 600;
            }}
            
            .chart-container img {{
                width: 100%;
                border-radius: 10px;
                box-shadow: 0 10px 20px rgba(0, 0, 0, 0.2);
            }}
            
            /* Recommendations */
            .recommendations-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
                gap: 20px;
                margin: 20px 0;
            }}
            
            .recommendation-card {{
                background: var(--card-bg);
                padding: 20px;
                border-radius: 15px;
                border-left: 4px solid var(--primary);
                transition: transform 0.3s ease;
            }}
            
            .recommendation-card:hover {{
                transform: translateX(5px);
            }}
            
            .recommendation-card.priority-1 {{
                border-left-color: var(--danger);
            }}
            
            .recommendation-card.priority-2 {{
                border-left-color: var(--warning);
            }}
            
            .recommendation-card.priority-3 {{
                border-left-color: var(--secondary);
            }}
            
            .recommendation-card .priority {{
                display: inline-block;
                padding: 4px 12px;
                border-radius: 15px;
                font-size: 0.8em;
                font-weight: 600;
                margin-bottom: 10px;
            }}
            
            .priority-1 .priority {{ background: var(--danger); }}
            .priority-2 .priority {{ background: var(--warning); }}
            .priority-3 .priority {{ background: var(--secondary); }}
            
            /* Risk Factors */
            .risk-factors {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 15px;
                margin: 20px 0;
            }}
            
            .risk-factor {{
                background: rgba(255, 255, 255, 0.05);
                padding: 15px;
                border-radius: 10px;
                text-align: center;
            }}
            
            .risk-factor .value {{
                font-size: 1.5em;
                font-weight: 700;
                margin: 5px 0;
            }}
            
            /* Sustainability Meter */
            .sustainability-meter {{
                background: var(--gradient-success);
                padding: 30px;
                border-radius: 15px;
                text-align: center;
                margin: 20px 0;
            }}
            
            .sustainability-score {{
                font-size: 4em;
                font-weight: 700;
                margin: 10px 0;
            }}
            
            .sustainability-level {{
                font-size: 1.5em;
                font-weight: 600;
                opacity: 0.9;
            }}
            
            /* Anomalies */
            .anomalies-container {{
                background: rgba(239, 68, 68, 0.1);
                padding: 20px;
                border-radius: 15px;
                border-left: 4px solid var(--danger);
                margin: 20px 0;
            }}
            
            /* Footer */
            .footer {{
                text-align: center;
                padding: 30px;
                margin-top: 50px;
                border-top: 1px solid rgba(255, 255, 255, 0.1);
                opacity: 0.7;
                font-size: 0.9em;
            }}
            
            /* Responsive */
            @media (max-width: 768px) {{
                .chart-grid {{
                    grid-template-columns: 1fr;
                }}
                
                .stats-grid {{
                    grid-template-columns: 1fr;
                }}
                
                .header h1 {{
                    font-size: 2em;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <!-- Header -->
            <div class="header">
                <h1><i class="fas fa-water"></i> Advanced Groundwater Analysis</h1>
                <h2>{engine.selected_block}, {engine.selected_district}, {engine.selected_state}</h2>
                <div class="risk-badge">
                    <i class="fas fa-exclamation-triangle"></i> Risk Level: {risk_level}
                </div>
            </div>
            
            <!-- Key Statistics -->
            <div class="stats-grid">
                <div class="stat-card">
                    <i class="fas fa-chart-line" style="color: #3b82f6;"></i>
                    <h3>Current Extraction</h3>
                    <div class="value" style="color: {risk_color};">
                        {risk_data.get('current_extraction', 0):.1f}%
                    </div>
                    <div class="trend">
                        {trend_data.get('trend_direction', 'Unknown').title()} Trend
                    </div>
                </div>
                
                <div class="stat-card">
                    <i class="fas fa-balance-scale" style="color: #10b981;"></i>
                    <h3>Water Balance</h3>
                    <div class="value" style="color: #10b981;">
                        {water_balance.get('status', 'Unknown')}
                    </div>
                    <div class="trend">
                        {water_balance.get('balance_mcm', 0):.1f} MCM
                    </div>
                </div>
                
                <div class="stat-card">
                    <i class="fas fa-leaf" style="color: #22c55e;"></i>
                    <h3>Sustainability</h3>
                    <div class="value" style="color: {sustainability_color};">
                        {sustainability.get('composite_sustainability_score', 0):.0f}/100
                    </div>
                    <div class="trend">
                        {sustainability_level}
                    </div>
                </div>
                
                <div class="stat-card">
                    <i class="fas fa-calendar-alt" style="color: #8b5cf6;"></i>
                    <h3>Data Coverage</h3>
                    <div class="value" style="color: #8b5cf6;">
                        {basic_stats.get('data_range', 'Unknown')}
                    </div>
                    <div class="trend">
                        {basic_stats.get('total_records', 0)} Records
                    </div>
                </div>
            </div>
            
            <!-- Risk Factors -->
            <div class="chart-section">
                <div class="section-header">
                    <i class="fas fa-exclamation-circle" style="color: #ef4444;"></i>
                    <h2>Risk Assessment</h2>
                </div>
                
                <div class="chart-grid">
                    <div class="chart-container">
                        <h3><i class="fas fa-gauge-high"></i> Risk Level Analysis</h3>
                        <img src="{visualizations.get('risk_gauge', '')}" alt="Risk Gauge">
                        
                        <div class="risk-factors">
                            {generate_risk_factors_html(risk_data)}
                        </div>
                    </div>
                    
                    <div class="chart-container">
                        <h3><i class="fas fa-chart-bar"></i> Water Balance Analysis</h3>
                        <img src="{visualizations.get('water_balance', '')}" alt="Water Balance">
                        
                        <div style="margin-top: 20px;">
                            <div class="sustainability-meter">
                                <div class="sustainability-score">
                                    {sustainability.get('composite_sustainability_score', 0):.0f}
                                </div>
                                <div class="sustainability-level">
                                    {sustainability_level}
                                </div>
                                <p>Overall Sustainability Score</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Trend Analysis -->
            <div class="chart-section">
                <div class="section-header">
                    <i class="fas fa-chart-line" style="color: #3b82f6;"></i>
                    <h2>Trend Analysis</h2>
                </div>
                
                <div class="chart-grid">
                    <div class="chart-container">
                        <h3><i class="fas fa-trend-up"></i> Extraction Trend</h3>
                        <img src="{visualizations.get('extraction_trend', '')}" alt="Extraction Trend">
                    </div>
                    
                    <div class="chart-container">
                        <h3><i class="fas fa-crystal-ball"></i> Future Projections</h3>
                        <img src="{visualizations.get('predictive_analysis', '')}" alt="Predictive Analysis">
                        
                        {generate_predictive_insights_html(predictive)}
                    </div>
                </div>
            </div>
            
            <!-- Anomaly Detection -->
            {generate_anomalies_section(anomalies, visualizations)}
            
            <!-- Comparative Analysis -->
            {generate_comparative_section(comparative, engine)}
            
            <!-- Recommendations -->
            <div class="chart-section">
                <div class="section-header">
                    <i class="fas fa-lightbulb" style="color: #f59e0b;"></i>
                    <h2>Recommendations & Action Plan</h2>
                </div>
                
                <div class="recommendations-grid">
                    {generate_recommendations_html(risk_data.get('recommendations', []))}
                </div>
            </div>
            
            <!-- Footer -->
            <div class="footer">
                <p>Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p>Advanced Groundwater Analysis Engine v2.0 • Powered by Nova</p>
            </div>
        </div>
        
        <script>
            // Add simple animations
            document.addEventListener('DOMContentLoaded', function() {{
                const cards = document.querySelectorAll('.stat-card, .chart-container');
                cards.forEach((card, index) => {{
                    card.style.opacity = '0';
                    card.style.transform = 'translateY(20px)';
                    setTimeout(() => {{
                        card.style.transition = 'all 0.6s ease';
                        card.style.opacity = '1';
                        card.style.transform = 'translateY(0)';
                    }}, index * 100);
                }});
            }});
        </script>
    </body>
    </html>
    """

def generate_risk_factors_html(risk_data):
    """Generate HTML for risk factors breakdown"""
    factors = risk_data.get('risk_factors', {})
    html_parts = []
    
    for factor, value in factors.items():
        percentage = value * 100
        color = '#ef4444' if percentage > 50 else '#f59e0b' if percentage > 25 else '#10b981'
        
        html_parts.append(f"""
        <div class="risk-factor">
            <div style="font-size: 0.9em; opacity: 0.8;">{factor.replace('_', ' ').title()}</div>
            <div class="value" style="color: {color};">{percentage:.1f}%</div>
        </div>
        """)
    
    return ''.join(html_parts)

def generate_predictive_insights_html(predictive):
    """Generate HTML for predictive insights"""
    if 'error' in predictive:
        return '<p style="color: #ef4444; text-align: center;">Predictive analysis not available</p>'
    
    critical_year = predictive.get('critical_year_linear') or predictive.get('critical_year_poly')
    
    if critical_year:
        return f"""
        <div style="background: rgba(239, 68, 68, 0.1); padding: 15px; border-radius: 10px; margin-top: 15px; border-left: 4px solid #ef4444;">
            <h4 style="margin: 0 0 10px 0; color: #ef4444;">
                <i class="fas fa-exclamation-triangle"></i> Critical Projection
            </h4>
            <p style="margin: 0;">Based on current trends, critical extraction levels (100%) may be reached by <strong>{critical_year}</strong></p>
        </div>
        """
    else:
        return """
        <div style="background: rgba(16, 185, 129, 0.1); padding: 15px; border-radius: 10px; margin-top: 15px; border-left: 4px solid #10b981;">
            <h4 style="margin: 0 0 10px 0; color: #10b981;">
                <i class="fas fa-check-circle"></i> Stable Projection
            </h4>
            <p style="margin: 0;">Current trends suggest sustainable extraction levels in the foreseeable future</p>
        </div>
        """

def generate_anomalies_section(anomalies, visualizations):
    """Generate anomalies section HTML"""
    if 'error' in anomalies or anomalies.get('total_anomalies', 0) == 0:
        return ''
    
    return f"""
    <div class="chart-section">
        <div class="section-header">
            <i class="fas fa-radar" style="color: #f59e0b;"></i>
            <h2>Anomaly Detection</h2>
        </div>
        
        <div class="chart-grid">
            <div class="chart-container">
                <h3><i class="fas fa-exclamation-triangle"></i> Detected Anomalies</h3>
                <img src="{visualizations.get('anomaly_detection', '')}" alt="Anomaly Detection">
            </div>
            
            <div class="anomalies-container">
                <h4><i class="fas fa-bell"></i> Anomaly Alert</h4>
                <p>System detected {anomalies.get('total_anomalies', 0)} unusual data points in the historical record.</p>
                <p>Anomaly years: {', '.join(map(str, anomalies.get('anomaly_years', [])))}</p>
            </div>
        </div>
    </div>
    """

def generate_comparative_section(comparative, engine):
    """Generate comparative analysis section HTML"""
    if 'error' in comparative:
        return ''
    
    html_parts = []
    
    for comparison, data in comparative.items():
        if comparison == 'vs_district':
            performance = data.get('performance', 'Unknown')
            color = '#10b981' if performance == 'Better' else '#ef4444'
            icon = 'fa-arrow-up' if performance == 'Better' else 'fa-arrow-down'
            
            html_parts.append(f"""
            <div class="stat-card">
                <i class="fas fa-map-marker-alt" style="color: #3b82f6;"></i>
                <h3>District Comparison</h3>
                <div class="value" style="color: {color};">
                    {performance}
                </div>
                <div class="trend">
                    <i class="fas {icon}"></i> {data.get('difference', 0):.1f}% vs District Average
                </div>
            </div>
            """)
    
    if html_parts:
        return f"""
        <div class="chart-section">
            <div class="section-header">
                <i class="fas fa-chart-bar" style="color: #8b5cf6;"></i>
                <h2>Comparative Analysis</h2>
            </div>
            
            <div class="stats-grid">
                {''.join(html_parts)}
            </div>
        </div>
        """
    return ''

def generate_recommendations_html(recommendations):
    """Generate HTML for recommendations"""
    html_parts = []
    
    for rec in recommendations:
        html_parts.append(f"""
        <div class="recommendation-card priority-{rec['priority']}">
            <div class="priority">Priority {rec['priority']}</div>
            <h4>{rec['action']}</h4>
            <p>{rec['details']}</p>
        </div>
        """)
    
    return ''.join(html_parts)

def get_sustainability_color(level):
    """Get color for sustainability level"""
    colors = {
        'Highly Sustainable': '#16a34a',
        'Sustainable': '#22c55e',
        'Moderately Sustainable': '#f59e0b',
        'Unsustainable': '#ef4444',
        'Critically Unsustainable': '#dc2626'
    }
    return colors.get(level, '#6b7280')



@function_tool()
async def open_app_on_screen(app_name: str, screen_side: str = "left") -> str:
    """
    Opens an application and moves it to the chosen monitor (left or right).

    Args:
        app_name: Application name (e.g., "chrome")
        screen_side: "left" or "right" (default = right)

    Returns:
        str: Status message
    """
    try:
        print(f"🚀 Opening app: {app_name} on {screen_side} screen")

        # Step 1: Open via Start Menu
        await asyncio.to_thread(pyautogui.press, 'win')
        await asyncio.sleep(0.5)
        await asyncio.to_thread(pyautogui.typewrite, app_name, interval=0.1)
        await asyncio.sleep(0.5)
        await asyncio.to_thread(pyautogui.press, 'enter')
        await asyncio.sleep(4)  # wait for app to launch

        # Step 2: Move window to the chosen screen
        if screen_side.lower() == "right":
            await asyncio.to_thread(pyautogui.hotkey, 'win', 'shift', 'right')
        elif screen_side.lower() == "left":
            await asyncio.to_thread(pyautogui.hotkey, 'win', 'shift', 'left')
        else:
            return "⚠️ Invalid screen side! Use 'left' or 'right'."

        return f"✅ '{app_name}' खोला गया और {screen_side} screen पर भेजा गया।"

    except Exception as e:
        return f"❌ Error: {str(e)}"

# ================= Smart Selector ==================
@function_tool()
async def use_smart_selector(prompt: str, count: int) -> str:
    """
    Selects multiple items by holding Ctrl and pressing Down Arrow multiple times.

    Args:
        prompt: The user's request, e.g., "select top 10".
        count: How many times to press the Down Arrow with Ctrl held.

    Returns:
        A message confirming the selection.
    """
    try:
        if count < 1:
            return "⚠️ Error: Count must be 1 or greater."

        # Hold Ctrl
        pyautogui.keyDown("shift")

        # Press Down Arrow `count` times
        for _ in range(count):
            pyautogui.press("down")
            time.sleep(0.1)  # thoda delay taki smooth chale

        # Release Ctrl
        pyautogui.keyUp("ctrl")

        return f"✅ Selected top {count} items using Ctrl + Down Arrow."
    except Exception as e:
        return f"❌ Smart selector operation failed: {str(e)}"


# from diffusers import StableDiffusionPipeline
# import torch
# import asyncio

# # Load model once (GPU optimized)
# pipe = StableDiffusionPipeline.from_pretrained(
#     "runwayml/stable-diffusion-v1-5",
#     torch_dtype=torch.float16
# ).to("cuda")  # RTX GPU

# # ================= Image Generator Tool ==================
# @function_tool()
# async def generate_image_from_prompt(prompt: str, output_path: str = "nova_generated.png") -> str:
#     """
#     Generates an image from a text prompt using Stable Diffusion and saves it.

#     Args:
#         prompt: The text description for image generation.
#         output_path: Path to save the generated image (default = "nova_generated.png").

#     Returns:
#         str: Status message confirming image generation.
#     """
#     try:
#         print(f"🎨 Generating image for prompt: {prompt}")

#         # Generate image asynchronously
#         image = await asyncio.to_thread(pipe, prompt)
#         image_result = image.images[0]
#         image_result.save(output_path)

#         return f"✅ Image generated and saved at '{output_path}'."
#     except Exception as e:
#         return f"❌ Image generation failed: {str(e)}"


# from diffusers import StableDiffusionPipeline, DPMSolverMultistepScheduler, EulerDiscreteScheduler, LMSDiscreteScheduler, PNDMScheduler
# import torch
# import asyncio
# import os
# from PIL import Image, ImageFilter, ImageEnhance
# import subprocess
# import platform
# import random
# from datetime import datetime
# import time
# import gc
# from typing import Dict, List, Optional, Union
# import json

# # Global pipeline instance with lazy loading
# _pipeline = None

# def get_pipeline():
#     """Get or initialize the pipeline with optimized settings"""
#     global _pipeline
#     if _pipeline is None:
#         print("🚀 Initializing Optimized Stable Diffusion Pipeline...")
        
#         start_time = time.time()
        
#         # Clear GPU memory first
#         if torch.cuda.is_available():
#             torch.cuda.empty_cache()
#             gc.collect()
        
#         try:
#             # Use a smaller, faster model for better performance
#             model_id = "runwayml/stable-diffusion-v1-5"  # You can try "stabilityai/stable-diffusion-2-base" for faster generation
            
#             _pipeline = StableDiffusionPipeline.from_pretrained(
#                 model_id,
#                 torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
#                 use_safetensors=True,
#                 safety_checker=None,  # Disable safety checker to save memory
#                 requires_safety_checker=False
#             )
            
#             # Move to GPU if available
#             if torch.cuda.is_available():
#                 _pipeline = _pipeline.to("cuda")
#                 print(f"✅ Moved pipeline to GPU | VRAM: {torch.cuda.memory_allocated()/1024**3:.1f}GB")
#             else:
#                 print("⚠️ Using CPU - performance will be slow")
            
#             # Use a faster scheduler
#             _pipeline.scheduler = DPMSolverMultistepScheduler.from_config(
#                 _pipeline.scheduler.config,
#                 algorithm_type="dpmsolver++",
#                 solver_order=2,
#                 lower_order_final=True,
#                 use_karras_sigmas=True  # Better quality with fewer steps
#             )
            
#             # Enable memory optimizations
#             _pipeline.enable_attention_slicing(slice_size="auto")
            
#             # Try to enable xformers if available
#             try:
#                 _pipeline.enable_xformers_memory_efficient_attention()
#                 print("✅ XFormers enabled")
#             except:
#                 print("⚠️ XFormers not available, using default attention")
            
#             load_time = time.time() - start_time
#             print(f"✅ Pipeline loaded in {load_time:.2f}s")
            
#         except Exception as e:
#             print(f"❌ Pipeline initialization failed: {e}")
#             # Try CPU fallback with smaller model
#             try:
#                 print("🔄 Trying CPU fallback with smaller model...")
#                 _pipeline = StableDiffusionPipeline.from_pretrained(
#                     "runwayml/stable-diffusion-v1-5",
#                     torch_dtype=torch.float32
#                 )
#                 print("✅ Pipeline loaded on CPU")
#             except Exception as fallback_error:
#                 print(f"❌ CPU fallback also failed: {fallback_error}")
#                 raise fallback_error
    
#     return _pipeline

# def open_image(image_path: str):
#     """Open image with default viewer across all platforms"""
#     try:
#         if platform.system() == "Windows":
#             os.startfile(image_path)
#         elif platform.system() == "Darwin":
#             subprocess.run(["open", image_path])
#         else:
#             subprocess.run(["xdg-open", image_path])
#         return True
#     except Exception as e:
#         print(f"⚠️ Could not auto-open image: {e}")
#         return False

# def enhance_image(image_path: str, enhancements: Dict = None):
#     """Apply post-processing enhancements to generated image"""
#     if enhancements is None:
#         enhancements = {"sharpen": True, "contrast": 1.1, "vibrance": 1.05}
    
#     try:
#         with Image.open(image_path) as img:
#             if enhancements.get("sharpen"):
#                 img = img.filter(ImageFilter.SHARPEN)
            
#             if enhancements.get("contrast", 1.0) != 1.0:
#                 enhancer = ImageEnhance.Contrast(img)
#                 img = enhancer.enhance(enhancements["contrast"])
            
#             if enhancements.get("vibrance", 1.0) != 1.0:
#                 enhancer = ImageEnhance.Color(img)
#                 img = enhancer.enhance(enhancements["vibrance"])
            
#             # Save enhanced version
#             enhanced_path = image_path.replace(".png", "_enhanced.png")
#             img.save(enhanced_path, quality=95, optimize=True)
#             return enhanced_path
#     except Exception as e:
#         print(f"⚠️ Image enhancement failed: {e}")
#         return image_path

# def get_scheduler(scheduler_name: str):
#     """Get different schedulers for varied artistic results"""
#     pipe = get_pipeline()
#     config = pipe.scheduler.config
    
#     schedulers = {
#         "dpm": DPMSolverMultistepScheduler.from_config(config, algorithm_type="dpmsolver++"),
#         "dpm_adaptive": DPMSolverMultistepScheduler.from_config(config, algorithm_type="dpmsolver++", adaptive=True),
#         "euler": EulerDiscreteScheduler.from_config(config),
#         "euler_ancestral": EulerDiscreteScheduler.from_config(config, use_karras_sigmas=True),
#         "lms": LMSDiscreteScheduler.from_config(config),
#         "lms_karras": LMSDiscreteScheduler.from_config(config, use_karras_sigmas=True),
#         "pndm": PNDMScheduler.from_config(config),
#     }
    
#     return schedulers.get(scheduler_name, schedulers["dpm"])

# def generate_filename(prompt: str, quality: str) -> str:
#     """Generate meaningful filename from prompt"""
#     # Clean prompt for filename
#     clean_prompt = "".join(c for c in prompt[:30] if c.isalnum() or c in " _-").rstrip()
#     timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
#     return f"{clean_prompt}_{quality}_{timestamp}.png"

# def format_size(bytes_size: int) -> str:
#     """Format file size in human-readable format"""
#     for unit in ['B', 'KB', 'MB', 'GB']:
#         if bytes_size < 1024.0:
#             return f"{bytes_size:.1f} {unit}"
#         bytes_size /= 1024.0
#     return f"{bytes_size:.1f} TB"

# # ================= ULTIMATE UNIVERSAL IMAGE GENERATOR ==================
# @function_tool()
# async def generate_ai_image(
#     prompt: str,
#     negative_prompt: str = None,
#     output_path: str = None,
#     quality: str = "fast",
#     width: int = 512,
#     height: int = 512,
#     seed: int = None,
#     scheduler: str = "dpm",
#     style: str = None,
#     num_images: int = 1,
#     enhance: bool = False,
#     auto_open: bool = True,  # Changed to True by default
#     show_stats: bool = True,
#     save_config: bool = False,
#     num_inference_steps: int = None,
#     guidance_scale: float = None,
#     timeout: int = 20
# ) -> Union[str, List[str]]:
#     """
#     🎨 Optimized AI Image Generator - Faster generation to avoid timeouts
#     """
    
#     # Start timing
#     total_start_time = time.time()
    
#     try:
#         # ================= OPTIMIZED SETTINGS =================
#         pipe = get_pipeline()
        
#         # Force faster settings to avoid timeouts
#         quality_configs = {
#             "fast": {"steps": 12, "guidance": 7.0, "size": (512, 512)},
#             "good": {"steps": 15, "guidance": 7.5, "size": (512, 512)},
#             "premium": {"steps": 20, "guidance": 8.0, "size": (512, 512)},
#         }
        
#         config = quality_configs.get(quality, quality_configs["fast"])
        
#         # Apply config
#         num_inference_steps = num_inference_steps or config["steps"]
#         guidance_scale = guidance_scale or config["guidance"]
#         target_width = width or config["size"][0]
#         target_height = height or config["size"][1]
        
#         # Set seed
#         if seed is None:
#             seed = random.randint(0, 2**32 - 1)
        
#         # Generate output path
#         if output_path is None:
#             output_path = generate_filename(prompt, quality)
        
#         # ================= DISPLAY GENERATION INFO =================
#         if show_stats:
#             print(f"\n🎨 AI IMAGE GENERATION STARTED (Optimized)")
#             print(f"📝 Prompt: {prompt}")
#             print(f"⚡ Quality: {quality.upper()} ({num_inference_steps} steps)")
#             print(f"📏 Size: {target_width}x{target_height}")
#             print(f"📂 Will save to: {output_path}")
        
#         # ================= IMAGE GENERATION =================
#         # Clear memory before generation
#         if torch.cuda.is_available():
#             torch.cuda.empty_cache()
#             gc.collect()
        
#         # Generate image with timeout
#         try:
#             image_result = await asyncio.wait_for(
#                 asyncio.to_thread(
#                     pipe,
#                     prompt=prompt,
#                     negative_prompt=negative_prompt or "blurry, low quality, distorted",
#                     num_inference_steps=num_inference_steps,
#                     guidance_scale=guidance_scale,
#                     width=target_width,
#                     height=target_height,
#                     generator=torch.Generator("cuda").manual_seed(seed),
#                     output_type="pil"
#                 ),
#                 timeout=timeout
#             )
#         except asyncio.TimeoutError:
#             return "❌ **GENERATION TIMEOUT**\n\nImage generation took too long. Try using even simpler prompts or 'fast' quality."
        
#         # Save image
#         image_result.images[0].save(output_path, quality=95, optimize=True)
        
#         total_time = time.time() - total_start_time
        
#         if show_stats:
#             file_size = os.path.getsize(output_path)
#             print(f"✅ Image generated in {total_time:.1f}s | Size: {format_size(file_size)}")
        
#         # ================= AUTO-OPEN IMAGE =================
#         if auto_open:
#             open_success = open_image(output_path)
#             if open_success:
#                 print(f"🖼️ Image opened in default viewer: {output_path}")
#             else:
#                 print(f"⚠️ Could not auto-open image: {output_path}")
        
#         # Clean up GPU memory
#         if torch.cuda.is_available():
#             torch.cuda.empty_cache()
#             gc.collect()
        
#         # Return the result with image opening status
#         result_message = f"🎉 **IMAGE GENERATED SUCCESSFULLY**\n\n• **File**: {output_path}\n• **Time**: {total_time:.1f}s\n• **Size**: {target_width}x{target_height}\n• **Opened**: {'Yes' if auto_open else 'No'}\n• **Prompt**: _{prompt}_"
        
#         return result_message
        
#     except Exception as e:
#         # Clean up on error
#         if torch.cuda.is_available():
#             torch.cuda.empty_cache()
#             gc.collect()
        
#         error_msg = f"❌ **GENERATION FAILED**\n\nError: {str(e)}"
        
#         if "CUDA out of memory" in str(e):
#             error_msg += "\n\n💡 Try reducing image size or using CPU"
#         elif "timeout" in str(e).lower():
#             error_msg += "\n\n💡 Generation took too long. Use simpler prompts or smaller size"
        
#         return error_msg


import aiohttp
import asyncio
import os
import random
from datetime import datetime
import time
from typing import Dict, List, Optional, Union
from PIL import Image, ImageFilter, ImageEnhance
import subprocess
import platform
import json
from urllib.parse import quote
import io

# Pollinations.ai API configuration
POLLINATIONS_BASE_URL = "https://image.pollinations.ai"
POLLINATIONS_VIDEO_URL = "https://video.pollinations.ai"

class PollinationsAdvancedGenerator:
    """Advanced Pollinations.ai image and video generator with enhanced features"""
    
    def __init__(self):
        self.available_models = [
            "flux", "flux-pro", "sd3", "sd3-large", "sd3-medium",
            "kandinsky", "dreamshaper", "realistic", "anime", "concept"
        ]
        self.available_aspect_ratios = {
            "square": (1024, 1024),
            "portrait": (768, 1024),
            "landscape": (1024, 768),
            "widescreen": (1280, 720),
            "ultrawide": (1920, 1080),
            "mobile": (576, 1024),
            "cinematic": (2048, 858)
        }
        self.quality_presets = {
            "lightning": {"steps": 10, "cfg": 6.0},
            "fast": {"steps": 15, "cfg": 7.0},
            "balanced": {"steps": 20, "cfg": 7.5},
            "quality": {"steps": 30, "cfg": 8.0},
            "ultra": {"steps": 50, "cfg": 9.0}
        }
        
    def build_prompt(self, base_prompt: str, style: str = None, artist: str = None, 
                    lighting: str = None, composition: str = None) -> str:
        """Build enhanced prompt with style and quality modifiers"""
        prompt_parts = [base_prompt]
        
        # Style modifiers
        style_modifiers = {
            "photorealistic": "photorealistic, hyperdetailed, 8K, UHD, realistic lighting",
            "anime": "anime style, vibrant colors, cel-shaded, Japanese animation",
            "painting": "oil painting, brush strokes, artistic, masterpiece",
            "digital_art": "digital art, concept art, trending on artstation",
            "minimalistic": "minimalistic, clean lines, simple composition",
            "cyberpunk": "cyberpunk, neon lights, futuristic, sci-fi",
            "fantasy": "fantasy, magical, epic, mythical creatures",
            "abstract": "abstract art, geometric patterns, colorful, modern art"
        }
        
        if style and style in style_modifiers:
            prompt_parts.append(style_modifiers[style])
        
        # Artist styles
        artist_styles = {
            "van_gogh": "in the style of Van Gogh",
            "picasso": "cubist style like Picasso",
            "monet": "impressionist style like Monet",
            "da_vinci": "renaissance style like Leonardo da Vinci",
            "dali": "surrealist style like Salvador Dali",
            "warhol": "pop art style like Andy Warhol"
        }
        
        if artist and artist in artist_styles:
            prompt_parts.append(artist_styles[artist])
        
        # Lighting modifiers
        lighting_modifiers = {
            "dramatic": "dramatic lighting, cinematic lighting",
            "soft": "soft lighting, gentle shadows",
            "studio": "studio lighting, professional photography",
            "natural": "natural lighting, sunlight",
            "neon": "neon lighting, vibrant colors",
            "moody": "moody lighting, high contrast"
        }
        
        if lighting and lighting in lighting_modifiers:
            prompt_parts.append(lighting_modifiers[lighting])
        
        # Composition modifiers
        composition_modifiers = {
            "closeup": "close-up shot, detailed",
            "wide": "wide shot, expansive view",
            "dynamic": "dynamic composition, interesting angles",
            "symmetrical": "symmetrical composition, balanced",
            "rule_of_thirds": "rule of thirds composition"
        }
        
        if composition and composition in composition_modifiers:
            prompt_parts.append(composition_modifiers[composition])
        
        return ", ".join(prompt_parts)

def open_image(image_path: str) -> bool:
    """Open image with default viewer"""
    try:
        if platform.system() == "Windows":
            os.startfile(image_path)
        elif platform.system() == "Darwin":
            subprocess.run(["open", image_path], check=True)
        else:
            subprocess.run(["xdg-open", image_path], check=True)
        return True
    except Exception as e:
        print(f"⚠️ Could not auto-open image: {e}")
        return False

def enhance_image(image_path: str, enhancements: Dict = None):
    """Apply post-processing enhancements to generated image"""
    if enhancements is None:
        enhancements = {
            "sharpen": True, 
            "contrast": 1.1, 
            "vibrance": 1.05,
            "upscale": False
        }
    
    try:
        with Image.open(image_path) as img:
            original_mode = img.mode
            
            # Convert to RGB if needed
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            if enhancements.get("sharpen"):
                img = img.filter(ImageFilter.SHARPEN)
            
            if enhancements.get("contrast", 1.0) != 1.0:
                enhancer = ImageEnhance.Contrast(img)
                img = enhancer.enhance(enhancements["contrast"])
            
            if enhancements.get("vibrance", 1.0) != 1.0:
                enhancer = ImageEnhance.Color(img)
                img = enhancer.enhance(enhancements["vibrance"])
            
            # Optional upscaling
            if enhancements.get("upscale"):
                width, height = img.size
                img = img.resize((width * 2, height * 2), Image.LANCZOS)
            
            # Save enhanced version
            enhanced_path = image_path.replace(".png", "_enhanced.png")
            img.save(enhanced_path, quality=95, optimize=True)
            return enhanced_path
    except Exception as e:
        print(f"⚠️ Image enhancement failed: {e}")
        return image_path

def generate_filename(prompt: str, quality: str, media_type: str = "image") -> str:
    """Generate meaningful filename from prompt with proper sanitization"""
    try:
        # Clean prompt for filename - more robust cleaning
        import re
        clean_prompt = re.sub(r'[^\w\s-]', '', prompt.lower())
        clean_prompt = re.sub(r'[-\s]+', '_', clean_prompt)
        clean_prompt = clean_prompt.strip('_-')
        
        # Ensure we have at least some filename
        if not clean_prompt or len(clean_prompt) < 3:
            clean_prompt = "ai_image"
        else:
            clean_prompt = clean_prompt[:30]  # Limit length
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        extension = "png" if media_type == "image" else "mp4"
        
        filename = f"pollinations_{clean_prompt}_{quality}_{timestamp}.{extension}"
        
        # Double-check it's a valid filename
        if not filename or len(filename) < 5:
            filename = f"pollinations_{timestamp}.{extension}"
            
        return filename
        
    except Exception as e:
        # Fallback if anything goes wrong
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"pollinations_{timestamp}.png"

def format_size(bytes_size: int) -> str:
    """Format file size"""
    for unit in ['B', 'KB', 'MB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} GB"

async def download_file(url: str, filepath: str, timeout: int = 60) -> bool:
    """Fixed file downloader with proper path handling"""
    try:
        # CRITICAL FIX: Validate filepath is not empty
        if not filepath or filepath.strip() == "":
            # Generate a fallback filename
            timestamp = datetime.now().strftime("%H%M%S")
            filepath = f"generated_image_{timestamp}.png"
            print(f"⚠️ Empty path detected, using fallback: {filepath}")
        
        print(f"🔗 Downloading from: {url[:80]}...")
        print(f"📁 Saving to: {filepath}")
        
        timeout_config = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(timeout=timeout_config) as session:
            async with session.get(url) as response:
                print(f"📡 HTTP Status: {response.status}")
                
                if response.status == 200:
                    content = await response.read()
                    print(f"📦 Received: {len(content)} bytes")
                    
                    # Save file
                    with open(filepath, 'wb') as f:
                        f.write(content)
                    
                    print(f"✅ Saved to: {filepath}")
                    return True
                else:
                    print(f"❌ Server error: {response.status}")
                    return False
                    
    except Exception as e:
        print(f"❌ Download error: {e}")
        return False

@function_tool()
async def generate_ai_image(
    prompt: str,
    output_path: str = "",
    quality: str = "balanced",
    width: int = 1024,
    height: int = 1024,
    model: str = "flux"
) -> str:
    """
    🎨 Simple AI Image Generator using Pollinations.ai
    Generates image from prompt and automatically opens it.
    
    IMPORTANT: Always use English for prompts to ensure best results.
    
    Args:
        prompt: Image description in ENGLISH (required)
        output_path: Where to save the image (optional - auto-generated if empty)
        quality: "fast", "balanced", or "quality" (default: balanced)
        width: Image width (default: 1024)
        height: Image height (default: 1024)
        model: AI model to use (default: flux)
    
    Returns:
        Success message with image details
    """
    
    print("🚀 Starting image generation...")
    start_time = time.time()
    
    try:
        # Validate prompt is in English (basic check)
        english_check = prompt.strip()
        if not english_check:
            return "❌ Please provide an English prompt description"
        
        print(f"📝 Prompt: {prompt}")
        
        # Quality settings
        quality_settings = {
            "fast": {"steps": 15, "cfg": 7.0},
            "balanced": {"steps": 20, "cfg": 7.5},
            "quality": {"steps": 30, "cfg": 8.0}
        }
        
        config = quality_settings.get(quality, quality_settings["balanced"])
        
        # Generate filename if not provided OR if empty string
        if not output_path or output_path.strip() == "":
            # Simple filename generation
            clean_name = "".join(c for c in prompt[:20] if c.isalnum() or c in " _").strip()
            if not clean_name:
                clean_name = "image"
            timestamp = datetime.now().strftime("%H%M%S")
            output_path = f"{clean_name}_{timestamp}.png"
        
        # Ensure .png extension
        if not output_path.lower().endswith('.png'):
            output_path += '.png'
            
        print(f"📁 Will save to: {output_path}")
        
        # Build the API URL
        from urllib.parse import quote
        encoded_prompt = quote(prompt)
        
        params = {
            "prompt": prompt,
            "width": width,
            "height": height,
            "model": model,
            "steps": config["steps"],
            "cfg": config["cfg"]
        }
        
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?{query_string}"
        
        print("📡 Downloading image from Pollinations.ai...")
        
        # Download the image
        success = await download_file(image_url, output_path, timeout=60)
        
        if not success:
            return "❌ Failed to generate or download image. Please try again with a different prompt."
        
        # Check if file was created
        if not os.path.exists(output_path):
            return "❌ Image file was not created. Please try again."
        
        file_size = os.path.getsize(output_path)
        if file_size < 1000:
            return "❌ Generated image is too small. The AI might have had issues with your prompt."
        
        generation_time = time.time() - start_time
        
        print(f"✅ Image generated in {generation_time:.1f}s")
        print(f"📦 File size: {format_size(file_size)}")
        
        # Auto-open the image
        print("🖼️ Opening image...")
        open_success = open_image(output_path)
        
        if open_success:
            result = f"""
🎉 **IMAGE GENERATED SUCCESSFULLY!**

📝 **Prompt:** {prompt}
📏 **Size:** {width}x{height}
⚡ **Quality:** {quality}
🤖 **Model:** {model}
⏱️ **Time:** {generation_time:.1f}s
📦 **Size:** {format_size(file_size)}
📁 **Location:** {output_path}

✅ Image has been generated and opened automatically!
"""
        else:
            result = f"""
🎉 **IMAGE GENERATED SUCCESSFULLY!**

📝 **Prompt:** {prompt}
📏 **Size:** {width}x{height}
📁 **Saved as:** {output_path}

✅ Image generated! (Could not auto-open, but file is saved)
"""
        
        return result.strip()
        
    except Exception as e:
        error_msg = f"❌ **GENERATION FAILED**\n\nError: {str(e)}"
        print(f"💥 Error: {e}")
        return error_msg

@function_tool()
async def generate_ai_video(
    prompt: str,
    output_path: str = None,
    duration: int = 4,
    fps: int = 24,
    quality: str = "balanced",
    seed: int = None,
    model: str = "flux",
    style: str = None,
    auto_open: bool = False,
    timeout: int = 120
) -> str:
    """
    🎥 Generate AI Videos using Pollinations.ai
    Create stunning video animations from text prompts
    """
    
    try:
        total_start_time = time.time()
        advanced_gen = PollinationsAdvancedGenerator()
        
        # Set seed
        if seed is None:
            seed = random.randint(0, 2**32 - 1)
        
        # Build enhanced prompt
        enhanced_prompt = advanced_gen.build_prompt(prompt, style)
        
        # Generate output path
        if output_path is None:
            output_path = generate_filename(prompt, quality, "video")
        
        # Build video URL
        video_url = f"{POLLINATIONS_VIDEO_URL}/prompt/{enhanced_prompt}?duration={duration}&fps={fps}&seed={seed}&model={model}"
        
        print(f"\n🎥 GENERATING AI VIDEO")
        print(f"📝 Prompt: {prompt}")
        print(f"⏱️ Duration: {duration}s")
        print(f"🎞️ FPS: {fps}")
        print(f"📂 Output: {output_path}")
        
        # Download video
        download_success = await download_file(video_url, output_path, timeout)
        
        if not download_success:
            return "❌ **VIDEO GENERATION FAILED**\n\nVideo generation timed out or failed. Try shorter duration or simpler prompt."
        
        total_time = time.time() - total_start_time
        file_size = os.path.getsize(output_path)
        
        # Auto-open if requested
        if auto_open:
            open_success = open_image(output_path)
        
        result_message = f"""
🎬 **AI VIDEO GENERATED SUCCESSFULLY**

• **File**: `{output_path}`
• **Duration**: {duration}s
• **FPS**: {fps}
• **Size**: {format_size(file_size)}
• **Generation Time**: {total_time:.1f}s
• **Model**: {model}

**Prompt**: _{prompt}_
"""
        
        return result_message.strip()
        
    except Exception as e:
        return f"❌ **VIDEO GENERATION FAILED**\n\nError: {str(e)}"

@function_tool()
async def get_generation_presets() -> Dict:
    """
    📊 Get available generation presets and options
    """
    advanced_gen = PollinationsAdvancedGenerator()
    
    return {
        "models": advanced_gen.available_models,
        "quality_presets": advanced_gen.quality_presets,
        "aspect_ratios": list(advanced_gen.available_aspect_ratios.keys()),
        "styles": [
            "photorealistic", "anime", "painting", "digital_art", 
            "minimalistic", "cyberpunk", "fantasy", "abstract"
        ],
        "artists": [
            "van_gogh", "picasso", "monet", "da_vinci", "dali", "warhol"
        ],
        "lighting_options": [
            "dramatic", "soft", "studio", "natural", "neon", "moody"
        ],
        "composition_options": [
            "closeup", "wide", "dynamic", "symmetrical", "rule_of_thirds"
        ]
    }

import os
import subprocess
import platform
from pathlib import Path
import glob

@function_tool()
async def open_file_command(user_command: str) -> str:
    r"""
    Smart file opener that understands natural language commands and searches system-wide.
    Can open both files and folders.
    
    Args:
        user_command: Natural language command like:
                    - "open report.pdf"
                    - "open the excel file in documents"
                    - "open MC folder on desktop"
                    - "open C:\Users\Ankit Singh\Contacts"
                    - "open this file" (searches current folder)
    
    Returns:
        Status message about the operation
    """
    try:
        print(f"🎯 User command: {user_command}")
        
        # First check if it's a direct path
        if await _is_direct_path(user_command):
            return await _open_direct_path(user_command)
        
        # Extract filename and location from command
        filename, location, is_folder = await _parse_file_command(user_command)
        
        if not filename:
            return "❌ Please tell me which file or folder to open. Examples:\n" \
                   "• 'Open report.pdf'\n" \
                   "• 'Open data.xlsx from documents'\n" \
                   "• 'Open MC folder on desktop'\n" \
                   "• 'Open this file' (opens any file in current folder)"
        
        print(f"🔍 Command analysis - File/Folder: '{filename}', Location: '{location}', Is Folder: {is_folder}")
        
        # Search for the file or folder with location priority
        return await _find_and_open_file_or_folder(filename, location, is_folder)
        
    except Exception as e:
        return f"❌ Failed to open: {str(e)}"

async def _is_direct_path(user_command: str) -> bool:
    """Check if the command contains a direct file/folder path"""
    # Remove "open" from the beginning if present
    clean_command = user_command.lower().replace("open", "").strip()
    
    # Check for path patterns
    path_indicators = [":\\", ":/", "\\", "/", "~/"]
    return any(indicator in clean_command for indicator in path_indicators)

async def _open_direct_path(user_command: str) -> str:
    """Open a direct file/folder path"""
    try:
        # Extract the path from the command
        path = user_command.lower().replace("open", "").strip()
        
        # Handle quoted paths
        if path.startswith('"') and path.endswith('"'):
            path = path[1:-1]
        elif path.startswith("'") and path.endswith("'"):
            path = path[1:-1]
        
        # Expand user directory if needed
        if path.startswith("~"):
            path = os.path.expanduser(path)
        
        print(f"🛣️  Direct path detected: {path}")
        
        if os.path.exists(path):
            return await _open_file_or_folder(path)
        else:
            return f"❌ Path not found: {path}"
            
    except Exception as e:
        return f"❌ Failed to open path: {str(e)}"

async def _parse_file_command(user_command: str) -> tuple:
    """Parse the user command to extract filename, location, and whether it's a folder"""
    filename = None
    location = None
    is_folder = False
    
    user_lower = user_command.lower()
    
    # Check if it's a folder request
    folder_keywords = ["folder", "directory", "dir"]
    is_folder = any(keyword in user_lower for keyword in folder_keywords)
    
    # FIRST: Extract location to avoid conflicts
    location_keywords = {
        "documents": os.path.expanduser("~/Documents"),
        "downloads": os.path.expanduser("~/Downloads"),
        "desktop": os.path.expanduser("~/Desktop"),
        "pictures": os.path.expanduser("~/Pictures"),
        "music": os.path.expanduser("~/Music"),
        "videos": os.path.expanduser("~/Videos"),
        "contacts": os.path.expanduser("~/Contacts"),
        "c drive": "C:/",
        "c:": "C:/", 
        "d drive": "D:/",
        "d:": "D:/",
        "current folder": ".",
        "this folder": ".",
        "current directory": "."
    }
    
    # Check for location keywords
    for keyword, path in location_keywords.items():
        if keyword in user_lower:
            location = path
            print(f"📍 Location detected: {keyword} -> {path}")
            break
    
    # If location mentioned with prepositions, be more specific
    if not location:
        location_patterns = [
            ("in documents", "~/Documents"),
            ("in downloads", "~/Downloads"), 
            ("in desktop", "~/Desktop"),
            ("in pictures", "~/Pictures"),
            ("from documents", "~/Documents"),
            ("from downloads", "~/Downloads"),
            ("from desktop", "~/Desktop"),
            ("on desktop", "~/Desktop"),
            ("at documents", "~/Documents")
        ]
        
        for pattern, path in location_patterns:
            if pattern in user_lower:
                location = os.path.expanduser(path)
                print(f"📍 Location pattern detected: {pattern} -> {location}")
                break
    
    # Extract the main target (file/folder name)
    words = user_lower.split()
    
    # Remove common words to find the target
    common_words = {"open", "the", "a", "an", "file", "folder", "directory", "in", "from", "on", "at"}
    target_words = [word for word in words if word not in common_words and word not in location_keywords]
    
    if target_words:
        # The first non-common word is likely the target
        filename = target_words[0]
        
        # If it's a multi-word target like "MC folder", combine them
        if len(target_words) > 1 and not is_folder:
            # Check if the second word is not a location indicator
            if target_words[1] not in location_keywords:
                filename = " ".join(target_words[:2])
    
    # Special case: "open this file" or "current file"
    if not filename and ("this file" in user_lower or "current file" in user_lower):
        filename = "*"
    
    # Special case: "open this folder" or "current folder" 
    if not filename and ("this folder" in user_lower or "current folder" in user_lower):
        filename = "."
        is_folder = True
    
    return filename, location, is_folder

async def _find_and_open_file_or_folder(filename: str, location: str, is_folder: bool) -> str:
    """
    Find and open file or folder with location priority
    """
    print(f"🔍 Final search - Target: '{filename}', Location: '{location}', Is Folder: {is_folder}")
    
    # If specific location is mentioned, search ONLY there
    if location:
        print(f"🎯 Searching specifically in: {location}")
        result = await _search_in_location_thorough(filename, location, is_folder)
        if result:
            return result
        else:
            return f"❌ {'Folder' if is_folder else 'File'} '{filename}' not found in the specified location: {location}"
    
    # If no specific location, search in order of priority
    print("🔍 No specific location mentioned, searching common locations...")
    
    # Strategy 1: Search in current directory
    result = await _search_in_location_thorough(filename, ".", is_folder)
    if result:
        return result
    
    # Strategy 2: Search in common user directories
    common_locations = [
        os.path.expanduser("~/Desktop"),     # Most common for quick access
        os.path.expanduser("~/Documents"),   
        os.path.expanduser("~/Downloads"),   
        os.path.expanduser("~/Pictures"),
        os.path.expanduser("~/Music"),
        os.path.expanduser("~/Videos"),
        os.path.expanduser("~/Contacts"),
    ]
    
    for loc in common_locations:
        if os.path.exists(loc):
            print(f"🔍 Searching in: {loc}")
            result = await _search_in_location_thorough(filename, loc, is_folder)
            if result:
                return result
    
    return f"❌ {'Folder' if is_folder else 'File'} '{filename}' not found in common locations"

async def _search_in_location_thorough(target: str, location: str, is_folder: bool) -> str:
    """Thorough search for file or folder in a specific location"""
    try:
        if not os.path.exists(location):
            return None
        
        print(f"🔍 Thorough search in: {location} for {'folder' if is_folder else 'file'}")
        
        # Special case: open current directory
        if target == ".":
            return await _open_file_or_folder(location)
        
        # Special case: open any file in current folder
        if target == "*" and not is_folder:
            files = [f for f in os.listdir(location) if os.path.isfile(os.path.join(location, f))]
            if files:
                file_path = os.path.join(location, files[0])
                return await _open_file_or_folder(file_path)
            return None
        
        # Search strategies in order of specificity:
        
        # 1. Exact match
        exact_path = os.path.join(location, target)
        if os.path.exists(exact_path):
            if (is_folder and os.path.isdir(exact_path)) or (not is_folder and os.path.isfile(exact_path)):
                print(f"✅ Exact match found: {exact_path}")
                return await _open_file_or_folder(exact_path)
        
        # 2. Case-insensitive search
        if os.path.isdir(location):
            for item in os.listdir(location):
                item_path = os.path.join(location, item)
                # Check if it matches our criteria (file/folder)
                if ((is_folder and os.path.isdir(item_path)) or 
                    (not is_folder and os.path.isfile(item_path))):
                    
                    # Case-insensitive comparison
                    if target.lower() in item.lower():
                        print(f"✅ Case-insensitive match: {item_path}")
                        return await _open_file_or_folder(item_path)
        
        # 3. Partial match (for multi-word targets like "MC folder")
        if " " in target:
            target_parts = target.lower().split()
            if os.path.isdir(location):
                for item in os.listdir(location):
                    item_path = os.path.join(location, item)
                    # Check if it matches our criteria (file/folder)
                    if ((is_folder and os.path.isdir(item_path)) or 
                        (not is_folder and os.path.isfile(item_path))):
                        
                        item_lower = item.lower()
                        # Check if all target parts are in the item name
                        if all(part in item_lower for part in target_parts):
                            print(f"✅ Multi-word match: {item_path}")
                            return await _open_file_or_folder(item_path)
        
        print(f"❌ No matches found in: {location}")
        return None
        
    except Exception as e:
        print(f"⚠️ Search error in {location}: {e}")
        return None

async def _open_file_or_folder(path: str) -> str:
    """Open file or folder with system default application"""
    system = platform.system()
    name = os.path.basename(path)
    folder_path = os.path.dirname(path)
    is_folder = os.path.isdir(path)
    
    try:
        print(f"🔄 Opening: {path} ({'folder' if is_folder else 'file'})")
        
        if system == "Windows":
            if is_folder:
                # For folders, use explorer
                subprocess.run(["explorer", path], check=True)
            else:
                # For files, use startfile
                os.startfile(path)
        elif system == "Darwin":  # macOS
            subprocess.run(["open", path], check=True)
        else:  # Linux
            subprocess.run(["xdg-open", path], check=True)
        
        item_type = "folder" if is_folder else "file"
        return f"✅ Successfully opened {item_type}: {name}\n📁 Location: {folder_path}"
    except Exception as e:
        item_type = "folder" if is_folder else "file"
        return f"❌ Failed to open {item_type} {name}: {str(e)}"



import os
import aiohttp
import asyncio
import pyautogui
import tempfile
import subprocess
from typing import Optional, Dict, List
from pathlib import Path

@function_tool()
async def generate_and_type_code(prompt: str, filename: str, language: Optional[str] = None) -> str:
    """
    Generates complete, well-formatted code using Groq AI models with syntax validation,
    types it in the editor, and saves automatically.

    Args:
        prompt (str): User request for code generation.
        filename (str): Name to save the generated file as.
        language (Optional[str]): (Optional) Force language type.
    
    Returns:
        str: Status message (success/failure) with formatting details
    """
    try:
        # ✅ Enhanced Configuration
        GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
        GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
        
        AVAILABLE_MODELS = [
            "llama-3.3-70b-versatile",
            "meta-llama/llama-4-maverick-17b-128e-instruct",  # Better for code
            "qwen/qwen3-32b",
            "llama-3.1-8b-instant",
            "openai/gpt-oss-120b"
        ]

        # ✅ Enhanced Language Configuration with formatters
        LANG_CONFIG: Dict[str, Dict] = {
            "python": {
                "ext": "py",
                "formatter": "black",
                "linter": "pylint",
                "syntax_check": ["python", "-m", "py_compile"]
            },
            "javascript": {
                "ext": "js",
                "formatter": "prettier",
                "linter": "eslint",
                "syntax_check": ["node", "--check"]
            },
            "html": {
                "ext": "html",
                "formatter": "prettier",
                "linter": None,
                "syntax_check": None
            },
            "css": {
                "ext": "css",
                "formatter": "prettier",
                "linter": None,
                "syntax_check": None
            },
            "java": {
                "ext": "java",
                "formatter": "google-java-format",
                "linter": "checkstyle",
                "syntax_check": ["javac"]
            },
            "cpp": {
                "ext": "cpp",
                "formatter": "clang-format",
                "linter": "cpplint",
                "syntax_check": ["g++", "-fsyntax-only"]
            },
            "c": {
                "ext": "c",
                "formatter": "clang-format",
                "linter": "cpplint",
                "syntax_check": ["gcc", "-fsyntax-only"]
            },
            "php": {
                "ext": "php",
                "formatter": "php-cs-fixer",
                "linter": "php -l",
                "syntax_check": ["php", "-l"]
            },
            "kotlin": {
                "ext": "kt",
                "formatter": "ktlint",
                "linter": "detekt",
                "syntax_check": ["kotlinc"]
            }
        }

        # ✅ Enhanced Language Detection
        def detect_language(prompt_text: str) -> str:
            if language:
                return language.lower()
            
            prompt_lower = prompt_text.lower()
            lang_keywords = {
                "python": ["python", "py", "pandas", "numpy", "django", "flask"],
                "javascript": ["javascript", "js", "node", "react", "vue", "angular"],
                "html": ["html", "webpage", "website"],
                "css": ["css", "stylesheet", "styling"],
                "java": ["java", "spring", "android"],
                "cpp": ["c++", "cpp", "stl"],
                "c": [" c ", "c program"],
                "php": ["php", "wordpress", "laravel"],
                "kotlin": ["kotlin", "android"]
            }
            
            for lang, keywords in lang_keywords.items():
                if any(keyword in prompt_lower for keyword in keywords):
                    return lang
            return "python"

        lang = detect_language(prompt)
        model = AVAILABLE_MODELS[0]  # Best model for code generation

        # ✅ Enhanced System Prompt for Better Formatting
        system_prompt = f"""You are a professional {lang} developer. Generate complete, runnable, and WELL-FORMATTED code.

IMPORTANT FORMATTING RULES:
1. Use proper indentation and spacing
2. Follow language-specific style guides (PEP8 for Python, etc.)
3. Include necessary imports/headers
4. Add appropriate comments for complex logic
5. Ensure code is syntactically correct
6. Use meaningful variable names
7. Include proper error handling where needed

Return ONLY the code without any explanations or markdown formatting."""

        # ✅ Fetch code from Groq API
        logger.info(f"🧠 Generating well-formatted {lang} code via {model}")
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Write a complete, well-formatted {lang} program for: {prompt}"}
            ],
            "temperature": 0.3,  # Lower temperature for more consistent formatting
            "max_tokens": 4096,  # Increased for better code completion
            "top_p": 0.9
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(GROQ_API_URL, headers=headers, json=payload, timeout=60) as res:
                data = await res.json()
                if res.status != 200:
                    return f"❌ API Error {res.status}: {data}"

                code = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )

                # Remove markdown formatting if present
                if code.startswith("```"):
                    lines = code.split("\n")
                    # Remove first and last line (markdown tags)
                    code = "\n".join(lines[1:-1])

        # ✅ Code Validation and Formatting
        lang_config = LANG_CONFIG.get(lang, LANG_CONFIG["python"])
        extension = lang_config["ext"]
        full_filename = f"{filename}"
        
        # Create temporary file for validation
        with tempfile.NamedTemporaryFile(mode='w', suffix=f'.{extension}', delete=False) as temp_file:
            temp_file.write(code)
            temp_path = temp_file.name

        validation_results = []
        
        try:
            # Syntax Check
            if lang_config["syntax_check"]:
                syntax_cmd = lang_config["syntax_check"] + [temp_path]
                result = subprocess.run(syntax_cmd, capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    validation_results.append("✅ Syntax validation passed")
                else:
                    validation_results.append(f"⚠️ Syntax issues: {result.stderr[:200]}")

            # Format code if formatter available
            formatted_code = code
            try:
                if lang_config["formatter"] == "black" and lang == "python":
                    result = subprocess.run(["black", "--quiet", temp_path], 
                                         capture_output=True, text=True, timeout=30)
                    if result.returncode == 0:
                        with open(temp_path, 'r') as f:
                            formatted_code = f.read()
                        validation_results.append("✅ Code formatted with Black")
                
                elif lang_config["formatter"] == "prettier" and lang in ["javascript", "html", "css"]:
                    result = subprocess.run(["npx", "prettier", "--write", temp_path], 
                                         capture_output=True, text=True, timeout=30)
                    if result.returncode == 0:
                        with open(temp_path, 'r') as f:
                            formatted_code = f.read()
                        validation_results.append("✅ Code formatted with Prettier")
                        
            except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError) as e:
                validation_results.append("⚠️ Formatting skipped (formatter not available)")

        finally:
            # Cleanup temp file
            Path(temp_path).unlink(missing_ok=True)

        # ✅ FIXED: Simple and reliable typing approach
        logger.info(f"⌨️ Typing well-formatted {lang} code to editor...")
        
        # Ensure we have focus on the editor
        await asyncio.sleep(2)  # Give user time to focus on editor

        pyautogui.hotkey("ctrl", "n")
        await asyncio.sleep(2)
        
        # Method 1: Use clipboard for perfect formatting (recommended)
        try:
            import pyperclip
            logger.info("📋 Using clipboard method for perfect formatting...")
            pyperclip.copy(formatted_code)
            await asyncio.sleep(0.5)
            pyautogui.hotkey('ctrl', 'v')  # Paste
            await asyncio.sleep(1)
            
        except ImportError:
            # Method 2: Fallback to direct typing with better approach
            logger.info("⌨️ Using direct typing method...")
            
            # Split into lines and type each line properly
            lines = formatted_code.split('\n')
            
            for i, line in enumerate(lines):
                if line.strip():  # Only type non-empty lines
                    # Type the entire line at once
                    pyautogui.write(line, interval=0.01)
                
                # Add newline if not the last line
                if i < len(lines) - 1:
                    pyautogui.press('enter')
                    await asyncio.sleep(0.05)

        logger.info("💾 Saving formatted file...")
        await asyncio.sleep(1)
        pyautogui.hotkey("ctrl", "s")
        await asyncio.sleep(1)
        pyautogui.write(full_filename)
        await asyncio.sleep(2)
        pyautogui.press("enter")
        await asyncio.sleep(0.5)

        # ✅ Final Status with Validation Summary
        validation_summary = " | ".join(validation_results)
        return f"✅ Code generated & saved as {full_filename} | {validation_summary}"

    except subprocess.TimeoutExpired:
        logger.warning("Code validation timed out, proceeding with unvalidated code")
        return f"✅ Code generated & saved as {full_filename} (validation skipped)"
        
    except Exception as e:
        logger.error(f"❌ Advanced code generation failed: {e}")
        return f"❌ Failed: {str(e)}"
    



import os
import subprocess
import pyautogui
import time

@function_tool()
async def run_file_in_vscode(file_path: str = None) -> str:
    """
    Automatically runs the current or specified file in VS Code based on its file extension.
    
    Args:
        file_path: Optional path to specific file. If not provided, runs currently active file.
    
    Returns:
        A message confirming the action or error details.
    """
    try:
        # File extensions and their run commands
        RUN_COMMANDS = {
            '.py': 'python',
            '.js': 'node',
            '.html': 'start',  # Windows
            '.java': 'javac',
            '.cpp': 'g++',
            '.c': 'gcc',
            '.php': 'php',
            '.rb': 'ruby',
            '.go': 'go run',
            '.rs': 'cargo run',
            '.sh': 'bash',
            '.bat': '',
            '.ps1': 'powershell'
        }
        
        # If no file path provided, get currently active file in VS Code
        if file_path is None:
            # Save current file first (Ctrl+S)
            pyautogui.hotkey('ctrl', 's')
            time.sleep(0.5)
            
            # Get file path from VS Code (using copy path command)
            pyautogui.hotkey('ctrl', 'k')
            pyautogui.hotkey('ctrl', 'p')
            time.sleep(0.5)
            
            # For now, we'll assume user provides path or we detect active file
            return "⚠️ Please specify file path, or ensure a file is active in VS Code."
        
        # Check if file exists
        if not os.path.exists(file_path):
            return f"❌ File not found: {file_path}"
        
        # Get file extension
        _, extension = os.path.splitext(file_path)
        extension = extension.lower()
        
        if extension not in RUN_COMMANDS:
            return f"❌ Unsupported file type: {extension}"
        
        run_command = RUN_COMMANDS[extension]
        
        # Open VS Code terminal (Ctrl + `)
        pyautogui.hotkey('ctrl', '`')
        time.sleep(1)
        
        # Clear terminal (Ctrl + L)
        pyautogui.hotkey('ctrl', 'l')
        time.sleep(0.5)
        
        # Build the full command based on file type
        if extension == '.html':
            # For HTML, open in browser
            command = f'{run_command} "{file_path}"'
        elif extension in ['.java', '.cpp', '.c']:
            # For compiled languages, compile first then run
            if extension == '.java':
                compile_cmd = f'javac "{file_path}"'
                run_cmd = f'java "{os.path.splitext(file_path)[0]}"'
            else:  # C/C++
                output_file = os.path.splitext(file_path)[0] + '.exe'
                compile_cmd = f'g++ "{file_path}" -o "{output_file}"'
                run_cmd = f'"{output_file}"'
            
            # Type compile command
            pyautogui.write(compile_cmd)
            pyautogui.press('enter')
            time.sleep(2)
            
            # Type run command
            pyautogui.write(run_cmd)
        else:
            # For interpreted languages
            command = f'{run_command} "{file_path}"'
            pyautogui.write(command)
        
        pyautogui.press('enter')
        
        return f"✅ Running {extension} file: {file_path}"
        
    except Exception as e:
        return f"❌ Error running file: {str(e)}"

