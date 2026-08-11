import asyncio
import pygetwindow as gw
import pyautogui
import psutil
import os
from typing import Optional, Literal, List, Dict, Tuple
from enum import Enum
import logging
from livekit.agents import function_tool
from difflib import SequenceMatcher
import re
import time
import ctypes
from ctypes import wintypes

logger = logging.getLogger(__name__)

class WindowAction(Enum):
    CLOSE = "close"
    MINIMIZE = "minimize" 
    MAXIMIZE = "maximize"
    RESTORE = "restore"
    FOCUS = "focus"

class AdvancedWindowManager:
    def __init__(self):
        self._last_action_time = 0
        self._action_delay = 0.3
        
        # Windows API constants
        self.SW_RESTORE = 9
        self.SW_SHOWMAXIMIZED = 3
        self.SW_SHOWMINIMIZED = 2
        self.SW_SHOW = 5
        self.HWND_TOP = 0
        self.HWND_TOPMOST = -1
        self.HWND_NOTOPMOST = -2
        self.SWP_NOSIZE = 0x0001
        self.SWP_NOMOVE = 0x0002
        self.SWP_SHOWWINDOW = 0x0040
    
    async def _get_active_window(self) -> Optional[gw.Window]:
        """Get currently active window"""
        try:
            return await asyncio.to_thread(gw.getActiveWindow)
        except Exception as e:
            logger.error(f"Active window error: {e}")
            return None
    
    def _clean_title(self, title: str) -> str:
        """Clean window title"""
        if not title:
            return ""
        
        patterns_to_remove = [
            r'^- ', r' - Google Chrome$', r' - Microsoft Edge$',
            r' - Firefox$', r' - VLC media player$', r' - Notepad$',
            r' - WhatsApp$', r' - Visual Studio Code$', r' — Discord$',
        ]
        
        cleaned = title.strip()
        for pattern in patterns_to_remove:
            cleaned = re.sub(pattern, '', cleaned)
        
        return cleaned.strip()
    
    def _calculate_similarity(self, search: str, target: str) -> float:
        """Calculate similarity between search term and target"""
        if not search or not target:
            return 0.0
        
        search_clean = search.lower().strip()
        target_clean = target.lower().strip()
        
        if search_clean == target_clean:
            return 1.0
        
        if search_clean in target_clean:
            return 0.95
        
        search_cleaned = self._clean_title(search_clean)
        target_cleaned = self._clean_title(target_clean)
        
        if search_cleaned and target_cleaned:
            if search_cleaned == target_cleaned:
                return 0.98
            if search_cleaned in target_cleaned:
                return 0.9
        
        search_words = set(re.findall(r'\w+', search_clean))
        target_words = set(re.findall(r'\w+', target_clean))
        
        if search_words and target_words:
            common_words = search_words.intersection(target_words)
            if common_words:
                word_score = len(common_words) / max(len(search_words), len(target_words))
                return max(word_score, 0.6)
        
        return SequenceMatcher(None, search_clean, target_clean).ratio()
    
    async def _get_all_windows_detailed(self) -> List[Tuple[gw.Window, str, str]]:
        """Get all windows with titles and process info"""
        try:
            windows = await asyncio.to_thread(gw.getAllWindows)
            detailed_windows = []
            
            for win in windows:
                try:
                    title = win.title.strip() if win.title else ""
                    if not title:
                        continue
                    
                    process_name = ""
                    try:
                        if hasattr(win, '_hWnd') and win._hWnd:
                            pid = wintypes.DWORD()
                            ctypes.windll.user32.GetWindowThreadProcessId(win._hWnd, ctypes.byref(pid))
                            process = psutil.Process(pid.value)
                            process_name = process.name().lower().replace('.exe', '')
                    except:
                        pass
                    
                    detailed_windows.append((win, title, process_name))
                    
                except Exception:
                    continue
            
            return detailed_windows
            
        except Exception as e:
            logger.error(f"Get all windows error: {e}")
            return []
    
    async def _find_window_by_title(self, search_title: str) -> Optional[gw.Window]:
        """Find the best matching window for the given title"""
        try:
            detailed_windows = await self._get_all_windows_detailed()
            if not detailed_windows:
                return None
            
            search_lower = search_title.lower().strip()
            best_match = None
            best_score = 0.0
            
            active_window = await self._get_active_window()
            active_title = active_window.title if active_window else ""
            
            for win, title, process_name in detailed_windows:
                title_lower = title.lower()
                is_active = (title == active_title)
                
                title_similarity = self._calculate_similarity(search_lower, title_lower)
                process_similarity = self._calculate_similarity(search_lower, process_name) if process_name else 0.0
                
                combined_score = (title_similarity * 0.8 + process_similarity * 0.2)
                
                if is_active:
                    combined_score += 0.15
                
                if search_lower == title_lower or search_lower == process_name:
                    combined_score = 1.0
                elif search_lower in title_lower:
                    combined_score = max(combined_score, 0.9)
                elif process_name and search_lower in process_name:
                    combined_score = max(combined_score, 0.85)
                
                if combined_score > best_score and combined_score > 0.5:
                    best_score = combined_score
                    best_match = win
            
            return best_match
            
        except Exception as e:
            logger.error(f"Find window error: {e}")
            return None
    
    async def _ensure_action_delay(self):
        """Prevent rapid successive actions"""
        current_time = time.time()
        time_since_last = current_time - self._last_action_time
        if time_since_last < self._action_delay:
            await asyncio.sleep(self._action_delay - time_since_last)
        self._last_action_time = time.time()
    
    def _get_window_handle(self, window: gw.Window):
        """Get window handle from pygetwindow object"""
        try:
            return window._hWnd
        except:
            return None
    
    async def _focus_with_direct_api(self, window: gw.Window) -> bool:
        """Use direct Windows API for reliable focus"""
        try:
            hwnd = self._get_window_handle(window)
            if not hwnd:
                return False
            
            # Method 1: Simple SetForegroundWindow
            try:
                result = ctypes.windll.user32.SetForegroundWindow(hwnd)
                if result:
                    await asyncio.sleep(0.5)
                    return True
            except Exception as e:
                logger.warning(f"SetForegroundWindow failed: {e}")
            
            # Method 2: ShowWindow with restore
            try:
                ctypes.windll.user32.ShowWindow(hwnd, self.SW_RESTORE)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.warning(f"ShowWindow restore failed: {e}")
            
            # Method 3: SetWindowPos to force to top
            try:
                ctypes.windll.user32.SetWindowPos(
                    hwnd, self.HWND_TOP, 0, 0, 0, 0,
                    self.SWP_NOSIZE | self.SWP_NOMOVE
                )
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.warning(f"SetWindowPos failed: {e}")
            
            # Method 4: Alt+Tab simulation as last resort
            try:
                await asyncio.to_thread(pyautogui.keyDown, 'alt')
                await asyncio.sleep(0.1)
                await asyncio.to_thread(pyautogui.press, 'tab')
                await asyncio.sleep(0.1)
                await asyncio.to_thread(pyautogui.keyUp, 'alt')
                await asyncio.sleep(0.5)
                
                # Multiple tab presses to cycle through windows
                for _ in range(5):
                    active = await self._get_active_window()
                    if active and active.title == window.title:
                        return True
                    await asyncio.to_thread(pyautogui.press, 'tab')
                    await asyncio.sleep(0.2)
            except Exception as e:
                logger.warning(f"Alt+Tab failed: {e}")
            
            # Final verification
            active = await self._get_active_window()
            return active and active.title == window.title
            
        except Exception as e:
            logger.error(f"Direct API focus failed: {e}")
            return False
    
    async def _maximize_with_direct_api(self, window: gw.Window) -> bool:
        """Use direct Windows API for maximize"""
        try:
            hwnd = self._get_window_handle(window)
            if not hwnd:
                return False
            
            # First ensure window is focused
            await self._focus_with_direct_api(window)
            await asyncio.sleep(0.3)
            
            # Method 1: ShowWindow maximize
            try:
                result = ctypes.windll.user32.ShowWindow(hwnd, self.SW_SHOWMAXIMIZED)
                if result:
                    await asyncio.sleep(0.3)
                    return True
            except Exception as e:
                logger.warning(f"ShowWindow maximize failed: {e}")
            
            # Method 2: Windows hotkey
            try:
                await asyncio.to_thread(pyautogui.hotkey, 'win', 'up')
                await asyncio.sleep(0.5)
                return True
            except Exception as e:
                logger.warning(f"Win+Up failed: {e}")
            
            return False
            
        except Exception as e:
            logger.error(f"Direct API maximize failed: {e}")
            return False
    
    async def _minimize_with_direct_api(self, window: gw.Window) -> bool:
        """Use direct Windows API for minimize"""
        try:
            hwnd = self._get_window_handle(window)
            if not hwnd:
                return False
            
            # Method 1: ShowWindow minimize
            try:
                result = ctypes.windll.user32.ShowWindow(hwnd, self.SW_SHOWMINIMIZED)
                if result:
                    await asyncio.sleep(0.3)
                    return True
            except Exception as e:
                logger.warning(f"ShowWindow minimize failed: {e}")
            
            # Method 2: Windows hotkey
            try:
                await self._focus_with_direct_api(window)
                await asyncio.sleep(0.2)
                await asyncio.to_thread(pyautogui.hotkey, 'win', 'down')
                await asyncio.sleep(0.3)
                return True
            except Exception as e:
                logger.warning(f"Win+Down failed: {e}")
            
            return False
            
        except Exception as e:
            logger.error(f"Direct API minimize failed: {e}")
            return False
    
    async def _close_with_direct_api(self, window: gw.Window) -> bool:
        """Use direct Windows API for close"""
        try:
            hwnd = self._get_window_handle(window)
            if not hwnd:
                return False
            
            # Method 1: Send close message
            try:
                WM_CLOSE = 0x0010
                result = ctypes.windll.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                if result:
                    await asyncio.sleep(0.5)
                    return True
            except Exception as e:
                logger.warning(f"PostMessage close failed: {e}")
            
            # Method 2: Alt+F4
            try:
                await self._focus_with_direct_api(window)
                await asyncio.sleep(0.2)
                await asyncio.to_thread(pyautogui.hotkey, 'alt', 'f4')
                await asyncio.sleep(0.5)
                return True
            except Exception as e:
                logger.warning(f"Alt+F4 failed: {e}")
            
            return False
            
        except Exception as e:
            logger.error(f"Direct API close failed: {e}")
            return False
    
    async def _perform_window_action(self, window: gw.Window, action: WindowAction) -> bool:
        """Perform action on window using direct Windows API"""
        await self._ensure_action_delay()
        
        try:
            if action == WindowAction.CLOSE:
                return await self._close_with_direct_api(window)
                    
            elif action == WindowAction.MINIMIZE:
                return await self._minimize_with_direct_api(window)
                
            elif action == WindowAction.MAXIMIZE:
                return await self._maximize_with_direct_api(window)
                
            elif action == WindowAction.RESTORE:
                try:
                    hwnd = self._get_window_handle(window)
                    if hwnd:
                        ctypes.windll.user32.ShowWindow(hwnd, self.SW_RESTORE)
                        await asyncio.sleep(0.3)
                        return True
                    return False
                except Exception as e:
                    logger.error(f"Restore failed: {e}")
                    return False
                
            elif action == WindowAction.FOCUS:
                return await self._focus_with_direct_api(window)
            
            return False
            
        except Exception as e:
            logger.error(f"Window action {action} failed: {e}")
            return False

