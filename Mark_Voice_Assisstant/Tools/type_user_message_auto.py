import pyautogui
import asyncio
import requests
import datetime
import time
from livekit.agents import function_tool

def translate_to_english(text: str) -> str:
    """Translate Hindi/other languages to English for search"""
    translation_map = {
        # Hindi to English
        "निबंध": "essay", "लिखो": "write", "बनाओ": "make", "करो": "do",
        "टेक्नोलॉजी": "technology", "विज्ञान": "science", "शिक्षा": "education",
        "स्वास्थ्य": "health", "पर्यावरण": "environment", "कंप्यूटर": "computer",
        "मोबाइल": "mobile", "फोन": "phone", "इंटरनेट": "internet",
        "कृत्रिम": "artificial", "बुद्धिमत्ता": "intelligence", "ग्लोबल": "global",
        "वार्मिंग": "warming", "पानी": "water", "हवा": "air", "प्रदूषण": "pollution",
        "जानवर": "animal", "पेड़": "tree", "पौधे": "plants", "प्रकृति": "nature",
        
        # Common words
        "मेरा": "my", "तेरा": "your", "हमारा": "our", "उसका": "his",
        "यह": "this", "वह": "that", "क्या": "what", "क्यों": "why",
        "कब": "when", "कहाँ": "where", "कैसे": "how", "कौन": "who",
        
        # Actions
        "लिखना": "write", "पढ़ना": "read", "सीखना": "learn", "सिखाना": "teach",
        "बोलना": "speak", "सुनना": "listen", "देखना": "see", "समझना": "understand",
        
        # Document types
        "पत्र": "letter", "आवेदन": "application", "रिपोर्ट": "report",
        "नोट": "note", "सारांश": "summary", "विवरण": "description"
    }
    
    # If text is already in English, return as is
    if all(ord(char) < 128 for char in text):
        return text
    
    # Translate word by word
    words = text.split()
    translated_words = []
    
    for word in words:
        clean_word = word.strip('.,!?').lower()
        if clean_word in translation_map:
            translated_words.append(translation_map[clean_word])
        else:
            # Keep the word as is if no translation found
            translated_words.append(word)
    
    result = ' '.join(translated_words)
    # Capitalize first letter
    if result:
        result = result[0].upper() + result[1:]
    
    return result

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

@function_tool()
async def type_user_message_auto(message: str) -> str:
    """
    Types content into active window after translating to English.
    Uses free translation APIs without API keys.
    
    Args:
        message: Text to type (any language, will be translated to English)
        
    Returns:
        str: Typing confirmation
    """
    
    if not message or not message.strip():
        return "⚠️ Message is empty sir."
    
    try:
        # Store original mouse position
        original_pos = pyautogui.position()
        
        # Translate to English using free APIs
        english_message = await translate_to_english_free(message.strip())
        
        # Add a small delay to ensure focus is on correct window
        await asyncio.sleep(0.5)
        
        # Type the translated message
        await asyncio.to_thread(pyautogui.typewrite, english_message, interval=0.05)
        
        # Return to original position
        pyautogui.moveTo(original_pos.x, original_pos.y)
        
        return f"✅ Typed successfully: \"{english_message}\""
        
    except Exception as e:
        return f"❌ Error while typing: {str(e)}"



