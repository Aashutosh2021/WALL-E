import asyncio
import os
import time
from datetime import datetime
from typing import List, Optional

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any

# Fix dotenv parsing issue first
def fix_dotenv_file():
    """Fix malformed .env file"""
    env_path = Path('.env')
    if env_path.exists():
        try:
            with open(env_path, 'r') as f:
                lines = f.readlines()
            
            # Remove or fix line 8 if it's problematic
            if len(lines) >= 8:
                # Common issues: missing quotes, incorrect format
                line_8 = lines[7].strip()
                if '=' in line_8:
                    key, value = line_8.split('=', 1)
                    # Ensure proper formatting
                    if not (value.startswith('"') and value.endswith('"')) and not value.isalnum():
                        lines[7] = f'{key}=""\n'
            
            # Write back fixed content
            with open(env_path, 'w') as f:
                f.writelines(lines)
                
        except Exception as e:
            print(f"⚠️ Could not fix .env file: {e}")
            # Create fresh .env if corrupted
            with open(env_path, 'w') as f:
                f.write('# MARK AI Environment Variables\n')

# Fix .env file before loading
fix_dotenv_file()

# Now load dotenv properly
from dotenv import load_dotenv
load_dotenv()


from livekit import rtc
import livekit.agents as agents
from livekit.agents import Agent, AgentSession, RoomInputOptions, get_job_context
from livekit.plugins import noise_cancellation, google
# from livekit.plugins import openai
from livekit.agents.llm.chat_context import ChatContext

# Import prompts and tools
from prompts import (
    AGENT_INSTRUCTION,
    SESSION_INSTRUCTION,
    AGENT_INSTRUCTION_FOR_TOOLS,
    SESSION_INSTRUCTION_2
)
from Tools.manage_windows import manage_window,list_windows
from Tools.search_web import search_web
from Tools.send_whatsapp_message import send_whatsapp_message
from Tools.system_power_action import system_power_action
from Tools.type_user_message_auto import type_user_message_auto
from Tools.write_in_notepad import write_in_notepad
from Tools.desktop_control import desktop_control
from Tools.scroll_content import scroll_content
from Tools.code_handler import fix_code_error
from Tools.file_searching import universal_file_opener
from Tools.press_key import press_key,use_smart_clipboard
from Tools.open_app import open_app
from Tools.scan_system_for_viruses import scan_system_for_viruses
from Tools.time_volume_bright import control_screen_brightness,control_system_volume,get_time_info,get_weather,get_system_info_deep
from Tools.multi_task import execute_multi_task
from Tools.generate_ai_image import generate_ai_image
from Tools.code_generator import generate_and_type_code,run_file_in_vscode
from Tools.news_provider import get_top_news
from Tools.youtube_videos import play_media
from Tools.reminder import set_reminder, view_reminders, cancel_reminder
from Tools.screen_short import screen_short
from Tools.pdf_reader import process_document_query
from Tools.send_media_whatsapp import send_media_to_whatsapp




import asyncio
import os
import time
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path

