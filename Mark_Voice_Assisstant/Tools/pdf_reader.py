import os
import pyautogui
import asyncio
import aiohttp
import json
from livekit.agents import function_tool

async def translate_to_english_free(text: str) -> str:
    """
    Translate text to English using free APIs without API keys
    """
    print(f"🔤 Translation Input: '{text}'")
    if not text.strip():
        print("❌ Empty text for translation")
        return text
    
    # Check if text is already in English
    if is_english(text):
        print("✅ Text is already in English")
        return text
    
    # Try multiple free translation services
    print("🔄 Trying Google Translate...")
    translation = await try_google_translate(text)
    if translation:
        print(f"✅ Google Translate Success: '{translation}'")
        return translation
    
    print("🔄 Trying MyMemory Translate...")
    translation = await try_my_memory_translate(text)
    if translation:
        print(f"✅ MyMemory Translate Success: '{translation}'")
        return translation
    
    print("🔄 Trying LibreTranslate...")
    translation = await try_libretranslate(text)
    if translation:
        print(f"✅ LibreTranslate Success: '{translation}'")
        return translation
    
    # Fallback to basic translation if all APIs fail
    print("⚠️ Using fallback translation")
    fallback = fallback_translation(text)
    print(f"🔄 Fallback Translation: '{fallback}'")
    return fallback

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
        print(f"🌐 Google Translate Request for: '{text[:50]}...'")
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
                print(f"📡 Google Translate Response Status: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    print(f"📊 Google Translate Data: {data}")
                    # Extract translated text from response
                    if data and len(data) > 0:
                        translated_parts = [part[0] for part in data[0] if part[0]]
                        result = ''.join(translated_parts)
                        print(f"✅ Google Translate Result: '{result}'")
                        return result
                else:
                    print(f"❌ Google Translate HTTP Error: {response.status}")
    except Exception as e:
        print(f"❌ Google Translate failed: {e}")
    return None

async def try_my_memory_translate(text: str) -> str:
    """
    Try MyMemory Translation API (free)
    """
    try:
        print(f"🌐 MyMemory Translate Request for: '{text[:50]}...'")
        url = "https://api.mymemory.translated.net/get"
        params = {
            'q': text,
            'langpair': 'auto|en'
        }
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(url, params=params) as response:
                print(f"📡 MyMemory Response Status: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    print(f"📊 MyMemory Data: {data}")
                    if data.get('responseStatus') == 200:
                        result = data['responseData']['translatedText']
                        print(f"✅ MyMemory Result: '{result}'")
                        return result
                    else:
                        print(f"❌ MyMemory API Error: {data.get('responseStatus')}")
                else:
                    print(f"❌ MyMemory HTTP Error: {response.status}")
    except Exception as e:
        print(f"❌ MyMemory Translate failed: {e}")
    return None

async def try_libretranslate(text: str) -> str:
    """
    Try LibreTranslate (free open-source)
    """
    try:
        print(f"🌐 LibreTranslate Request for: '{text[:50]}...'")
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
            for i, instance_url in enumerate(instances):
                try:
                    print(f"🔄 Trying LibreTranslate instance {i+1}: {instance_url}")
                    async with session.post(instance_url, 
                                          data=json.dumps(payload), 
                                          headers=headers) as response:
                        print(f"📡 LibreTranslate {i+1} Response Status: {response.status}")
                        if response.status == 200:
                            data = await response.json()
                            print(f"📊 LibreTranslate {i+1} Data: {data}")
                            result = data.get('translatedText')
                            if result:
                                print(f"✅ LibreTranslate Result: '{result}'")
                                return result
                        else:
                            print(f"❌ LibreTranslate {i+1} HTTP Error: {response.status}")
                except Exception as e:
                    print(f"❌ LibreTranslate instance {i+1} failed: {e}")
                    continue  # Try next instance
                    
    except Exception as e:
        print(f"❌ LibreTranslate failed: {e}")
    return None

def fallback_translation(text: str) -> str:
    """
    Basic fallback translation for common words
    """
    print("🔄 Using fallback translation")
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
    
    result = ' '.join(translated_words)
    print(f"🔄 Fallback Translation Result: '{result}'")
    return result



import os
import PyPDF2
import docx
import chardet
import sqlite3
import hashlib
import numpy as np
from tkinter import Tk, filedialog
from livekit.agents import function_tool
from typing import List, Dict, Any
from datetime import datetime
import aiohttp
import asyncio

class AdvancedFileProcessor:
    def __init__(self, groq_api_key: str, db_path: str = "file_chunks.db"):
        print(f"🔄 Initializing AdvancedFileProcessor with DB: {db_path}")
        self.groq_api_key = groq_api_key
        self.db_path = db_path
        self.chunk_size = 1500
        self.overlap = 300
        self._init_database()
        self.groq_api_url = "https://api.groq.com/openai/v1/chat/completions"
        print("✅ AdvancedFileProcessor initialized")
    
    def _init_database(self):
        """Initialize SQLite database for storing chunks and embeddings"""
        print("🔄 Initializing database...")
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS document_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_hash TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                chunk_text TEXT NOT NULL,
                embedding BLOB,
                token_count INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(file_hash, chunk_index)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS file_metadata (
                file_hash TEXT PRIMARY KEY,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER,
                page_count INTEGER,
                total_chunks INTEGER,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        print("✅ Database initialized successfully")
    
    def select_file(self) -> str:
        """File dialog for file selection"""
        print("🔄 Opening file selection dialog...")
        root = Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        
        file_path = filedialog.askopenfilename(
            title="Process karne ke liye file select karein",
            filetypes=[
                ("All supported files", "*.pdf *.txt *.docx *.doc"),
                ("PDF files", "*.pdf"),
                ("Text files", "*.txt"),
                ("Word documents", "*.docx *.doc"),
            ]
        )
        root.destroy()
        print(f"📁 Selected file: {file_path}")
        return file_path
    
    def calculate_file_hash(self, file_path: str) -> str:
        """Calculate MD5 hash for file identification"""
        print(f"🔢 Calculating file hash for: {file_path}")
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        file_hash = hasher.hexdigest()
        print(f"✅ File hash: {file_hash}")
        return file_hash
    
    def is_file_processed(self, file_hash: str) -> bool:
        """Check if file is already processed"""
        print(f"🔍 Checking if file is processed (hash: {file_hash})")
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM file_metadata WHERE file_hash = ?", (file_hash,))
        result = cursor.fetchone()
        conn.close()
        is_processed = result is not None
        print(f"📊 File processed status: {is_processed}")
        return is_processed
    
    def read_file(self, file_path: str) -> Dict[str, Any]:
        """Read file and return content with metadata"""
        print(f"📖 Reading file: {file_path}")
        if not os.path.exists(file_path):
            print("❌ File not found")
            raise Exception("File nahi mili")
        
        file_ext = os.path.splitext(file_path)[1].lower()
        file_size = os.path.getsize(file_path)
        print(f"📄 File extension: {file_ext}, Size: {file_size} bytes")
        
        try:
            if file_ext == '.pdf':
                print("📚 Reading PDF file...")
                content, page_count = self._read_pdf(file_path)
            elif file_ext in ['.docx', '.doc']:
                print("📝 Reading Word document...")
                content, page_count = self._read_docx(file_path)
            elif file_ext == '.txt':
                print("📃 Reading text file...")
                content, page_count = self._read_txt(file_path), 1
            else:
                print(f"❌ Unsupported file format: {file_ext}")
                raise Exception("Unsupported file format")
            
            result = {
                'content': content,
                'page_count': page_count,
                'file_size': file_size,
                'file_name': os.path.basename(file_path)
            }
            print(f"✅ File read successfully. Pages: {page_count}, Content length: {len(content)}")
            return result
            
        except Exception as e:
            print(f"❌ File read error: {str(e)}")
            raise Exception(f"File read error: {str(e)}")
    
    def _read_pdf(self, file_path: str) -> tuple[str, int]:
        """Read PDF file with robust text extraction"""
        print(f"📚 Extracting text from PDF: {file_path}")
        text = ""
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            page_count = len(pdf_reader.pages)
            print(f"📄 PDF has {page_count} pages")
            
            for page_num, page in enumerate(pdf_reader.pages):
                page_text = page.extract_text()
                if page_text.strip():
                    text += f"--- Page {page_num + 1} ---\n{page_text}\n\n"
                else:
                    text += f"--- Page {page_num + 1} ---\n[No extractable text]\n\n"
                print(f"📖 Processed page {page_num + 1}/{page_count}")
        
        print(f"✅ PDF extraction complete. Total text length: {len(text)}")
        return text, page_count
    
    def _read_docx(self, file_path: str) -> tuple[str, int]:
        """Read Word document"""
        print(f"📝 Reading Word document: {file_path}")
        doc = docx.Document(file_path)
        text = ""
        page_count = 0
        
        for para in doc.paragraphs:
            if para.text.strip():
                text += para.text + "\n"
                # Estimate page breaks (rough calculation)
                if len(text) % 1500 == 0:
                    page_count += 1
        
        page_count = max(1, page_count)
        print(f"✅ Word document read. Estimated pages: {page_count}, Text length: {len(text)}")
        return text, page_count
    
    def _read_txt(self, file_path: str) -> str:
        """Read text file with encoding detection"""
        print(f"📃 Reading text file: {file_path}")
        with open(file_path, 'rb') as file:
            raw_data = file.read()
            encoding = chardet.detect(raw_data)['encoding'] or 'utf-8'
            print(f"🔤 Detected encoding: {encoding}")
        
        try:
            with open(file_path, 'r', encoding=encoding) as file:
                content = file.read()
                print(f"✅ Text file read successfully. Length: {len(content)}")
                return content
        except UnicodeDecodeError:
            print("🔄 Trying fallback encodings...")
            # Fallback to common encodings
            for encoding in ['utf-8', 'latin-1', 'cp1252']:
                try:
                    print(f"🔄 Trying encoding: {encoding}")
                    with open(file_path, 'r', encoding=encoding) as file:
                        content = file.read()
                        print(f"✅ Success with encoding: {encoding}")
                        return content
                except UnicodeDecodeError:
                    continue
            print("❌ All encoding attempts failed")
            raise Exception("Text file encoding detect nahi ho payi")
    
    def smart_chunking(self, text: str) -> List[Dict[str, Any]]:
        """Advanced chunking with context preservation"""
        print(f"✂️ Starting smart chunking. Text length: {len(text)}")
        if not text.strip():
            print("❌ Empty text for chunking")
            return []
        
        # Clean and normalize text
        text = ' '.join(text.split())
        print(f"🔄 Text cleaned. New length: {len(text)}")
        
        chunks = []
        start = 0
        chunk_index = 0
        
        while start < len(text):
            # Calculate chunk end
            end = start + self.chunk_size
            
            if end >= len(text):
                # Last chunk
                chunk_text = text[start:]
                print(f"📦 Last chunk {chunk_index}: {len(chunk_text)} chars")
            else:
                # Find natural break point
                break_chars = ['. ', '\n', '? ', '! ', '। ', '| ']
                break_pos = -1
                
                for break_char in break_chars:
                    pos = text.rfind(break_char, start, end)
                    if pos > break_pos:
                        break_pos = pos
                
                if break_pos != -1 and (break_pos - start) > (self.chunk_size // 2):
                    end = break_pos + 2  # Include break characters
                    print(f"📦 Chunk {chunk_index} break at character: {break_pos}")
                else:
                    # Force break at space
                    space_pos = text.rfind(' ', start, end)
                    if space_pos != -1:
                        end = space_pos
                        print(f"📦 Chunk {chunk_index} forced break at space: {space_pos}")
                    else:
                        print(f"📦 Chunk {chunk_index} no break found, using default")
            
            chunk_text = text[start:end].strip()
            
            if chunk_text:
                chunks.append({
                    'index': chunk_index,
                    'text': chunk_text,
                    'start_char': start,
                    'end_char': end,
                    'token_count': len(chunk_text.split())
                })
                print(f"✅ Created chunk {chunk_index}: {len(chunk_text)} chars, {chunks[-1]['token_count']} tokens")
                chunk_index += 1
            else:
                print(f"⚠️ Empty chunk at index {chunk_index}")
            
            # Move start with overlap
            start = end - self.overlap
            if start < 0:
                start = 0
            print(f"🔄 Next chunk start: {start}")
        
        print(f"✅ Chunking complete. Total chunks: {len(chunks)}")
        return chunks
    
    def store_chunks_in_db(self, file_hash: str, file_name: str, file_path: str, chunks: List[Dict], metadata: Dict):
        """Store chunks and metadata in database"""
        print(f"💾 Storing {len(chunks)} chunks in database...")
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # Store file metadata
            cursor.execute('''
                INSERT OR REPLACE INTO file_metadata 
                (file_hash, file_name, file_path, file_size, page_count, total_chunks)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (file_hash, file_name, file_path, metadata['file_size'], 
                  metadata['page_count'], len(chunks)))
            print("✅ File metadata stored")
            
            # Store chunks
            for chunk in chunks:
                cursor.execute('''
                    INSERT OR REPLACE INTO document_chunks 
                    (file_hash, file_name, file_path, chunk_index, chunk_text, token_count)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (file_hash, file_name, file_path, chunk['index'], 
                      chunk['text'], chunk['token_count']))
            
            conn.commit()
            print(f"✅ All {len(chunks)} chunks stored successfully")
            
        except Exception as e:
            print(f"❌ Database storage error: {e}")
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def get_all_chunks(self, file_hash: str) -> List[str]:
        """Get ALL chunks from the document for comprehensive processing"""
        print(f"📚 Getting ALL chunks for file hash: {file_hash}")
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT chunk_text FROM document_chunks 
            WHERE file_hash = ? 
            ORDER BY chunk_index
        ''', (file_hash,))
        
        all_chunks = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        print(f"✅ Retrieved {len(all_chunks)} total chunks from document")
        return all_chunks
    
    def get_smart_chunks(self, file_hash: str, max_chunks: int = 10) -> List[str]:
        """Get smart selection of chunks (first few + last few for context)"""
        print(f"🎯 Getting smart chunks for file hash: {file_hash}")
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get total number of chunks
        cursor.execute('SELECT COUNT(*) FROM document_chunks WHERE file_hash = ?', (file_hash,))
        total_chunks = cursor.fetchone()[0]
        
        # Get first few chunks (introduction/content)
        cursor.execute('''
            SELECT chunk_text FROM document_chunks 
            WHERE file_hash = ? 
            ORDER BY chunk_index LIMIT ?
        ''', (file_hash, max_chunks//2))
        
        first_chunks = [row[0] for row in cursor.fetchall()]
        
        # Get last few chunks (conclusion/summary)
        if total_chunks > max_chunks//2:
            cursor.execute('''
                SELECT chunk_text FROM document_chunks 
                WHERE file_hash = ? 
                ORDER BY chunk_index DESC LIMIT ?
            ''', (file_hash, max_chunks//2))
            
            last_chunks = [row[0] for row in cursor.fetchall()]
        else:
            last_chunks = []
        
        conn.close()
        
        # Combine and remove duplicates
        all_smart_chunks = first_chunks + last_chunks
        unique_chunks = list(dict.fromkeys(all_smart_chunks))
        
        print(f"✅ Smart chunks selected: {len(unique_chunks)} (first {len(first_chunks)} + last {len(last_chunks)})")
        return unique_chunks[:max_chunks]

    async def process_with_groq(self, query: str, context_chunks: List[str]) -> str:
        """Process query with Groq AI using relevant context"""
        print(f"🧠 Starting Groq processing for query: '{query}'")
        print(f"📚 Context chunks: {len(context_chunks)}")
        
        try:
            # Combine context chunks
            context = "\n\n".join(context_chunks)
            print(f"📄 Combined context length: {len(context)}")
            
            # If context is too large, truncate but keep important parts
            if len(context) > 8000:
                print("📄 Context is large, using first 8000 chars")
                context = context[:8000] + "... [document continues]"

            prompt = f"""
            DOCUMENT CONTEXT:
            {context}
            
            USER QUESTION: {query}
            
            Instructions:
            - Read the entire document context carefully
            - Answer the user's question based ONLY on the document content
            - If the answer is not in the document, say so clearly
            - Provide detailed and accurate information
            - Respond in the same language as the user's question
            - Be comprehensive and helpful
            """
            
            print("📡 Sending request to Groq API...")
            headers = {
                "Authorization": f"Bearer {self.groq_api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "llama3-8b-8192",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that provides accurate information from documents. Always answer based on the given context."
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                "temperature": 0.1,
                "max_tokens": 2000,
                "top_p": 0.9
            }
            
            print(f"🌐 Groq API Request: {payload['model']}, Tokens: {payload['max_tokens']}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.groq_api_url, 
                    headers=headers, 
                    json=payload, 
                    timeout=60
                ) as response:
                    
                    print(f"📡 Groq API Response Status: {response.status}")
                    if response.status != 200:
                        error_text = await response.text()
                        print(f"❌ Groq API Error: {error_text}")
                        raise Exception(f"Groq API error {response.status}: {error_text}")
                    
                    data = await response.json()
                    print("✅ Groq API Response received successfully")
                    
                    answer = data["choices"][0]["message"]["content"].strip()
                    print(f"🤖 Groq Answer length: {len(answer)}")
                    return answer
                    
        except Exception as e:
            print(f"❌ Groq processing error: {str(e)}")
            raise Exception(f"Groq processing error: {str(e)}")

@function_tool()
async def process_document_query(user_query: str) -> str:
    """
    Advanced Document Processing System - Automatically processes documents and answers questions.
    
    When user asks about PDFs or documents, this tool automatically opens file selection,
    processes the content, and provides AI-powered answers.
    """
    print(f"🚀 Starting document processing for query: '{user_query}'")
    try:
        # Initialize processor
        groq_api_key = os.getenv("GROQ_API_KEY", "")
        print("🔄 Initializing AdvancedFileProcessor...")
        processor = AdvancedFileProcessor(groq_api_key)

        user_query = await translate_to_english_free(user_query)
        
        # File selection
        print("🔄 Opening file selection...")
        file_path = processor.select_file()
        if not file_path:
            print("❌ No file selected")
            return "❌ Koi file select nahi ki gayi."
        
        file_name = os.path.basename(file_path)
        print(f"📁 Selected file: {file_name}")
        
        # Check if file already processed
        print("🔍 Checking if file is already processed...")
        file_hash = processor.calculate_file_hash(file_path)
        
        if not processor.is_file_processed(file_hash):
            print("🔄 Processing new file...")
            # New file - process and store
            file_data = processor.read_file(file_path)
            
            if not file_data['content'].strip():
                print("❌ File content is empty")
                return f"❌ File '{file_name}' khaali hai ya read nahi ho payi."
            
            # Smart chunking
            print("✂️ Performing smart chunking...")
            chunks = processor.smart_chunking(file_data['content'])
            
            if not chunks:
                print("❌ No chunks created from file")
                return f"❌ File '{file_name}' se koi processable content nahi mila."
            
            # Store in database
            print("💾 Storing chunks in database...")
            processor.store_chunks_in_db(file_hash, file_name, file_path, chunks, file_data)
            
            processing_msg = f"✅ **Nayi file process hui:** {file_name}\n"
            processing_msg += f"📊 **Pages:** {file_data['page_count']} | **Chunks:** {len(chunks)}\n\n"
            print("✅ New file processed and stored")
        else:
            processing_msg = f"✅ **File already processed:** {file_name}\n\n"
            print("✅ Using existing file from database")
        
        # Get ALL chunks for comprehensive processing
        print("📚 Getting ALL document chunks...")
        all_chunks = processor.get_all_chunks(file_hash)
        
        if not all_chunks:
            print("❌ No chunks found in database")
            return f"{processing_msg}❌ Document mein koi content nahi mila."
        
        print(f"✅ Using {len(all_chunks)} chunks for processing")
        
        # If too many chunks, use smart selection
        if len(all_chunks) > 10:
            print("🎯 Too many chunks, using smart selection...")
            context_chunks = processor.get_smart_chunks(file_hash, max_chunks=8)
        else:
            context_chunks = all_chunks
        
        # Process with Groq AI
        print("🧠 Processing with Groq AI...")
        answer = await processor.process_with_groq(user_query, context_chunks)
        
        result = f"""📄 **File:** {file_name}
❓ **Question:** {user_query}

🤖 **Answer:**
{answer}"""
        
        print("✅ Document processing completed successfully")
        return result
        
    except Exception as e:
        print(f"❌ System error in process_document_query: {str(e)}")
        import traceback
        print(f"🔍 Stack trace: {traceback.format_exc()}")
        return f"❌ System error: {str(e)}"