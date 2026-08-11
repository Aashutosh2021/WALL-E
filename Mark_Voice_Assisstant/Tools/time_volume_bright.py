import time
import logging
from datetime import datetime
from typing import Optional
from livekit.agents import function_tool
import asyncio
import aiohttp
from livekit.agents import RunContext
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    import screen_brightness_control as sbc
    BRIGHTNESS_AVAILABLE = True
except ImportError:
    BRIGHTNESS_AVAILABLE = False
    logger.warning("screen_brightness_control not available. Install with: pip install screen-brightness-control")

try:
    import pycaw.pycaw as pycaw
    VOLUME_AVAILABLE = True
except ImportError:
    VOLUME_AVAILABLE = False
    logger.warning("pycaw not available. Install with: pip install pycaw")


@function_tool()
async def get_time_info(context: RunContext) -> str:
    """
    Returns system current time in HH:MM AM/PM format.
    """
    from datetime import datetime

    try:
        now = datetime.now()
        current_time = now.strftime("%I:%M %p")
        return f"⏰ Current Time: {current_time}"
    
    except Exception as e:
        return f"❌ Error: {e}"


@function_tool()
async def control_screen_brightness(
    brightness_level: int, 
    prompt: Optional[str] = None,
    gradual_change: bool = False
) -> str:
    """
    Advanced screen brightness control with gradual adjustment option.
    
    Args:
        brightness_level: Integer (0-100) representing desired brightness
        prompt: Optional user request string
        gradual_change: If True, gradually changes brightness
    
    Returns:
        str: Confirmation message
    """
    if not BRIGHTNESS_AVAILABLE:
        return "❌ Brightness control not available. Install screen-brightness-control"
    
    try:
        if not 0 <= brightness_level <= 100:
            return "⚠️ Error: Brightness level must be between 0 and 100."
        
        current_brightness = sbc.get_brightness()[0]
        
        if gradual_change and abs(current_brightness - brightness_level) > 20:
            # Gradual brightness change
            steps = abs(current_brightness - brightness_level) // 10
            step_direction = 1 if brightness_level > current_brightness else -1
            
            for step in range(1, steps + 1):
                intermediate = current_brightness + (step * step_direction * 10)
                intermediate = max(0, min(100, intermediate))
                sbc.set_brightness(intermediate)
                await asyncio.sleep(0.1)
        
        # Set final brightness
        sbc.set_brightness(brightness_level)
        
        # Get monitor info
        monitors = sbc.list_monitors()
        monitor_info = f" ({monitors[0]})" if monitors else ""
        
        return f"✅ Screen brightness{monitor_info} set to {brightness_level}% " + \
               f"(from {current_brightness}%)"
               
    except Exception as e:
        logger.error(f"Error in control_screen_brightness: {e}")
        return f"❌ Failed to adjust brightness: {str(e)}"

@function_tool()
async def control_system_volume(prompt: str, volume_level: int) -> str:
    """
    Adjusts system volume using simple Windows commands.
    """
    try:
        if not 0 <= volume_level <= 100:
            return "⚠️ Error: Volume level must be between 0 and 100."
        
        import subprocess
        
        # Simple command that often works
        cmd = f"""
        $wsh = New-Object -ComObject WScript.Shell
        $wsh.SendKeys([char]173)  # Mute
        Start-Sleep -Milliseconds 200
        $wsh.SendKeys([char]174)  # Volume Down 50 times to ensure 0%
        1..50 | % {{ $wsh.SendKeys([char]174); Start-Sleep -Milliseconds 10 }}
        Start-Sleep -Milliseconds 200
        # Now press Volume Up exact number of times
        $presses = {volume_level} / 2
        1..$presses | % {{ $wsh.SendKeys([char]175); Start-Sleep -Milliseconds 30 }}
        """
        
        result = subprocess.run(
            ["powershell", "-Command", cmd],
            capture_output=True,
            text=True,
            timeout=15
        )
        
        return f"✅ System volume has been set to {volume_level}%."
        
    except Exception as e:
        return f"❌ Failed to adjust volume: {str(e)}"

