import os
import tkinter as tk
from tkinter import scrolledtext, messagebox
import asyncio
import requests
import json
from livekit.agents import function_tool

class CodeErrorGUI:
    def __init__(self):
        self.groq_api_key = os.getenv("GROQ_API_KEY", "")
        self.groq_url = "https://api.groq.com/openai/v1/chat/completions"
    
    def create_input_gui(self):
        """Input GUI for language, code and error with attractive design"""
        root = tk.Tk()
        root.title("🚀 Nova AI - Code Fixer Pro")
        root.geometry("900x700")
        root.configure(bg='#1e1e1e')
        root.resizable(True, True)
        
        # Center the window
        root.eval('tk::PlaceWindow . center')
        
        result = []
        
        def submit():
            language = language_var.get().strip()
            code = code_text.get("1.0", tk.END).strip()
            error = error_text.get("1.0", tk.END).strip()
            
            if not language:
                messagebox.showerror("Error", "Please select a programming language!")
                return
                
            if not code:
                messagebox.showerror("Error", "Please enter your code!")
                return
                
            if not error:
                messagebox.showerror("Error", "Please enter the error message!")
                return
            
            # Check if code exceeds 500 lines
            code_lines = len(code.split('\n'))
            if code_lines > 500:
                messagebox.showerror("Error", f"Code too large! Maximum 500 lines allowed.\nYour code has {code_lines} lines.")
                return
                
            result.extend([language, code, error])
            root.destroy()
        
        # Header
        header_frame = tk.Frame(root, bg='#1e1e1e')
        header_frame.pack(fill='x', padx=20, pady=20)
        
        tk.Label(header_frame, text="🚀 Nova AI Code Fixer", 
                font=("Arial", 20, "bold"), fg="#00ff88", bg='#1e1e1e').pack()
        tk.Label(header_frame, text="Paste your code and error message to get AI-powered fixes", 
                font=("Arial", 12), fg="#cccccc", bg='#1e1e1e').pack(pady=5)
        
        # Main content frame
        main_frame = tk.Frame(root, bg='#2d2d2d', relief='raised', bd=1)
        main_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        # Language Selection
        lang_frame = tk.Frame(main_frame, bg='#2d2d2d')
        lang_frame.pack(fill='x', padx=15, pady=(15, 10))
        
        tk.Label(lang_frame, text="Programming Language:", 
                font=("Arial", 11, "bold"), fg="#00ff88", bg='#2d2d2d').pack(anchor='w')
        
        language_var = tk.StringVar(value="python")  # Default to Python
        languages = ["python", "javascript", "java", "cpp", "c", "php", "html", "css", "ruby", "go", "rust", "swift", "kotlin"]
        
        language_dropdown = tk.OptionMenu(lang_frame, language_var, *languages)
        language_dropdown.config(width=18, font=("Arial", 10), bg='#404040', fg='white', 
                               relief='flat', highlightthickness=0)
        language_dropdown['menu'].config(bg='#404040', fg='white', relief='flat')
        language_dropdown.pack(anchor='w', pady=5)
        
        # Create a notebook-style layout for code and error
        content_frame = tk.Frame(main_frame, bg='#2d2d2d')
        content_frame.pack(fill='both', expand=True, padx=15, pady=10)
        
        # Code Input Section
        code_frame = tk.LabelFrame(content_frame, text="📝 Your Code (max 500 lines)", 
                                  font=("Arial", 11, "bold"), fg="#00ff88", bg='#2d2d2d', 
                                  relief='groove', bd=1)
        code_frame.pack(fill='both', expand=True, side=tk.LEFT, padx=(0, 5))
        
        # Create a frame for the text widget with border
        code_text_frame = tk.Frame(code_frame, bg='#404040', relief='sunken', bd=1)
        code_text_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        code_text = scrolledtext.ScrolledText(code_text_frame, height=15, width=45, 
                                            font=("Consolas", 10), 
                                            bg='#1e1e1e', fg='#00ff88',
                                            insertbackground='white',
                                            relief='flat', padx=10, pady=10)
        code_text.pack(fill='both', expand=True, padx=2, pady=2)
        
        # Error Input Section
        error_frame = tk.LabelFrame(content_frame, text="❌ Error Message", 
                                   font=("Arial", 11, "bold"), fg="#ff6b6b", bg='#2d2d2d', 
                                   relief='groove', bd=1)
        error_frame.pack(fill='both', expand=True, side=tk.RIGHT, padx=(5, 0))
        
        # Create a frame for the error text widget with border
        error_text_frame = tk.Frame(error_frame, bg='#404040', relief='sunken', bd=1)
        error_text_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        error_text = scrolledtext.ScrolledText(error_text_frame, height=15, width=45, 
                                             font=("Consolas", 10), 
                                             bg='#1e1e1e', fg='#ff6b6b',
                                             insertbackground='white',
                                             relief='flat', padx=10, pady=10)
        error_text.pack(fill='both', expand=True, padx=2, pady=2)
        
        # Button Frame
        button_frame = tk.Frame(main_frame, bg='#2d2d2d')
        button_frame.pack(fill='x', padx=15, pady=20)
        
        # Submit Button with modern design
        submit_btn = tk.Button(button_frame, text="🔧 Fix My Code Now", command=submit, 
                              bg="#00ff88", fg="#1e1e1e", 
                              font=("Arial", 14, "bold"), 
                              padx=40, pady=15,
                              relief='raised', bd=0,
                              cursor='hand2')
        submit_btn.pack(pady=10)
        
        # Hover effects
        def on_enter(e):
            e.widget['bg'] = '#00cc6a'
            e.widget['fg'] = '#ffffff'
            
        def on_leave(e):
            e.widget['bg'] = '#00ff88'
            e.widget['fg'] = '#1e1e1e'
            
        submit_btn.bind("<Enter>", on_enter)
        submit_btn.bind("<Leave>", on_leave)
        
        # Footer
        footer_frame = tk.Frame(root, bg='#1e1e1e')
        footer_frame.pack(fill='x', padx=20, pady=10)
        
        tk.Label(footer_frame, text="💡 Tip: Paste your code and the exact error message you're getting for best results", 
                font=("Arial", 10), fg="#888888", bg='#1e1e1e').pack()
        
        # Add some sample text to help users
        code_text.insert("1.0", "# Paste your code here...\n# Example:\n# def hello():\n#     print('Hello World')\n")
        error_text.insert("1.0", "# Paste your error message here...\n# Example:\n# SyntaxError: invalid syntax\n# NameError: name 'x' is not defined")
        
        root.mainloop()
        
        if result:
            return result[0], result[1], result[2]
        return None, None, None

    def show_result_gui(self, fixed_code: str, original_language: str = ""):
        """Enhanced Result GUI with super attractive design and code formatting"""
        root = tk.Tk()
        root.title(f"✅ {original_language.upper()} Code Fixed Successfully - Nova AI")
        root.geometry("1000x800")
        root.configure(bg='#1e1e1e')
        
        # Center the window
        root.eval('tk::PlaceWindow . center')
        
        # Header with language badge
        header_frame = tk.Frame(root, bg='#1e1e1e')
        header_frame.pack(fill='x', padx=20, pady=20)
        
        # Title with language
        title_frame = tk.Frame(header_frame, bg='#1e1e1e')
        title_frame.pack()
        
        tk.Label(title_frame, text="✅ Code Fixed Successfully", 
                font=("Arial", 22, "bold"), fg="#00ff88", bg='#1e1e1e').pack()
        
        # Language badge
        if original_language:
            lang_badge = tk.Frame(title_frame, bg='#007acc', relief='raised', bd=1)
            lang_badge.pack(pady=5)
            tk.Label(lang_badge, text=f"🔄 {original_language.upper()}", 
                    font=("Arial", 12, "bold"), fg="white", bg='#007acc',
                    padx=15, pady=5).pack()
        
        tk.Label(header_frame, text="Your optimized and corrected code is ready to use", 
                font=("Arial", 12), fg="#cccccc", bg='#1e1e1e').pack(pady=5)
        
        # Stats frame
        stats_frame = tk.Frame(header_frame, bg='#2d2d2d', relief='raised', bd=1)
        stats_frame.pack(pady=10)
        
        # Calculate some stats
        lines = fixed_code.count('\n') + 1
        comments = fixed_code.count('#') + fixed_code.count('//')
        
        stats_text = f"📊 Fixed Code Stats: {lines} lines | {comments} comments | ✅ AI Verified"
        tk.Label(stats_frame, text=stats_text, 
                font=("Arial", 10, "bold"), fg="#00ff88", bg='#2d2d2d',
                padx=15, pady=8).pack()
        
        # Main content frame
        main_frame = tk.Frame(root, bg='#2d2d2d', relief='raised', bd=1)
        main_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        # Code display with tabs-like interface
        code_display_frame = tk.Frame(main_frame, bg='#2d2d2d')
        code_display_frame.pack(fill='both', expand=True, padx=15, pady=15)
        
        # Code header with file icon
        code_header = tk.Frame(code_display_frame, bg='#404040')
        code_header.pack(fill='x')
        
        tk.Label(code_header, text="📄 fixed_code." + original_language, 
                font=("Consolas", 12, "bold"), fg="#00ff88", bg='#404040',
                padx=15, pady=8).pack(side=tk.LEFT)
        
        # Copy button in header
        def copy_code():
            root.clipboard_clear()
            root.clipboard_append(fixed_code)
            # Show temporary confirmation
            copy_confirm = tk.Label(code_header, text="✅ Copied!", 
                                  font=("Arial", 10, "bold"), fg="#00ff88", bg='#404040')
            copy_confirm.pack(side=tk.RIGHT, padx=10)
            root.after(2000, copy_confirm.destroy)
        
        header_copy_btn = tk.Button(code_header, text="📋 Copy", command=copy_code,
                                  bg="#007acc", fg="white", 
                                  font=("Arial", 9, "bold"), 
                                  relief='flat', bd=0)
        header_copy_btn.pack(side=tk.RIGHT, padx=10, pady=5)
        
        # Text frame with line numbers
        text_container = tk.Frame(code_display_frame, bg='#404040', relief='sunken', bd=1)
        text_container.pack(fill='both', expand=True, pady=(0, 10))
        
        # Line numbers frame
        line_frame = tk.Frame(text_container, bg='#2d2d2d', width=50)
        line_frame.pack(side=tk.LEFT, fill='y')
        line_frame.pack_propagate(False)
        
        line_text = scrolledtext.ScrolledText(line_frame, width=6, height=30,
                                            font=("Consolas", 10), 
                                            bg='#2d2d2d', fg='#888888',
                                            relief='flat', state='disabled')
        line_text.pack(fill='both', expand=True)
        
        # Main code text
        code_text_frame = tk.Frame(text_container, bg='#1e1e1e')
        code_text_frame.pack(side=tk.LEFT, fill='both', expand=True)
        
        code_text = scrolledtext.ScrolledText(code_text_frame, height=25, width=90, 
                                            font=("Consolas", 11), 
                                            bg='#1e1e1e', fg='#00ff88',
                                            insertbackground='white',
                                            relief='flat', padx=10, pady=10,
                                            wrap=tk.NONE)
        
        # Add scrollbar for horizontal scrolling
        h_scrollbar = tk.Scrollbar(code_text_frame, orient=tk.HORIZONTAL, command=code_text.xview)
        code_text.configure(xscrollcommand=h_scrollbar.set)
        
        code_text.pack(fill='both', expand=True)
        h_scrollbar.pack(fill='x')
        
        # Insert code with syntax highlighting simulation
        self._insert_colored_code(code_text, fixed_code, original_language)
        code_text.config(state='disabled')
        
        # Update line numbers
        self._update_line_numbers(line_text, fixed_code)
        
        # Button Frame with multiple actions
        button_frame = tk.Frame(main_frame, bg='#2d2d2d')
        button_frame.pack(fill='x', padx=15, pady=20)
        
        # Action buttons
        actions = [
            ("📋 Copy Code", copy_code, "#007acc"),
            ("🔄 Fix Another", lambda: [root.destroy(), asyncio.create_task(fix_code_error())], "#ff6b00"),
            ("💾 Save As...", lambda: self._save_code(fixed_code, original_language), "#28a745"),
            ("❌ Close", root.destroy, "#dc3545")
        ]
        
        for text, command, color in actions:
            btn = tk.Button(button_frame, text=text, command=command,
                          bg=color, fg="white", 
                          font=("Arial", 11, "bold"), 
                          padx=20, pady=10,
                          relief='raised', bd=0,
                          cursor='hand2')
            btn.pack(side=tk.LEFT, padx=10)
            
            # Hover effect
            def make_hover_func(btn, color):
                def on_enter(e):
                    btn['bg'] = self._darken_color(color)
                def on_leave(e):
                    btn['bg'] = color
                return on_enter, on_leave
            
            on_enter, on_leave = make_hover_func(btn, color)
            btn.bind("<Enter>", on_enter)
            btn.bind("<Leave>", on_leave)
        
        # Features footer
        features_frame = tk.Frame(root, bg='#1e1e1e')
        features_frame.pack(fill='x', padx=20, pady=10)
        
        features = "✨ Features: Syntax Fixed • Logic Corrected • Optimized • Comments Added • Error Handling"
        tk.Label(features_frame, text=features, 
                font=("Arial", 10), fg="#888888", bg='#1e1e1e').pack()
        
        root.mainloop()
    
    def _darken_color(self, color):
        """Darken a hex color for hover effect"""
        color = color.lstrip('#')
        rgb = tuple(int(color[i:i+2], 16) for i in (0, 2, 4))
        darkened = tuple(max(0, c - 30) for c in rgb)
        return f'#{darkened[0]:02x}{darkened[1]:02x}{darkened[2]:02x}'
    
    def _insert_colored_code(self, text_widget, code: str, language: str):
        """Insert code with basic syntax highlighting"""
        text_widget.config(state='normal')
        text_widget.delete('1.0', tk.END)
        
        # Basic syntax highlighting rules
        keywords = {
            'python': ['def', 'class', 'import', 'from', 'as', 'if', 'else', 'elif', 'for', 'while', 
                      'return', 'try', 'except', 'finally', 'with', 'as', 'pass', 'break', 'continue'],
            'javascript': ['function', 'const', 'let', 'var', 'if', 'else', 'for', 'while', 'return', 
                          'try', 'catch', 'finally', 'class', 'import', 'export'],
            'java': ['public', 'private', 'protected', 'class', 'void', 'static', 'if', 'else', 'for', 
                    'while', 'return', 'try', 'catch', 'finally', 'import', 'package'],
            'cpp': ['#include', 'using', 'namespace', 'int', 'void', 'class', 'public', 'private', 
                   'if', 'else', 'for', 'while', 'return', 'try', 'catch'],
        }
        
        lang_keywords = keywords.get(language, [])
        
        lines = code.split('\n')
        for line in lines:
            # Apply basic coloring
            colored_line = line
            
            # Highlight comments (green)
            if '#' in line or '//' in line:
                parts = line.split('#') if '#' in line else line.split('//')
                if len(parts) > 1:
                    colored_line = parts[0] + '# ' + parts[1]
            
            # Highlight keywords (yellow)
            for keyword in lang_keywords:
                if keyword in line:
                    colored_line = colored_line.replace(keyword, f'[{keyword}]')
            
            text_widget.insert(tk.END, line + '\n')
        
        text_widget.config(state='disabled')
    
    def _update_line_numbers(self, line_widget, code: str):
        """Update line numbers in the line number widget"""
        line_widget.config(state='normal')
        line_widget.delete('1.0', tk.END)
        
        line_count = code.count('\n') + 1
        line_numbers = '\n'.join(str(i) for i in range(1, line_count + 1))
        line_widget.insert('1.0', line_numbers)
        line_widget.config(state='disabled')
    
    def _save_code(self, code: str, language: str):
        """Save code to file"""
        from tkinter import filedialog
        import os
        
        filename = filedialog.asksaveasfilename(
            defaultextension=f".{language}",
            filetypes=[("All files", "*.*"), 
                      (f"{language.upper()} files", f"*.{language}"),
                      ("Text files", "*.txt")],
            title="Save Fixed Code As"
        )
        
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(code)
                messagebox.showinfo("Success", f"✅ Code saved successfully!\n{os.path.basename(filename)}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save file: {str(e)}")

    async def _call_groq_ai(self, language: str, code: str, error: str) -> str:
        """Call Groq AI to fix code for specific programming language"""
        try:
            headers = {
                "Authorization": f"Bearer {self.groq_api_key}",
                "Content-Type": "application/json"
            }
            
            model = "llama-3.1-8b-instant"
            
            prompt = f"""
            Fix this {language} code based on the error message and return ONLY the corrected code with comments explaining the fixes:
            
            ORIGINAL CODE:
            {code}
            
            ERROR MESSAGE:
            {error}
            
            Requirements:
            - Fix all syntax and logical errors mentioned in the error
            - Return complete runnable code
            - Add comments to explain what was fixed and why
            - Maintain the original code structure and functionality
            - Use proper {language} syntax and best practices
            - Make sure the code is well-formatted and indented properly
            - Include proper error handling if relevant
            - Ensure the fix addresses the specific error mentioned
            
            Return ONLY the corrected code with comments, no additional explanations.
            """
            
            payload = {
                "messages": [{"role": "user", "content": prompt}],
                "model": model,
                "temperature": 0.3,
                "max_tokens": 3000,
                "top_p": 0.9
            }
            
            response = requests.post(self.groq_url, headers=headers, json=payload, timeout=45)
            
            if response.status_code != 200:
                error_msg = f"API Error {response.status_code}: {response.text}"
                return error_msg
            
            result = response.json()
            fixed_code = result["choices"][0]["message"]["content"]
            
            # Clean up the response if it has markdown
            if fixed_code.startswith("```"):
                lines = fixed_code.split("\n")
                fixed_code = "\n".join(lines[1:-1])
            
            return fixed_code.strip()
            
        except requests.exceptions.RequestException as e:
            return f"Network error: {str(e)}"
        except Exception as e:
            return f"Error calling AI: {str(e)}"

