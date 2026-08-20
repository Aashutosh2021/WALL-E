"""WALL-E launcher."""
import asyncio
from dotenv import load_dotenv

load_dotenv(override=True)

# uvloop was already a declared dependency (requirements.txt) but was never
# actually installed as the event loop policy anywhere in the project — so
# every asyncio.run() was paying full default-loop overhead for nothing.
# uvloop's event loop is a real, measurable latency win for exactly this
# kind of workload (many small awaits: websocket recv, executor calls,
# to_thread SQLite writes) on constrained hardware like a Pi 3B+. This is
# the only place it needs to be set, before the loop is created.
try:
    import uvloop
    uvloop.install()
except ImportError:
    pass  # Falls back to the default asyncio loop — still correct, just slower.

from walle_direct_gemini import run


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("WALL-E stopped.")