# Global instance
_window_manager = AdvancedWindowManager()

@function_tool()
async def manage_window(
    action: Literal["close", "minimize", "maximize", "restore", "focus"],
    window_title: Optional[str] = None
) -> str:
    """
    Advanced window management using direct Windows API.
    
    Args:
        action: Window operation to perform
        window_title: Specific window title to target (uses active window if not provided)
        
    Returns:
        str: Success/error message in Hindi/English
    """
    try:
        logger.info(f"Window action: {action}, target: {window_title or 'active window'}")
        
        target_window = None
        
        if window_title:
            for attempt in range(2):
                target_window = await _window_manager._find_window_by_title(window_title)
                if target_window:
                    break
                await asyncio.sleep(0.2)
                
            if not target_window:
                return f"❌ '{window_title}' विंडो नहीं मिली। 'list_windows' कमांड से सभी खुली विंडो देखें।"
        else:
            target_window = await _window_manager._get_active_window()
            if not target_window:
                return "❌ कोई सक्रिय विंडो नहीं मिली।"
        
        window_title_display = target_window.title.strip() if target_window.title else "अज्ञात विंडो"
        
        action_enum = WindowAction(action)
        success = await _window_manager._perform_window_action(target_window, action_enum)
        
        if success:
            action_messages = {
                "close": "बंद कर दी गई",
                "minimize": "छोटी की गई", 
                "maximize": "बड़ी की गई",
                "restore": "सामान्य आकार में लाई गई",
                "focus": "पर फोकस किया गया"
            }
            return f"✅ '{window_title_display}' विंडो {action_messages[action]}।"
        else:
            return f"❌ '{window_title_display}' विंडो {action} करने में विफल।"
            
    except Exception as e:
        logger.error(f"Window management error: {e}")
        return f"❌ विंडो {action} करने में त्रुटि: {str(e)}"

