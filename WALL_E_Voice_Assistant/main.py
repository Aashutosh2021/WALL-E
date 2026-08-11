"""
WALL-E AI Companion Robot - Headless Terminal Entrypoint
Zero GUI overhead, ultra-lightweight for Raspberry Pi 3B+ (1GB RAM)
"""

import os
import sys
import logging

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
from livekit.agents import WorkerOptions, cli as agents_cli
from WALL_E_Assistant import entrypoint

# Configure clean terminal logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S"
)

if __name__ == "__main__":
    load_dotenv()
    print("==================================================")
    print("🤖 WALL-E AI Companion Robot - Headless Terminal Mode")
    print("==================================================")
    
    # Run LiveKit Agents CLI
    agents_cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