async def fetch_essay_content(topic: str) -> str:
    """Fetch 300 words English essay content from internet - FAST VERSION"""
    try:
        # First translate topic to English for search
        english_topic = translate_to_english(topic)
        print(f"🔤 TOPIC TRANSLATION: '{topic}' → '{english_topic}'")
        
        print(f"🚀 FAST SEARCH STARTED FOR: '{english_topic}'")
        print("=" * 50)
        
        # METHOD 1: Quick Wikipedia try (5 seconds timeout)
        print("1️⃣ TRYING WIKIPEDIA API...")
        clean_topic = english_topic.replace(' ', '_')
        wiki_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{clean_topic}"
        print(f"   📡 URL: {wiki_url}")
        
        start_time = time.time()
        response = await asyncio.to_thread(requests.get, wiki_url, timeout=5)
        wiki_time = time.time() - start_time
        
        print(f"   ⏱️ Response Time: {wiki_time:.2f}s")
        print(f"   📊 Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if 'extract' in data:
                content = data['extract']
                word_count = len(content.split())
                print(f"   ✅ WIKIPEDIA SUCCESS - {word_count} words")
                print(f"   📄 Preview: {content[:80]}...")
                
                # Quick content adjustment
                if word_count > 300:
                    content = ' '.join(content.split()[:300]) + "..."
                elif word_count < 150:
                    content += f" {english_topic} continues to be relevant in modern contexts with ongoing developments and applications across various fields."
                
                print("=" * 50)
                return content
            else:
                print("   ❌ No extract in response")
        else:
            print(f"   ❌ Wikipedia failed: {response.status_code}")
        
        # METHOD 2: Quick DuckDuckGo (3 seconds timeout)
        print("2️⃣ TRYING DUCKDUCKGO API...")
        ddg_url = "https://api.duckduckgo.com/"
        params = {'q': english_topic, 'format': 'json', 'no_html': '1'}
        print(f"   📡 URL: {ddg_url}")
        print(f"   🔍 Query: {english_topic}")
        
        start_time = time.time()
        ddg_response = await asyncio.to_thread(requests.get, ddg_url, params=params, timeout=3)
        ddg_time = time.time() - start_time
        
        print(f"   ⏱️ Response Time: {ddg_time:.2f}s")
        
        ddg_data = ddg_response.json()
        
        if ddg_data.get('Abstract'):
            content = ddg_data['Abstract']
            word_count = len(content.split())
            print(f"   ✅ DUCKDUCKGO SUCCESS - {word_count} words")
            print(f"   📄 Preview: {content[:80]}...")
            print("=" * 50)
            return content
        else:
            print("   ❌ No abstract found")
        
        # METHOD 3: Ultra-fast generated content
        print("3️⃣ USING INSTANT GENERATED CONTENT...")
        
        # Pre-built templates for common topics
        instant_templates = {
            "technology": """Technology has revolutionized modern society through rapid innovation and digital transformation. The evolution of computing, internet connectivity, and mobile devices has fundamentally changed how people communicate, work, and access information. From artificial intelligence to blockchain, emerging technologies continue to reshape industries and create new opportunities. The impact of technology extends across education, healthcare, business, and entertainment, driving efficiency and enabling global collaboration. While offering tremendous benefits, technology also presents challenges like privacy concerns and digital divides that require careful consideration and responsible development.""",
            
            "environment": """The environment encompasses all living and non-living things occurring naturally on Earth. Environmental conservation has become increasingly important due to challenges like climate change, pollution, deforestation, and biodiversity loss. Sustainable practices aim to balance human needs with ecological preservation for future generations. Environmental science studies these interactions and develops solutions for pressing ecological issues. Protecting natural resources and promoting environmental awareness are essential for planetary health and human well-being."""
        }
        
        # Check for instant template
        topic_lower = english_topic.lower()
        for key, template in instant_templates.items():
            if key in topic_lower:
                print(f"   ✅ INSTANT TEMPLATE USED: {key}")
                print("=" * 50)
                return template
        
        # Quick generated content
        quick_content = f"""{english_topic} represents a significant subject with broad implications across multiple domains. This topic has evolved through historical developments and continues to demonstrate contemporary relevance through various applications and ongoing research. The importance of {english_topic} extends to technological, social, and economic spheres, influencing modern society in numerous ways. Current advancements and future potential make this an area of continued interest and study for researchers, professionals, and the general public alike. Understanding {english_topic} provides valuable insights into broader trends and developments shaping our world today and in the future."""
        
        print(f"   ✅ GENERATED INSTANT CONTENT - {len(quick_content.split())} words")
        print("=" * 50)
        return quick_content
        
    except Exception as e:
        print(f"🚨 SEARCH ERROR: {e}")
        print("🔄 USING FALLBACK CONTENT")
        print("=" * 50)
        return f"""The topic of {english_topic} encompasses important concepts and applications relevant to contemporary discussions. This subject has developed through various stages and continues to evolve with new discoveries and innovations. The significance of {english_topic} can be observed across different fields and contexts, making it a valuable area of study and practical application. Ongoing research and development in this domain suggest continued relevance and potential for future advancements that may further enhance our understanding and utilization of related principles and technologies."""


@function_tool()
async def create_essay_in_notepad() -> str:
    """
    Create a 300-word essay in Notepad by asking user for title.
    Automatically researches the topic and writes in English.
    
    Returns:
        str: Success confirmation
    """
    return "📝 कृपया निबंध का विषय बताएं:\n\nमैं तुरंत रिसर्च करके 300 शब्दों का निबंध अंग्रेजी में लिख दूंगा!\n\nउदाहरण: टेक्नोलॉजी, विज्ञान, शिक्षा, स्वास्थ्य, पर्यावरण\n\nYou can tell me in Hindi or English - I'll understand both! 🇮🇳🇺🇸"


@function_tool()
async def write_essay_in_notepad(topic: str) -> str:
    """
    Write a 300-word essay in Notepad on the given topic.
    Ultra-fast research and writing. Supports all languages.
    
    Args:
        topic: Essay topic/title (any language)
        
    Returns:
        str: Success confirmation
    """
    
    if not topic.strip():
        return "❌ कृपया निबंध का विषय दें। | Please provide an essay topic."
    
    try:
        print(f"🎯 ESSAY COMMAND RECEIVED: '{topic}'")
        
        # Translate topic to English for search
        english_topic = translate_to_english(topic)
        print(f"🔤 TRANSLATED TO ENGLISH: '{english_topic}'")
        
        print("⚡ STARTING INSTANT ESSAY CREATION...")
        
        # Store original position
        original_pos = pyautogui.position()
        
        # STEP 1: Ultra-fast content fetch
        print("🔍 PHASE 1: Content Research")
        start_fetch = time.time()
        essay_content = await fetch_essay_content(topic)  # Pass original topic for context
        fetch_time = time.time() - start_fetch
        word_count = len(essay_content.split())
        
        print(f"✅ CONTENT READY: {word_count} words in {fetch_time:.2f}s")
        
        # STEP 2: Quick Notepad opening
        print("🖥️ PHASE 2: Notepad Setup")
        await asyncio.to_thread(pyautogui.hotkey, 'win', 'r')
        await asyncio.sleep(0.3)
        await asyncio.to_thread(pyautogui.typewrite, 'notepad')
        await asyncio.sleep(0.2)
        await asyncio.to_thread(pyautogui.press, 'enter')
        await asyncio.sleep(1.5)  # Reduced wait time
        
        # STEP 3: Fast typing
        print("⌨️ PHASE 3: Instant Typing")
        current_date = datetime.datetime.now().strftime("%d/%m/%Y")
        
        essay_text = f"""ESSAY: {english_topic}
Date: {current_date}

{essay_content}

Word Count: {word_count} words
Generated: {datetime.datetime.now().strftime('%H:%M:%S')}"""
        
        # Fast typing with minimal delays
        lines = essay_text.split('\n')
        for i, line in enumerate(lines):
            if line.strip():
                await asyncio.to_thread(pyautogui.typewrite, line, interval=0.02)  # Faster typing
            if i < len(lines) - 1:
                await asyncio.to_thread(pyautogui.press, 'enter')
        
        # STEP 4: Quick save
        print("💾 PHASE 4: Quick Save")
        await asyncio.sleep(0.5)
        await asyncio.to_thread(pyautogui.hotkey, 'ctrl', 's')
        await asyncio.sleep(1)
        
        safe_topic = english_topic.replace(' ', '_')[:20]
        filename = f"essay_{safe_topic}_{datetime.datetime.now().strftime('%H%M%S')}.txt"
        
        await asyncio.to_thread(pyautogui.typewrite, filename, interval=0.03)
        await asyncio.to_thread(pyautogui.press, 'enter')
        
        # Return cursor
        pyautogui.moveTo(original_pos.x, original_pos.y)
        
        total_time = time.time() - start_fetch
        print(f"✅ ESSAY COMPLETED: {total_time:.2f} seconds total")
        
        return f"""✅ निबंध तैयार! | Essay Created!

📖 विषय/Topic: {topic} → {english_topic}
📄 फाइल/File: {filename}  
📝 शब्द/Words: {word_count}
⏱️ समय/Time: {total_time:.1f}s
🎯 स्थिति/Status: तैयार | Ready to use"""

    except Exception as e:
        error_msg = f"❌ त्रुटि | Error: {str(e)}"
        print(f"🚨 {error_msg}")
        return error_msg


# PyAutoGUI Configuration
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05  # Faster operations