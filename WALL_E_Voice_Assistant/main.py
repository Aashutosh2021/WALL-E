"""
WALL-E AI Companion Robot — headless terminal entrypoint.
"""

import sys
import asyncio
import logging

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

try:
    import uvloop
    uvloop.install()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)

if __name__ == "__main__":
    load_dotenv(override=True)

    print("==================================================")
    print("WALL-E AI Companion Robot - Fast Terminal Launcher")
    print("==================================================")

    from walle_direct_gemini import run_direct_gemini_robot

    try:
        asyncio.run(run_direct_gemini_robot())
    except KeyboardInterrupt:
        print("\nWALL-E stopped.")