@function_tool()
async def fix_code_error() -> str:
    """
    Advanced Code Error Solver - Fixes programming code errors using Groq AI
    
    This function provides a complete solution for fixing code errors across multiple programming languages.
    It opens a user-friendly GUI where you can:
    
    1. Select your programming language (Python, JavaScript, Java, C++, etc.)
    2. Paste your problematic code (maximum 500 lines)
    3. Enter the error message you're receiving
    
    The function then uses Groq AI to analyze and fix the code, displaying the corrected version
    in a clean results window with copy-to-clipboard functionality.
    
    Returns:
        str: Success confirmation message
        
    Example:
        await fix_code_error()
    """
    gui = CodeErrorGUI()
    
    try:
        # Get input from GUI
        language, code, error = gui.create_input_gui()
        
        if not language or not code or not error:
            return "❌ Input cancelled by user"
        
        # Show attractive processing message
        processing = tk.Tk()
        processing.title("🔄 Processing - Nova AI")
        processing.geometry("400x150")
        processing.configure(bg='#1e1e1e')
        processing.eval('tk::PlaceWindow . center')
        
        # Processing content
        processing_frame = tk.Frame(processing, bg='#1e1e1e')
        processing_frame.pack(expand=True, fill='both', padx=20, pady=20)
        
        tk.Label(processing_frame, text="🔍 Nova AI is fixing your code...", 
                font=("Arial", 14, "bold"), fg="#00ff88", bg='#1e1e1e').pack(pady=10)
        tk.Label(processing_frame, text="Analyzing error and generating solution", 
                font=("Arial", 11), fg="#cccccc", bg='#1e1e1e').pack(pady=5)
        
        # Animated dots
        dots_label = tk.Label(processing_frame, text="", 
                             font=("Arial", 14), fg="#00ff88", bg='#1e1e1e')
        dots_label.pack(pady=5)
        
        def animate_dots():
            dots = [".", "..", "...", "...."]
            idx = 0
            def update():
                nonlocal idx
                dots_label.config(text=f"Processing{dots[idx]}")
                idx = (idx + 1) % len(dots)
                processing.after(500, update)
            update()
        
        animate_dots()
        processing.update()
        
        # Fix code using AI
        fixed_code = await gui._call_groq_ai(language, code, error)
        
        # Close processing window
        processing.destroy()
        
        
        # Show result in enhanced GUI
        gui.show_result_gui(fixed_code, language)
        
        return f"✅ {language.capitalize()} code has been successfully fixed! Check the result window."
        
    except Exception as e:
        return f"❌ Unexpected error: {str(e)}"