import os
import time
import aiohttp
from datetime import datetime
from urllib.parse import quote
from livekit.agents import function_tool


async def download_file(url: str, output_path: str, timeout: int = 60) -> bool:
    """Fast async downloader."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=timeout) as resp:
                if resp.status != 200:
                    return False
                data = await resp.read()
                with open(output_path, "wb") as f:
                    f.write(data)
                return True
    except:
        return False


def open_image(path: str) -> bool:
    try:
        os.startfile(path)
        return True
    except:
        return False


def format_size(size_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} TB"


@function_tool()
async def generate_ai_image(
    prompt: str,
    output_path: str = "",
    quality: str = "balanced",
    width: int = 1024,
    height: int = 1024,
    model: str = "flux"
) -> str:
    """
    ⚡ Ultra-fast AI Image Generator using Pollinations.ai
    - English prompt recommended
    - Auto filename
    - Auto-open image
    """

    t0 = time.time()

    try:
        if not prompt.strip():
            return "❌ Please enter a valid English prompt."

        # Quality presets
        q = {
            "fast": {"steps": 12, "cfg": 6.5},
            "balanced": {"steps": 20, "cfg": 7.2},
            "quality": {"steps": 32, "cfg": 8.0}
        }.get(quality, {"steps": 20, "cfg": 7.2})

        # File output name
        if not output_path:
            clean = "".join(c for c in prompt[:20] if c.isalnum() or c in " _").strip() or "image"
            output_path = f"{clean}_{datetime.now().strftime('%H%M%S')}.png"

        if not output_path.lower().endswith(".png"):
            output_path += ".png"

        # API URL
        encoded = quote(prompt)
        params = f"width={width}&height={height}&model={model}&steps={q['steps']}&cfg={q['cfg']}"
        image_url = f"https://image.pollinations.ai/prompt/{encoded}?{params}"

        # Download image
        if not await download_file(image_url, output_path, timeout=40):
            return "❌ Failed to generate image. Try changing your prompt or reducing quality."

        # Validate image size
        if not os.path.exists(output_path) or os.path.getsize(output_path) < 1500:
            return "❌ Image generation failed — received invalid/empty file."

        # Auto-open
        opened = open_image(output_path)
        dt = time.time() - t0

        return f"""
🎉 **Image Generated Successfully!**

📝 **Prompt:** {prompt}
⚡ **Quality:** {quality}
📏 **Size:** {width}×{height}
⏱️ **Time:** {dt:.1f}s
📦 **File Size:** {format_size(os.path.getsize(output_path))}
📁 **Saved at:** `{output_path}`
{ '🖼️ Opened Automatically!' if opened else '⚠️ Could not auto-open, but file is saved.' }
        """.strip()

    except Exception as e:
        return f"❌ Generation failed: {str(e)}"