@function_tool()
async def list_windows(search_term: Optional[str] = None, limit: int = 20) -> str:
    """
    List all currently open windows with their titles.
    
    Args:
        search_term: Optional search term to filter windows
        limit: Maximum number of windows to display
        
    Returns:
        str: Formatted list of windows
    """
    try:
        detailed_windows = await _window_manager._get_all_windows_detailed()
        if not detailed_windows:
            return "❌ कोई विंडो खुली नहीं है।"
        
        if search_term:
            search_lower = search_term.lower()
            filtered_windows = []
            for win, title, process_name in detailed_windows:
                title_lower = title.lower()
                if (search_lower in title_lower or 
                    (process_name and search_lower in process_name) or
                    search_lower in _window_manager._clean_title(title_lower)):
                    filtered_windows.append((win, title, process_name))
            detailed_windows = filtered_windows
        
        if not detailed_windows:
            return f"❌ '{search_term}' से मेल खाती कोई विंडो नहीं मिली।"
        
        window_list = []
        current_active = await _window_manager._get_active_window()
        active_title = current_active.title if current_active and current_active.title else ""
        
        for i, (win, title, process_name) in enumerate(detailed_windows[:limit], 1):
            try:
                is_active = (title == active_title)
                status = " ⭐ ACTIVE" if is_active else ""
                process_info = f" ({process_name})" if process_name else ""
                
                window_list.append(f"{i}. {title}{process_info}{status}")
            except:
                continue
        
        total = len(detailed_windows)
        header = f"📋 खुली हुई विंडो ({total} मिलीं)"
        if search_term:
            header = f"📋 '{search_term}' से मेल खाती विंडो ({total} मिलीं)"
        
        if total > limit:
            window_list.append(f"\n... और {total - limit} अधिक विंडो")
        
        return header + ":\n" + "\n".join(window_list)
        
    except Exception as e:
        logger.error(f"List windows error: {e}")
        return f"❌ विंडो लिस्ट करने में त्रुटि: {str(e)}"