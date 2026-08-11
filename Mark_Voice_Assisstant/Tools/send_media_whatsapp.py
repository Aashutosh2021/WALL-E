import pyautogui
import asyncio
import aiohttp
import json
from livekit.agents import function_tool

async def translate_to_english_free(text: str) -> str:
    """
    Translate text to English using free APIs without API keys
    """
    if not text.strip():
        return text
    
    # Check if text is already in English
    if is_english(text):
        return text
    
    # Try multiple free translation services
    translation = await try_google_translate(text)
    if translation:
        return translation
    
    translation = await try_my_memory_translate(text)
    if translation:
        return translation
    
    translation = await try_libretranslate(text)
    if translation:
        return translation
    
    # Fallback to basic translation if all APIs fail
    return fallback_translation(text)

def is_english(text: str) -> bool:
    """Check if text is already in English"""
    try:
        return all(ord(char) < 128 or char.isspace() for char in text)
    except:
        return True

async def try_google_translate(text: str) -> str:
    """
    Try Google Translate (free unofficial API)
    """
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            'client': 'gtx',
            'sl': 'auto',  # source language (auto-detect)
            'tl': 'en',    # target language (English)
            'dt': 't',
            'q': text
        }
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    # Extract translated text from response
                    if data and len(data) > 0:
                        translated_parts = [part[0] for part in data[0] if part[0]]
                        return ''.join(translated_parts)
    except Exception as e:
        print(f"Google Translate failed: {e}")
    return None

async def try_my_memory_translate(text: str) -> str:
    """
    Try MyMemory Translation API (free)
    """
    try:
        url = "https://api.mymemory.translated.net/get"
        params = {
            'q': text,
            'langpair': 'auto|en'
        }
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('responseStatus') == 200:
                        return data['responseData']['translatedText']
    except Exception as e:
        print(f"MyMemory Translate failed: {e}")
    return None

async def try_libretranslate(text: str) -> str:
    """
    Try LibreTranslate (free open-source)
    """
    try:
        # Try different LibreTranslate instances
        instances = [
            "https://libretranslate.de/translate",
            "https://translate.argosopentech.com/translate",
            "https://libretranslate.pussthecat.org/translate"
        ]
        
        payload = {
            'q': text,
            'source': 'auto',
            'target': 'en',
            'format': 'text'
        }
        
        headers = {
            'Content-Type': 'application/json'
        }
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            for instance_url in instances:
                try:
                    async with session.post(instance_url, 
                                          data=json.dumps(payload), 
                                          headers=headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            return data.get('translatedText')
                except:
                    continue  # Try next instance
                    
    except Exception as e:
        print(f"LibreTranslate failed: {e}")
    return None

def fallback_translation(text: str) -> str:
    """
    Basic fallback translation for common words
    """
    basic_translations = {
        # Hindi
        "नमस्ते": "hello", "हैलो": "hello", "हाय": "hi", "कैसे": "how", "हो": "are",
        "आप": "you", "तुम": "you", "मैं": "I", "मेरा": "my", "नाम": "name",
        "धन्यवाद": "thank you", "शुक्रिया": "thanks", "कृपया": "please",
        "हाँ": "yes", "ना": "no", "नहीं": "no", "ठीक": "ok", "अच्छा": "good",
        
        # Actions
        "लिखो": "write", "टाइप": "type", "बनाओ": "make", "करो": "do",
        "दिखाओ": "show", "भेजो": "send", "खोलो": "open", "बंद": "close",
        
        # Common words
        "मदद": "help", "समय": "time", "दिन": "day", "रात": "night",
        "क्या": "what", "क्यों": "why", "कब": "when", "कहाँ": "where"
    }
    
    words = text.split()
    translated_words = []
    
    for word in words:
        clean_word = word.strip('.,!?;:').lower()
        if clean_word in basic_translations:
            translated_words.append(basic_translations[clean_word])
        else:
            translated_words.append(word)
    
    return ' '.join(translated_words)



import pyautogui
import time
from livekit.agents import function_tool

@function_tool()
async def send_media_to_whatsapp(contact_name: str) -> str:
    """
    Sends selected media file to a WhatsApp contact with complete automation.
    
    Complete Steps:
    1. Press Ctrl+C to copy selected file
    2. Open WhatsApp Desktop using Windows key
    3. Search for contact using Ctrl+F
    4. Type contact name, press down arrow, then Enter
    5. Go to chat and press Ctrl+V to paste media
    6. Press Enter to send
    
    Args:
        contact_name: The name of the WhatsApp contact to send media to
    
    Returns:
        str: Confirmation message or error.
    """
    try:
        print(f"🚀 Starting process to send media to '{contact_name}'...")
        
        contact_name = await translate_to_english_free(contact_name)
        # Step 1: Press Ctrl+C to copy selected file
        print("📋 Copying selected file (Ctrl+C)...")
        pyautogui.hotkey('ctrl', 'c')
        time.sleep(2)  # File copy hone ka wait
        
        # Step 2: Open WhatsApp using Windows key
        print("🪟 Opening WhatsApp...")
        pyautogui.hotkey('win')
        time.sleep(1.5)
        
        # Type WhatsApp
        pyautogui.write('WhatsApp')
        time.sleep(2)
        
        # Press Enter to open WhatsApp Desktop
        pyautogui.press('enter')
        print("📱 WhatsApp opening...")
        time.sleep(4)  # WhatsApp fully load hone ka wait
        
        # Step 3: Search for contact (Ctrl+F)
        print(f"🔍 Searching for contact: {contact_name}")
        pyautogui.hotkey('ctrl', 'f')
        time.sleep(1.5)
        
        # Step 4: Type contact name
        pyautogui.write(contact_name)
        time.sleep(2)  # Search results load hone ka wait
        
        # Press down arrow to select first result
        pyautogui.press('down')
        time.sleep(0.5)
        
        # Press Enter to open chat
        pyautogui.press('enter')
        print("💬 Chat opened...")
        time.sleep(2)
        
        # Step 5: Paste the copied media (Ctrl+V)
        print("📎 Pasting media...")
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(3)  # Media load hone ka wait (important for images/videos)
        
        # Step 6: Press Enter to send
        print("📤 Sending media...")
        pyautogui.press('enter')
        time.sleep(1)
        
        return f"✅ Media successfully sent to '{contact_name}'!"
        
    except Exception as e:
        return f"❌ Error: {str(e)}"


# Screenshot + Send Combination Tool



