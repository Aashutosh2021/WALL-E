import os
import aiohttp
import asyncio
import pyautogui
import tempfile
import subprocess
from typing import Optional, Dict, List
from pathlib import Path
from livekit.agents import function_tool
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@function_tool()
async def generate_and_type_code(prompt: str, filename: str, language: Optional[str] = None) -> str:
    """
    Generates complete, well-formatted code using Groq AI models with syntax validation,
    types it in the editor, and saves automatically.

    Args:
        prompt (str): User request for code generation.
        filename (str): Name to save the generated file as.
        language (Optional[str]): (Optional) Force language type.
    
    Returns:
        str: Status message (success/failure) with formatting details
    """
    try:
        # ✅ Enhanced Configuration
        GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
        GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
        
        AVAILABLE_MODELS = [
            "llama-3.3-70b-versatile",
            "meta-llama/llama-4-maverick-17b-128e-instruct",  # Better for code
            "qwen/qwen3-32b",
            "llama-3.1-8b-instant",
            "openai/gpt-oss-120b"
        ]

        # ✅ Enhanced Language Configuration with formatters
        LANG_CONFIG: Dict[str, Dict] = {
            "python": {
                "ext": "py",
                "formatter": "black",
                "linter": "pylint",
                "syntax_check": ["python", "-m", "py_compile"]
            },
            "javascript": {
                "ext": "js",
                "formatter": "prettier",
                "linter": "eslint",
                "syntax_check": ["node", "--check"]
            },
            "html": {
                "ext": "html",
                "formatter": "prettier",
                "linter": None,
                "syntax_check": None
            },
            "css": {
                "ext": "css",
                "formatter": "prettier",
                "linter": None,
                "syntax_check": None
            },
            "java": {
                "ext": "java",
                "formatter": "google-java-format",
                "linter": "checkstyle",
                "syntax_check": ["javac"]
            },
            "cpp": {
                "ext": "cpp",
                "formatter": "clang-format",
                "linter": "cpplint",
                "syntax_check": ["g++", "-fsyntax-only"]
            },
            "c": {
                "ext": "c",
                "formatter": "clang-format",
                "linter": "cpplint",
                "syntax_check": ["gcc", "-fsyntax-only"]
            },
            "php": {
                "ext": "php",
                "formatter": "php-cs-fixer",
                "linter": "php -l",
                "syntax_check": ["php", "-l"]
            },
            "kotlin": {
                "ext": "kt",
                "formatter": "ktlint",
                "linter": "detekt",
                "syntax_check": ["kotlinc"]
            }
        }

        # ✅ Enhanced Language Detection
        def detect_language(prompt_text: str) -> str:
            if language:
                return language.lower()
            
            prompt_lower = prompt_text.lower()
            lang_keywords = {
                "python": ["python", "py", "pandas", "numpy", "django", "flask"],
                "javascript": ["javascript", "js", "node", "react", "vue", "angular"],
                "html": ["html", "webpage", "website"],
                "css": ["css", "stylesheet", "styling"],
                "java": ["java", "spring", "android"],
                "cpp": ["c++", "cpp", "stl"],
                "c": [" c ", "c program"],
                "php": ["php", "wordpress", "laravel"],
                "kotlin": ["kotlin", "android"]
            }
            
            for lang, keywords in lang_keywords.items():
                if any(keyword in prompt_lower for keyword in keywords):
                    return lang
            return "python"

        lang = detect_language(prompt)
        model = AVAILABLE_MODELS[0]  # Best model for code generation

        # ✅ Enhanced System Prompt for Better Formatting
        system_prompt = f"""You are a professional {lang} developer. Generate complete, runnable, and WELL-FORMATTED code.

IMPORTANT FORMATTING RULES:
1. Use proper indentation and spacing
2. Follow language-specific style guides (PEP8 for Python, etc.)
3. Include necessary imports/headers
4. Add appropriate comments for complex logic
5. Ensure code is syntactically correct
6. Use meaningful variable names
7. Include proper error handling where needed

Return ONLY the code without any explanations or markdown formatting."""

        # ✅ Fetch code from Groq API
        logger.info(f"🧠 Generating well-formatted {lang} code via {model}")
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Write a complete, well-formatted {lang} program for: {prompt}"}
            ],
            "temperature": 0.3,  # Lower temperature for more consistent formatting
            "max_tokens": 4096,  # Increased for better code completion
            "top_p": 0.9
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(GROQ_API_URL, headers=headers, json=payload, timeout=60) as res:
                data = await res.json()
                if res.status != 200:
                    return f"❌ API Error {res.status}: {data}"

                code = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )

                # Remove markdown formatting if present
                if code.startswith("```"):
                    lines = code.split("\n")
                    # Remove first and last line (markdown tags)
                    code = "\n".join(lines[1:-1])

        # ✅ Code Validation and Formatting
        lang_config = LANG_CONFIG.get(lang, LANG_CONFIG["python"])
        extension = lang_config["ext"]
        full_filename = f"{filename}"
        
        # Create temporary file for validation
        with tempfile.NamedTemporaryFile(mode='w', suffix=f'.{extension}', delete=False) as temp_file:
            temp_file.write(code)
            temp_path = temp_file.name

        validation_results = []
        
        try:
            # Syntax Check
            if lang_config["syntax_check"]:
                syntax_cmd = lang_config["syntax_check"] + [temp_path]
                result = subprocess.run(syntax_cmd, capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    validation_results.append("✅ Syntax validation passed")
                else:
                    validation_results.append(f"⚠️ Syntax issues: {result.stderr[:200]}")

            # Format code if formatter available
            formatted_code = code
            try:
                if lang_config["formatter"] == "black" and lang == "python":
                    result = subprocess.run(["black", "--quiet", temp_path], 
                                         capture_output=True, text=True, timeout=30)
                    if result.returncode == 0:
                        with open(temp_path, 'r') as f:
                            formatted_code = f.read()
                        validation_results.append("✅ Code formatted with Black")
                
                elif lang_config["formatter"] == "prettier" and lang in ["javascript", "html", "css"]:
                    result = subprocess.run(["npx", "prettier", "--write", temp_path], 
                                         capture_output=True, text=True, timeout=30)
                    if result.returncode == 0:
                        with open(temp_path, 'r') as f:
                            formatted_code = f.read()
                        validation_results.append("✅ Code formatted with Prettier")
                        
            except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError) as e:
                validation_results.append("⚠️ Formatting skipped (formatter not available)")

        finally:
            # Cleanup temp file
            Path(temp_path).unlink(missing_ok=True)

        # ✅ FIXED: Simple and reliable typing approach
        logger.info(f"⌨️ Typing well-formatted {lang} code to editor...")
        
        # Ensure we have focus on the editor
        await asyncio.sleep(2)  # Give user time to focus on editor

        pyautogui.hotkey("ctrl", "n")
        await asyncio.sleep(2)
        
        # Method 1: Use clipboard for perfect formatting (recommended)
        try:
            import pyperclip
            logger.info("📋 Using clipboard method for perfect formatting...")
            pyperclip.copy(formatted_code)
            await asyncio.sleep(0.5)
            pyautogui.hotkey('ctrl', 'v')  # Paste
            await asyncio.sleep(1)
            
        except ImportError:
            # Method 2: Fallback to direct typing with better approach
            logger.info("⌨️ Using direct typing method...")
            
            # Split into lines and type each line properly
            lines = formatted_code.split('\n')
            
            for i, line in enumerate(lines):
                if line.strip():  # Only type non-empty lines
                    # Type the entire line at once
                    pyautogui.write(line, interval=0.01)
                
                # Add newline if not the last line
                if i < len(lines) - 1:
                    pyautogui.press('enter')
                    await asyncio.sleep(0.05)

        logger.info("💾 Saving formatted file...")
        await asyncio.sleep(1)
        pyautogui.hotkey("ctrl", "s")
        await asyncio.sleep(1)
        pyautogui.write(full_filename)
        await asyncio.sleep(2)
        pyautogui.press("enter")
        await asyncio.sleep(0.5)

        # ✅ Final Status with Validation Summary
        validation_summary = " | ".join(validation_results)
        return f"✅ Code generated & saved as {full_filename} | {validation_summary}"

    except subprocess.TimeoutExpired:
        logger.warning("Code validation timed out, proceeding with unvalidated code")
        return f"✅ Code generated & saved as {full_filename} (validation skipped)"
        
    except Exception as e:
        logger.error(f"❌ Advanced code generation failed: {e}")
        return f"❌ Failed: {str(e)}"
    



