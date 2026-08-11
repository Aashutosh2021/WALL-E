import os
import platform
import subprocess
import asyncio
import logging
from typing import Literal
import ctypes
from livekit.agents import function_tool

logger = logging.getLogger(__name__)

@function_tool()
async def system_power_action(action: Literal["shutdown", "restart", "lock", "sleep", "hibernate"]) -> str:
    """
    Advanced system power management across Windows/Linux/MacOS.
    
    Args:
        action: Power action to perform:
            - "shutdown": Powers off system completely
            - "restart": Reboots system
            - "lock": Locks workstation/screen
            - "sleep": Puts system to sleep
            - "hibernate": Hibernates system (Windows only)
            
    Returns:
        str: Action confirmation in Hindi/English with safety warnings
        
    Security:
        - Requires admin privileges for shutdown/restart
        - Confirmation recommended for destructive actions
    """
    try:
        logger.info(f"🔧 Power action requested: {action}")
        
        system = platform.system()
        action_messages = {
            "shutdown": "सिस्टम शटडाउन किया जा रहा है... ⚠️ सभी अनसेव्ड डेटा खो जाएगा!",
            "restart": "सिस्टम रीस्टार्ट किया जा रहा है... 🔄",
            "lock": "स्क्रीन लॉक की गई है। 🔒",
            "sleep": "सिस्टम स्लीप मोड में जा रहा है... 😴",
            "hibernate": "सिस्टम हाइबरनेट मोड में जा रहा है... 🐻"
        }
        
        if action == "shutdown":
            if system == "Windows":
                # Graceful shutdown with timeout
                await asyncio.to_thread(os.system, "shutdown /s /t 3 /c \"Nova Assistant: System shutting down in 3 seconds\"")
                return f"✅ {action_messages['shutdown']} (3 सेकंड में)"
            
            elif system == "Linux":
                # Immediate shutdown for Linux
                await asyncio.to_thread(os.system, "shutdown -h now")
                return f"✅ {action_messages['shutdown']}"
            
            elif system == "Darwin":  # macOS
                await asyncio.to_thread(os.system, "sudo shutdown -h now")
                return f"✅ {action_messages['shutdown']}"
        
        elif action == "restart":
            if system == "Windows":
                await asyncio.to_thread(os.system, "shutdown /r /t 3 /c \"Nova Assistant: System restarting in 3 seconds\"")
                return f"✅ {action_messages['restart']} (3 सेकंड में)"
            
            elif system == "Linux":
                await asyncio.to_thread(os.system, "reboot")
                return f"✅ {action_messages['restart']}"
            
            elif system == "Darwin":
                await asyncio.to_thread(os.system, "sudo shutdown -r now")
                return f"✅ {action_messages['restart']}"
        
        elif action == "lock":
            if system == "Windows":
                try:
                    # Method 1: Direct Windows API
                    await asyncio.to_thread(ctypes.windll.user32.LockWorkStation)
                    return f"✅ {action_messages['lock']}"
                except Exception as e:
                    # Method 2: Fallback using rundll32
                    await asyncio.to_thread(os.system, "rundll32.exe user32.dll,LockWorkStation")
                    return f"✅ {action_messages['lock']}"
            
            elif system == "Linux":
                try:
                    # Try multiple Linux locking methods
                    commands = [
                        ["gnome-screensaver-command", "-l"],  # GNOME
                        ["dm-tool", "lock"],  # LightDM
                        ["loginctl", "lock-session"],  # systemd
                        ["xscreensaver-command", "-lock"],  # XScreenSaver
                    ]
                    
                    for cmd in commands:
                        try:
                            result = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, timeout=5)
                            if result.returncode == 0:
                                return f"✅ {action_messages['lock']}"
                        except:
                            continue
                    
                    # Final fallback
                    await asyncio.to_thread(os.system, "xdg-screensaver lock")
                    return f"✅ {action_messages['lock']}"
                    
                except Exception as e:
                    logger.warning(f"Linux lock fallback: {e}")
                    return f"✅ {action_messages['lock']} (बेसिक मोड)"
            
            elif system == "Darwin":  # macOS
                await asyncio.to_thread(os.system, "pmset displaysleepnow")
                return f"✅ {action_messages['lock']}"
        
        elif action == "sleep":
            if system == "Windows":
                await asyncio.to_thread(os.system, "rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
                return f"✅ {action_messages['sleep']}"
            
            elif system == "Linux":
                await asyncio.to_thread(os.system, "systemctl suspend")
                return f"✅ {action_messages['sleep']}"
            
            elif system == "Darwin":
                await asyncio.to_thread(os.system, "pmset sleepnow")
                return f"✅ {action_messages['sleep']}"
        
        elif action == "hibernate":
            if system == "Windows":
                await asyncio.to_thread(os.system, "shutdown /h")
                return f"✅ {action_messages['hibernate']}"
            else:
                return "❌ हाइबरनेशन सिर्फ Windows सिस्टम पर उपलब्ध है।"
        
        return f"❌ अज्ञात एक्शन: {action}"
        
    except PermissionError:
        logger.error("Permission denied for power action")
        return "❌ इस एक्शन के लिए एडमिन अधिकार चाहिए। कृपया एडमिनिस्ट्रेटर के रूप में रन करें।"
    
    except Exception as e:
        logger.error(f"Power action failed: {e}")
        return f"❌ {action} करने में समस्या आई: {str(e)}"


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



