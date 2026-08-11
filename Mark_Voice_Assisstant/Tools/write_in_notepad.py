import asyncio
import logging
from datetime import datetime
from typing import Callable
import pyautogui
import requests
import time
from livekit.agents import function_tool

@function_tool()
async def write_in_notepad(title: str, content: str, document_type: str = "letter") -> str:
    """
    Creates formatted documents in Notepad.

    Args:
        title: Document heading
        content: Main text (typing should always be in English)
        document_type: Format template:
            - "letter": Formal layout
            - "application": Structured
            - "note": Simple text

    Returns:
        str: Saved file path confirmation
    """

    try:
        print(f"📝 Starting Notepad writing process: {document_type} - {title}")
        original_pos = await asyncio.to_thread(pyautogui.position)

        # Step 1: Open Notepad using Win key
        print("🔧 Opening Notepad...")
        await asyncio.to_thread(pyautogui.press, 'win')
        await asyncio.sleep(1)

        # Step 2: Type "notepad" and press Enter
        await asyncio.to_thread(pyautogui.typewrite, 'notepad', interval=0.1)
        await asyncio.sleep(1)
        await asyncio.to_thread(pyautogui.press, 'enter')
        await asyncio.sleep(3)  # Wait for Notepad to open

        # Step 3: Create new file (Ctrl+N) to ensure clean slate
        print("📄 Creating new file...")
        await asyncio.to_thread(pyautogui.hotkey, 'ctrl', 'n')
        await asyncio.sleep(1)

        # Step 4: Clear any existing content (Ctrl+A, Delete)
        await asyncio.to_thread(pyautogui.hotkey, 'ctrl', 'a')
        await asyncio.sleep(0.5)
        await asyncio.to_thread(pyautogui.press, 'delete')
        await asyncio.sleep(0.5)

        # Step 5: Start writing the document with proper formatting
        print("✍️ Writing document content...")
        
        # Add date at the top
        current_date = datetime.now().strftime("%d/%m/%Y")
        await asyncio.to_thread(pyautogui.typewrite, f"Date: {current_date}", interval=0.05)
        await asyncio.to_thread(pyautogui.press, 'enter')
        await asyncio.to_thread(pyautogui.press, 'enter')

        # Add document title
        await asyncio.to_thread(pyautogui.typewrite, f"Subject: {title}", interval=0.05)
        await asyncio.to_thread(pyautogui.press, 'enter')
        await asyncio.to_thread(pyautogui.press, 'enter')

        # Add greeting for letters/applications
        if document_type.lower() in ["letter", "application"]:
            await asyncio.to_thread(pyautogui.typewrite, "Dear Sir/Madam,", interval=0.05)
            await asyncio.to_thread(pyautogui.press, 'enter')
            await asyncio.to_thread(pyautogui.press, 'enter')

        # Write main content with proper paragraph formatting
        paragraphs = content.split('\n\n')
        for i, paragraph in enumerate(paragraphs):
            if paragraph.strip():  # Skip empty paragraphs
                # Clean the paragraph text
                clean_paragraph = paragraph.strip()
                await asyncio.to_thread(pyautogui.typewrite, clean_paragraph, interval=0.03)
                await asyncio.to_thread(pyautogui.press, 'enter')
                await asyncio.to_thread(pyautogui.press, 'enter')

        # Add professional closing for letters/applications
        if document_type.lower() in ["letter", "application"]:
            await asyncio.to_thread(pyautogui.typewrite, "Thank you for your time and consideration.", interval=0.05)
            await asyncio.to_thread(pyautogui.press, 'enter')
            await asyncio.to_thread(pyautogui.press, 'enter')
            await asyncio.to_thread(pyautogui.typewrite, "Yours sincerely,", interval=0.05)
            await asyncio.to_thread(pyautogui.press, 'enter')
            await asyncio.to_thread(pyautogui.press, 'enter')
            await asyncio.to_thread(pyautogui.typewrite, "[Your Name]", interval=0.05)

        # Step 6: Save the document
        print("💾 Saving document...")
        await asyncio.sleep(1)
        await asyncio.to_thread(pyautogui.hotkey, 'ctrl', 's')
        await asyncio.sleep(2)
        
        # Create clean filename
        safe_title = title.replace(' ', '_').replace('/', '_').replace('\\', '_')
        filename = f"{document_type}_{safe_title}_{current_date.replace('/', '_')}.txt"
        
        await asyncio.to_thread(pyautogui.typewrite, filename, interval=0.05)
        await asyncio.to_thread(pyautogui.press, 'enter')
        await asyncio.sleep(1)

        print("✅ Document created successfully!")
        return (
            f"✅ '{title}' {document_type} successfully created in Notepad\n"
            f"📄 File saved as: {filename}\n"
            f"🎯 Document type: {document_type.title()}\n"
            f"📝 Content written with proper formatting\n"
            f"🔄 New file created for clean writing experience"
        )

    except Exception as e:
        error_msg = f"❌ Error writing to Notepad: {str(e)}"
        print(error_msg)
        return error_msg

    finally:
        try:
            # Return mouse to original position
            await asyncio.to_thread(pyautogui.moveTo, original_pos.x, original_pos.y, duration=0.1)
        except:
            pass


# PyAutoGUI Configuration
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1