import asyncio
import pyautogui
from typing import Literal
from functools import wraps
import logging
from dataclasses import dataclass
from enum import Enum
from livekit.agents import function_tool

class DesktopAction(Enum):
    SHOW = "show"

@dataclass
class MousePosition:
    x: int
    y: int

@dataclass
class ScreenDimensions:
    width: int
    height: int

class DesktopControlError(Exception):
    """Custom exception for desktop control operations"""
    pass

class DesktopController:
    """
    Advanced Desktop Controller - Show Desktop Only
    """
    
    def __init__(self):
        self.logger = self._setup_logger()
        self.animation_duration = 0.1
        self._performance_cache = {}
        
    def _setup_logger(self) -> logging.Logger:
        """Setup advanced logging system"""
        logger = logging.getLogger('DesktopController')
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger

    def _async_executor(self, func, *args, **kwargs):
        """Advanced async wrapper for synchronous operations"""
        @wraps(func)
        async def wrapper():
            try:
                return await asyncio.to_thread(func, *args, **kwargs)
            except Exception as e:
                self.logger.error(f"Async execution failed for {func.__name__}: {e}")
                raise DesktopControlError(f"Operation failed: {str(e)}")
        return wrapper

    async def _get_current_mouse_position(self) -> MousePosition:
        """Get current mouse position with caching"""
        cache_key = "mouse_position"
        if cache_key in self._performance_cache:
            return self._performance_cache[cache_key]
            
        try:
            x, y = await self._async_executor(pyautogui.position)()
            position = MousePosition(x=x, y=y)
            self._performance_cache[cache_key] = position
            return position
        except Exception as e:
            raise DesktopControlError(f"Failed to get mouse position: {str(e)}")

    async def _restore_mouse_position(self, original_pos: MousePosition):
        """Restore mouse position with smooth animation"""
        try:
            await self._async_executor(
                pyautogui.moveTo, 
                original_pos.x, 
                original_pos.y, 
                duration=self.animation_duration
            )()
            self.logger.debug("Mouse position restored successfully")
        except Exception as e:
            self.logger.warning(f"Failed to restore mouse position: {str(e)}")

    async def _execute_with_position_restoration(self, operation):
        """
        Advanced context manager for mouse position restoration
        """
        original_pos = await self._get_current_mouse_position()
        
        try:
            result = await operation()
            return result
        except Exception as e:
            self.logger.error(f"Operation failed: {e}")
            raise
        finally:
            await self._restore_mouse_position(original_pos)

    async def _show_desktop_primary_method(self) -> str:
        """Primary method: Windows key + D"""
        try:
            await self._async_executor(pyautogui.hotkey, 'win', 'd')()
            self.logger.info("Desktop shown using Windows+D method")
            return "🖥️ डेस्कटॉप दिखाया जा रहा है।"
        except Exception as e:
            self.logger.warning(f"Primary method failed: {e}")
            raise

    async def _show_desktop_secondary_method(self) -> str:
        """Secondary method: Right-click context menu"""
        try:
            await self._async_executor(pyautogui.click, button='right')()
            await asyncio.sleep(0.5)
            await self._async_executor(pyautogui.press, 'm')()
            self.logger.info("Desktop shown using context menu method")
            return "🖥️ डेस्कटॉप दिखाया जा रहा है।"
        except Exception as e:
            self.logger.warning(f"Secondary method failed: {e}")
            raise

    async def _show_desktop_tertiary_method(self) -> str:
        """Tertiary method: Alt+Tab and minimize"""
        try:
            # Alt+Tab to ensure we're on a window
            await self._async_executor(pyautogui.hotkey, 'alt', 'tab')()
            await asyncio.sleep(0.2)
            # Alt+Space to open window menu
            await self._async_executor(pyautogui.hotkey, 'alt', 'space')()
            await asyncio.sleep(0.2)
            # Press 'n' for minimize
            await self._async_executor(pyautogui.press, 'n')()
            self.logger.info("Desktop shown using minimize method")
            return "🖥️ डेस्कटॉप दिखाया जा रहा है।"
        except Exception as e:
            self.logger.warning(f"Tertiary method failed: {e}")
            raise

    async def show_desktop(self) -> str:
        """Show desktop using multiple fallback strategies"""
        methods = [
            self._show_desktop_primary_method,
            self._show_desktop_secondary_method, 
            self._show_desktop_tertiary_method
        ]
        
        last_exception = None
        
        for i, method in enumerate(methods, 1):
            try:
                self.logger.info(f"Attempting desktop show method {i}")
                result = await method()
                return result
            except Exception as e:
                last_exception = e
                self.logger.warning(f"Desktop show method {i} failed: {e}")
                continue
        
        # All methods failed
        error_msg = f"सभी डेस्कटॉप दिखाने के तरीके विफल। अंतिम त्रुटि: {str(last_exception)}"
        self.logger.error(error_msg)
        raise DesktopControlError(error_msg)

    @function_tool()
    async def desktop_control(
        self, 
        action: Literal["show"]
    ) -> str:
        """
        Advanced desktop control - Show Desktop Only
        
        Args:
            action: "show" desktop
            
        Returns:
            str: Action confirmation in Hindi
            
        Notes:
            - Automatically restores mouse position after operation
            - Uses multiple fallback methods for reliability
            - Includes performance caching and advanced error handling
        """
        self.logger.info(f"Desktop control requested: action={action}")
        
        async def operation():
            if action == DesktopAction.SHOW.value:
                return await self.show_desktop()
            else:
                raise DesktopControlError(f"अमान्य एक्शन: {action}. केवल 'show' उपलब्ध है।")
        
        try:
            return await self._execute_with_position_restoration(operation)
            
        except DesktopControlError as e:
            return f"❌ {str(e)}"
        except Exception as e:
            error_msg = f"डेस्कटॉप कंट्रोल में अप्रत्याशित त्रुटि: {str(e)}"
            self.logger.error(error_msg)
            return f"❌ {error_msg}"

# Global optimized instance
_desktop_controller = DesktopController()

# Main function with decorator - ONLY SHOW ACTION
@function_tool()
async def desktop_control(action: Literal["show"]) -> str:
    """
    Controls desktop UI elements - Show Desktop Only
    
    Args:
        action: "show" desktop
        
    Returns:
        str: Action confirmation
        
    Notes:
        - Restores mouse position after operation
        - Uses advanced performance optimization
        - Multiple fallback methods for reliability
    """
    return await _desktop_controller.desktop_control(action)