@function_tool()
async def get_current_volume() -> str:
    """
    Get current system volume level.
    
    Returns:
        str: Current volume information
    """
    if not VOLUME_AVAILABLE:
        return "❌ Volume control not available"
    
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        
        audio = pycaw.AudioUtilities()
        speaker = audio.GetSpeakers()
        interface = speaker.Activate(
            pycaw.IAudioEndpointVolume._iid_, 
            pycaw.CLSCTX_ALL, 
            None
        )
        volume = cast(interface, POINTER(pycaw.IAudioEndpointVolume))
        
        current_volume = volume.GetMasterVolumeLevelScalar()
        current_volume_percent = int(current_volume * 100)
        is_muted = volume.GetMute()
        
        return f"🔊 Current volume: {current_volume_percent}% {'(Muted)' if is_muted else ''}"
        
    except Exception as e:
        logger.error(f"Error in get_current_volume: {e}")
        return f"❌ Failed to get volume: {str(e)}"

@function_tool()
async def get_system_status() -> str:
    """
    Get current system status including time, brightness and volume.
    
    Returns:
        str: Comprehensive system status report
    """
    try:
        # Get time info
        time_info = await get_time_info(language="english")
        
        # Get brightness info
        brightness_info = "N/A"
        if BRIGHTNESS_AVAILABLE:
            try:
                current_brightness = sbc.get_brightness()[0]
                brightness_info = f"{current_brightness}%"
            except:
                brightness_info = "Unavailable"
        
        # Get volume info  
        volume_info = "N/A"
        if VOLUME_AVAILABLE:
            try:
                from ctypes import cast, POINTER
                from comtypes import CLSCTX_ALL
                
                audio = pycaw.AudioUtilities()
                speaker = audio.GetSpeakers()
                interface = speaker.Activate(
                    pycaw.IAudioEndpointVolume._iid_, 
                    pycaw.CLSCTX_ALL, 
                    None
                )
                volume = cast(interface, POINTER(pycaw.IAudioEndpointVolume))
                
                current_volume = volume.GetMasterVolumeLevelScalar()
                current_volume_percent = int(current_volume * 100)
                is_muted = volume.GetMute()
                volume_info = f"{current_volume_percent}% {'(Muted)' if is_muted else ''}"
            except:
                volume_info = "Unavailable"
        
        status_report = (
            "🖥️ SYSTEM STATUS REPORT\n"
            "────────────────────\n"
            f"{time_info}\n"
            f"💡 Screen Brightness: {brightness_info}\n"
            f"🔊 System Volume: {volume_info}\n"
            "────────────────────"
        )
        
        return status_report
        
    except Exception as e:
        logger.error(f"Error in get_system_status: {e}")
        return "❌ Error generating system status report"

# Utility functions for external use
def get_available_functions():
    """Return list of available function tools"""
    functions = [get_time_info, control_screen_brightness, control_system_volume, get_system_status]
    
    # Only include additional volume functions if available
    if VOLUME_AVAILABLE:
        functions.append(get_current_volume)
    
    return functions

