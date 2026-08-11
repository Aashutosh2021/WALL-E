import asyncio
import re
from datetime import datetime, timedelta
from livekit.agents import function_tool
from typing import Dict, Any

def parse_schedule_time(time_str: str) -> datetime:
    """Parse schedule time string to datetime"""
    time_str = time_str.lower().strip()
    now = datetime.now()
    
    # Today at specific time
    time_match = re.search(r'(\d{1,2}):(\d{2})\s*(am|pm)?', time_str)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
        am_pm = time_match.group(3)
        
        # Convert to 24-hour format
        if am_pm == 'pm' and hour < 12:
            hour += 12
        elif am_pm == 'am' and hour == 12:
            hour = 0
            
        schedule_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # If time already passed today, schedule for tomorrow
        if schedule_time < now:
            schedule_time += timedelta(days=1)
            
        return schedule_time
    
    # After X minutes/hours
    time_patterns = [
        (r'after\s*(\d+)\s*minutes?', 60),
        (r'after\s*(\d+)\s*hours?', 3600),
        (r'in\s*(\d+)\s*minutes?', 60),
        (r'in\s*(\d+)\s*hours?', 3600),
    ]
    
    for pattern, multiplier in time_patterns:
        match = re.search(pattern, time_str)
        if match:
            seconds = int(match.group(1)) * multiplier
            return now + timedelta(seconds=seconds)
    
    # Tomorrow at specific time
    if 'tomorrow' in time_str:
        time_match = re.search(r'(\d{1,2}):(\d{2})\s*(am|pm)?', time_str)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2))
            am_pm = time_match.group(3)
            
            if am_pm == 'pm' and hour < 12:
                hour += 12
            elif am_pm == 'am' and hour == 12:
                hour = 0
                
            schedule_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            schedule_time += timedelta(days=1)
            return schedule_time
    
    return None

@function_tool()
async def schedule_task(
    task_description: str,
    schedule_time: str,
    tool_name: str,
    tool_parameters: str = ""
) -> str:
    """
    Schedule a task to be executed automatically at specific time.
    
    Examples:
    - "Schedule to open browser at 3:00 PM"
    - "Set task to check weather tomorrow at 9:00 AM" 
    - "After 30 minutes, search for AI news"
    - "At 6:00 PM, send WhatsApp message to mom"
    
    Args:
        task_description: What task to perform
        schedule_time: When to execute (e.g., "3:00 PM", "after 30 minutes", "tomorrow at 9:00 AM")
        tool_name: Which tool to execute (e.g., "open_app", "search_web", "send_whatsapp_message")
        tool_parameters: Parameters for the tool (e.g., "browser", "AI news", "message to mom")
    """
    try:
        # Parse schedule time
        scheduled_datetime = parse_schedule_time(schedule_time)
        if not scheduled_datetime:
            return "❌ Could not understand the schedule time. Please specify like '3:00 PM' or 'after 30 minutes'"
        
        # Store task in agent's scheduler system
        from tools import assistant_instance
        if hasattr(assistant_instance, 'add_scheduled_task'):
            task_id = assistant_instance.add_scheduled_task(
                task_description=task_description,
                schedule_time=scheduled_datetime,
                tool_name=tool_name,
                tool_parameters=tool_parameters
            )
            
            return (f"✅ Task scheduled successfully!\n"
                   f"📝 Task: {task_description}\n"
                   f"🛠️ Tool: {tool_name}\n" 
                   f"⏰ Time: {scheduled_datetime.strftime('%Y-%m-%d %H:%M:%S')}\n"
                   f"🆔 ID: {task_id}")
        else:
            return "❌ Task scheduler not available"
            
    except Exception as e:
        return f"❌ Failed to schedule task: {str(e)}"

@function_tool()
async def view_scheduled_tasks() -> str:
    """View all scheduled tasks"""
    try:
        from tools import assistant_instance
        if hasattr(assistant_instance, 'get_scheduled_tasks'):
            tasks = assistant_instance.get_scheduled_tasks()
            if not tasks:
                return "📋 No scheduled tasks"
            
            task_list = []
            for task_id, task in tasks.items():
                time_left = task['schedule_time'] - datetime.now()
                hours, remainder = divmod(int(time_left.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                
                task_list.append(
                    f"🆔 {task_id}\n"
                    f"📝 {task['task_description']}\n"
                    f"🛠️ Tool: {task['tool_name']}\n"
                    f"⏰ Time: {task['schedule_time'].strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"⏳ Time left: {hours}h {minutes}m {seconds}s\n"
                )
            
            return "📋 Scheduled Tasks:\n\n" + "\n".join(task_list)
        else:
            return "❌ Task scheduler not available"
            
    except Exception as e:
        return f"❌ Failed to view scheduled tasks: {str(e)}"

@function_tool()
async def cancel_scheduled_task(task_id: str) -> str:
    """Cancel a specific scheduled task by ID"""
    try:
        from tools import assistant_instance
        if hasattr(assistant_instance, 'cancel_scheduled_task'):
            success = assistant_instance.cancel_scheduled_task(task_id)
            if success:
                return f"✅ Task {task_id} cancelled successfully"
            else:
                return f"❌ Task {task_id} not found"
        else:
            return "❌ Task scheduler not available"
            
    except Exception as e:
        return f"❌ Failed to cancel task: {str(e)}"