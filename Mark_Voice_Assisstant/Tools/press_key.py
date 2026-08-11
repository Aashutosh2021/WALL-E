
from livekit.agents import function_tool
@function_tool()
async def press_key(key: str) -> str:
    """
    Simulates keyboard key presses.
    
    Args:
        key: Single key ("enter") or combo ("ctrl+alt+del")
        
    Returns:
        str: Press confirmation
        
    Notes:
        - Supports most standard keyboard keys
    """
    import pyautogui
    import asyncio

    try:
        # Normalize input
        key = key.strip().lower()

        # Split combination if needed
        if '+' in key:
            keys = [k.strip() for k in key.split('+')]
            await asyncio.to_thread(pyautogui.hotkey, *keys)
        else:
            await asyncio.to_thread(pyautogui.press, key)

        return f"✅ '{key}' दबा दिया गया है।"

    except Exception as e:
        return f"❌ कुंजी दबाने में त्रुटि: {str(e)}"
    
import pyautogui
import time


@function_tool()
async def use_smart_clipboard(prompt: str, action: str, item_index: int = None) -> str:
    """
    Manages the Windows clipboard history.

    Args:
        prompt: The user's request, e.g., "open smart clipboard" or "paste the 4th item".
        action: The specific command, like "open_history" or "paste_item".
        item_index: The position of the clipboard item to paste (starting from 1).
                    This is optional and used only with "paste_item" action.

    Returns:
        A message confirming the action.
    """
    try:
        if action == "open_history":
            # Open Clipboard History (Win + V)
            pyautogui.hotkey("win", "v")
            return "📋 Clipboard history opened."

        elif action == "paste_item" and item_index is not None:
            if item_index < 1:
                return "⚠️ Error: Item index must be 1 or greater."

            # Open Clipboard History
            pyautogui.hotkey("win", "v")
            time.sleep(0.5)

            # Navigate with down arrow
            for _ in range(item_index - 1):
                pyautogui.press("down")

            # Select item
            pyautogui.press("enter")

            return f"📋 Pasted item at index {item_index} from clipboard history."

        else:
            return "⚠️ Invalid action or missing/invalid item index."
    except Exception as e:
        return f"❌ Smart clipboard operation failed: {str(e)}"