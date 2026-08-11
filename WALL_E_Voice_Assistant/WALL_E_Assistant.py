"""
WALL-E AI Companion Robot - Realtime Speech-to-Speech (STS) Agent
Full Realtime Audio Streaming + Automatic OLED Eyes Sync + Motor Controls
"""

import asyncio
import os
import sys
import gc
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =========================
# LIVEKIT IMPORTS
# =========================
from livekit import agents
from livekit.agents import Agent, AgentSession, RoomInputOptions
from livekit.plugins import google, noise_cancellation
from livekit.plugins.google.realtime import RealtimeModel

# Import Prompts & Tools
from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
from tools import (
    send_uart_command,
    see_object,
    move_robot,
    get_weather,
    get_time_info,
    search_web
)

# =========================
# WALL-E REALTIME STS AGENT
# =========================
class WalleRealtimeAgent(Agent):
    def __init__(self) -> None:
        # All WALL-E active tools
        self._tools_list = [
            send_uart_command,
            see_object,
            move_robot,
            get_weather,
            get_time_info,
            search_web
        ]

        # Initialize base Agent with Gemini Realtime Audio Model
        super().__init__(
            instructions=self._build_instructions(),
            tools=self._tools_list,
            llm=RealtimeModel(
                model="gemini-2.5-flash-native-audio-preview-12-2025",
                voice="Charon",
                temperature=0.8,
                max_output_tokens=1024,
            ),
        )

        self._current_session: Optional[AgentSession] = None
        print(f"✅ WALL-E Realtime STS initialized with {len(self._tools_list)} tools")

    def set_session(self, session: AgentSession) -> None:
        """Store active session reference"""
        self._current_session = session
        print("🔔 Session reference connected to WALL-E Brain")

    def _build_instructions(self) -> str:
        return "\n".join([
            AGENT_INSTRUCTION,
            "You are WALL-E, an affectionate, snappy, mini companion robot built by Aashutosh.",
            "Always respond in short, conversational sentences (1-3 sentences maximum) for natural speech flow.",
            "You have direct control over hardware motors and camera vision using tools.",
            "Execute tools immediately when asked to move, look, or check information."
        ])

    # ==========================================
    # LIFECYCLE EVENTS (UART EXPRESSIONS SYNC)
    # ==========================================
    async def on_tool_call_start(self, tool_call):
        """Trigger Thinking Eyes when tool execution starts"""
        print(f"🔧 [TOOL START] Executing: {tool_call.function_info.name}")
        send_uart_command("EYES_THINKING")
        return await super().on_tool_call_start(tool_call)

    async def on_tool_call_end(self, tool_call, result):
        """Trigger Normal Eyes when tool completes"""
        print(f"🔧 [TOOL END] Finished: {tool_call.function_info.name}")
        send_uart_command("EYES_NORMAL")
        return await super().on_tool_call_end(tool_call, result)

    async def on_user_turn_completed(self, turn_ctx, new_message):
        """Process user speech turn completion"""
        user_text = turn_ctx.user_message.text_content if turn_ctx.user_message else ""
        assistant_text = new_message.text_content if new_message else ""

        if user_text:
            print(f"🗣️ User: {user_text}")
        if assistant_text:
            print(f"🤖 WALL-E: {assistant_text}")

        # Trigger eyes back to normal after speaking finishes
        send_uart_command("EYES_NORMAL")
        return await super().on_user_turn_completed(turn_ctx, new_message)


# =========================
# ENTRYPOINT FUNCTION
# =========================
async def entrypoint(ctx: agents.JobContext):
    print("🤖 Booting WALL-E Realtime AI Engine...")

    # Hardware Startup Signal
    send_uart_command("EYES_NORMAL")

    agent = WalleRealtimeAgent()
    session = AgentSession()

    # Start LiveKit Session with Audio Noise Cancellation
    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            video_enabled=False,
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    agent.set_session(session)

    # Connect to room
    await ctx.connect()

    # Initial Welcome Greeting
    send_uart_command("EYES_TALKING")
    await session.generate_reply(instructions=SESSION_INSTRUCTION)
    send_uart_command("EYES_NORMAL")

    print("🔥 WALL-E Live Speech-to-Speech is ONLINE & LISTENING!")

    try:
        await asyncio.Future()  # Keep alive loop
    except asyncio.CancelledError:
        print("🛑 WALL-E Engine Shutting Down...")
        send_uart_command("STOP")
        send_uart_command("EYES_NORMAL")


# =========================
# CLI RUNNER
# =========================
if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))