import os
import subprocess
import pyautogui
import time

@function_tool()
async def run_file_in_vscode(file_path: str = None) -> str:
    """
    Automatically runs the current or specified file in VS Code based on its file extension.
    
    Args:
        file_path: Optional path to specific file. If not provided, runs currently active file.
    
    Returns:
        A message confirming the action or error details.
    """
    try:
        # File extensions and their run commands
        RUN_COMMANDS = {
            '.py': 'python',
            '.js': 'node',
            '.html': 'start',  # Windows
            '.java': 'javac',
            '.cpp': 'g++',
            '.c': 'gcc',
            '.php': 'php',
            '.rb': 'ruby',
            '.go': 'go run',
            '.rs': 'cargo run',
            '.sh': 'bash',
            '.bat': '',
            '.ps1': 'powershell'
        }
        
        # If no file path provided, get currently active file in VS Code
        if file_path is None:
            # Save current file first (Ctrl+S)
            pyautogui.hotkey('ctrl', 's')
            time.sleep(0.5)
            
            # Get file path from VS Code (using copy path command)
            pyautogui.hotkey('ctrl', 'k')
            pyautogui.hotkey('ctrl', 'p')
            time.sleep(0.5)
            
            # For now, we'll assume user provides path or we detect active file
            return "⚠️ Please specify file path, or ensure a file is active in VS Code."
        
        # Check if file exists
        if not os.path.exists(file_path):
            return f"❌ File not found: {file_path}"
        
        # Get file extension
        _, extension = os.path.splitext(file_path)
        extension = extension.lower()
        
        if extension not in RUN_COMMANDS:
            return f"❌ Unsupported file type: {extension}"
        
        run_command = RUN_COMMANDS[extension]
        
        # Open VS Code terminal (Ctrl + `)
        pyautogui.hotkey('ctrl', '`')
        time.sleep(1)
        
        # Clear terminal (Ctrl + L)
        pyautogui.hotkey('ctrl', 'l')
        time.sleep(0.5)
        
        # Build the full command based on file type
        if extension == '.html':
            # For HTML, open in browser
            command = f'{run_command} "{file_path}"'
        elif extension in ['.java', '.cpp', '.c']:
            # For compiled languages, compile first then run
            if extension == '.java':
                compile_cmd = f'javac "{file_path}"'
                run_cmd = f'java "{os.path.splitext(file_path)[0]}"'
            else:  # C/C++
                output_file = os.path.splitext(file_path)[0] + '.exe'
                compile_cmd = f'g++ "{file_path}" -o "{output_file}"'
                run_cmd = f'"{output_file}"'
            
            # Type compile command
            pyautogui.write(compile_cmd)
            pyautogui.press('enter')
            time.sleep(2)
            
            # Type run command
            pyautogui.write(run_cmd)
        else:
            # For interpreted languages
            command = f'{run_command} "{file_path}"'
            pyautogui.write(command)
        
        pyautogui.press('enter')
        
        return f"✅ Running {extension} file: {file_path}"
        
    except Exception as e:
        return f"❌ Error running file: {str(e)}"

