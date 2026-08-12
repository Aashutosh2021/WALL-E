"""
WALL-E AI Companion Robot - Headless Terminal Entrypoint
Zero GUI overhead, ultra-lightweight for Raspberry Pi 3B+ (1GB RAM)
"""

import sys
import asyncio
import logging

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S"
)

if __name__ == "__main__":
    load_dotenv(override=True)
    print("==================================================")
    print("🤖 WALL-E AI Companion Robot - Terminal Launcher")
    print("==================================================")

    from walle_direct_gemini import run_direct_gemini_robot
    print("⚡ Starting Direct Gemini Live WebSocket Client (~300ms Latency)...")
    try:
        asyncio.run(run_direct_gemini_robot())
    except KeyboardInterrupt:
        print("\n🛑 WALL-E Stopped.")
