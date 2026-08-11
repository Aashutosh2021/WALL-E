from livekit.agents import function_tool
# PyAutoGUI Configuration
import pyautogui
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1



@function_tool()
async def open_app(app_name: str) -> str:
    """
    Launches applications via Start Menu search.
    
    Args:
        app_name: Application name (e.g., "chrome")
        
    Returns:
        str: Launch confirmation or error
        
    Notes:
        - Windows-specific implementation
    """
    import pyautogui
    import asyncio

    try:
        print(f"🚀 ऐप खोलने का प्रयास: {app_name}")
        original_pos = await asyncio.to_thread(pyautogui.position)

        # Step 1: Press Win key to open start menu
        await asyncio.to_thread(pyautogui.press, 'win')
        await asyncio.sleep(1)

        # Step 2: Type app name
        await asyncio.to_thread(pyautogui.typewrite, app_name, interval=0.1)
        await asyncio.sleep(1)

        # Step 3: Press Enter to open the app
        await asyncio.to_thread(pyautogui.press, 'enter')

        return f"✅ '{app_name}' खोल दिया गया है।"

    except Exception as e:
        return f"❌ ऐप खोलने में त्रुटि: {str(e)}"

    finally:
        try:
            await asyncio.to_thread(pyautogui.moveTo, original_pos.x, original_pos.y, duration=0.1)
        except:
            pass
