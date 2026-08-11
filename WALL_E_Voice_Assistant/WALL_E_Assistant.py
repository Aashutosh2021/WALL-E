import os
import sys
import gc
import asyncio
import logging

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from pathlib import Path
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

from livekit import rtc
import livekit.agents as agents
from livekit.agents import Agent, AgentSession, WorkerOptions, cli as agents_cli
from livekit.plugins import google, noise_cancellation

from prompts import AGENT_INSTRUCTION
from tools import (
    move_robot,
    see_object,
    get_weather,
    get_time_info,
    search_web,
    play_media,
    send_uart_command
)

def set_eye_state(state: str):
    """Sends eye animation state command to ESP32 over UART serial link."""
    send_uart_command(state)


class Assistant(Agent):
    def __init__(self) -> None:
        walle_tools = [
            move_robot,
            see_object,
            get_weather,
            get_time_info,
            search_web,
            play_media,
        ]

        super().__init__(
            instructions=AGENT_INSTRUCTION,
            tools=walle_tools,
            llm=google.LLM(model="gemini-2.5-flash"),
        )


async def entrypoint(ctx: agents.JobContext):
    logger.info("🤖 Connecting to LiveKit Room for WALL-E AI Companion Robot...")
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
    logger.info("✅ WALL-E AI Companion Robot Session Started!")


if __name__ == "__main__":
    agents_cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
