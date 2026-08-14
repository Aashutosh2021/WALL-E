"""WALL-E launcher."""
import asyncio
from dotenv import load_dotenv
load_dotenv(override=True)
from walle_direct_gemini_fast import run

if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("WALL-E stopped.")