async def demo():
    """Demo all functions"""
    print("=== System Controller Demo ===")
    
    # Time info
    time_info = await get_time_info()
    print(f"Time Info: {time_info}")
    
    # System status
    status = await get_system_status()
    print(f"System Status: {status}")
    
    # Test brightness (set to 80%)
    if BRIGHTNESS_AVAILABLE:
        brightness_result = await control_screen_brightness(80)
        print(f"Brightness: {brightness_result}")
    
    # Test volume (set to 70%)
    if VOLUME_AVAILABLE:
        volume_result = await control_system_volume("set volume to 70", 70)
        print(f"Volume: {volume_result}")
        
        current_vol = await get_current_volume()
        print(f"Current Volume: {current_vol}")




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
async def get_system_info_deep() -> str:
    """
    Provides deep system diagnostics including:
    - CPU (per-core, freq, temp)
    - RAM full breakdown
    - Storage per-drive
    - Network (local IP, external IP, ping test)
    - Battery deep info
    - OS details
    - Process count
    - Uptime
    """

    import psutil
    import platform
    import shutil
    import socket
    import requests
    import time
    from datetime import datetime, timedelta

    try:
        # ---------- SYSTEM UPTIME ----------
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot_time
        uptime_str = str(timedelta(seconds=int(uptime.total_seconds())))

        # ---------- CPU DETAILS ----------
        cpu_percent_total = psutil.cpu_percent(interval=1)
        cpu_per_core = psutil.cpu_percent(interval=1, percpu=True)
        cpu_freq = psutil.cpu_freq()
        cpu_temp = "N/A"

        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for name, entries in temps.items():
                    if entries:
                        cpu_temp = f"{entries[0].current}°C"
                        break
        except:
            cpu_temp = "N/A"

        # ---------- RAM DETAILS ----------
        ram = psutil.virtual_memory()
        ram_total = round(ram.total / (1024**3), 2)
        ram_used = round(ram.used / (1024**3), 2)
        ram_free = round(ram.available / (1024**3), 2)

        # ---------- STORAGE (ALL DRIVES) ----------
        drives_info = ""
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                drives_info += (
                    f"\n📁 Drive {part.device}\n"
                    f"   • Total: {usage.total // (2**30)} GB\n"
                    f"   • Used: {usage.used // (2**30)} GB\n"
                    f"   • Free: {usage.free // (2**30)} GB\n"
                )
            except:
                continue

        # ---------- NETWORK ----------
        # Internal IP
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
        except:
            local_ip = "N/A"

        # External IP
        try:
            external_ip = requests.get("https://api.ipify.org").text
        except:
            external_ip = "N/A"

        # Ping test
        import subprocess, platform as pf
        ping_cmd = ["ping", "-n" if pf.system() == "Windows" else "-c", "1", "8.8.8.8"]
        try:
            ping_result = subprocess.run(ping_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            ping_status = "Online ✔️" if ping_result.returncode == 0 else "Offline ❌"
        except:
            ping_status = "N/A"

        # ---------- BATTERY ----------
        battery = psutil.sensors_battery()
        if battery:
            battery_status = (
                f"{battery.percent}% | "
                f"{'Charging ⚡' if battery.power_plugged else 'On Battery 🔋'} | "
                f"Time Left: {round(battery.secsleft / 60)} min" if battery.secsleft != psutil.POWER_TIME_UNLIMITED else "∞"
            )
        else:
            battery_status = "N/A"

        # ---------- PROCESS COUNT ----------
        process_count = len(psutil.pids())

        # ---------- OS INFO ----------
        os_name = platform.system()
        os_version = platform.version()
        device_name = platform.node()

        # ---------- FINAL OUTPUT ----------
        return (
            f"🖥️ **Deep System Diagnostics**\n"
            f"📌 Device: {device_name}\n"
            f"🕒 Uptime: {uptime_str}\n\n"

            f"🔥 **CPU**\n"
            f"   • Total Usage: {cpu_percent_total}%\n"
            f"   • Temperature: {cpu_temp}\n"
            f"   • Frequency: {cpu_freq.current} MHz\n"
            f"   • Per-Core Usage: {cpu_per_core}\n\n"

            f"🧠 **Memory (RAM)**\n"
            f"   • Total: {ram_total} GB\n"
            f"   • Used: {ram_used} GB\n"
            f"   • Free: {ram_free} GB\n"
            f"   • Usage: {ram.percent}%\n\n"

            f"💾 **Storage**\n"
            f"{drives_info}\n"

            f"🌐 **Network**\n"
            f"   • Local IP: {local_ip}\n"
            f"   • External IP: {external_ip}\n"
            f"   • Internet Status: {ping_status}\n\n"

            f"🔋 **Battery**\n"
            f"   • {battery_status}\n\n"

            f"🧩 **OS**\n"
            f"   • {os_name} ({os_version})\n\n"

            f"⚙️ **Processes Running:** {process_count}"
        )

    except Exception as e:
        return f"❌ Error: {str(e)}"
