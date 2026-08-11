import os
import subprocess
from pathlib import Path
from livekit.agents import function_tool
import asyncio

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




# 🔥 SMART FOLDER PRESETS
FOLDER_SHORTCUTS = {
    "downloads": Path.home() / "Downloads",
    "documents": Path.home() / "Documents",
    "pictures": Path.home() / "Pictures",
    "photos": Path.home() / "Pictures",
    "images": Path.home() / "Pictures",
    "videos": Path.home() / "Videos",
    "music": Path.home() / "Music",
    "desktop": Path.home() / "Desktop",
}


@function_tool()
async def universal_file_opener(
    file_input: str,
    target_path: str = "",
    file_type: str = "any",
    auto_open: bool = True
) -> str:
    """
    Opens a file from:
    ✔ Smart folders (Downloads/Documents/Pictures/Videos)
    ✔ Specific user path
    ✔ Current directory if nothing given
    """

    try:
        # Englishfy inputs
        file_input = await translate_to_english_free(file_input)
        file_input = file_input.strip().lower()

        # --- DETECT SMART FOLDER ---
        target_path_raw = target_path.strip().lower()
        target_path = translate_to_english_free(target_path_raw)

        if target_path_raw in FOLDER_SHORTCUTS:
            target_path = FOLDER_SHORTCUTS[target_path_raw]
        elif target_path_raw == "" or target_path_raw is None:
            # 📌 USER DIDN’T GIVE ANY PATH → CURRENT FOLDER
            target_path = Path(os.getcwd())
        else:
            # normal path
            target_path = await translate_to_english_free(target_path_raw)
            target_path = Path(target_path).expanduser().resolve()

        # validate folder
        if not target_path.exists() or not target_path.is_dir():
            return f"❌ Invalid folder path: {target_path}"

        EXT_MAP = {
            "pdf": [".pdf"],
            "ppt": [".ppt", ".pptx"],
            "doc": [".doc", ".docx", ".txt"],
            "image": [".jpg", ".jpeg", ".png"],
            "video": [".mp4", ".mkv", ".avi"],
            "audio": [".mp3", ".wav", ".aac"],
            "css": [".css"],
            "js": [".js"],
            "html": [".html", ".htm"],
            "any": []
        }

        allowed_ext = EXT_MAP.get(file_type, [])

        # 🔍 search only inside selected folder
        for item in target_path.iterdir():
            if not item.is_file():
                continue

            if file_input in item.name.lower():

                if allowed_ext and item.suffix.lower() not in allowed_ext:
                    return f"❌ File found but wrong type: {item}"

                abs_path = str(item.resolve())

                if auto_open:
                    try:
                        subprocess.Popen(["explorer", abs_path])
                    except:
                        os.startfile(abs_path)

                return f"✅ File opened successfully!\n📂 {abs_path}"

        return f"❌ No file found named '{file_input}' in:\n📁 {target_path}"

    except Exception as e:
        return f"❌ Error: {e}"
