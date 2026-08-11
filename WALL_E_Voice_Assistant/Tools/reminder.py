import asyncio
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import re
from livekit.agents import function_tool

@function_tool()
async def set_reminder(
    reminder_text: str,
    time_duration: str = "10 minutes",
    reminder_type: str = "message"
) -> str:
    """
    Set a reminder for later. 
    Examples: 
    - "10 minutes later remind me about meeting"
    - "after 1 hour call mom"
    - "set reminder for 5 pm today"
    - "tomorrow at 9 am meeting reminder"
    
    Args:
        reminder_text: What to remind about
        time_duration: When to remind (e.g., "10 minutes", "1 hour", "30 seconds")
        reminder_type: Type of reminder (message, alert, etc.)
    """
    try:
        # Parse time duration
        seconds = parse_time_duration(time_duration)
        if seconds <= 0:
            return "❌ Please provide a valid future time for the reminder"
        
        # Calculate reminder time
        reminder_time = datetime.now() + timedelta(seconds=seconds)
        
        # Store reminder in agent's reminder system
        from tools import assistant_instance
        if hasattr(assistant_instance, 'add_reminder'):
            reminder_id = assistant_instance.add_reminder(
                reminder_text=reminder_text,
                reminder_time=reminder_time,
                reminder_type=reminder_type
            )
            
            return f"✅ Reminder set successfully!\n📝 Reminder: {reminder_text}\n⏰ Time: {reminder_time.strftime('%Y-%m-%d %H:%M:%S')}\n🆔 ID: {reminder_id}"
        else:
            return "❌ Reminder system not available"
            
    except Exception as e:
        return f"❌ Failed to set reminder: {str(e)}"

def parse_time_duration(time_str: str) -> int:
    """Parse time duration string to seconds"""
    time_str = time_str.lower().strip()
    
    # Pattern matching for different time formats
    patterns = [
        (r'(\d+)\s*seconds?', 1),
        (r'(\d+)\s*minutes?', 60),
        (r'(\d+)\s*hours?', 3600),
        (r'(\d+)\s*days?', 86400),
        (r'(\d+)\s*weeks?', 604800),
    ]
    
    for pattern, multiplier in patterns:
        match = re.search(pattern, time_str)
        if match:
            return int(match.group(1)) * multiplier
    
    # Default to minutes if no unit specified
    match = re.search(r'(\d+)', time_str)
    if match:
        return int(match.group(1)) * 60  # Default to minutes
    
    return 0

@function_tool()
async def view_reminders() -> str:
    """View all active reminders"""
    try:
        from tools import assistant_instance
        if hasattr(assistant_instance, 'get_reminders'):
            reminders = assistant_instance.get_reminders()
            if not reminders:
                return "📋 No active reminders"
            
            reminder_list = []
            for reminder_id, reminder in reminders.items():
                time_left = reminder['reminder_time'] - datetime.now()
                hours, remainder = divmod(int(time_left.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                
                reminder_list.append(
                    f"🆔 {reminder_id}\n"
                    f"📝 {reminder['reminder_text']}\n"
                    f"⏰ {reminder['reminder_time'].strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"⏳ Time left: {hours}h {minutes}m {seconds}s\n"
                )
            
            return "📋 Active Reminders:\n\n" + "\n".join(reminder_list)
        else:
            return "❌ Reminder system not available"
            
    except Exception as e:
        return f"❌ Failed to view reminders: {str(e)}"

@function_tool()
async def cancel_reminder(reminder_id: str) -> str:
    """Cancel a specific reminder by ID"""
    try:
        from tools import assistant_instance
        if hasattr(assistant_instance, 'cancel_reminder'):
            success = assistant_instance.cancel_reminder(reminder_id)
            if success:
                return f"✅ Reminder {reminder_id} cancelled successfully"
            else:
                return f"❌ Reminder {reminder_id} not found"
        else:
            return "❌ Reminder system not available"
            
    except Exception as e:
        return f"❌ Failed to cancel reminder: {str(e)}"