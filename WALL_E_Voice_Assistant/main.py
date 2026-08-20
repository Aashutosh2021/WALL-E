"""WALL-E launcher."""
import asyncio
from dotenv import load_dotenv

load_dotenv(override=True)

try:
    import uvloop
    uvloop.install()
except ImportError:
    pass  # falls back to stdlib asyncio loop if uvloop isn't installed

from walle_direct_gemini import run


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("WALL-E stopped.")
