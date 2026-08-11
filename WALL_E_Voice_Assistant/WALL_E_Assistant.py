"""
WALL-E AI Companion Robot - Pure Voice Conversation Agent
Pure speaking & listening voice assistant (No GUI, No Tools, No Bloat)
"""

import os
import sys
import gc
import asyncio
import logging

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import livekit.agents as agents
from livekit.agents import Agent, AgentSession, WorkerOptions, cli as agents_cli
from livekit.plugins import google, noise_cancellation
try:
    from livekit.plugins.google.realtime import RealtimeModel
    REALTIME_AVAILABLE = True
except ImportError:
    REALTIME_AVAILABLE = False

from prompts import AGENT_INSTRUCTION
from tools import send_uart_command


def set_eye_state(state: str):
    """Sends eye animation state command to ESP32 over UART serial link."""
    send_uart_command(state)


class Assistant(Agent):
    def __init__(self) -> None:
        # Pure conversation mode (No tools)
        llm_engine = (
            RealtimeModel(
                model="gemini-2.5-flash",
                voice="Puck",
                temperature=0.7,
            )
            if REALTIME_AVAILABLE
            else google.LLM(model="gemini-2.5-flash")
        )

        super().__init__(
            instructions=AGENT_INSTRUCTION,
            tools=[],  # Pure conversation mode (No extra tools or bloat)
            llm=llm_engine,
        )


async def entrypoint(ctx: agents.JobContext):
    logger.info("🤖 Connecting to LiveKit Room for WALL-E Pure Voice Conversation Agent...")
    await ctx.connect()

    set_eye_state("EYES_NORMAL")

    assistant = Assistant()

    @assistant.on("user_speech_started")
    def _on_user_listening():
        set_eye_state("EYES_LISTEN")

    @assistant.on("agent_thinking")
    def _on_agent_thinking():
        set_eye_state("EYES_THINKING")

    @assistant.on("agent_speech_started")
    def _on_agent_speaking():
        set_eye_state("EYES_TALKING")

    @assistant.on("agent_speech_stopped")
    def _on_agent_idle():
        set_eye_state("EYES_NORMAL")
        gc.collect()

    session = AgentSession(
        assistant=assistant,
        noise_cancellation=noise_cancellation.BVNC(),
    )

    await session.start(room=ctx.room)
    logger.info("✅ WALL-E Pure Voice Conversation Agent is LIVE & READY!")


if __name__ == "__main__":
    agents_cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