class Assistant(Agent):
    def __init__(self) -> None:
        # Set assistant instance for tools
        import tools
        tools.assistant_instance = self

        # Feature mapping for different variants
        FEATURE_MAP = {
            "core": [
                search_web,
                get_time_info,
                open_app,
                get_system_info_deep,
            ],
            "pro": [
                get_weather,
                manage_window,
                list_windows,
                play_media,
                press_key,
                write_in_notepad,
                desktop_control,
                scroll_content,
                send_whatsapp_message,
                use_smart_clipboard,
                universal_file_opener,
                get_system_info_deep,
                system_power_action,
                get_top_news,
                execute_multi_task,
                generate_and_type_code,
                run_file_in_vscode,
                screen_short
            ],
            "ultra": [
                search_web,
                get_time_info,
                open_app,
                get_system_info_deep,
                system_power_action,
                get_weather,
                manage_window,
                list_windows,
                play_media,
                press_key,
                type_user_message_auto,
                desktop_control,
                scan_system_for_viruses,
                send_whatsapp_message,
                write_in_notepad,
                use_smart_clipboard,
                control_system_volume,
                control_screen_brightness,
                execute_multi_task,
                generate_ai_image,
                generate_and_type_code,
                run_file_in_vscode,
                scroll_content,
                fix_code_error,
                universal_file_opener,
                get_top_news,
                set_reminder,  # ✅ Added reminder tools
                view_reminders,
                cancel_reminder,
                screen_short,
                process_document_query,
                send_media_to_whatsapp,
                
                
            ],
        }

        # Determine variant from environment
        variant = os.getenv("MARK_VARIANT", "core").lower()
        if variant not in FEATURE_MAP:
            print(f"[WARN] Unknown variant '{variant}', defaulting to core.")
            variant = "core"

        # Initialize only allowed tools
        allowed_tools = FEATURE_MAP[variant]
        self._tools = self._initialize_tools(allowed_tools)

        print(f"[INFO] Assistant initialized with variant: {variant} ({len(allowed_tools)} tools)")

        # Initialize agent with optimized configuration
        super().__init__(
            instructions=self._build_instructions(),
            llm=google.beta.realtime.RealtimeModel(    
                model="gemini-2.5-flash-native-audio-preview-12-2025",          
                voice="Charon",
                temperature=0.9,
                top_p=0.9,
                max_output_tokens=1024,   
            ),
            
            tools=self._tools,
        )
        
        # State tracking
        self._last_tool_used: Optional[str] = None
        self._last_tool_success: bool = False
        self._chat_log_path = "chat_log.txt"
        
        # 🔥 REMINDER SYSTEM
        self._reminders: Dict[str, Dict[str, Any]] = {}
        self._reminder_counter = 0
        self._reminder_task: Optional[asyncio.Task] = None
        self._current_session: Optional[Any] = None  # Store session reference

    def set_session(self, session):
        """Set the current session for sending reminders"""
        self._current_session = session
        print("🔔 Session reference set for reminders")

    def add_reminder(self, reminder_text: str, reminder_time: datetime, reminder_type: str = "message") -> str:
        """Add a new reminder to the system"""
        reminder_id = f"reminder_{self._reminder_counter}"
        self._reminder_counter += 1
        
        self._reminders[reminder_id] = {
            'text': reminder_text,
            'time': reminder_time,
            'type': reminder_type,
            'created': datetime.now()
        }
        
        print(f"🔔 Reminder added: {reminder_id} - {reminder_text} at {reminder_time}")
        
        # Start reminder monitoring if not already running
        if self._reminder_task is None or self._reminder_task.done():
            self._reminder_task = asyncio.create_task(self._monitor_reminders())
        
        return reminder_id

    def get_reminders(self) -> Dict[str, Dict[str, Any]]:
        """Get all active reminders"""
        return self._reminders.copy()

    def cancel_reminder(self, reminder_id: str) -> bool:
        """Cancel a specific reminder"""
        if reminder_id in self._reminders:
            del self._reminders[reminder_id]
            print(f"🔔 Reminder cancelled: {reminder_id}")
            return True
        return False

    async def _monitor_reminders(self):
        """Background task to monitor and trigger reminders"""
        print("🔔 Reminder monitoring started")
        
        while True:
            try:
                current_time = datetime.now()
                reminders_to_remove = []
                
                for reminder_id, reminder in self._reminders.items():
                    if current_time >= reminder['time']:
                        # Time to trigger reminder
                        await self._trigger_reminder(reminder_id, reminder)
                        reminders_to_remove.append(reminder_id)
                
                # Remove triggered reminders
                for reminder_id in reminders_to_remove:
                    if reminder_id in self._reminders:
                        del self._reminders[reminder_id]
                
                # Sleep for a short interval
                await asyncio.sleep(5)  # Check every 5 seconds
                
                # Stop if no reminders left
                if not self._reminders:
                    print("🔔 No active reminders, monitoring paused")
                    break
                    
            except Exception as e:
                print(f"🔔 Error in reminder monitoring: {e}")
                await asyncio.sleep(10)  # Longer sleep on error

    async def _trigger_reminder(self, reminder_id: str, reminder: Dict[str, Any]):
        """Trigger a reminder by sending message to user"""
        try:
            reminder_message = f"{reminder['text']} : यह रिमाइंडर यूजर ने तुम्हें याद दिलाने के लिए कहा था, तो यूजर को इसके बारे में याद दिलाएं।"
            print(f"🔔 Triggering reminder: {reminder_message}")
            
            # Use session's generate_reply to send reminder to user
            if self._current_session:
                await self._current_session.generate_reply(instructions=reminder_message)
                print(f"✅ Reminder sent successfully: {reminder['text']}")
            else:
                print("❌ No active session to send reminder")
            
            # Log the reminder trigger
            await self._log_conversation("System", f"Reminder triggered: {reminder['text']}")
            
        except Exception as e:
            print(f"🔔 Failed to trigger reminder {reminder_id}: {e}")

  

    def _initialize_tools(self, tools: List) -> List:
        """Validate and initialize tools with minimal overhead."""
        validated_tools = []
        for tool in tools:
            try:
                if not callable(tool):
                    raise ValueError(f"Tool {getattr(tool, '__name__', str(tool))} is not callable")
                
                # Add minimal metadata
                tool.metadata = {
                    'description': tool.__doc__.strip() if tool.__doc__ else f"Tool: {tool.__name__}",
                    'last_used': None,
                    'usage_count': 0
                }
                validated_tools.append(tool)
            except Exception as e:
                print(f"⚠️ Failed to initialize tool {getattr(tool, '__name__', str(tool))}: {str(e)}")
        
        return validated_tools

    def _build_instructions(self) -> str:
        """Construct optimized instruction set."""
        tool_descriptions = []
        for tool in self._tools:
            tool_name = tool.__name__
            tool_doc = tool.__doc__ if tool.__doc__ else "No description available"
            tool_descriptions.append(f"- {tool_name}: {tool_doc.strip()}")
        
        available_tools = "\n".join(tool_descriptions)
        
        return "\n".join([
            AGENT_INSTRUCTION,
            SESSION_INSTRUCTION,
            AGENT_INSTRUCTION_FOR_TOOLS,
            "You are a multilingual assistant capable of understanding and responding in multiple languages.",
            f"\nAvailable tools:\n{available_tools}",
            "\nWhen a user request requires tool usage, actively use the appropriate tool and provide feedback about the action taken."
        ])

    async def on_tool_call_start(self, tool_call):
        """Handle tool call start event."""
        print(f"🔧 Starting tool call: {tool_call.function_info.name}")
        self._last_tool_used = tool_call.function_info.name
        return await super().on_tool_call_start(tool_call)

    async def on_tool_call_end(self, tool_call, result):
        """Handle tool call completion."""
        success = result and not isinstance(result, Exception)
        self._last_tool_success = success
        
        print(f"🔧 Tool call completed: {tool_call.function_info.name} - {'✅ Success' if success else '❌ Failed'}")
        return await super().on_tool_call_end(tool_call, result)

    async def on_user_turn_completed(self, turn_ctx, new_message):
        """Handle post-processing after user turn completion."""
        user_message = turn_ctx.user_message.text_content if turn_ctx.user_message else "[no user input]"
        assistant_message = new_message.text_content if new_message else "[no assistant reply]"

        # Log conversation
        print(f"\n🗣️ USER: {user_message}")
        print(f"🤖 ASSISTANT: {assistant_message}")
        await self._log_conversation("User", user_message)
        await self._log_conversation("Assistant", assistant_message)

        # Update tool usage tracking
        if self._last_tool_used:
            for tool in self._tools:
                if tool.__name__ == self._last_tool_used:
                    tool.metadata['last_used'] = datetime.now()
                    tool.metadata['usage_count'] += 1
                    break

        return await super().on_user_turn_completed(turn_ctx, new_message)

    async def _log_conversation(self, sender: str, message: str) -> None:
        """Log conversation to file."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            with open(self._chat_log_path, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {sender}: {message}\n")
        except IOError as e:
            print(f"⚠️ Failed to log conversation: {str(e)}")

    async def send_periodic_welcome(self, session):
        """Send periodic welcome message every 10 minutes"""
        current_time = time.time()
        if current_time - self._last_periodic_message_time >= 30:  # 10 minutes = 600 seconds
            try:
                welcome_message = "Hello sir! 10 minutes have passed. Welcome! How can I assist you today?"
                await session.generate_reply(instructions=welcome_message)
                self._last_periodic_message_time = current_time
                print("🕐 Periodic welcome message sent")
            except Exception as e:
                print(f"⚠️ Failed to send periodic welcome message: {e}")


async def start_periodic_messaging(agent, session):
    """Start background task for periodic messaging"""
    while True:
        try:
            await agent.send_periodic_welcome(session)
            await asyncio.sleep(60)  # Check every minute
        except Exception as e:
            print(f"⚠️ Error in periodic messaging: {e}")
            await asyncio.sleep(60)


async def entrypoint(ctx: agents.JobContext):
    """Optimized main entry point for the agent."""
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(1, max_retries + 1):
        try:
            # Create agent and session
            agent = Assistant()
            session = AgentSession()
            
            # Start session with timeout
            await asyncio.wait_for(
                session.start(
                    room=ctx.room,
                    agent=agent,
                    room_input_options=RoomInputOptions(
                        video_enabled=False,
                        noise_cancellation=noise_cancellation.BVC(),
                    ),
                ),
                timeout=20.0
            )
            
            # 🔥 SET SESSION REFERENCE FOR REMINDERS
            agent.set_session(session)
            
            # Connect to room
            await ctx.connect()
            
            # Generate startup message
            if os.getenv("MARK_VARIANT", "core").lower() in ["ultra", "pro"]:
                await session.generate_reply(instructions=SESSION_INSTRUCTION_2)
            else:       
                await session.generate_reply(instructions=SESSION_INSTRUCTION_2)
            
            print("✅ Agent session started successfully with reminder system")
            
            # Keep the session alive - reminder system automatically runs in background
            try:
                await asyncio.Future()  # Run forever until cancelled
            except asyncio.CancelledError:
                print("🛑 Session cancelled")
            
            break
            
        except Exception as e:
            print(f"❌ Entrypoint failed on attempt {attempt}: {e}")
            if attempt < max_retries:
                await asyncio.sleep(retry_delay)
            else:
                raise

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))

