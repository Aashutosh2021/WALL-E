import pyautogui
import os
from datetime import datetime
from livekit.agents import function_tool

@function_tool()
async def screen_short() -> str:
    """
    Takes a screenshot of the entire screen and saves it in the OneDrive Pictures/nova_screenshots folder.
    
    Returns:
        str: Confirmation message that screenshot was taken and saved.
    """
    try:
        # OneDrive Pictures folder path
        onedrive_path = os.path.join(os.path.expanduser("~"), "OneDrive")
        pictures_folder = os.path.join(onedrive_path, "Pictures", "nova_screenshots")
        
        # Create nova_screenshots folder if it doesn't exist
        if not os.path.exists(pictures_folder):
            os.makedirs(pictures_folder)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"Screenshot_{timestamp}.png"
        filepath = os.path.join(pictures_folder, filename)
        
        # Take screenshot
        screenshot = pyautogui.screenshot()
        screenshot.save(filepath)
        
        return f"📸 Screenshot le liya gaya hai! OneDrive Pictures/nova_screenshots me save ho gaya."
        
    except Exception as e:
        return f"❌ Screenshot lene mein error: {str(e)}"